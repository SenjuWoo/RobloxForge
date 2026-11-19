"""Engine-trap lint: Luau patterns that compile fine and still break a Roblox game.

Findings carry the file, line, why it bites, the fix, the reference that explains it, and the
evidence class behind the rule:

- `docs`  - the official engine reference says so (deprecations, non-scriptable properties, limits);
- `live`  - observed in a Studio session by this project's maintainers;
- `field` - reported once from a real project and not reproduced elsewhere. A lead, never a rule.

Heuristic: every finding is something to read, not a verdict.
"""
import os
import re

from . import luau_text
from . import project as project_mod
from . import review as review_mod

REF = "skills/roblox-game-development/references/"

# id, pattern, scope (any|server|client|notclient), severity, evidence, why, fix, reference
_LINE_RULES = [
    ("T001", r"(?<![\w.:])wait\s*\(", "any", "low", "docs",
     "wait() is the legacy throttled scheduler", "use task.wait()", REF + "sharp-edges.md"),
    ("T002", r"(?<![\w.:])(spawn|delay)\s*\(", "any", "low", "docs",
     "spawn/delay are legacy and can be deferred unpredictably", "use task.spawn / task.delay",
     REF + "sharp-edges.md"),
    ("T005", r"\bLocalPlayer\b", "server", "high", "docs",
     "Players.LocalPlayer is nil on the server", "pass the player from the remote/PlayerAdded instead",
     REF + "architecture.md"),
    ("T006", r"RenderStepped|BindToRenderStep", "server", "high", "docs",
     "RenderStepped/BindToRenderStep do not exist on the server", "use RunService.Heartbeat on the server",
     REF + "architecture.md"),
    ("T007", r"Instance\.new\(\s*[\"'](Unreliable)?Remote(Event|Function)[\"']", "client", "high", "docs",
     "a remote created on the client never replicates to the server",
     "create remotes on the server (or in the place file)", REF + "security-networking.md"),
    ("T008", r"Instance\.new\(\s*[\"']Body(Velocity|Gyro|Position|AngularVelocity|Force|Thrust)[\"']",
     "any", "low", "docs", "legacy body movers are deprecated",
     "LinearVelocity / AlignPosition / AlignOrientation / VectorForce", REF + "sharp-edges.md"),
    ("T009", r"SetPrimaryPartCFrame", "any", "low", "docs",
     "SetPrimaryPartCFrame is deprecated and drifts", "model:PivotTo(cf)", REF + "sharp-edges.md"),
    ("T010", r"Instance\.new\(\s*[\"'][\w]+[\"']\s*,", "any", "low", "docs",
     "the parent argument parents before properties are set (extra replication and change events)",
     "set properties first, assign .Parent last", REF + "performance.md"),
    ("T012", r"GetPartBoundsIn(Box|Radius)|GetPartsInPart", "any", "info", "live",
     "spatial queries skip CanQuery = false parts (generated decor, screens)",
     "never use them alone to prove an area is clear; see the box-scan probe",
     REF + "sightlines-and-openings.md"),
    ("T017", r"Humanoid\w*:LoadAnimation|hum\w*:LoadAnimation", "any", "low", "docs",
     "Humanoid:LoadAnimation is deprecated",
     "load through the Animator (humanoid:FindFirstChildOfClass('Animator'))", REF + "animation.md"),
    ("T020", r"while\s+wait\s*\(", "any", "low", "docs",
     "while wait() do hides the loop condition and uses the legacy scheduler",
     "while cond do ... task.wait() end", REF + "sharp-edges.md"),
    ("T021", r"(?<![\w.:])tick\s*\(\s*\)", "any", "low", "docs",
     "tick() is deprecated and timezone-dependent",
     "os.clock() for durations, workspace:GetServerTimeNow() for shared time", REF + "sharp-edges.md"),
    ("T026", r":(connect|disconnect)\s*\(", "any", "low", "docs",
     "lower-case :connect/:disconnect are deprecated aliases", "use :Connect / :Disconnect",
     REF + "sharp-edges.md"),
    ("T027", r":InvokeClient\s*\(", "notclient", "high", "docs",
     "InvokeClient yields on a machine you do not control: a client that never answers hangs the thread, "
     "one that errors throws on the server", "send a RemoteEvent and let the client answer with another",
     REF + "security-networking.md"),
    ("T028", r"FindPartOnRay(WithIgnoreList|WithWhitelist)?\s*\(", "any", "low", "docs",
     "FindPartOnRay* are deprecated", "workspace:Raycast(origin, direction, RaycastParams)",
     REF + "sharp-edges.md"),
    ("T029", r":Remove\(\s*\)", "any", "low", "docs",
     "Instance:Remove() is deprecated and leaves connections alive", "use :Destroy()",
     REF + "sharp-edges.md"),
    ("T030", r"Lighting\.Technology\s*=(?!=)", "any", "medium", "docs",
     "Lighting.Technology is not scriptable; the assignment throws",
     "set it in Studio's Properties (or the Rojo project file); script LightingStyle instead",
     REF + "worldbuilding-lighting.md"),
    ("T031", r"(?<![\w.])(_G|shared)\.\w+\s*=(?!=)", "any", "low", "docs",
     "state in _G/shared depends on script start order and is invisible to the type checker",
     "export it from a ModuleScript and require it", REF + "architecture.md"),
    ("T032", r":(GetAsync|SetAsync|UpdateAsync|RemoveAsync|IncrementAsync)\s*\([^)\n]*\.Name\b", "any",
     "high", "docs", "a data store key built from a name: players rename, and the data is orphaned",
     "key by player.UserId", REF + "persistence.md"),
    ("T033", r"PromptProductPurchaseFinished", "any", "high", "docs",
     "PromptProductPurchaseFinished fires on the client's say-so and also on cancelled or failed "
     "purchases; granting from it gives items away",
     "grant only inside MarketplaceService.ProcessReceipt, idempotently, and return PurchaseGranted",
     "skills/roblox-monetization/SKILL.md"),
    ("T034", r"\.Key(Down|Up)\s*:\s*Connect", "client", "low", "docs",
     "Mouse.KeyDown/KeyUp are deprecated and ignore chat focus",
     "UserInputService.InputBegan with the gameProcessed check, or the Input Action System",
     REF + "current-engine.md"),
    ("T035", r":LoadCharacter\s*\(", "notclient", "low", "docs",
     "Player:LoadCharacter is superseded", "player:LoadCharacterAsync()", REF + "current-engine.md"),
    ("T036", r"HttpService\s*:\s*(GetAsync|PostAsync|RequestAsync)|:(GetAsync|PostAsync|RequestAsync)\s*\(\s*[\"']https?:",
     "client", "high", "docs", "HttpService requests only work on the server",
     "ask the server through a remote; never ship a URL or key to the client", REF + "architecture.md"),
]
_LINE_RULES = [(i, re.compile(p), s, sev, ev, w, f, r) for i, p, s, sev, ev, w, f, r in _LINE_RULES]

_DS_CALL = re.compile(r":(GetAsync|SetAsync|UpdateAsync|IncrementAsync|RemoveAsync)\s*\(")
# Web-backed calls that throw on outage or throttling just like data stores do.
_WEB_CALL = re.compile(r":(UserOwnsGamePassAsync|GetProductInfo|GetRankInGroup|GetRoleInGroup|IsInGroup|"
                       r"GetUserThumbnailAsync|TeleportAsync|TeleportToPrivateServer|ReserveServer|"
                       r"FilterStringAsync|PublishAsync|GetNameFromUserIdAsync|GetUserIdFromNameAsync)\s*\(")
_LOOP_EVENT = re.compile(r"(Heartbeat|Stepped|RenderStepped|PreRender|PreSimulation|PostSimulation)\s*:\s*Connect")
# UserInputService only: a GuiObject's InputBegan has no second argument, and InputEnded must run
# regardless (it releases a held action).
_INPUT_ONE_ARG = re.compile(r"\b(UserInputService|UIS|InputService|uis)\s*\.\s*InputBegan\s*:\s*Connect\("
                            r"\s*function\s*\(\s*\w+\s*(:\s*[\w.]+)?\s*\)")
_SERVER_HANDLER = re.compile(r"\.OnServerEvent\s*:\s*Connect\(\s*function\s*\(([^)]*)\)")
_CLIENT_VALUE = re.compile(r"^(amount|damage|dmg|reward|coins?|cash|money|gems?|gold|price|cost|xp|exp|"
                           r"score|points|health|hp)\w*$", re.I)
_DEBUG_REMOTE = re.compile(r"\b(\w*(?:Test|Debug|Admin|Cheat|Dev)\w*)\s*(?:::\s*[\w.]+\s*\))?\s*\.OnServerEvent")
_DEBUG_GUARD = re.compile(r"IsStudio\s*\(|CreatorId|GetRankInGroup|GetRoleInGroup|IsInGroup|"
                          r"admins?\s*\[|allow\w*\s*\[|whitelist\w*\s*\[", re.I)
# A failed load has to end somewhere other than "use the defaults": a kick, a retry, an error, a flag.
_LOAD_FAILURE_HANDLED = re.compile(
    r":Kick\s*\(|\bnot\s+(ok|success|succeeded|loaded|okay)\b|\b(ok|success)\s*==\s*false|"
    r"\berror\s*\(|(?i:\bretr(y|ies)\b|load_?failed)|StartSessionAsync|\bProfileStore\b|\bProfileService\b")
_CHARACTER_READ = re.compile(r"\.Character\b(?!Added|Removing|AutoLoads|Appearance)")
# An attachment made without a parent argument; T045 then checks the order of its first writes.
_ATTACH_NEW = re.compile(r"(?<![.\w])(\w+)\s*(?::\s*\w+\s*)?=\s*Instance\.new\(\s*[\"']Attachment[\"']\s*\)")


def _scope(rel):
    low = rel.lower()
    if ".server." in low or "/server/" in low or "serverscriptservice" in low or "serverstorage" in low:
        return "server"
    if ".client." in low or "/client/" in low or "starterplayer" in low or "startergui" in low:
        return "client"
    return "shared"


def _applies(rule_scope, scope):
    if rule_scope == "any":
        return True
    if rule_scope == "notclient":
        return scope != "client"
    return rule_scope == scope


def scan_text(rel, text):
    findings = []
    scope = _scope(rel)
    lines = text.splitlines()
    # Comments gone, strings kept, line numbers intact: a rule about `Instance.new("SurfaceGui")`
    # needs the string, and a comment that names wait() is not a call.
    code = luau_text.code_only(text, keep_strings=True, keep_lines=True)
    code_lines = code.splitlines()

    def add(rule_id, sev, line_no, why, fix, ref, evidence="docs"):
        findings.append({"id": rule_id, "severity": sev, "file": rel, "line": line_no,
                         "why": why, "fix": fix, "ref": ref, "evidence": evidence})

    def line_of(pos):
        return code.count("\n", 0, pos) + 1

    for n, cl in enumerate(code_lines, 1):
        if not cl.strip():
            continue
        for rid, rx, rscope, sev, ev, why, fix, ref in _LINE_RULES:
            if _applies(rscope, scope) and rx.search(cl):
                add(rid, sev, n, why, fix, ref, ev)
        guarded = "pcall" in "\n".join(code_lines[max(0, n - 4):n])
        if _DS_CALL.search(cl) and not guarded:
            add("T011", "high", n, "DataStore calls throw on throttling and outages",
                "wrap in pcall (with retry/backoff) and handle failure without wiping data",
                REF + "persistence.md")
        elif _WEB_CALL.search(cl) and not guarded:
            add("T037", "medium", n, "this call reaches a Roblox web service and throws when it is slow or down",
                "wrap in pcall and decide what the player gets when it fails", REF + "persistence.md")

    # ---- file-level rules -------------------------------------------------------------------
    if re.search(r"Instance\.new\(\s*[\"']SurfaceGui[\"']", code) and "ClipsDescendants" not in code:
        n = next(i for i, l in enumerate(code_lines, 1) if "SurfaceGui" in l)
        add("T003", "medium", n,
            "SurfaceGui.ClipsDescendants defaults to false: oversized children paint in mid-air, one-sided",
            "set gui.ClipsDescendants = true", REF + "sightlines-and-openings.md", "live")
    if "SurfaceGui" in code:
        for n, cl in enumerate(code_lines, 1):
            if re.search(r"AlwaysOnTop\s*=\s*true", cl):
                add("T004", "info", n,
                    "an AlwaysOnTop SurfaceGui failed to render in one project's Studio captures",
                    "if yours does not show, try a depth-tested pane close to the camera; otherwise ignore",
                    REF + "ui-craft.md", "field")
    for m in _LOOP_EVENT.finditer(code):
        chunk = code[m.end():m.end() + 600]
        if "FireAllClients" in chunk or "FireClient" in chunk or "FireServer" in chunk:
            add("T013", "medium", line_of(m.start()), "firing remotes every frame floods the network",
                "send on change, or batch at 5-10 Hz", REF + "security-networking.md")
    # Viewmodel: a clone that still carries its character joints drags the player when it is anchored.
    if ":Clone()" in code and re.search(r"viewmodel", code, re.I) and "CurrentCamera" in code \
            and "JointInstance" not in code:
        n = next((i for i, l in enumerate(code_lines, 1) if ":Clone()" in l), 1)
        add("T022", "medium", n,
            "a cloned weapon keeps the welds that bind it to the hand; welded to an anchored viewmodel "
            "it flings the player",
            "destroy JointInstance/Constraint in the clone before welding it to the camera",
            REF + "animation.md", "live")
    m = re.search(r'GetAttribute\(\s*[\"\']Debug', code)
    if m and "IsStudio()" not in code:
        add("T024", "medium", line_of(m.start()),
            "a Debug* attribute read without an IsStudio guard is a switch any client can flip in a shipped build",
            "gate it: RunService:IsStudio() and player:GetAttribute(...)", REF + "live-iteration.md", "live")
    m = re.search(r"LocalTransparencyModifier\s*=\s*(saved|prev|original|value)\b", code)
    if m:
        add("T023", "medium", line_of(m.start()),
            "the engine also owns the local head's LocalTransparencyModifier; restoring a saved value "
            "leaves the head invisible",
            "restore hidden parts to 0 explicitly and never touch HumanoidRootPart", REF + "animation.md", "live")
    m = re.search(r"ImageTransparency\s*=\s*1\b", code)
    if m and "IsLoaded" in code:
        add("T014", "low", line_of(m.start()), "an ImageLabel at ImageTransparency = 1 never reports IsLoaded",
            "start the fade at 0.99 or check ContentProvider:GetAssetFetchStatus",
            REF + "live-iteration.md", "live")

    # Data safety. A load that fails and a player who is new must not look the same: the default
    # profile then gets saved over the real one on the way out. This is how games wipe inventories.
    m = re.search(r":GetAsync\s*\(", code)
    if m and scope != "client" and re.search(r":(SetAsync|UpdateAsync)\s*\(", code) \
            and not _LOAD_FAILURE_HANDLED.search(code):
        add("T038", "high", line_of(m.start()),
            "a failed data store read is indistinguishable from a new player here: the default profile "
            "is used, then saved over the real data",
            "keep a per-player 'loaded' flag: on a failed read retry, then kick, and never save a "
            "profile that did not load", REF + "persistence.md")
    m = re.search(r"PlayerRemoving", code)
    if m and scope != "client" and re.search(r":(SetAsync|UpdateAsync)\s*\(", code) and "BindToClose" not in code:
        add("T039", "medium", line_of(m.start()),
            "saves on PlayerRemoving only: on shutdown the server exits before those saves finish",
            "game:BindToClose(function() save every remaining player, then return end)",
            REF + "persistence.md")

    # Lifecycle: the handler has to cover what already exists when the script starts.
    m = re.search(r"PlayerAdded\s*:\s*Connect", code)
    if m and scope != "client" and "GetPlayers()" not in code:
        add("T040", "medium", line_of(m.start()),
            "PlayerAdded alone misses players who joined before this script ran (always the case in a "
            "Studio play test with a slow start)",
            "after connecting, loop Players:GetPlayers() and call the same handler", REF + "architecture.md")
    m = re.search(r"CharacterAdded\s*:\s*Connect", code)
    if m and not _CHARACTER_READ.search(code):
        add("T041", "low", line_of(m.start()),
            "CharacterAdded alone misses a character that already exists",
            "if player.Character then onCharacter(player.Character) end, next to the Connect",
            REF + "architecture.md")

    # Input: the second argument says the UI or chat already consumed the event.
    if scope != "server":
        for m in _INPUT_ONE_ARG.finditer(code):
            add("T042", "medium", line_of(m.start()),
                "the handler ignores gameProcessedEvent, so typing in chat or clicking a button fires "
                "the game action too",
                "function(input, gameProcessed) if gameProcessed then return end ...",
                REF + "ui-mobile.md")

    # Remotes.
    for m in _SERVER_HANDLER.finditer(code):
        params = [p.split(":")[0].strip() for p in m.group(1).split(",")][1:]
        named = [p for p in params if _CLIENT_VALUE.match(p)]
        if named:
            add("T043", "medium", line_of(m.start()),
                "the client supplies %s: an exploiter sends any number" % ", ".join(named),
                "send the intent (which item, which target); look the value up or compute it on the server",
                REF + "security-networking.md")
    m = _DEBUG_REMOTE.search(code)
    if m and not _DEBUG_GUARD.search(code):
        add("T044", "high", line_of(m.start()),
            "%s is a test/debug remote any client can fire in a published game" % m.group(1),
            "guard the handler (RunService:IsStudio() or a creator/group check) or delete the remote",
            REF + "security-networking.md")

    # Placement: world coordinates written to an unparented attachment are stored as its local offset.
    for m in _ATTACH_NEW.finditer(code):
        name = re.escape(m.group(1))
        rest = code[m.end():m.end() + 3000]
        again = re.search(r"(?<![.\w])%s\s*=\s*(?!=)" % name, rest)
        if again:
            rest = rest[:again.start()]  # the name is reassigned: later writes are another attachment
        world = re.search(r"(?<![.\w])%s\.World(CFrame|Position|Axis|SecondaryAxis)\s*=(?!=)" % name, rest)
        parent = re.search(r"(?<![.\w])%s\.Parent\s*=(?!=)" % name, rest)
        if world and (not parent or world.start() < parent.start()):
            add("T045", "medium", line_of(m.end() + world.start()),
                "%s.World%s is set before the attachment has a parent: the value is kept as a local "
                "offset, so once parented it lands that far from its part" % (m.group(1), world.group(1)),
                "set .Parent first, then World*, or set .CFrame in the part's own space",
                REF + "sharp-edges.md", "live")
    return findings


# Every rule id with its evidence class: the docs and the tests read this, so a rule cannot be added
# without saying what stands behind it.
def catalog():
    out = {rid: ev for rid, _rx, _s, _sev, ev, _w, _f, _r in _LINE_RULES}
    out.update({"T003": "live", "T004": "field", "T011": "docs", "T013": "docs", "T014": "live",
                "T022": "live", "T023": "live", "T024": "live", "T037": "docs", "T038": "docs",
                "T039": "docs", "T040": "docs", "T041": "docs", "T042": "docs", "T043": "docs",
                "T044": "docs", "T045": "live"})
    return dict(sorted(out.items()))


def review(path="."):
    sources, root = review_mod._collect_sources(path, include_snapshots=True)
    kept, skipped = project_mod.shipped_sources(root, [full for _rel, full in sources])
    keep = set(kept)
    findings = []
    for rel, full in sources:
        if full in keep:
            findings.extend(scan_text(rel, review_mod._read((rel, full))[1]))
    rank = {"high": 0, "medium": 1, "low": 2, "info": 3}
    findings.sort(key=lambda f: (rank[f["severity"]], f["file"], f["line"]))
    by_id = {}
    for f in findings:
        by_id[f["id"]] = by_id.get(f["id"], 0) + 1
    return {
        "scope": os.path.abspath(path),
        "files_scanned": len(kept),
        "files_skipped": len(skipped),
        "counts": by_id,
        "findings": findings[:80],
        "limits": ["regex heuristics - read each hit; scope (server/client) comes from file names and folders",
                   "evidence: docs = official reference, live = observed in Studio, field = one project report"],
    }
