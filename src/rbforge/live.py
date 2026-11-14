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
import time
import zlib

from . import luau_text
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
        try:
            self.request("initialize", {"protocolVersion": studio_mod.PROTOCOL_VERSION, "capabilities": {},
                                        "clientInfo": {"name": "rbforge-live", "version": "1"}})
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
            self.studio_id = studio_id or self._only_studio()
        except BaseException:
            # The constructor failed, so `with` never reaches __exit__: without this, every
            # "two Studios open, pass --studio" answer left a StudioMCP process running.
            self.close()
            raise

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

def rojo_targets(project_file, spellings=None):
    """file path (normcase) -> (dotted parent path in the DataModel, instance name, class).

    `spellings`, when given, is filled with normcase path -> the path as spelled on disk, so reports
    can name `src/Shop.luau` instead of the lowercased key.
    """
    root = os.path.dirname(os.path.abspath(project_file))
    try:
        with open(project_file, encoding="utf-8") as fh:
            tree = json.load(fh).get("tree")
    except (OSError, ValueError, AttributeError) as exc:
        raise ForgeError("RBF-ARG-002", "cannot read Rojo project %s: %s" % (project_file, exc),
                         hint="run `rbforge check` on the project; it names the malformed field")
    if not isinstance(tree, dict) or not tree:
        raise ForgeError("RBF-ARG-002", "Rojo project %s has no 'tree' object" % project_file,
                         hint="Rojo needs a non-empty tree; `rbforge check` validates the project")
    out = {}

    def put(path, value):
        out[os.path.normcase(path)] = value
        if spellings is not None:
            spellings[os.path.normcase(path)] = path

    def klass(fname):
        if ".server." in fname:
            return "Script"
        if ".client." in fname:
            return "LocalScript"
        return "ModuleScript"

    def walk(node, path):
        p = node.get("$path")
        if isinstance(p, str) and p and path:
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
                        put(os.path.join(dirpath, init),
                            (".".join(node_path[:-1]), node_path[-1], klass(init)))
                    for f in files:
                        if f.endswith((".luau", ".lua")) and not f.startswith("init."):
                            put(os.path.join(dirpath, f),
                                (".".join(path + sub), script_name(f), klass(f)))
            elif full.endswith((".luau", ".lua")):
                put(full, (".".join(path[:-1]), path[-1], klass(os.path.basename(full))))
        for k, v in node.items():
            if not k.startswith("$") and isinstance(v, dict):
                walk(v, path + [k])

    walk(tree, [])
    return out


_SCRIPT_SUFFIXES = (".server.luau", ".server.lua", ".client.luau", ".client.lua", ".luau", ".lua")


def script_name(filename):
    """The instance name Rojo gives a script file: the name minus its script suffix only.

    `Foo.spec.luau` is the ModuleScript `Foo.spec`, not `Foo` - cutting at the first dot pushed a spec
    file into its own module and made the two overwrite each other.
    """
    low = filename.lower()
    for suffix in _SCRIPT_SUFFIXES:
        if low.endswith(suffix):
            return filename[:-len(suffix)]
    return filename


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


def _push_code(parent, name, klass, text, parent_classes=None, expects=None, force=False):
    """Luau that applies one script and reports what actually happened.

    States: SYNCED, HIERARCHY, CONFLICT, BACKUP_FAILED, ROLLED_BACK, ROLLBACK_FAILED, MISMATCH,
    UNVERIFIED.

    Every string is embedded with `long_string` (JSON escapes are not Luau escapes, and the class
    map used to be pasted as JSON, which is not a table literal). A rollback is only reported as
    ROLLED_BACK after the previous source, or the previous instance, has been read back and
    compared - a successful `pcall` is not proof of restoration.

    `expects` maps a place key to the stamp this tool last wrote there. Studio picks its own key, so
    the guard needs no extra round trip: when the script's current Source is neither that stamp nor
    the new text, someone edited it in Studio since the last push and the write is refused
    (CONFLICT) unless `force`. Any overwrite of a Source this tool did not write - a first push, or a
    forced one - clones the Studio copy into ServerStorage.rbforge_backups before writing.
    """
    classes_json = json.dumps(parent_classes or {}, ensure_ascii=False)
    expects_json = json.dumps(expects or {}, ensure_ascii=False)
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
        "local src = %s\n" % long_string(text)
        + "local placeKey = game.PlaceId ~= 0 and tostring(game.PlaceId) or ('0:' .. game.Name)\n"
        "local expect = Http:JSONDecode(%s)[placeKey] or ''\n" % long_string(expects_json)
        + "local force = %s\n" % ("true" if force else "false")
        + "local copied = nil\n"
        "if prev ~= nil and not created and prev ~= src then\n"
        "  local prevStamp = stamp(prev)\n"
        "  local ours = expect ~= '' and prevStamp == expect\n"
        "  if expect ~= '' and not ours and not force then\n"
        "    return 'CONFLICT ' .. prevStamp .. ' ' .. Http:JSONEncode({place = placeKey, expect = expect})\n"
        "  end\n"
        "  if not ours then\n"
        "    -- Not a Source this tool wrote: keep the Studio copy before replacing it.\n"
        "    local store = game:GetService('ServerStorage')\n"
        "    local backups = store:FindFirstChild('rbforge_backups')\n"
        "    if not backups then backups = Instance.new('Folder') backups.Name = 'rbforge_backups' backups.Parent = store end\n"
        "    local okc, copy = pcall(function() return target:Clone() end)\n"
        "    if not okc or not copy then return 'BACKUP_FAILED ' .. prevStamp end\n"
        "    copy.Name = target.Name .. '_rbforge_' .. tostring(os.time() * 1000)\n"
        "    copy.Parent = backups\n"
        "    copied = copy.Name\n"
        "  end\n"
        "end\n"
        "local function restore(reason)\n"
        "  -- A class change also creates a stand-in, so the backup must win: put the original\n"
        "  -- back first, then remove whatever temporary instance this push made.\n"
        "  if backup then\n"
        "    local removed = true\n"
        "    if created then\n"
        "      pcall(function() created:Destroy() end)\n"
        "      removed = created.Parent == nil\n"
        "    end\n"
        "    local moved = pcall(function() backup.Name = backupName backup.Parent = node end)\n"
        "    if moved and backup.Parent == node and backup.Name == backupName and removed then\n"
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
        "    local okRead, now = pcall(function() return target.Source end)\n"
        "    if set and okRead and now == prev then return 'ROLLED_BACK ' .. reason end\n"
        "    return 'ROLLBACK_FAILED ' .. reason .. ' (previous source could not be restored)'\n"
        "  end\n"
        "  return 'ROLLBACK_FAILED ' .. reason .. ' (nothing to restore)'\n"
        "end\n"
        "local wrote = pcall(function() target.Source = src end)\n"
        "if not wrote then return restore('write failed') end\n"
        "local ok, got = pcall(function() return target.Source end)\n"
        "if not ok or type(got) ~= 'string' then return restore('source unreadable') end\n"
        "if got ~= src then return restore('readback mismatch ' .. stamp(got)) end\n"
        "return 'SYNCED ' .. stamp(got) .. ' ' .. Http:JSONEncode({place = placeKey, backup = copied})"
    )


# ------------------------------------------------------------------ push ledger
#
# What push last wrote, per project, place and target. It is the "read" half of a read-then-write
# guard: a Studio copy whose stamp is neither the ledger's nor the new file's was edited in Studio.

def _ledger_path():
    from . import paths as paths_mod
    return os.path.join(paths_mod.home(), "push-ledger.json")


def _ledger_load():
    try:
        with open(_ledger_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {"version": 1, "projects": {}}
    if not isinstance(data, dict) or not isinstance(data.get("projects"), dict):
        return {"version": 1, "projects": {}}
    return data


def _ledger_expects(ledger, project_key, target):
    """{place key: stamp} this tool last wrote for `target`, across every place it has seen."""
    places = ledger["projects"].get(project_key)
    out = {}
    if isinstance(places, dict):
        for place, entries in places.items():
            entry = entries.get(target) if isinstance(entries, dict) else None
            if isinstance(entry, dict) and isinstance(entry.get("stamp"), str):
                out[place] = entry["stamp"]
    return out


def _ledger_save(project_key, updates):
    """Merge `updates` [(place, target, stamp, file)] under the lock; never loses other projects."""
    if not updates:
        return
    from .verification import _FileLock, _write_json
    path = _ledger_path()
    with _FileLock(path + ".lock"):
        ledger = _ledger_load()
        places = ledger["projects"].setdefault(project_key, {})
        if not isinstance(places, dict):
            places = ledger["projects"][project_key] = {}
        for place, target, stamp, file in updates:
            if not isinstance(places.get(place), dict):
                places[place] = {}
            places[place][target] = {
                "stamp": stamp, "file": file, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        _write_json(path, ledger)


def _parse_reply(got):
    """(word, stamp, meta) from 'WORD <stamp> {json}'; meta is {} when absent or unreadable."""
    word, _, rest = got.partition(" ")
    stamp, _, tail = rest.partition(" ")
    meta = {}
    if tail.strip().startswith("{"):
        try:
            meta = json.loads(tail)
        except ValueError:
            meta = {}
    return word, stamp, meta if isinstance(meta, dict) else {}


def push(paths, project_file="default.project.json", studio_id=None, force=False):
    """Set each mapped script's Source from disk and verify it inside Studio.

    A script edited in Studio since this tool last pushed it is refused (`conflict`) unless
    `force`; any overwrite of a Source this tool did not write is backed up first.
    """
    if not os.path.isfile(project_file):
        raise ForgeError("RBF-ARG-001", "no Rojo project file at %s" % project_file,
                         hint="run from the project root or pass --project")
    spelled = {}
    targets = rojo_targets(project_file, spelled)
    project_root = os.path.dirname(os.path.abspath(project_file))
    project_key = os.path.normcase(os.path.abspath(project_file))
    parent_classes = rojo_parent_classes(project_file)
    if paths == ["ALL"]:
        files = list(targets)
    else:
        files = []
        for p in paths:
            key = os.path.normcase(os.path.abspath(p))
            spelled.setdefault(key, os.path.abspath(p))
            files.append(key)

    def show(f):
        # Keys are normcased for matching; reports use the on-disk spelling.
        return _rel(spelled.get(f, f), project_root)

    allowed_places = _project_place_ids(project_file)
    ledger = _ledger_load()
    updates = []
    results = []
    try:
        stop_reason = _push_files(studio_id, allowed_places, files, targets, show,
                                  project_file, parent_classes, ledger, project_key, force,
                                  results, updates)
    finally:
        # Persist what landed even when a later file raised (Studio entered Play, pipe closed).
        _ledger_save(project_key, updates)
    if stop_reason:
        attempted = {r["file"] for r in results}
        for f in files:
            name = show(f)
            if name not in attempted:
                results.append({"file": name, "target": None, "state": "not_attempted",
                                "ok": False, "got": None, "want": None, "why": stop_reason})
    synced = [r for r in results if r["state"] == "synced"]
    out = {"pushed": len(synced), "failed": len(results) - len(synced)}
    for key, state in (("mismatched", "mismatch"), ("unverified", "unverified"),
                       ("unmapped", "unmapped"), ("unreadable", "unreadable"),
                       ("hierarchy", "hierarchy"), ("conflicts", "conflict"),
                       ("backup_failed", "backup_failed"), ("rolled_back", "rolled_back"),
                       ("rollback_failed", "rollback_failed"), ("not_attempted", "not_attempted")):
        out[key] = [r for r in results if r["state"] == state]
    out["backed_up"] = [{"file": r["file"], "backup": "ServerStorage.rbforge_backups." + r["backup"]}
                        for r in results if r.get("backup")]
    out["results"] = results
    out["note"] = "Edit-mode sources changed; stop/start Play to run them, and the owner saves the place"
    if out["conflicts"]:
        out["conflict_hint"] = ("these scripts were edited in Studio after the last push: copy the "
                                "Studio change into the file, or push again with --force (the Studio "
                                "copy is cloned into ServerStorage.rbforge_backups first)")
    return out


def _push_files(studio_id, allowed_places, files, targets, show, project_file,
                parent_classes, ledger, project_key, force, results, updates):
    """The Studio half of `push`; fills `results` and `updates`, returns a stop reason or None."""
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
                results.append({"file": show(f), "target": None,
                                "state": "unmapped", "ok": False, "got": None, "want": None,
                                "why": "not mapped by %s" % project_file})
                continue
            parent, name, klass = targets[f]
            try:
                with open(f, encoding="utf-8") as fh:
                    text = fh.read().replace("\r\n", "\n")
            except (OSError, UnicodeDecodeError) as exc:
                results.append({"file": show(f), "target": None,
                                "state": "unreadable", "ok": False, "got": None, "want": None,
                                "why": str(exc)})
                continue
            want = adler(text)
            target = "%s.%s" % (parent, name)
            expects = _ledger_expects(ledger, project_key, target)
            got = s.luau(_push_code(parent, name, klass, text, parent_classes,
                                    expects=expects, force=force)).strip()
            word, stamp, meta = _parse_reply(got)
            # The stamp is compared as a whole token: `endswith` let "SYNCED 13:123" match "3:123".
            state = ("synced" if word == "SYNCED" and stamp == want else
                     "mismatch" if word == "MISMATCH" else
                     "hierarchy" if word == "HIERARCHY" else
                     "conflict" if word == "CONFLICT" else
                     "backup_failed" if word == "BACKUP_FAILED" else
                     "rolled_back" if word == "ROLLED_BACK" else
                     "rollback_failed" if word == "ROLLBACK_FAILED" else "unverified")
            row = {"file": show(f), "target": target,
                   "state": state, "ok": state == "synced", "got": got, "want": want,
                   "why": got if state in ("hierarchy", "rollback_failed", "backup_failed") else None}
            if state == "conflict":
                row["why"] = ("Studio copy (%s) differs from the last push (%s) and from the file; "
                              "it was edited in Studio" % (stamp, meta.get("expect") or "?"))
            if meta.get("backup"):
                row["backup"] = str(meta["backup"])
            results.append(row)
            if state == "synced" and isinstance(meta.get("place"), str):
                updates.append((meta["place"], target, want, row["file"]))
            if state == "rollback_failed":
                # The place may be damaged or hold an orphaned original: stop writing and say which
                # files were never attempted instead of compounding the failure.
                return ("%s left unrecovered; check ServerStorage.rbforge_backups before "
                        "pushing again" % show(f))
    return None


def _read_source(path, what):
    """File text, or a structured error instead of a traceback for a missing or unreadable file."""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise ForgeError("RBF-ARG-001", "cannot read %s %s: %s" % (what, path, exc),
                         hint="pass the path of an existing UTF-8 .luau file")


def run_file(path, datamodel="Edit", studio_id=None):
    code = _read_source(path, "Luau file")
    with Session(studio_id) as s:
        return s.luau(code, datamodel)


def run_probe(name, overrides=None, datamodel=None, studio_id=None):
    from . import probes
    r = probes.render(name, overrides)
    dm = datamodel or (r["datamodel"] if r["datamodel"] != "any" else "Edit")
    with Session(studio_id) as s:
        return {"probe": name, "datamodel": dm, "output": s.luau(r["code"], dm)}


def _lua_code_only(src):
    """Executable text only: comments and string literals removed (see `luau_text.code_only`)."""
    return luau_text.code_only(src)


def server_test(path, attr, timeout=120, studio_id=None):
    """Run a test file as a temporary server Script in a running Play session, so it shares the game's module
    cache (execute_luau has its own). The test must set workspace:SetAttribute(attr, "PASS ..." | "FAIL ...")."""
    src = _read_source(path, "test file").replace("\r\n", "\n")
    # A test that never writes the attribute cannot report: the runner would sit for the full timeout
    # and call it TIMEOUT, which hides the real mistake. Only executable text counts - a mention in a
    # comment or a string is not a report - and a dynamically built attribute name is fine, because
    # the decision is "does this file call SetAttribute at all", not "does it contain this literal".
    if "SetAttribute" not in _lua_code_only(src):
        return {
            "test": path,
            "result": "INVALID: the test never calls SetAttribute for workspace:%s" % attr,
            "outcome": "fail",
            "passed": False,
            "reason": "a test that cannot report cannot pass; end it with "
                      'workspace:SetAttribute("%s", "PASS ...") or "FAIL ..."' % attr,
        }
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

