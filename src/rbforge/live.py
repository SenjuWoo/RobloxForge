"""Drive an open Studio place from a shell, through the official Studio MCP (stdio).

Why this exists: an agent that pastes a 900-line script through its own context
into execute_luau burns tokens, mangles whitespace, and cannot prove what landed.
`push` sets each script's Source from the file bytes, reads it back and compares, so
"synced" is a checked fact rather than an assumption. Each CLI command opens its own
Studio MCP session and closes it; `push` reuses one session for all of its files.

Every call names a studio; when exactly one Studio is open it is picked
automatically, otherwise the error lists the ids.
"""
import json
import os
import re
import subprocess
import threading
import zlib

from . import studio as studio_mod
from .errors import ForgeError


def long_string(text):
    """A Luau long-bracket literal that holds `text` exactly."""
    level = 1
    while ("]" + "=" * level + "]") in text:
        level += 1
    eq = "=" * level
    # Luau drops a newline right after the opening bracket, so add one to keep the text exact.
    return "[" + eq + "[\n" + text + "]" + eq + "]"


def adler(text):
    raw = text.encode("utf-8")
    return "%d:%d" % (len(raw), zlib.adler32(raw))


class Session:
    def __init__(self, studio_id=None, timeout=120.0):
        self.timeout = timeout
        self.proc = subprocess.Popen(studio_mod.mcp_command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                                     bufsize=1)
        self.lines, self.next_id = [], 0
        threading.Thread(target=self._read, daemon=True).start()
        self.request("initialize", {"protocolVersion": studio_mod.PROTOCOL_VERSION, "capabilities": {},
                                    "clientInfo": {"name": "rbforge-live", "version": "1"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        self.studio_id = studio_id or self._only_studio()

    def _read(self):
        try:
            for line in self.proc.stdout:
                self.lines.append(line)
        except (OSError, ValueError):
            pass

    def _send(self, msg):
        try:
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise ForgeError("RBF-MCP-002", "Studio MCP pipe closed: %s" % exc,
                             hint="is Studio open with the MCP server enabled? run `rbforge doctor`")

    def request(self, method, params):
        self.next_id += 1
        rid = self.next_id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        msg = studio_mod._await_id(self.lines, rid, self.proc, self.timeout)
        if msg is None:
            raise ForgeError("RBF-MCP-003", "no response to %s within %.0fs" % (method, self.timeout),
                             hint="Studio may be busy (a long execute_luau) or closed; `rbforge doctor`")
        if "error" in msg:
            raise ForgeError("RBF-MCP-004", "%s failed: %s" % (method, json.dumps(msg["error"])))
        return msg.get("result") or {}

    def call_content(self, tool, args):
        """Every MCP content block, unflattened: (blocks, is_error, text).

        `call` concatenates text and drops image blocks, which is why a screenshot could never be
        proven to exist. Callers that need an image use this.
        """
        res = self.request("tools/call", {"name": tool, "arguments": args})
        blocks = [c for c in (res.get("content") or []) if isinstance(c, dict)]
        text = "".join(b.get("text", "") for b in blocks if b.get("type", "text") == "text")
        return blocks, bool(res.get("isError")), text

    def call(self, tool, args):
        res = self.request("tools/call", {"name": tool, "arguments": args})
        text = "".join(c.get("text", "") for c in res.get("content", []) if isinstance(c, dict))
        if res.get("isError"):
            hint = None
            if "not available" in text and "Play" in text:
                hint = "Studio is in Play mode: stop play (start_stop_play is_start=false) for Edit work"
            raise ForgeError("RBF-STUDIO-002", text.strip()[:600] or "tool error", hint=hint)
        return text

    def _only_studio(self):
        studios = studio_mod._parse_studios({"result": self.request(
            "tools/call", {"name": "list_roblox_studios", "arguments": {}})}) or []
        if len(studios) == 1:
            return studios[0].get("id")
        raise ForgeError("RBF-STUDIO-001", "%d Studio instances open; pass --studio" % len(studios),
                         hint="; ".join("%s = %s" % (s.get("id"), s.get("name")) for s in studios) or
                              "open the place in Studio and enable the MCP server")

    def luau(self, code, datamodel="Edit"):
        return self.call("execute_luau", {"code": code, "datamodel_type": datamodel, "studio_id": self.studio_id})

    def close(self):
        studio_mod._terminate(self.proc)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# ------------------------------------------------------------------ rojo mapping

def rojo_targets(project_file):
    """file path (normcase) -> (dotted parent path in the DataModel, instance name, class)."""
    root = os.path.dirname(os.path.abspath(project_file))
    with open(project_file, encoding="utf-8") as fh:
        tree = json.load(fh)["tree"]
    out = {}

    def klass(fname):
        if ".server." in fname:
            return "Script"
        if ".client." in fname:
            return "LocalScript"
        return "ModuleScript"

    def walk(node, path):
        p = node.get("$path")
        if p:
            full = os.path.normpath(os.path.join(root, p))
            if os.path.isdir(full):
                for dirpath, _dirs, files in os.walk(full):
                    rel = os.path.relpath(dirpath, full)
                    sub = [] if rel == "." else rel.replace("\\", "/").split("/")
                    # Rojo turns a directory containing init.* into that script and nests its
                    # children under it; skipping init files silently dropped whole modules.
                    init = _init_file(files)
                    if init:
                        node_path = path + sub
                        out[os.path.normcase(os.path.join(dirpath, init))] = (
                            ".".join(node_path[:-1]), node_path[-1], klass(init))
                    for f in files:
                        if f.endswith((".luau", ".lua")) and not f.startswith("init."):
                            out[os.path.normcase(os.path.join(dirpath, f))] = (
                                ".".join(path + sub), f.split(".")[0], klass(f))
            elif full.endswith((".luau", ".lua")):
                out[os.path.normcase(full)] = (".".join(path[:-1]), path[-1], klass(os.path.basename(full)))
        for k, v in node.items():
            if not k.startswith("$") and isinstance(v, dict):
                walk(v, path + [k])

    walk(tree, [])
    return out


def rojo_parent_classes(project_file):
    """Dotted path -> $className for every node that declares one (game excluded)."""
    root = os.path.dirname(os.path.abspath(project_file))
    with open(project_file, encoding="utf-8") as fh:
        tree = json.load(fh).get("tree") or {}
    classes = {}

    def walk(node, path):
        if not isinstance(node, dict):
            return
        cls = node.get("$className")
        if isinstance(cls, str) and path:
            classes[".".join(path)] = cls
        for key, value in node.items():
            if not key.startswith("$"):
                walk(value, path + [key])

    walk(tree, [])
    return classes


def _project_place_ids(project_file):
    """`servePlaceIds` as ints, or None when the project does not constrain the place.

    Fails closed: a malformed list raises instead of collapsing to "no restriction", because a
    typo in `servePlaceIds` used to silently disable the wrong-place guard. An explicitly empty
    list means "no restriction" and is returned as an empty list.
    """
    try:
        with open(project_file, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if "servePlaceIds" not in data:
        return None
    raw = data["servePlaceIds"]
    if not isinstance(raw, list):
        raise ForgeError("RBF-ARG-002", "servePlaceIds must be a list, found %s"
                         % type(raw).__name__,
                         hint="use e.g. \"servePlaceIds\": [1234] or remove the field")
    out = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, int):
            if isinstance(value, str) and value.strip().isdigit():
                out.append(int(value.strip()))
                continue
            raise ForgeError("RBF-ARG-002",
                             "servePlaceIds contains %r; place ids must be integers" % (value,),
                             hint="remove the entry or use the numeric place id")
        out.append(value)
    return out


def _rel(path, root):
    """Path relative to `root`, falling back to the absolute path across Windows drives."""
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return os.path.abspath(path)


def _init_file(files):
    """The init script Rojo accepts for a directory, in its precedence order, or None."""
    for candidate in ("init.luau", "init.lua", "init.server.luau", "init.server.lua",
                      "init.client.luau", "init.client.lua"):
        if candidate in files:
            return candidate
    return None


def _push_code(parent, name, klass, text, parent_classes=None):
    """Luau that applies one script and reports what actually happened.

    States: SYNCED, HIERARCHY, ROLLED_BACK, ROLLBACK_FAILED, MISMATCH, UNVERIFIED.

    Every string is embedded with `long_string` (JSON escapes are not Luau escapes, and the class
    map used to be pasted as JSON, which is not a table literal). A rollback is only reported as
    ROLLED_BACK after the previous source, or the previous instance, has been read back and
    compared - a successful `pcall` is not proof of restoration.
    """
    classes_json = json.dumps(parent_classes or {}, ensure_ascii=False)
    instantiate = ("Instance.new('%s')" % klass if klass in ("ModuleScript", "Script", "LocalScript")
                   else "Instance.new(%s)" % long_string(klass))
    return (
        "local Http = game:GetService('HttpService')\n"
        + "local parts = string.split(%s, '.')\n" % long_string(parent)
        + "local classes = Http:JSONDecode(%s)\n" % long_string(classes_json)
        + "local function stamp(s) local a,b=1,0 for i=1,#s do a=(a+string.byte(s,i))%%65521 "
        "b=(b+a)%%65521 end return #s..':'..(b*65536+a) end\n"
        "local node = game:GetService(parts[1])\n"
        "for i = 2, #parts do\n"
        "  local key = table.concat(parts, '.', 1, i)\n"
        "  local want = classes[key]\n"
        "  local nxt = node:FindFirstChild(parts[i])\n"
        "  if nxt then\n"
        "    -- Compare every declared class, including Folder: an existing Model must not satisfy a\n"
        "    -- project that declares a Folder, and nothing is converted silently.\n"
        "    if want and nxt.ClassName ~= want then\n"
        "      return 'HIERARCHY ' .. key .. ' is ' .. nxt.ClassName .. ', the project expects ' .. want\n"
        "    end\n"
        "  else\n"
        "    local cls = want or 'Folder'\n"
        "    if cls ~= 'Folder' and cls ~= 'Model' and cls ~= 'Configuration' then\n"
        "      return 'HIERARCHY ' .. key .. ' must be a ' .. cls .. '; create it or fix the project'\n"
        "    end\n"
        "    nxt = Instance.new(cls) nxt.Name = parts[i] nxt.Parent = node\n"
        "  end\n"
        "  node = nxt\n"
        "end\n"
        "local target = node:FindFirstChild(%s)\n" % long_string(name)
        + "local backup, backupName, created = nil, nil, nil\n"
        "if target and target.ClassName ~= %s then\n" % long_string(klass)
        + "  local store = game:GetService('ServerStorage')\n"
        "  local backups = store:FindFirstChild('rbforge_backups')\n"
        "  if not backups then backups = Instance.new('Folder') backups.Name = 'rbforge_backups' backups.Parent = store end\n"
        "  backup, backupName = target, target.Name\n"
        "  target.Name = backupName .. '_rbforge_' .. tostring(os.time() * 1000)\n"
        "  target.Parent = backups\n"
        "  target = nil\n"
        "end\n"
        "if not target then target = %s target.Name = %s target.Parent = node created = target end\n"
        % (instantiate, long_string(name))
        + "local okPrev, prev = pcall(function() return target.Source end)\n"
        "if not okPrev or type(prev) ~= 'string' then prev = nil end\n"
        "local function restore(reason)\n"
        "  -- A class change also creates a stand-in, so the backup must win: put the original\n"
        "  -- back first, then remove whatever temporary instance this push made.\n"
        "  if backup then\n"
        "    if created then pcall(function() created:Destroy() end) end\n"
        "    local moved = pcall(function() backup.Name = backupName backup.Parent = node end)\n"
        "    if moved and backup.Parent == node and backup.Name == backupName then\n"
        "      return 'ROLLED_BACK ' .. reason .. ' (original restored)'\n"
        "    end\n"
        "    return 'ROLLBACK_FAILED ' .. reason .. ' (original kept in ServerStorage.rbforge_backups)'\n"
        "  end\n"
        "  if created then\n"
        "    pcall(function() created:Destroy() end)\n"
        "    if created.Parent == nil then return 'ROLLED_BACK ' .. reason .. ' (new script removed)' end\n"
        "    return 'ROLLBACK_FAILED ' .. reason .. ' (new script could not be removed)'\n"
        "  end\n"
        "  if prev ~= nil then\n"
        "    local set = pcall(function() target.Source = prev end)\n"
        "    local same = set and target.Source == prev\n"
        "    if same then return 'ROLLED_BACK ' .. reason end\n"
        "    return 'ROLLBACK_FAILED ' .. reason .. ' (previous source could not be restored)'\n"
        "  end\n"
        "  return 'ROLLBACK_FAILED ' .. reason .. ' (nothing to restore)'\n"
        "end\n"
        "local src = %s\n" % long_string(text)
        + "local wrote = pcall(function() target.Source = src end)\n"
        "if not wrote then return restore('write failed') end\n"
        "local ok, got = pcall(function() return target.Source end)\n"
        "if not ok or type(got) ~= 'string' then return restore('source unreadable') end\n"
        "if got ~= src then return restore('readback mismatch ' .. stamp(got)) end\n"
        "return 'SYNCED ' .. stamp(got)"
    )


def push(paths, project_file="default.project.json", studio_id=None):
    """Set each mapped script's Source from disk and verify it inside Studio."""
    if not os.path.isfile(project_file):
        raise ForgeError("RBF-ARG-001", "no Rojo project file at %s" % project_file,
                         hint="run from the project root or pass --project")
    targets = rojo_targets(project_file)
    project_root = os.path.dirname(os.path.abspath(project_file))
    parent_classes = rojo_parent_classes(project_file)
    files = list(targets) if paths == ["ALL"] else [os.path.normcase(os.path.abspath(p)) for p in paths]
    allowed_places = _project_place_ids(project_file)
    results = []
    with Session(studio_id) as s:
        if allowed_places:
            # Wrong-place protection runs before any source is touched.
            try:
                place_id = int((s.luau("return tostring(game.PlaceId)") or "0").strip() or 0)
            except (TypeError, ValueError):
                place_id = 0
            if place_id not in allowed_places:
                raise ForgeError(
                    "RBF-STUDIO-003",
                    "Studio is on place %s but the project serves %s"
                    % (place_id or "unknown", ", ".join(str(i) for i in allowed_places)),
                    hint="open the intended place, or remove servePlaceIds from the project")
        for f in files:
            if f not in targets:
                # Every result carries the same keys: an unmapped path used to produce a row without
                # "state", and the aggregation below then raised KeyError on a mixed batch.
                results.append({"file": _rel(f, project_root), "target": None,
                                "state": "unmapped", "ok": False, "got": None, "want": None,
                                "why": "not mapped by %s" % project_file})
                continue
            parent, name, klass = targets[f]
            try:
                with open(f, encoding="utf-8") as fh:
                    text = fh.read().replace("\r\n", "\n")
            except OSError as exc:
                results.append({"file": _rel(f, project_root), "target": None,
                                "state": "unreadable", "ok": False, "got": None, "want": None,
                                "why": str(exc)})
                continue
            want = adler(text)
            got = s.luau(_push_code(parent, name, klass, text, parent_classes)).strip()
            state = ("synced" if got.startswith("SYNCED") and got.endswith(want) else
                     "mismatch" if got.startswith("MISMATCH") else
                     "hierarchy" if got.startswith("HIERARCHY") else
                     "rolled_back" if got.startswith("ROLLED_BACK") else
                     "rollback_failed" if got.startswith("ROLLBACK_FAILED") else "unverified")
            results.append({"file": _rel(f, project_root), "target": "%s.%s" % (parent, name),
                            "state": state, "ok": state == "synced", "got": got, "want": want,
                            "why": got if state == "hierarchy" else None})
    synced = [r for r in results if r["state"] == "synced"]
    return {"pushed": len(synced), "failed": len(results) - len(synced),
            "mismatched": [r for r in results if r["state"] == "mismatch"],
            "unverified": [r for r in results if r["state"] == "unverified"],
            "unmapped": [r for r in results if r["state"] == "unmapped"],
            "unreadable": [r for r in results if r["state"] == "unreadable"],
            "hierarchy": [r for r in results if r["state"] == "hierarchy"],
            "rolled_back": [r for r in results if r["state"] == "rolled_back"],
            "rollback_failed": [r for r in results if r["state"] == "rollback_failed"],
            "results": results,
            "note": "Edit-mode sources changed; stop/start Play to run them, and the owner saves the place"}


def run_file(path, datamodel="Edit", studio_id=None):
    with open(path, encoding="utf-8") as fh:
        code = fh.read()
    with Session(studio_id) as s:
        return s.luau(code, datamodel)


def run_probe(name, overrides=None, datamodel=None, studio_id=None):
    from . import probes
    r = probes.render(name, overrides)
    dm = datamodel or (r["datamodel"] if r["datamodel"] != "any" else "Edit")
    with Session(studio_id) as s:
        return {"probe": name, "datamodel": dm, "output": s.luau(r["code"], dm)}


def server_test(path, attr, timeout=120, studio_id=None):
    """Run a test file as a temporary server Script in a running Play session, so it shares the game's module
    cache (execute_luau has its own). The test must set workspace:SetAttribute(attr, "PASS ..." | "FAIL ...")."""
    with open(path, encoding="utf-8") as fh:
        src = fh.read().replace("\r\n", "\n")
    code = (
        "workspace:SetAttribute(%s, nil)\n" % json.dumps(attr)
        + "local s = Instance.new('Script')\n"
        "s.Name = 'RbforgeServerTest'\n"
        "s.Source = %s\n" % long_string(src)
        + "s.Parent = game:GetService('ServerScriptService')\n"
        "local t0 = os.clock()\n"
        "while workspace:GetAttribute(%s) == nil and os.clock() - t0 < %d do task.wait(0.5) end\n" % (json.dumps(attr), timeout)
        + "s:Destroy()\n"
        "return tostring(workspace:GetAttribute(%s) or 'TIMEOUT')\n" % json.dumps(attr)
    )
    with Session(studio_id, timeout=timeout + 30) as s:
        out = s.luau(code, "Server")
    # The test writes "PASS ..." or "FAIL ..."; a substring test let NOT_PASS through as a pass.
    first = next((line.strip() for line in (out or "").splitlines() if line.strip()), "")
    outcome = "pass" if re.match(r"^PASS\b", first) else (
        "fail" if re.match(r"^(FAIL|NOT_PASS|TIMEOUT)\b", first) else "unknown")
    return {"test": path, "result": first, "outcome": outcome, "passed": outcome == "pass"}

