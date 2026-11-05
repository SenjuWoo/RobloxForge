"""Drive an open Studio place from a shell, through the official Studio MCP (stdio).

Why this exists: an agent that pastes a 900-line script through its own context
into execute_luau burns tokens, mangles whitespace, and cannot prove what landed.
`push` sets each script's Source from the file bytes and has Studio return an
Adler-32 of what it now holds, so "synced" is a checked fact. `exec`, `probe
--run` and `servertest` reuse the same session.

Every call names a studio; when exactly one Studio is open it is picked
automatically, otherwise the error lists the ids.
"""
import json
import os
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


def _push_code(parent, name, klass, text):
    return (
        "local parts = string.split(%s, '.')\n" % json.dumps(parent)
        + "local node = game:GetService(parts[1])\n"
        "for i = 2, #parts do\n"
        "  local nxt = node:FindFirstChild(parts[i])\n"
        "  if not nxt then nxt = Instance.new('Folder') nxt.Name = parts[i] nxt.Parent = node end\n"
        "  node = nxt\n"
        "end\n"
        "local inst = node:FindFirstChild(%s)\n" % json.dumps(name)
        + "if inst and inst.ClassName ~= %s then inst:Destroy() inst = nil end\n" % json.dumps(klass)
        + "if not inst then inst = Instance.new(%s) inst.Name = %s inst.Parent = node end\n" % (json.dumps(klass), json.dumps(name))
        + "local src = %s\n" % long_string(text)
        + "inst.Source = src\n"
        "local a, b = 1, 0\n"
        "for i = 1, #src do a = (a + string.byte(src, i)) % 65521 b = (b + a) % 65521 end\n"
        "return #src .. ':' .. (b * 65536 + a)\n"
    )


def push(paths, project_file="default.project.json", studio_id=None):
    """Set each mapped script's Source from disk and verify it inside Studio."""
    if not os.path.isfile(project_file):
        raise ForgeError("RBF-ARG-001", "no Rojo project file at %s" % project_file,
                         hint="run from the project root or pass --project")
    targets = rojo_targets(project_file)
    files = list(targets) if paths == ["ALL"] else [os.path.normcase(os.path.abspath(p)) for p in paths]
    results = []
    with Session(studio_id) as s:
        for f in files:
            if f not in targets:
                results.append({"file": f, "ok": False, "why": "not mapped by %s" % project_file})
                continue
            parent, name, klass = targets[f]
            with open(f, encoding="utf-8") as fh:
                text = fh.read().replace("\r\n", "\n")
            want = adler(text)
            got = s.luau(_push_code(parent, name, klass, text)).strip()
            results.append({"file": os.path.relpath(f), "target": "%s.%s" % (parent, name),
                            "ok": got.endswith(want), "got": got, "want": want})
    return {"pushed": sum(r["ok"] for r in results), "failed": sum(not r["ok"] for r in results),
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
    return {"test": path, "result": out, "passed": "PASS" in out and "FAIL" not in out and "TIMEOUT" not in out}

