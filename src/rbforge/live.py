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
    """Luau that writes one script and reports SYNCED / MISMATCH / HIERARCHY / UNVERIFIED."""
    return (
        "local parts = string.split(%s, '.')\n" % json.dumps(parent)
        + "local classes = %s\n" % json.dumps(parent_classes or {})
        + "local node = game:GetService(parts[1])\n"
        "for i = 2, #parts do\n"
        "  local nxt = node:FindFirstChild(parts[i])\n"
        "  if not nxt then\n"
        "    local want = classes[table.concat(parts, '.', 1, i)] or 'Folder'\n"
        "    -- Only containers can be created to hold a script; anything else means the project\n"
        "    -- declares a hierarchy we cannot rebuild safely, so say so instead of guessing.\n"
        "    if want ~= 'Folder' and want ~= 'Model' and want ~= 'Configuration' then\n"
        "      return 'HIERARCHY ' .. table.concat(parts, '.', 1, i) .. ' must be a ' .. want\n"
        "    end\n"
        "    nxt = Instance.new(want) nxt.Name = parts[i] nxt.Parent = node\n"
        "  end\n"
        "  node = nxt\n"
        "end\n"
        "local inst = node:FindFirstChild(%s)\n" % json.dumps(name)
        # A class change used to destroy the old script outright. Move it to a backup folder instead, so the
        # previous body stays recoverable and nothing is silently lost.
        + "if inst and inst.ClassName ~= %s then\n" % json.dumps(klass)
        + "  local store = game:GetService('ServerStorage')\n"
        "  local backups = store:FindFirstChild('rbforge_backups')\n"
        "  if not backups then backups = Instance.new('Folder') backups.Name = 'rbforge_backups' backups.Parent = store end\n"
        "  inst.Name = inst.Name .. '_backup_' .. tostring(os.time())\n"
        "  inst.Parent = backups\n"
        "  inst = nil\n"
        "end\n"
        + "if not inst then inst = Instance.new(%s) inst.Name = %s inst.Parent = node end\n" % (json.dumps(klass), json.dumps(name))
        + "local src = %s\n" % long_string(text)
        + "inst.Source = src\n"
        "-- Read back what Studio actually stored: hashing the string we just sent proves nothing.\n"
        "local ok, got = pcall(function() return inst.Source end)\n"
        "if not ok or type(got) ~= 'string' then return 'UNVERIFIED' end\n"
        "local a, b = 1, 0\n"
        "for i = 1, #got do a = (a + string.byte(got, i)) % 65521 b = (b + a) % 65521 end\n"
        "local stamp = #got .. ':' .. (b * 65536 + a)\n"
        "if got == src then return 'SYNCED ' .. stamp end\n"
        "return 'MISMATCH ' .. stamp"
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
    results = []
    with Session(studio_id) as s:
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
                     "hierarchy" if got.startswith("HIERARCHY") else "unverified")
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

