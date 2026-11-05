"""Engine-trap lint: Luau patterns that compile fine and still break a Roblox game.

Every rule here comes from a real failure (most of them cost an agent several
Studio boots). Findings carry the file, line, why it bites, the fix, and the
reference that explains it. Heuristic: a finding is a lead to read.
"""
import os
import re

from . import review as review_mod

REF = "skills/roblox-game-development/references/"

# id, pattern, scope (any|server|client), severity, why, fix, reference
_LINE_RULES = [
    ("T001", r"(?<![\w.:])wait\s*\(", "any", "low",
     "wait() is the legacy throttled scheduler", "use task.wait()", REF + "sharp-edges.md"),
    ("T002", r"(?<![\w.:])(spawn|delay)\s*\(", "any", "low",
     "spawn/delay are legacy and can be deferred unpredictably", "use task.spawn / task.delay", REF + "sharp-edges.md"),
    ("T005", r"\bLocalPlayer\b", "server", "high",
     "Players.LocalPlayer is nil on the server", "pass the player from the remote/PlayerAdded instead", REF + "architecture.md"),
    ("T006", r"RenderStepped|BindToRenderStep", "server", "high",
     "RenderStepped/BindToRenderStep do not exist on the server", "use RunService.Heartbeat on the server", REF + "architecture.md"),
    ("T007", r"Instance\.new\(\s*[\"'](Unreliable)?Remote(Event|Function)[\"']", "client", "high",
     "a remote created on the client never replicates to the server", "create remotes on the server (or in the place file)", REF + "security-networking.md"),
    ("T008", r"Instance\.new\(\s*[\"']Body(Velocity|Gyro|Position|AngularVelocity|Force|Thrust)[\"']", "any", "low",
     "legacy body movers are deprecated", "LinearVelocity / AlignPosition / AlignOrientation / VectorForce", REF + "sharp-edges.md"),
    ("T009", r"SetPrimaryPartCFrame", "any", "low",
     "SetPrimaryPartCFrame is deprecated and drifts", "model:PivotTo(cf)", REF + "sharp-edges.md"),
    ("T010", r"Instance\.new\(\s*[\"'][\w]+[\"']\s*,", "any", "low",
     "the parent argument parents before properties are set (extra replication and change events)",
     "set properties first, assign .Parent last", REF + "performance.md"),
    ("T012", r"GetPartBoundsIn(Box|Radius)|GetPartsInPart", "any", "info",
     "spatial queries skip CanQuery = false parts (generated decor, screens)",
     "never use them alone to prove an area is clear; see the box-scan probe", REF + "sightlines-and-openings.md"),
    ("T017", r"Humanoid\w*:LoadAnimation|hum\w*:LoadAnimation", "any", "low",
     "Humanoid:LoadAnimation is deprecated", "load through the Animator (humanoid:FindFirstChildOfClass('Animator'))", REF + "animation.md"),
    ("T020", r"while\s+wait\s*\(", "any", "low",
     "while wait() do hides the loop condition and uses the legacy scheduler", "while cond do ... task.wait() end", REF + "sharp-edges.md"),
    ("T021", r"(?<![\w.:])tick\s*\(\s*\)", "any", "low",
     "tick() is deprecated and timezone-dependent", "os.clock() for durations, workspace:GetServerTimeNow() for shared time", REF + "sharp-edges.md"),
]
_LINE_RULES = [(i, re.compile(p), s, sev, w, f, r) for i, p, s, sev, w, f, r in _LINE_RULES]

_DS_CALL = re.compile(r":(GetAsync|SetAsync|UpdateAsync|IncrementAsync|RemoveAsync)\s*\(")
_LOOP_EVENT = re.compile(r"(Heartbeat|Stepped|RenderStepped)\s*:\s*Connect")


def _scope(rel):
    low = rel.lower()
    if ".server." in low or "/server/" in low:
        return "server"
    if ".client." in low or "/client/" in low or "starterplayer" in low or "startergui" in low:
        return "client"
    return "shared"


def scan_text(rel, text):
    findings = []
    scope = _scope(rel)
    lines = text.splitlines()

    def add(rule_id, sev, line_no, why, fix, ref):
        findings.append({"id": rule_id, "severity": sev, "file": rel, "line": line_no,
                         "why": why, "fix": fix, "ref": ref})

    for n, line in enumerate(lines, 1):
        code = line.split("--", 1)[0]
        if not code.strip():
            continue
        for rid, rx, rscope, sev, why, fix, ref in _LINE_RULES:
            if rscope != "any" and rscope != scope:
                continue
            if rx.search(code):
                add(rid, sev, n, why, fix, ref)
        if _DS_CALL.search(code):
            window = "\n".join(lines[max(0, n - 4):n])
            if "pcall" not in window:
                add("T011", "high", n, "DataStore calls throw on throttling and outages",
                    "wrap in pcall (with retry/backoff) and handle failure without wiping data", REF + "persistence.md")

    # file-level rules
    if re.search(r"Instance\.new\(\s*[\"']SurfaceGui[\"']", text) and "ClipsDescendants" not in text:
        n = next(i for i, l in enumerate(lines, 1) if "SurfaceGui" in l)
        add("T003", "medium", n,
            "SurfaceGui.ClipsDescendants defaults to false: oversized children paint in mid-air, one-sided",
            "set gui.ClipsDescendants = true", REF + "sightlines-and-openings.md")
    if "SurfaceGui" in text:
        for n, line in enumerate(lines, 1):
            if re.search(r"AlwaysOnTop\s*=\s*true", line.split("--", 1)[0]):
                add("T004", "low", n, "AlwaysOnTop SurfaceGuis did not render in testing",
                    "depth-tested panes close to the camera instead", REF + "ui-craft.md")
    for m in _LOOP_EVENT.finditer(text):
        chunk = text[m.end():m.end() + 600]
        if "FireAllClients" in chunk or "FireClient" in chunk:
            n = text.count("\n", 0, m.start()) + 1
            add("T013", "medium", n, "firing remotes every frame floods the network",
                "send on change, or batch at 5-10 Hz", REF + "security-networking.md")
    # Viewmodel: a clone that still carries its character joints drags the player when it is anchored.
    if ":Clone()" in text and re.search(r"CurrentCamera|Viewmodel|ViewmodelFolder", text) and "JointInstance" not in text:
        n = next((i for i, l in enumerate(lines, 1) if ":Clone()" in l), 1)
        add("T022", "high", n,
            "a cloned weapon keeps the welds that bind it to the hand; welded to an anchored viewmodel it flings the player",
            "destroy JointInstance/Constraint in the clone before welding it to the camera", REF + "animation.md")
    m = re.search(r'[\"\'][A-Za-z]*(Tendril|Nodule|Vein|Decor|Foliage|Pine|Blossom|Cable|Rust[A-Za-z]*)[\"\'][^\n]*,\s*true\s*\)', text)
    if m and "CanCollide" not in text[m.start():m.start() + 400]:
        n = text.count("\n", 0, m.start()) + 1
        add("T025", "high", n,
            "decorative geometry created with collision: players snag on it and probes report it as a wall",
            "pass collide=false and set CanCollide/CanQuery false on decor parts", REF + "sightlines-and-openings.md")
    m = re.search(r'GetAttribute\(\s*[\"\']Debug', text)
    if m and "IsStudio()" not in text:
        n = text.count("\n", 0, m.start()) + 1
        add("T024", "medium", n,
            "a Debug* attribute read without an IsStudio guard is a switch any client can flip in a shipped build",
            "gate it: RunService:IsStudio() and player:GetAttribute(...)", REF + "live-iteration.md")
    m = re.search(r"LocalTransparencyModifier\s*=\s*(saved|prev|original|value)\b", text)
    if m:
        n = text.count("\n", 0, m.start()) + 1
        add("T023", "medium", n,
            "the engine also owns the local head's LocalTransparencyModifier; restoring a saved value leaves the head invisible",
            "restore hidden parts to 0 explicitly and never touch HumanoidRootPart", REF + "animation.md")
    if re.search(r"ImageTransparency\s*=\s*1\b", text) and "IsLoaded" in text:
        n = next(i for i, l in enumerate(lines, 1) if re.search(r"ImageTransparency\s*=\s*1\b", l))
        add("T014", "low", n, "an ImageLabel at ImageTransparency = 1 never reports IsLoaded",
            "start the fade at 0.99 or check ContentProvider:GetAssetFetchStatus", REF + "live-iteration.md")
    return findings


def review(path="."):
    sources, _root = review_mod._collect_sources(path)
    findings = []
    skipped = 0
    for rel, full in sources:
        if re.search(r"(^|/)(artifacts|backups?|recovery|Packages|_Index)/", rel, re.I):
            skipped += 1  # snapshots and vendored packages are not the code being shipped
            continue
        findings.extend(scan_text(rel, review_mod._read((rel, full))[1]))
    rank = {"high": 0, "medium": 1, "low": 2, "info": 3}
    findings.sort(key=lambda f: (rank[f["severity"]], f["file"], f["line"]))
    by_id = {}
    for f in findings:
        by_id[f["id"]] = by_id.get(f["id"], 0) + 1
    return {
        "scope": os.path.abspath(path),
        "files_scanned": len(sources) - skipped,
        "files_skipped": skipped,
        "counts": by_id,
        "findings": findings[:80],
        "limits": ["regex heuristics - read each hit; scope (server/client) comes from file names and folders"],
    }
