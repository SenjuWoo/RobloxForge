"""Project detection & analysis.

Detects Studio-native vs Rojo projects on the filesystem. Live Studio-only
places are NOT analyzable from disk - the module says so and defers to the
official MCP instead of pretending.
"""
import json
import os
import re

from .errors import ForgeError

_LUAU_EXTS = (".lua", ".luau")


def detect(path):
    """Classify a directory. Returns dict; raises RBF-PROJECT-001 if absent."""
    if not os.path.isdir(path):
        raise ForgeError("RBF-PROJECT-001", "not a directory: %r" % path)
    rojo = None
    for name in ("default.project.json",):
        candidate = os.path.join(path, name)
        if os.path.isfile(candidate):
            rojo = candidate
    if not rojo:
        for name in os.listdir(path):
            if name.endswith(".project.json"):
                rojo = os.path.join(path, name)
                break
    style = "rojo" if rojo else "studio-native"
    return {"path": os.path.abspath(path), "style": style,
            "rojo_project": rojo,
            "note": ("live Studio places are not on disk; analyze via the "
                     "official MCP tools instead" if False else None)}


# Directories that hold copies of the code rather than the code: recovery snapshots and vendored
# packages. Auditing them reports defects nobody can fix and buries the real ones. Build output is
# left to .gitignore (`out/` is the shipped Luau of a roblox-ts project, so no name can decide it).
SNAPSHOT_DIRS = frozenset({"artifacts", "backups", "backup", "recovery",
                           "Packages", "ServerPackages", "DevPackages", "_Index"})
_SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".sourcemap", "sourcemap"})


def is_snapshot(rel):
    """True when a project-relative path sits under a snapshot/vendored directory."""
    parts = rel.replace("\\", "/").split("/")[:-1]
    return any(p in SNAPSHOT_DIRS or p.lower() in ("artifacts", "backups", "backup", "recovery")
               for p in parts)


def git_ignored(root, rels):
    """The subset of `rels` (project-relative, forward slashes) that git ignores.

    Empty when `root` is not inside a work tree or git is absent: an unknown answer keeps the file in
    the audit, because dropping source silently is the worse error.
    """
    import subprocess
    rels = list(rels)
    if not rels:
        return set()
    try:
        # NUL-separated bytes both ways: text mode turns "\n" into "\r\n" on Windows and git then
        # looks up a path ending in "\r", which is never ignored.
        done = subprocess.run(["git", "check-ignore", "-z", "--stdin"], cwd=root,
                              input="\0".join(rels).encode("utf-8"), capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return set()
    if done.returncode not in (0, 1):  # 128: not a repository
        return set()
    return {p for p in done.stdout.decode("utf-8", "replace").split("\0") if p}


def nested_tree_dirs(root, rels):
    """Project-relative directories among the parents of `rels` that hold their own `.git`.

    A git worktree (`.claude/worktrees/<name>`) or a nested repository is a second checkout of the
    code, not this project: its files duplicate every module and its requires do not resolve against
    this project's sourcemap. The project root itself never counts.
    """
    found, seen = set(), set()
    for rel in rels:
        parts = rel.replace("\\", "/").split("/")[:-1]
        for i in range(1, len(parts) + 1):
            prefix = "/".join(parts[:i])
            if prefix in seen:
                continue
            seen.add(prefix)
            if os.path.exists(os.path.join(root, prefix, ".git")):
                found.add(prefix)
    return found


def excluded(root, rels):
    """The subset of project-relative `rels` that is not the project: snapshot or vendored
    directories, git-ignored paths and files inside a nested work tree. One rule for every rung."""
    rels = [r.replace("\\", "/") for r in rels]
    nested = nested_tree_dirs(root, rels)

    def in_nested(rel):
        return any(rel.startswith(d + "/") for d in nested)

    out = {r for r in rels if is_snapshot(r) or in_nested(r)}
    out |= git_ignored(root, [r for r in rels if r not in out])
    return out


def shipped_sources(root, files=None):
    """(kept, skipped) absolute paths: Luau sources that are part of the project being shipped."""
    files = list(files) if files is not None else list(_walk_sources(root))
    rel = {f: os.path.relpath(f, root).replace("\\", "/") for f in files}
    skip = excluded(root, rel.values())
    kept, skipped = [], []
    for f in files:
        (skipped if rel[f] in skip else kept).append(f)
    return kept, skipped


def _walk_sources(path):
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            if name.lower().endswith(_LUAU_EXTS) or name.endswith((".server.lua",
                                                                   ".client.lua")):
                yield os.path.join(dirpath, name)


def analyze(path=None):
    path = path or os.getcwd()
    det = detect(path)

    scripts = {"server": [], "client": [], "module": [], "unknown": []}
    remotes = set()
    datastore_hits = []
    monoliths = []
    hazards = []

    _srv = re.compile(r"\.(server\.lua|server\.luau)$|(^|[\\/])Server[\\/]", re.I)
    _cli = re.compile(r"\.(client\.lua|client\.luau)$|(^|[\\/])Client[\\/]", re.I)

    total = 0
    for full in _walk_sources(det["path"]):
        total += 1
        rel = os.path.relpath(full, det["path"]).replace("\\", "/")
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        low = text.lower()

        if ".server." in full or _srv.search(rel):
            kind = "server"
        elif ".client." in full or _cli.search(rel):
            kind = "client"
        else:
            kind = "module"

        scripts[kind].append({"path": rel, "lines": text.count("\n") + 1})

        for m in re.finditer(r"(RemoteEvent|RemoteFunction)\b", text):
            pass  # names alone are weak signal; instance creation is stronger
        for m in re.finditer(r'Instance\.new\("(RemoteEvent|RemoteFunction)"\)', text):
            remotes.add(m.group(1))
        if "getservice(\"datastoreservice\")" in low or "GetDataStore" in text:
            datastore_hits.append(rel)
        if "httprequest" in low and "post" in low:
            hazards.append({"file": rel, "why": "HttpService POST - verify destination"})
        if text.count("\n") + 1 > 400:
            monoliths.append({"file": rel, "lines": text.count("\n") + 1})

    # client-side authority smells
    for entry in scripts["client"]:
        full = os.path.join(det["path"], entry["path"])
        try:
            low = open(full, encoding="utf-8", errors="replace").read().lower()
        except OSError:
            continue
        for smell in ("leaderstats", "coins =", "coins+=", "damage", "humanoid.health ="):
            if smell in low:
                hazards.append({"file": entry["path"],
                                "why": "possible client-authority write: %r" % smell})
                break

    out = {
        **det,
        "script_count": total,
        "by_kind": {k: len(v) for k, v in scripts.items()},
        "scripts_over_400_lines": sorted(monoliths, key=lambda m: -m["lines"])[:10],
        "remote_types_created": sorted(remotes),
        "datastore_usage": datastore_hits[:20],
        "hazards": hazards[:30],
        "testing_setup": ("TestService present" if os.path.isdir(
            os.path.join(det["path"], "tests")) or _has_tests(det) else "none detected"),
        "limits": ["filesystem analysis only - live-only places need the official MCP",
                   "heuristic, not a proof: hazards are leads to read, not verdicts"],
    }
    return out


def _has_tests(det):
    for dirpath, dirnames, filenames in os.walk(det["path"]):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            if "test" in name.lower() and (name.endswith(".lua") or
                                           name.endswith(".spec.lua") or
                                           name.endswith("_spec.lua")):
                return True
        if dirpath.count(os.sep) > det["path"].count(os.sep) + 3:
            break
    return False
