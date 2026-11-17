"""Project health audit: what to read first when you take over an existing Roblox codebase.

`check` answers "is this edit clean"; `audit` answers "what is wrong with this project and in which
order should it be fixed". It ranks leads by what they cost a live game - lost player data first,
exploitable remotes second, crashes third - and only then structure, performance and deprecations.

Static and heuristic, like the other reviews: every item is a place to read, not a verdict. It never
opens Studio and never edits a file.
"""
import os
import re

from . import luau_text
from . import project as project_mod
from . import review as review_mod
from . import traps

REF = "skills/roblox-game-development/references/"

_HANDLER = re.compile(r"([\w.:\[\]\"'()]+?)\s*(?:::\s*[\w.]+\s*\))?\s*\.\s*(OnServerEvent\s*:\s*Connect\s*\(|"
                      r"OnServerInvoke\s*=)\s*(function\s*\(([^)]*)\)|[\w.:]+)")
_GUARDS = {
    "type": re.compile(r"\btypeof\s*\(|\btype\s*\(|\btonumber\s*\(|:IsA\s*\(|\bt\.\w+\(|\bcheck\w*\s*\("),
    "range": re.compile(r"math\.(clamp|min|max|floor)\s*\(|[<>]=?\s*[\w.#]"),
    "rate": re.compile(r"os\.clock|os\.time|\btick\s*\(|\btime\s*\(|cooldown|debounce|throttle|"
                       r"rate\s*limit|ratelimit|limiter|bucket|last\w*(fire|use|shot|at|time)", re.I),
    "distance": re.compile(r"\.Magnitude|DistanceFromCharacter|GetPivot\s*\(|\.Position\b"),
    "state": re.compile(r"owner|profile|session|GetAttribute\s*\(|:IsDescendantOf\s*\(|\.Parent\b|"
                        r"Health\b|alive|dead", re.I),
}
_WORLD_CLASSES = ("Part", "MeshPart", "WedgePart", "CornerWedgePart", "TrussPart", "UnionOperation",
                  "Model", "SpawnLocation", "Seat", "PointLight", "SpotLight", "SurfaceLight")
_UI_CLASSES = ("Frame", "TextLabel", "TextButton", "ImageLabel", "ImageButton", "ScrollingFrame",
               "TextBox", "CanvasGroup", "ViewportFrame", "ScreenGui", "SurfaceGui", "BillboardGui")
_INSTANCE_NEW = re.compile(r"Instance\.new\(\s*[\"'](\w+)[\"']")
_FRAME_EVENT = re.compile(r"(Heartbeat|Stepped|RenderStepped|PreRender|PreSimulation|PostSimulation|"
                          r"PreAnimation)\s*:\s*(Connect|ConnectParallel)|BindToRenderStep\s*\(")
_PLAYER_TABLE = re.compile(r"\[\s*(player|plr|ply)\s*\]\s*=(?!=)")
_PLAYER_CLEANUP = re.compile(r"PlayerRemoving|\[\s*(player|plr|ply)\s*\]\s*=\s*nil|"
                             r"function\s+[\w.:]*(Remove|Cleanup|CleanUp|Unload|Release|Clear|Forget|"
                             r"PlayerLeft|OnPlayerRemoving|Destroy)\w*\s*\(", re.I)

MONOLITH_LINES = 800       # past this a file is several systems; 300-800 is merely large
LARGE_LINES = 300
CODE_WORLD_THRESHOLD = 150  # Instance.new of world classes in server code
CODE_UI_THRESHOLD = 150
BUILDER_LINES_THRESHOLD = 1500


def _body_at(lines, start):
    """Lines of the block that opens on `lines[start]`, found by indentation (formatted code)."""
    first = lines[start]
    indent = len(first) - len(first.lstrip())
    out = [first]
    for line in lines[start + 1:start + 400]:
        out.append(line)
        if line.strip() and (len(line) - len(line.lstrip())) <= indent and line.lstrip().startswith("end"):
            break
    return "\n".join(out)


def _function_body(code_lines, name):
    """Body of `function <name>(` in this file; `name` may be `M.Fn` or `M:Fn`."""
    short = re.split(r"[.:]", name)[-1]
    rx = re.compile(r"function\s+[\w.:]*\b%s\s*\(|\b%s\s*=\s*function\s*\(" % (re.escape(short), re.escape(short)))
    for i, line in enumerate(code_lines):
        if rx.search(line):
            return _body_at(code_lines, i)
    return ""


def _remote_handlers(rel, code):
    """One row per server remote handler: its arguments and which kinds of guard the code shows."""
    rows = []
    code_lines = code.splitlines()
    for m in _HANDLER.finditer(code):
        line_no = code.count("\n", 0, m.start()) + 1
        target = m.group(3)
        if m.group(4) is not None:
            params = [p.split(":")[0].strip() for p in m.group(4).split(",") if p.strip()]
            body = _body_at(code_lines, line_no - 1)
        else:  # a named function is connected directly
            params = None
            body = _function_body(code_lines, target)
        # Follow delegation one level: handlers are often one line that calls the real function.
        seen = set()
        for call in re.findall(r"([A-Za-z_][\w.:]*)\s*\(", body):
            if call in seen or len(seen) >= 4 or "." not in call and ":" not in call:
                continue
            seen.add(call)
            body += "\n" + _function_body(code_lines, call)
        guards = sorted(k for k, rx in _GUARDS.items() if rx.search(body))
        args = (params or [])[1:] if params is not None else None
        missing = []
        if args is None or args:
            if "type" not in guards:
                missing.append("type")
        if "rate" not in guards:
            missing.append("rate")
        rows.append({
            "file": rel, "line": line_no,
            "remote": re.sub(r"\s+", "", m.group(1)).lstrip("(")[-60:],
            "kind": "function" if "OnServerInvoke" in m.group(2) else "event",
            "args": args,
            "guards_seen": guards,
            "missing": missing,
            "read_first": bool(missing and "type" in missing),
        })
    return rows


def _strict_mode(text):
    m = re.match(r"\s*--!(strict|nonstrict|nocheck)", text)
    return m.group(1) if m else "none"


def audit(path="."):
    sources, root = review_mod._collect_sources(path, include_snapshots=True)
    kept, skipped = project_mod.shipped_sources(root, [full for _rel, full in sources])
    keep = set(kept)

    files = []
    trap_findings = []
    handlers = []
    world_new, ui_new, frame_conns = {}, {}, {}
    leaks = []
    strict = {"strict": 0, "nonstrict": 0, "nocheck": 0, "none": 0}
    total_lines = 0
    all_server_code, all_client_code = [], []
    typed_text_sent = []

    for rel, full in sources:
        if full not in keep:
            continue
        text = review_mod._read((rel, full))[1]
        is_test = rel.startswith("tests/") or "/tests/" in rel or ".spec." in rel or rel.startswith("tools/")
        code = luau_text.code_only(text, keep_strings=True, keep_lines=True)
        lines = text.count("\n") + 1
        scope = traps._scope(rel)
        files.append({"file": rel, "lines": lines, "scope": scope, "test": is_test})
        if is_test:
            continue
        total_lines += lines
        strict[_strict_mode(text)] += 1
        trap_findings.extend(traps.scan_text(rel, text))
        (all_client_code if scope == "client" else all_server_code).append(code)

        if scope != "client":
            handlers.extend(_remote_handlers(rel, code))
            n = sum(1 for c in _INSTANCE_NEW.findall(code) if c in _WORLD_CLASSES)
            if n:
                world_new[rel] = n
            if _PLAYER_TABLE.search(code) and not _PLAYER_CLEANUP.search(code):
                leaks.append({"file": rel, "line": code.count("\n", 0, _PLAYER_TABLE.search(code).start()) + 1})
        if scope != "server":
            n = sum(1 for c in _INSTANCE_NEW.findall(code) if c in _UI_CLASSES)
            if n:
                ui_new[rel] = n
            m = re.search(r"(FireServer|InvokeServer)\s*\([^)\n]*\.Text\b", code)
            if m:
                typed_text_sent.append({"file": rel, "line": code.count("\n", 0, m.start()) + 1})
        n = len(_FRAME_EVENT.findall(code))
        if n:
            frame_conns[rel] = n

    server_blob = "\n".join(all_server_code)
    client_blob = "\n".join(all_client_code)
    by_id = {}
    for f in trap_findings:
        by_id.setdefault(f["id"], []).append(f)

    def where(ids, limit=6):
        out = []
        for rid in ids:
            for f in by_id.get(rid, []):
                out.append("%s:%d [%s]" % (f["file"], f["line"], rid))
        return out[:limit], len(out)

    spec_files = [f for f in files if ".spec." in f["file"]]
    other_tests = [f for f in files if f["test"] and ".spec." not in f["file"] and f["file"].startswith("tests/")]
    game_files = [f for f in files if not f["test"]]
    monoliths = sorted((f for f in game_files if f["lines"] > MONOLITH_LINES), key=lambda f: -f["lines"])
    large = sorted((f for f in game_files if LARGE_LINES < f["lines"] <= MONOLITH_LINES), key=lambda f: -f["lines"])
    unguarded = [h for h in handlers if h["read_first"]]

    order = []

    def item(tier, title, why, locs, total, ref):
        if total:
            order.append({"tier": tier, "title": title, "why": why, "count": total, "where": locs, "ref": ref})

    # 1 - player data
    locs, n = where(["T038", "T032", "T011", "T039"])
    item("1 data loss", "Data store reads and writes that can lose or orphan player data",
         "a wiped inventory cannot be patched afterwards; fix before any feature work", locs, n,
         REF + "persistence.md")
    uses_products = re.search(r"PromptProductPurchase\s*\(", client_blob + server_blob)
    if uses_products and "ProcessReceipt" not in server_blob:
        item("1 data loss", "Developer products are prompted but nothing sets ProcessReceipt",
             "purchases are charged and never granted (or granted from an event a client controls)",
             [], 1, "skills/roblox-monetization/SKILL.md")

    # 2 - authority
    locs, n = where(["T044", "T043", "T033", "T027", "T024"])
    item("2 exploitable", "Remotes and switches a client can abuse",
         "anything a client can fire, an exploiter fires with any arguments, as often as it likes",
         locs, n, REF + "security-networking.md")
    item("2 exploitable", "Remote handlers that take arguments and show no type check",
         "read each one: type, range, ownership, state and rate must all be decided on the server",
         ["%s:%d %s(%s)" % (h["file"], h["line"], h["remote"], ", ".join(h["args"] or ["?"]))
          for h in unguarded[:8]], len(unguarded), REF + "security-networking.md")
    sec = review_mod.security(path)
    client_auth = [f for f in sec["findings"] if f["severity"] == "high"]
    item("2 exploitable", "Client scripts that write authoritative-looking state",
         "health, currency and teleports decided on the client are decided by the exploiter",
         ["%s (%s)" % (f["file"], f["why"]) for f in client_auth[:6]], len(client_auth),
         REF + "architecture.md")
    if typed_text_sent and "FilterStringAsync" not in server_blob and "TextChatService" not in server_blob:
        item("2 exploitable", "Player-typed text is sent to the server and never filtered",
             "text one player types and another sees must pass TextService:FilterStringAsync; "
             "unfiltered text gets an experience moderated",
             ["%s:%d" % (t["file"], t["line"]) for t in typed_text_sent[:4]], len(typed_text_sent),
             "skills/roblox-text-chat/SKILL.md")

    # 3 - breaks at runtime
    locs, n = where(["T005", "T006", "T007", "T036", "T030", "T040", "T041", "T042", "T037"])
    item("3 runtime faults", "Code that fails or misfires in a real session",
         "server/client API mix-ups, missed players and characters, input that fires through chat",
         locs, n, REF + "sharp-edges.md")
    item("3 runtime faults", "Per-player tables with no visible cleanup",
         "an entry per player that is never cleared grows for the life of the server",
         ["%s:%d" % (l["file"], l["line"]) for l in leaks[:6]], len(leaks), REF + "architecture.md")

    # 4 - safety net before refactoring
    if not spec_files and not other_tests:
        item("4 no safety net", "No tests found",
             "write one characterization test per system you are about to change, before changing it",
             [], 1, REF + "existing-projects.md")
    elif not spec_files:
        item("4 no safety net", "No offline unit specs (tests/*.spec.luau)",
             "rules and maths that live in pure modules can be proven in milliseconds without Studio",
             ["%d Studio-side test files exist" % len(other_tests)], 1, REF + "testing-debugging.md")

    # 5 - structure
    item("5 structure", "Files that are several systems in one (> %d lines)" % MONOLITH_LINES,
         "split along the seams that already exist (one builder, one screen, one enemy) - never rewrite",
         ["%s (%d lines)" % (f["file"], f["lines"]) for f in monoliths[:8]], len(monoliths),
         REF + "existing-projects.md")
    locs, n = where(["T031"])
    item("5 structure", "Global state in _G / shared", "load-order races and no types", locs, n,
         REF + "architecture.md")
    unstrict = strict["none"] + strict["nocheck"]
    if game_files and unstrict > len(game_files) * 0.25:
        item("5 structure", "%d of %d files are not type checked" % (unstrict, len(game_files)),
             "add --!strict file by file, starting with the modules other files require",
             [], unstrict, REF + "typing-luau.md")

    # 6 - cost
    locs, n = where(["T013"])
    item("6 cost", "Remotes fired from a per-frame connection", "bandwidth and server time every frame",
         locs, n, REF + "performance.md")
    world_total = sum(world_new.values())
    # Projects that build through helper functions create few instances by name; the module names
    # and their size say the same thing.
    builders = [f for f in game_files if f["scope"] != "client"
                and re.search(r"(Builder|Kit|Generator|Worldgen|WorldGen)$", os.path.basename(f["file"]).split(".")[0])]
    builder_lines = sum(f["lines"] for f in builders)
    if world_total < CODE_WORLD_THRESHOLD and builder_lines >= BUILDER_LINES_THRESHOLD:
        top = sorted(builders, key=lambda f: -f["lines"])[:5]
        item("6 cost", "The world is built by server code (%d lines in %d builder modules)"
             % (builder_lines, len(builders)),
             "if that geometry is the same every session it belongs in the saved place: every server "
             "start rebuilds it, nothing can be edited by hand, and the build delays the first spawn. "
             "Measure the build time before deciding; a procedural game is the exception",
             ["%s (%d lines)" % (f["file"], f["lines"]) for f in top], len(builders),
             REF + "worldbuilding-lighting.md")
    if world_total >= CODE_WORLD_THRESHOLD:
        top = sorted(world_new.items(), key=lambda kv: -kv[1])[:5]
        item("6 cost", "The world is built by server code (%d part/model/light constructors)" % world_total,
             "if that geometry is the same every session it belongs in the saved place: every server "
             "start rebuilds it, nothing can be edited by hand, and the build delays the first spawn. "
             "Measure the build time before deciding; a procedural game is the exception",
             ["%s (%d)" % kv for kv in top], world_total, REF + "worldbuilding-lighting.md")
    ui_total = sum(ui_new.values())
    if ui_total >= CODE_UI_THRESHOLD:
        top = sorted(ui_new.items(), key=lambda kv: -kv[1])[:5]
        item("6 cost", "The interface is built by client code (%d GUI constructors)" % ui_total,
             "fine when it is split into small components; a single builder past a few hundred lines "
             "cannot be changed safely", ["%s (%d)" % kv for kv in top], ui_total, REF + "ui-craft.md")
    frame_total = sum(frame_conns.values())
    if frame_total >= 12:
        top = sorted(frame_conns.items(), key=lambda kv: -kv[1])[:5]
        item("6 cost", "%d per-frame connections" % frame_total,
             "each runs every frame for every client or on the server; profile before and after",
             ["%s (%d)" % kv for kv in top], frame_total, REF + "performance.md")

    # 7 - deprecations
    locs, n = where(["T001", "T002", "T008", "T009", "T017", "T020", "T021", "T026", "T028", "T029",
                     "T034", "T035", "T010"])
    item("7 deprecated", "Deprecated or legacy API calls", "they still run; replace them when you touch the file",
         locs, n, REF + "current-engine.md")

    return {
        "scope": root,
        "files": len(game_files),
        "lines": total_lines,
        "tests": {"unit_specs": len(spec_files), "studio_or_other": len(other_tests)},
        "skipped": {"snapshot_or_ignored": len(skipped)},
        "typing": strict,
        "largest_files": [{"file": f["file"], "lines": f["lines"]} for f in (monoliths + large)[:10]],
        "remote_handlers": handlers[:60],
        "trap_counts": {k: len(v) for k, v in sorted(by_id.items())},
        "fix_order": order,
        "next": ("Fix tier 1 before anything else. Before changing a system, pin its current behaviour "
                 "with a test. One system per change; re-run `rbforge check` and the play test after each."),
        "limits": ["static heuristics over files on disk: every item is a place to read, not a verdict",
                   "a guard 'seen' means a matching call appears in the handler or the function it calls, "
                   "not that the validation is correct",
                   "a place that exists only in Studio is not on disk: use the official MCP's script_grep"],
    }


def render(report):
    out = ["RobloxForge audit: %s" % report["scope"],
           "%d files, %d lines; %d unit specs, %d other tests; %d snapshot/ignored files skipped" % (
               report["files"], report["lines"], report["tests"]["unit_specs"],
               report["tests"]["studio_or_other"], report["skipped"]["snapshot_or_ignored"]),
           ""]
    if not report["fix_order"]:
        out.append("No leads from the static audit. That is not proof of a working game - play it.")
    for n, it in enumerate(report["fix_order"], 1):
        out.append("%d. [%s] %s (%d)" % (n, it["tier"], it["title"], it["count"]))
        out.append("     why: %s" % it["why"])
        for w in it["where"]:
            out.append("     - %s" % w)
        out.append("     ref: %s" % it["ref"])
    if report["remote_handlers"]:
        out += ["", "Remote handlers (the attack surface):"]
        for h in report["remote_handlers"]:
            args = "?" if h["args"] is None else ", ".join(h["args"]) or "-"
            out.append("  %s:%d  %s(%s)  guards: %s%s" % (
                h["file"], h["line"], h["remote"], args, ", ".join(h["guards_seen"]) or "none",
                ("  MISSING: " + ", ".join(h["missing"])) if h["missing"] else ""))
    out += ["", report["next"], ""]
    out += ["limit: " + l for l in report["limits"]]
    return "\n".join(out)
