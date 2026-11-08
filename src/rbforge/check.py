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

def changed_files(root, base_ref="HEAD"):
    """Luau files changed since `base_ref` (default HEAD means the working tree), plus untracked."""
    try:
        done = subprocess.run(["git", "-C", root, "diff", "--name-only", "--diff-filter=ACMR", base_ref],
                              capture_output=True, text=True, timeout=30)
        others = subprocess.run(["git", "-C", root, "ls-files", "--others", "--exclude-standard"],
                                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    names = [n.strip() for n in (done.stdout + "\n" + others.stdout).splitlines() if n.strip()]
    files = []
    for name in names:
        if name.endswith((".luau", ".lua")):
            path = os.path.join(root, name)
            if os.path.isfile(path):
                files.append(path)
    return sorted(set(files))



def _project_relative(path, root_abs):
    """Name an analyzer-reported file relative to the project root.

    Containment is a real path check (commonpath), not a string prefix, so `/proj2`
    never counts as being inside `/proj`. A different drive cannot be contained.
    Anything outside the root keeps the path the analyzer printed.
    """
    absolute = os.path.abspath(path)
    try:
        inside = os.path.commonpath([absolute, root_abs]) == root_abs
    except ValueError:
        inside = False
    return (os.path.relpath(absolute, root_abs) if inside else path).replace("\\", "/")


def _summarize_diagnostics(blocking, code, defs, sourcemap, root="."):
    """Compact map of where the type errors are, so an agent fixes a root cause instead of 4,000 leaves.

    Returns lines: totals, the worst files, the worst message kinds. Pure formating over the parsed
    diagnostics - no second analyzer, no re-run.
    """
    files = {}
    kinds = {}
    root_abs = os.path.abspath(root)
    for loc, kind, msg in blocking:
        path = re.split(r"\(\d+,|:\d+:", loc)[0]
        # Roblox projects are full of same-named files (init.luau, Config.luau) at different depths,
        # so the grouping key is the whole project-relative path: `src/Server/init.luau` and
        # `tests/Server/init.luau` are two files, and a last-two-segments key merged them into one.
        rel = _project_relative(path, root_abs)
        files[rel] = files.get(rel, 0) + 1
        # The first sentence of a diagnostic is its kind; the rest is the specific type.
        head = msg.split(";")[0].split(":")[0][:60]
        kinds[(kind, head)] = kinds.get((kind, head), 0) + 1
    worst_files = sorted(files.items(), key=lambda kv: -kv[1])[:5]
    worst_kinds = sorted(kinds.items(), key=lambda kv: -kv[1])[:5]
    lines = [
        "%d blocking diagnostic(s) in %d file(s); analyzer exit %s; definitions %s; sourcemap %s"
        % (len(blocking), len(files), code, "present" if defs else "missing",
           "present" if sourcemap else "missing"),
        "  worst files: " + ", ".join("%s %d" % (n, c) for n, c in worst_files),
        "  worst kinds: " + ", ".join("%s %d" % (k[1] or k[0], c) for k, c in worst_kinds),
    ]
    return "\n".join(lines)


def rung_static(root, changed=None):
    """Format, lint and typecheck. Each tool is independent; absence is a skip.

    `changed` limits stylua/selene to the files in that list: a project with legacy formatting
    debt should not make every edit look like a regression, and passing the changed set must never
    be reported as the whole project being clean.
    """
    rung = {"id": "static", "name": "Rung 1 - format/lint/typecheck", "checks": []}
    scoped = [p for p in (changed or []) if p.endswith((".luau", ".lua"))] if changed is not None else None

    if shutil.which("stylua"):
        if scoped is not None and not scoped:
            rung["checks"].append({"id": "stylua", "status": "skip",
                                   "detail": "no changed Luau files in the working tree"})
        else:
            argv = ["stylua", "--check"] + (scoped if scoped is not None else ["."])
            code, out = _run(argv, root)
            rung["checks"].append({
                "id": "stylua", "status": "pass" if code == 0 else ("fail" if code else "skip"),
                "detail": "formatted" if code == 0 else (out[:800] or "unknown")})
    else:
        rung["checks"].append({"id": "stylua", "status": "skip",
                               "detail": STATIC_TOOLS["stylua"]})

    if shutil.which("selene"):
        if scoped is not None:
            targets = scoped
        else:
            targets = [d for d in ("src", "ServerScriptService") if os.path.isdir(os.path.join(root, d))]
        if scoped is not None and not scoped:
            # Nothing to lint is a skip for THIS check only; the typechecker still runs below.
            rung["checks"].append({"id": "selene", "status": "skip",
                                   "detail": "no changed Luau files in the working tree"})
        else:
            cfg = os.path.join(root, "selene.toml")
            argv = ["selene"] + (targets or ["."])
            generated = None
            if os.path.isfile(cfg):
                argv += ["--config", cfg]
            else:
                # With no config selene parses as Lua 5.1 and rejects valid Luau (compound
                # assignment, `continue`, type annotations). Use the Roblox std.
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
    from . import types as types_mod

    defs, defs_source = types_mod.discover(root)
    if defs is None:
        defs = os.environ.get("RBFORGE_LUAU_DEFINITIONS") or _find_definitions(root)
    sourcemap = os.path.join(root, "sourcemap.json")
    if not shutil.which("luau-lsp"):
        rung["checks"].append({"id": "luau-lsp", "status": "skip",
                               "detail": STATIC_TOOLS["luau-lsp"]})
    elif not defs:
        rung["checks"].append({
            "id": "luau-lsp", "status": "skip",
            "detail": "no Roblox type definitions: run `rbforge types fetch` (offline: set "
                      "RBFORGE_LUAU_DEFINITIONS to a globalTypes.d.luau)"})
    else:
        argv = ["luau-lsp", "analyze", "--platform=roblox", "--definitions=@roblox=%s" % defs,
                "--ignore=artifacts/**", "--ignore=backups/**", "--ignore=.git/**"]
        generated_map = None
        if not os.path.isfile(sourcemap):
            # Without a sourcemap every `require` is "unknown", which buries real type errors. Rojo
            # can produce one from the project file; it is a temp file, never written into the repo.
            project_file = next((os.path.join(root, n) for n in
                                 ("default.project.json", "default.project.jsonc", "rojo.json")
                                 if os.path.isfile(os.path.join(root, n))), None)
            if project_file and shutil.which("rojo"):
                try:
                    handle, candidate = tempfile.mkstemp(suffix=".sourcemap.json")
                    os.close(handle)
                    code, out = _run(["rojo", "sourcemap", "--output", candidate, project_file], root, 90)
                    # An empty or failed sourcemap makes every require unknown again; use it only when
                    # rojo actually produced one.
                    if code == 0 and os.path.getsize(candidate) > 2:
                        generated_map = candidate
                    else:
                        os.remove(candidate)
                except OSError:
                    generated_map = None
            sourcemap = generated_map or sourcemap
        if os.path.isfile(sourcemap):
            argv.append("--sourcemap=%s" % sourcemap)
        if os.path.isfile(os.path.join(root, ".luaurc")):
            argv.append("--base-luaurc=%s" % os.path.join(root, ".luaurc"))
        code, out = _run(argv + [root], root)
        # Exit status decides, never a word search: "0 errors" contains "error", and a crashed
        # typechecker (127, "terminated unexpectedly") prints no diagnostics at all. Diagnostics look
        # like `src/a.luau:12:5: TypeError: ...`, so their absence is checked structurally.
        # luau-lsp prints `path(line,col): Kind: message`; older releases used `path:line:col`.
        # It reports type errors and lint findings in the same stream - selene already owns lint, so
        # only TypeError/SyntaxError blocks the gate, and lint-only output is a warning.
        found = re.findall(
            r"^\s*(\S.*?(?:\(\d+,\d+\)|:\d+:\d+)): (\w+): (.*)$", out, re.M)
        blocking = [(loc, kind, msg) for loc, kind, msg in found if kind in ("TypeError", "SyntaxError")]
        lint = [(loc, kind, msg) for loc, kind, msg in found if kind not in ("TypeError", "SyntaxError")]
        if code is None:
            status, detail = "skip", "typechecker could not run: " + out[:600]
        elif code not in (0, 1):
            # luau-lsp documents 0 = clean and 1 = findings. Anything else is the tool itself failing
            # (127 not found, crash, bad flag), and partial output must not downgrade that to a warn.
            status, detail = "fail", "typechecker exited %s (not a diagnostics result): %s" % (
                code, out[-400:])
        elif blocking:
            summary = _summarize_diagnostics(blocking, code, bool(defs),
                                             bool(os.path.isfile(sourcemap)), root)
            status, detail = "fail", "%d type error(s): " % len(blocking) + "; ".join(
                "%s %s: %s" % (loc[-40:], kind, msg[:110]) for loc, kind, msg in blocking[:3]
            ) + "\n" + summary
        elif lint:
            status, detail = "warn", "%d lint finding(s), no type errors: %s" % (
                len(lint), "; ".join("%s %s: %s" % (loc[-30:], kind, msg[:90])
                                     for loc, kind, msg in lint[:3]))
        elif code == 0:
            status, detail = "pass", "no type errors"
        else:
            # Non-zero with no readable diagnostics is a tool failure (crash, bad flag, killed process).
            status, detail = "fail", "luau-lsp exited %s without diagnostics: %s" % (code, out[:600])
        rung["checks"].append({"id": "luau-lsp", "status": status, "detail": detail})
        if generated_map and os.path.isfile(generated_map):
            try:
                os.remove(generated_map)
            except OSError:
                pass
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
        missing, errors = _validate_project(project, root)
        problems = list(errors or [])
        if missing:
            problems.append("missing $path targets: " + ", ".join(missing))
        rung["checks"].append({
            "id": "project-map",
            "status": "fail" if problems else "pass",
            "detail": "; ".join(problems[:6]) if problems
                      else "default.project.json is well formed and every $path exists"})

    if files:
        # Always state coverage: "no findings" over zero files is not a pass.
        rung["checks"].append({"id": "coverage", "status": "pass",
                               "detail": "%d Luau files audited" % len(files)})
    return rung


def _validate_project(project_file, root):
    """Check a Rojo project's shape, not only that its $paths exist.

    A file like {"name": "has no tree"} used to pass: there were no $paths to miss. Rojo itself
    rejects it, so the gate must too. Returns (missing, errors).
    """
    try:
        with open(project_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        return None, ["unreadable (%s)" % exc]
    except ValueError as exc:
        return None, ["malformed JSON (%s)" % exc]
    if not isinstance(data, dict):
        return None, ["root is %s, expected an object" % type(data).__name__]

    # Checked against Rojo 7.7.1: `name` is optional (Rojo falls back to the folder name), while an
    # empty tree is rejected and a tree holding only `$className` builds fine. Only diverge from
    # Rojo where a real build showed the difference.
    name = data.get("name")
    if name is not None and not isinstance(name, str):
        return None, ["'name' must be a string when present"]
    tree = data.get("tree")
    if not isinstance(tree, dict):
        return None, ["missing a 'tree' object - Rojo has nothing to build"]
    if not tree:
        return None, ["'tree' is empty - Rojo rejects a project with no root instances"]

    missing, errors = [], []
    seen = {}

    def walk(node, path):
        if not isinstance(node, dict):
            errors.append("%s: expected an object, found %s" % (".".join(path) or "tree",
                                                                type(node).__name__))
            return
        cls = node.get("$className")
        if cls is not None and not isinstance(cls, str):
            errors.append("%s: $className must be a string" % (".".join(path) or "tree"))
        target = node.get("$path")
        if target is not None:
            if not isinstance(target, str):
                errors.append("%s: $path must be a string" % (".".join(path) or "tree"))
            else:
                full = os.path.join(root, target)
                key = os.path.normcase(os.path.abspath(full))
                if key in seen:
                    errors.append("$path %r is mapped twice (%s and %s)" % (target, seen[key],
                                                                           ".".join(path) or "tree"))
                seen[key] = ".".join(path) or "tree"
                if not os.path.exists(full):
                    missing.append(target)
                elif not os.path.isdir(full) and not target.endswith((".luau", ".lua", ".rbxm",
                                                                      ".rbxmx", ".json", ".txt")):
                    errors.append("%s: $path %r is not a script, model or directory"
                                  % (".".join(path) or "tree", target))
        for key, value in node.items():
            if key.startswith("$"):
                continue
            walk(value, path + [key])

    walk(tree, [])
    return sorted(set(missing)), errors


# ----------------------------------------------------------------- aggregation

def run(root=".", scope=None, changed_only=False, base_ref="HEAD"):
    """Run the ladder over a project. `scope` limits rungs; `changed_only` limits the linters."""
    root = os.path.abspath(root)
    changed = changed_files(root, base_ref) if changed_only else None
    rungs = [rung_static, rung_unit, rung_structure]
    if scope:
        rungs = [r for r in rungs if r.__name__.split("_", 1)[1] in scope]
    results = []
    for fn in rungs:
        results.append(fn(root, changed=changed) if fn is rung_static else fn(root))
    coverage = {
        "mode": "changed-only" if changed_only else "full",
        "base_ref": base_ref if changed_only else None,
        "changed_luau_files": len(changed) if changed is not None else None,
        "note": None,
    }
    if changed_only:
        coverage["note"] = (("lint/format limited to %d changed file(s); this is not a whole-project audit"
                             % len(changed)) if changed is not None else
                            "changed-only requested but git is unavailable; the full project was checked")

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
        "coverage": coverage,
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
