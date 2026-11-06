"""Pre-Studio verification gate: catch what a Studio boot would catch, cheaper.

Booting a Studio playtest to discover a syntax error, a type mismatch or an
unanchored floor costs 10-30 seconds and a pile of context. This module runs
the checks that do not need the engine first, so only real runtime questions
reach the official Studio MCP.

Three outcomes matter and they are NOT the same:

  pass        every check that could run, ran, and passed
  fail        at least one check proved a defect
  incomplete  no defect found, but something could not be checked

`incomplete` is deliberately distinct from `pass`: a machine without StyLua is
not a machine with clean formatting, and an agent must never read a skip as a
green light. Rungs that need the live engine (playtest, Open Cloud) are out of
scope here and reported as not-run rather than faked.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

# Rung 1 tools: each absent one lowers coverage instead of failing the run.
STATIC_TOOLS = {
    "stylua": "formatter (rokit add JohnnyMorganz/StyLua)",
    "selene": "linter (rokit add Kampfkarren/selene)",
    "luau-lsp": "typechecker (rokit add JohnnyMorganz/luau-lsp)",
}

# Patterns that are almost always a defect in AI-written Luau.
DANGEROUS = [
    (re.compile(r"\bloadstring\s*\("), "loadstring", "fail",
     "loadstring is disabled in production and is a backdoor signature"),
    (re.compile(r"\bgetfenv\s*\(|\bsetfenv\s*\("), "fenv", "fail",
     "getfenv/setfenv break type checking and are sandbox escapes"),
    (re.compile(r"require\s*\(\s*\d+\s*\)"), "require-by-id", "fail",
     "require by numeric asset id cannot be typechecked or reviewed"),
]

UNANCHORED = re.compile(r"Instance\.new\s*\(\s*[\"'](Part|WedgePart|MeshPart|SpawnLocation|TrussPart)[\"']\s*\)")

# How far after an Instance.new to look for Anchored before treating it as loose.
ANCHOR_WINDOW = 600


def _run(argv, cwd, timeout=180):
    """Run one check command. Returns (code, output). Never raises."""
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout, errors="replace")
        return done.returncode, ((done.stdout or "") + (done.stderr or "")).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "could not run %r: %s" % (argv[0], exc)


def _luau_files(root):
    out = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in {".git", "Packages", "ServerPackages",
                                                "node_modules", "DevPackages"}]
        for name in files:
            if name.endswith(".luau") or name.endswith(".lua"):
                out.append(os.path.join(base, name))
    return sorted(out)


def _rel(root, path):
    return os.path.relpath(path, root).replace("\\", "/")


# ------------------------------------------------------------- rung 1: static

def rung_static(root):
    """Format, lint and typecheck. Each tool is independent; absence is a skip."""
    rung = {"id": "static", "name": "Rung 1 - format/lint/typecheck", "checks": []}

    if shutil.which("stylua"):
        code, out = _run(["stylua", "--check", "."], root)
        rung["checks"].append({
            "id": "stylua", "status": "pass" if code == 0 else ("fail" if code else "skip"),
            "detail": "formatted" if code == 0 else (out[:800] or "unknown")})
    else:
        rung["checks"].append({"id": "stylua", "status": "skip",
                               "detail": STATIC_TOOLS["stylua"]})

    if shutil.which("selene"):
        targets = [d for d in ("src", "ServerScriptService") if os.path.isdir(os.path.join(root, d))]
        cfg = os.path.join(root, "selene.toml")
        argv = ["selene"] + (targets or ["."])
        generated = None
        if os.path.isfile(cfg):
            argv += ["--config", cfg]
        else:
            # With no config selene parses as Lua 5.1 and rejects valid Luau (compound assignment,
            # `continue`, type annotations), which reads as a project defect. Use the Roblox std.
            generated = _default_selene_config()
            argv += ["--config", generated]
        try:
            code, out = _run(argv, root)
        finally:
            if generated:
                try:
                    os.remove(generated)
                except OSError:
                    pass
        rung["checks"].append({
            "id": "selene",
            "status": _lint_status(code, out),
            "detail": "clean" if code == 0 else (out[:800] or "unknown")})
    else:
        rung["checks"].append({"id": "selene", "status": "skip",
                               "detail": STATIC_TOOLS["selene"]})

    # luau-lsp without Roblox definitions reports `game`/`Instance` as unknown
    # and produces pure noise, so it runs only when definitions resolve.
    defs = os.environ.get("RBFORGE_LUAU_DEFINITIONS") or _find_definitions(root)
    sourcemap = os.path.join(root, "sourcemap.json")
    if not shutil.which("luau-lsp"):
        rung["checks"].append({"id": "luau-lsp", "status": "skip",
                               "detail": STATIC_TOOLS["luau-lsp"]})
    elif not defs:
        rung["checks"].append({
            "id": "luau-lsp", "status": "skip",
            "detail": "no Roblox type definitions; set RBFORGE_LUAU_DEFINITIONS "
                      "to globalTypes.d.luau (luau-lsp analyze --definitions=@roblox=...)"})
    else:
        argv = ["luau-lsp", "analyze", "--definitions=@roblox=%s" % defs]
        if os.path.isfile(sourcemap):
            argv.append("--sourcemap=%s" % sourcemap)
        if os.path.isfile(os.path.join(root, ".luaurc")):
            argv.append("--base-luaurc=%s" % os.path.join(root, ".luaurc"))
        code, out = _run(argv + [root], root)
        # Exit status decides, never a word search: "0 errors" contains "error", and a crashed
        # typechecker (127, "terminated unexpectedly") prints no diagnostics at all. Diagnostics look
        # like `src/a.luau:12:5: TypeError: ...`, so their absence is checked structurally.
        diagnostics = re.findall(r"^[^\s:][^:]*\.lua?u?:\d+:\d+", out, re.M)
        if code is None:
            status, detail = "skip", "typechecker could not run: " + out[:600]
        elif code == 0 and not diagnostics:
            status, detail = "pass", "no type errors"
        elif diagnostics:
            status, detail = "fail", out[:800]
        else:
            # Non-zero with no diagnostics is a tool failure (crash, bad flag, killed process).
            status, detail = "fail", "luau-lsp exited %s without diagnostics: %s" % (code, out[:600])
        rung["checks"].append({"id": "luau-lsp", "status": status, "detail": detail})
    return rung


def _lint_status(code, out):
    """Map a linter's exit status to a check status.

    selene exits 0 = clean, 1 = findings, anything else = the tool itself failed. A crash (127,
    "process terminated unexpectedly") used to be demoted to a warning, which let the whole gate
    report PASS on a linter that never ran.
    """
    if code is None:
        return "fail"  # found on PATH but could not execute: a broken install, not a skip
    if code == 0:
        return "pass"
    if code == 1:
        return "fail" if ("error[" in out or "error:" in out) else "warn"
    return "fail"


def _default_selene_config():
    """A minimal Roblox selene config for projects that ship none."""
    fd, path = tempfile.mkstemp(prefix="rbforge-selene-", suffix=".toml")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write('std = "roblox"\nexclude = ["Packages/**"]\n')
    return path


def _find_definitions(root):
    """Look where the toolchain conventionally caches globalTypes.d.luau."""
    candidates = [
        os.path.join(root, "globalTypes.d.luau"),
        os.path.join(root, "types", "globalTypes.d.luau"),
        os.path.join(os.path.expanduser("~"), ".cache", "roblox-agent", "globalTypes.d.luau"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "roblox-agent", "globalTypes.d.luau"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


# --------------------------------------------------------------- rung 2: unit

def rung_unit(root):
    """Run pure-Luau specs through Lune when the project has them."""
    rung = {"id": "unit", "name": "Rung 2 - headless unit tests", "checks": []}
    tests_dir = os.path.join(root, "tests")
    specs = []
    if os.path.isdir(tests_dir):
        specs = [p for p in _luau_files(tests_dir) if os.path.basename(p).endswith(".spec.luau")]
    if not specs:
        rung["checks"].append({"id": "lune", "status": "skip",
                               "detail": "no tests/*.spec.luau files"})
    elif not shutil.which("lune"):
        rung["checks"].append({"id": "lune", "status": "skip",
                               "detail": "lune not installed (rokit add lune-org/lune); "
                                         "%d spec(s) unrun" % len(specs)})
    else:
        for spec in specs:
            code, out = _run(["lune", "run", _rel(root, spec)], root)
            rung["checks"].append({
                "id": "lune:" + _rel(root, spec),
                "status": "pass" if code == 0 else "fail",
                "detail": "ok" if code == 0 else out[-800:]})
    return rung


# --------------------------------------------------------- rung 3: structural

def rung_structure(root):
    """Offline source/DataModel sanity that needs no Roblox install."""
    rung = {"id": "structure", "name": "Rung 3 - offline structure audit", "checks": []}
    files = [f for f in _luau_files(root) if "Packages" not in f]
    if not files:
        # Not a reason to stop: a project can be all project.json + models, and
        # the $path audit below is exactly what catches that state.
        rung["checks"].append({"id": "sources", "status": "skip",
                               "detail": "no Luau sources on disk"})

    problems = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            problems.append("%s: unreadable (%s)" % (_rel(root, path), exc))
            continue
        where = _rel(root, path)
        for pattern, name, _, why in DANGEROUS:
            if pattern.search(text):
                problems.append("%s: %s - %s" % (where, name, why))

        if not re.match(r"\s*--!", text):
            rung["checks"].append({"id": "strict:" + where, "status": "warn",
                                   "detail": "no --!strict / --!nonstrict header"})

        # Client scripts must never touch server-only services.
        if where.endswith(".client.luau") or "StarterPlayerScripts" in where:
            if "DataStoreService" in text:
                problems.append("%s: DataStoreService in a client script - "
                                "client has no authority and no access" % where)

        for match in UNANCHORED.finditer(text):
            window = text[match.end():match.end() + ANCHOR_WINDOW]
            if "Anchored = true" not in window and "Anchored=true" not in window:
                line = text.count("\n", 0, match.start()) + 1
                rung["checks"].append({
                    "id": "anchor:%s:%d" % (where, line), "status": "warn",
                    "detail": "Instance.new(\"%s\") nearby has no Anchored = true; "
                              "static geometry will fall" % match.group(1)})

    for item in problems:
        rung["checks"].append({"id": "danger", "status": "fail", "detail": item})

    project = os.path.join(root, "default.project.json")
    if os.path.isfile(project):
        missing, error = _missing_project_paths(project, root)
        if error:
            rung["checks"].append({
                "id": "project-map", "status": "fail",
                "detail": "default.project.json is unusable: " + error})
        else:
            rung["checks"].append({
                "id": "project-map",
                "status": "fail" if missing else "pass",
                "detail": ("missing $path targets: " + ", ".join(missing)) if missing
                          else "default.project.json targets all exist"})

    if files:
        # Always state coverage: "no findings" over zero files is not a pass.
        rung["checks"].append({"id": "coverage", "status": "pass",
                               "detail": "%d Luau files audited" % len(files)})
    return rung


def _missing_project_paths(project_file, root):
    """Every $path in a Rojo project must exist, or `rojo build` dies later.

    Returns (missing, error). A project file that cannot be parsed is reported as an error, never
    as "no paths missing" - an unreadable config is exactly the state that breaks the build.
    """
    try:
        with open(project_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        return None, "unreadable (%s)" % exc
    except ValueError as exc:
        return None, "malformed JSON (%s)" % exc
    if not isinstance(data, dict):
        return None, "root is %s, expected an object" % type(data).__name__
    missing = []

    def walk(node):
        if isinstance(node, dict):
            target = node.get("$path")
            if isinstance(target, str) and not os.path.exists(os.path.join(root, target)):
                missing.append(target)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return sorted(set(missing)), None


# ----------------------------------------------------------------- aggregation

def run(root=".", scope=None):
    """Run the ladder over a project. `scope` limits which rungs execute."""
    root = os.path.abspath(root)
    rungs = [rung_static, rung_unit, rung_structure]
    if scope:
        rungs = [r for r in rungs if r.__name__.split("_", 1)[1] in scope]
    results = [fn(root) for fn in rungs]

    statuses = [c["status"] for r in results for c in r["checks"]]
    if "fail" in statuses:
        status = "fail"
    elif "skip" in statuses:
        status = "incomplete"
    else:
        status = "pass"

    counts = {k: statuses.count(k) for k in ("pass", "fail", "warn", "skip")}
    ran = " + ".join(r["id"] for r in results)
    return {
        "root": root,
        "status": status,
        "counts": counts,
        "rungs_run": [r["id"] for r in results],
        "rungs": results,
        "gate": {
            "pass": "Clean: %s. Studio work may start." % ran,
            "incomplete": "No defect found, but checks were skipped - do NOT "
                          "report this as verified. Install the missing tool or "
                          "state the gap when claiming work.",
            "fail": "A defect was proven (%s). Fix it before opening Studio." % ran,
        }[status],
    }


def render(report):
    """One line per check, loudest first. Skips are visible, never silent."""
    order = {"fail": 0, "warn": 1, "skip": 2, "pass": 3}
    lines = ["rbforge check - %s" % report["root"], ""]
    for rung in report["rungs"]:
        lines.append(rung["name"])
        for check in sorted(rung["checks"], key=lambda c: order[c["status"]]):
            detail = check["detail"].replace("\n", "\n" + " " * 22)
            lines.append("  %-4s %-34s %s" % (check["status"].upper(),
                                              check["id"][:34], detail))
        lines.append("")
    c = report["counts"]
    lines.append("%s - %d pass, %d fail, %d warn, %d skipped"
                 % (report["status"].upper(), c["pass"], c["fail"], c["warn"], c["skip"]))
    lines.append(report["gate"])
    return "\n".join(lines)
