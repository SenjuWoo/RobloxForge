"""Static reviews: architecture + security.

Heuristics over Luau sources. Honest about their ceiling: these are LEADS
for a reader, not verdicts. Live-place review defers to the official MCP's
script_grep rather than pretending the disk has the whole game.
"""
import os
import re

from .errors import ForgeError
from . import project as project_mod

_CLIENT_AUTHORITY = [
    # `=(?!=)`: `if hum.Health == 0` and `coins == 5` are reads, not client writes.
    (re.compile(r"\.Health\s*=(?!=)\s*(?!100\b)", re.I), "sets Humanoid.Health directly"),
    (re.compile(r"TakeDamage\s*\("), "applies damage"),
    (re.compile(r"(coins?|cash|money|gems?)\w*\s*[:+-]?=(?!=)", re.I), "writes a currency-like variable"),
    (re.compile(r"leaderstats", re.I), "touches leaderstats"),
    (re.compile(r"TeleportToPlaceInstance\s*\(", re.I), "requests a teleport"),
    (re.compile(r"PivotTo\s*\(\s*CFrame\.new\(", re.I), "teleports something"),
]

_SERVER_REMOTE_SMELLS = [
    (re.compile(r"OnServerEvent"), None),
]

_UNVALIDATED_HINTS = [
    (re.compile(r"OnServerEvent[\s\S]{0,400}?\.Connect"), "handler body - check validation"),
]


def _collect_sources(path):
    if path:
        det = project_mod.detect(path)
        root = det["path"]
        files = list(project_mod._walk_sources(root))
    else:
        raise ForgeError("RBF-ARG-001",
                         "no source path; for live places use the official MCP's "
                         "script_grep with the patterns this review reports")
    return [(os.path.relpath(f, root).replace("\\", "/"), f) for f in files], root


def _read(rel_full):
    try:
        with open(rel_full[1], encoding="utf-8", errors="replace") as fh:
            return rel_full[0], fh.read()
    except OSError:
        return rel_full[0], ""


def security(path=None, live=False):
    """Find client-authority writes and remote handlers worth reading."""
    if live:
        from .errors import ForgeError as FE
        raise FE("RBF-VERIFY-004",
                 "live security review should use the official MCP's script_grep "
                 "(patterns: OnServerEvent, .Health =, leaderstats)",
                 hint="run script_grep via the Roblox Studio MCP, then read hits")
    sources, _root = _collect_sources(path)

    findings = []
    client_files = []
    for rel, full in sources:
        text = _read((rel, full))[1]
        low = text.lower()
        is_client = ".client." in rel or "/client/" in rel or "\\client\\" in rel
        if is_client:
            client_files.append(rel)
            for rx, why in _CLIENT_AUTHORITY:
                if rx.search(text):
                    findings.append({"severity": "high", "file": rel,
                                     "why": "client code %s" % why})
        if "onserverevent" in low:
            # server-side handler: look for the absence of guards nearby
            has_guard = any(g in low for g in ("typeof(", "if not", "tonumber(",
                                               "math.clamp", "os.clock", "tick()"))
            findings.append({"severity": "info" if has_guard else "medium",
                             "file": rel,
                             "why": ("remote handler present; guard heuristics seen"
                                     if has_guard else
                                     "remote handler without obvious type/rate guard - READ IT")})

    sev_rank = {"high": 0, "medium": 1, "low": 2, "info": 3}
    findings.sort(key=lambda f: (sev_rank[f["severity"]], f["file"]))
    return {
        "scope": path or "(cwd)",
        "files_scanned": len(sources),
        "client_scripts": len(client_files),
        "findings": findings[:50],
        "rule": "RemoteEvent != authorization. Every handler validates types, ranges, ownership, state, rate.",
        "limits": ["static heuristic scan - findings are leads, verify by reading the code"],
    }


def architecture(path=None, live=False):
    """Placement/monolith/ownership review over filesystem sources."""
    sources, root = _collect_sources(path)
    findings = []
    big = []
    for rel, full in sources:
        text = _read((rel, full))[1]
        lines = text.count("\n") + 1
        if lines > 300:
            big.append({"file": rel, "lines": lines,
                        "why": "monolith candidate - split by system"})
        base = os.path.basename(full)
        if base.endswith((".server.lua", ".server.luau")) and (
                "getservice(\"replicatedstorage\")" in text.lower().replace(" ", "")
                and "waitforchild" not in text.lower()):
            findings.append({"severity": "medium", "file": rel,
                             "why": "server script reads ReplicatedStorage without WaitForChild - race on join"})
        if re.search(r"Instance\.new\(\"Script\"\)", text):
            findings.append({"severity": "low", "file": rel,
                             "why": "creates Script instances at runtime - usually a design smell"})
        if re.search(r"while\s+true\s+do(?![\s\S]{0,200}task\.wait|[\s\S]{0,200}wait\()", text):
            findings.append({"severity": "high", "file": rel,
                             "why": "while true do without a visible wait in range - hang risk"})

    big.sort(key=lambda b: -b["lines"])
    return {
        "scope": path or "(cwd)",
        "files_scanned": len(sources),
        "findings": findings[:50],
        "monoliths": big[:10],
        "ownership_rule": "SERVER owns truth; CLIENT owns input/presentation; SHARED owns contracts/config.",
        "limits": ["static heuristic scan - findings are leads, not verdicts"],
    }
