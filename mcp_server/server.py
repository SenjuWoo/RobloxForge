"""RobloxForge - MCP server (dependency-free).

Speaks the MCP stdio wire protocol directly (newline-delimited JSON-RPC
2.0): initialize / tools/list / tools/call / ping. Works with any MCP
client:

    "robloxforge": {
        "command": "python",
        "args": ["<forge>\\mcp_server\\server.py"]
    }

SMALL ON PURPOSE. The official Roblox Studio MCP owns the live engine.
This server owns intelligence: doctor, capabilities, current docs, project
analysis, reviews, verification. Every tool wraps the SAME core the CLI
uses; results are JSON text.

Register it alongside (not instead of) the official Roblox_Studio server:
    hermes mcp add robloxforge --command python --args <path>\\server.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from rbforge.errors import ForgeError

from rbforge import __version__ as _forge_version

# Newest first. The server answers with the client's version when it is one of these, otherwise
# with the newest, and the client decides whether to continue (MCP lifecycle negotiation). Every
# version here shares what this server uses: tools/list, tools/call and text content.
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
PROTOCOL_VERSION = SUPPORTED_PROTOCOLS[-1]  # what older callers and tests were written against

SERVER_INFO = {"name": "robloxforge", "version": _forge_version}

# Sent once at initialize (2025-03-26+), so tool descriptions do not each repeat the workflow.
INSTRUCTIONS = (
    "RobloxForge plans, checks and verifies Roblox work; the official Roblox Studio MCP owns the live "
    "place. Start with rb_doctor and rb_capabilities. Run rb_check after every edit batch and before a "
    "playtest. A claim of 'working' needs rb_collect_evidence then rb_verify_receipt with its "
    "observation_id. Prefer rb_studio_push over pasting large scripts into execute_luau.")

TOOLS = {}

# Behaviour hints for clients that auto-approve or label tools (MCP tool annotations).
READ_ONLY = {"readOnlyHint": True, "openWorldHint": False}
LOCAL_WRITE = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}


def tool(name, schema, desc, annotations=None):
    def deco(fn):
        TOOLS[name] = (fn, schema, desc, annotations or READ_ONLY)
        return fn
    return deco


# ------------------------------------------------------------------ state

@tool("rb_doctor", {"type": "object", "properties": {
    "probe": {"type": "boolean", "default": True},
    "host_vision": {"type": "boolean",
                    "description": "true if you (the calling model) can inspect images"}},
      }, "Full health report: Studio, official MCP handshake, docs cache, "
         "toolchain, agent integrations. Run this FIRST in any session.")
def _doctor(a):
    from rbforge import doctor
    return doctor.collect(probe=a.get("probe", True),
                          host_vision=a.get("host_vision"))


@tool("rb_capabilities", {"type": "object", "properties": {
    "host_vision": {"type": "boolean",
                    "description": "true if you (the calling model) can inspect images"}}},
      "Honest capability matrix derived from live probes. Never assume a "
      "status; ask this before attempting anything.")
def _capabilities(a):
    from rbforge import capabilities
    return capabilities.compute(host_vision=a.get("host_vision"))


@tool("rb_docs_search", {"type": "object", "properties": {
    "query": {"type": "string"}, "limit": {"type": "integer", "default": 8}},
      "required": ["query"]},
      "Search CURRENT official Roblox creator-docs. Exact API names win: "
      "'TweenService:Create', 'ProcessReceipt', 'StreamingEnabled'.")
def _docs_search(a):
    from rbforge import docs
    return docs.search(a["query"], limit=int(a.get("limit", 8)))


@tool("rb_docs_read", {"type": "object", "properties": {
    "path": {"type": "string"}, "max_chars": {"type": "integer", "default": 8000},
    "around": {"type": "string"}}, "required": ["path"]},
      "Read one cached doc page (bounded). Use a path from rb_docs_search.")
def _docs_read(a):
    from rbforge import docs
    return docs.read(a["path"], max_chars=int(a.get("max_chars", 8000)),
                     around=a.get("around"))


@tool("rb_docs_update", {"type": "object", "properties": {}},
      "Refresh the creator-docs cache via git. Offline failure keeps the "
      "cached copy and reports honestly.",
      {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def _docs_update(a):
    from rbforge import docs
    return docs.ensure(refresh=True)


@tool("rb_project_analyze", {"type": "object", "properties": {
    "path": {"type": "string", "description": "filesystem project root; omit to auto-detect cwd"}},
      },
      "Analyze an existing filesystem project (Rojo or script-tree style): "
      "style, scripts, client/server split, remotes, DataStores, hazards.")
def _project_analyze(a):
    from rbforge import project
    root = a.get("path") or os.getcwd()
    return project.analyze(root)


@tool("rb_vertical_slice_plan", {"type": "object", "properties": {
    "genre": {"type": "string", "enum": ["generic", "obby", "simulator", "tycoon"]},
    "premise": {"type": "string"}}, "required": ["genre", "premise"]},
      "Turn a premise into the smallest playable vertical slice plan with "
      "authority boundaries and verification steps. Use BEFORE building.")
def _slice_plan(a):
    from rbforge import planning
    return planning.vertical_slice(a["genre"], a["premise"])


@tool("rb_architecture_review", {"type": "object", "properties": {
    "path": {"type": "string"},
    "live": {"type": "boolean", "default": False,
             "description": "review the live Studio place instead of files"}},
      },
      "Static architecture review of Luau sources: ownership violations, "
      "monoliths, placement problems. Static heuristics, not a runtime proof.")
def _arch_review(a):
    from rbforge import review
    return review.architecture(path=a.get("path"), live=a.get("live", False))


@tool("rb_security_review", {"type": "object", "properties": {
    "path": {"type": "string"},
    "live": {"type": "boolean", "default": False}},
      },
      "Security review: client-authority patterns, unvalidated remotes, "
      "client-owned currency/damage/teleport. RemoteEvent != authorization.")
def _sec_review(a):
    from rbforge import review
    return review.security(path=a.get("path"), live=a.get("live", False))


@tool("rb_collect_evidence", {"type": "object", "properties": {
    "studio_id": {"type": "string"},
    "project": {"type": "string", "description": "project identity this evidence belongs to"},
    "scenario": {"type": "string", "description": "test/scenario identifier; receipts must match it"},
    "revision": {"type": "string", "description": "source revision or snapshot id, for the record"},
    "test_path": {"type": "string", "description": "test file to run as a server Script in Play"},
    "test_attr": {"type": "string", "default": "RbforgeTest"},
    "capture_screenshot": {"type": "boolean", "default": True,
                           "description": "ask Studio for an image; only returned image bytes count"},
    "screenshots_inspected": {"type": "boolean", "default": False,
                              "description": "attestation that the captured image was looked at"},
    "untested": {"type": ["string", "array"], "items": {"type": "string"}}}},
      "Ask Studio for the observations a receipt needs and record them. Returns an opaque "
      "observation_id; only ids this tool recorded can produce a verified_playtest receipt.",
      LOCAL_WRITE)
def _collect_evidence(a):
    from rbforge import verification
    args = dict(a)
    # The schema advertises capture_screenshot=true; the Python default is False, so the default has
    # to be applied here or the advertised behaviour silently does nothing.
    args.setdefault("capture_screenshot", True)
    result = verification.collect_evidence(**args)
    shots = result.get("screenshots") or []
    result["capture"] = {
        "requested": bool(args.get("capture_screenshot")),
        "images": len(shots),
        "status": "captured" if shots else ("failed" if args.get("capture_screenshot") else "disabled"),
    }
    return result


@tool("rb_verify_receipt", {"type": "object", "properties": {
    "task": {"type": "string"},
    "checks": {"type": "array", "items": {"type": "string"},
               "description": "the agent's claims; recorded, never treated as evidence"},
    "observation_id": {"type": "string", "description":
                       "id returned by rb_collect_evidence; the only thing that can verify"},
    "evidence": {"type": "object", "description":
                 "extra context; recorded as the caller's word and can never verify"},
    "provenance": {"type": "string", "enum": ["tool", "agent"], "default": "agent",
                   "description": "ignored for trust - only observation_id verifies"},
    "project": {"type": "string", "description": "must match the observation's project"},
    "scenario": {"type": "string", "description":
                 "must match the observation's scenario; leaving it out does NOT match a scenario-bound "
                 "observation"},
    "revision": {"type": "string", "description":
                 "must match the observation's revision when one was recorded"},
    "studio_id": {"type": "string", "description": "must match the observing Studio"},
    "console_errors": {"type": "integer", "default": 0},
    "playtest_performed": {"type": "boolean"},
    "screenshot_captured": {"type": "boolean"},
    "screenshot_inspected": {"type": "boolean"},
    "limitations": {"type": ["string", "array"], "items": {"type": "string"}}}},
      "Record a verification receipt for completed work. Claims alone are UNVERIFIED; a receipt "
      "reaches verified_playtest only by referencing an observation_id recorded by "
      "rb_collect_evidence.",
      LOCAL_WRITE)
def _verify_receipt(a):
    from rbforge import verification
    return verification.receipt(**a)


@tool("rb_toolchain_status", {"type": "object", "properties": {}},
      "Status of optional Luau tooling (rojo, stylua, selene, luau-lsp, rokit).")
def _toolchain(a):
    from rbforge import tooling
    return tooling.status()


@tool("rb_check", {"type": "object", "properties": {
    "path": {"type": "string", "description": "project root; omit for cwd"},
    "scope": {"type": "array", "items": {"type": "string",
              "enum": ["static", "unit", "structure"]}},
    "changed_only": {"type": "boolean", "default": False,
                     "description": "limit lint/format to files changed since base_ref"},
    "base_ref": {"type": "string", "default": "HEAD",
                 "description": "with changed_only: commit to diff against"}}},
      "Offline verification gate: format, lint, typecheck, pure-Luau unit tests "
      "and structural audit. RUN THIS AFTER EVERY EDIT BATCH and BEFORE any "
      "Studio playtest. Clean is 'pass'; a proven defect is 'fail'; missing "
      "tooling is 'incomplete' and must never be reported as verified.")
def _check(a):
    from rbforge import check
    return check.run(a.get("path") or os.getcwd(), scope=a.get("scope"),
                     changed_only=bool(a.get("changed_only")), base_ref=a.get("base_ref") or "HEAD")


@tool("rb_plugins", {"type": "object", "properties": {}},
      "Which optional Studio plugins are installed, what each changes, and its free alternative. "
      "None is ever required.")
def _plugins(a):
    from rbforge import plugins
    return plugins.status()


@tool("rb_assets", {"type": "object", "properties": {
    "action": {"type": "string", "enum": ["status", "check"], "default": "status"},
    "path": {"type": "string", "description": "export to inspect when action=check"}}},
      "Optional 3D route: Blender and Roblox add-on detection, and whether a .glb fits the "
      "20,000-triangle-per-mesh cap. Never uploads or logs in.")
def _assets(a):
    from rbforge import assets
    if a.get("action") == "check":
        if not a.get("path"):
            return {"error": "check needs a path", "detail": "pass path=<file.glb|file.fbx>"}
        return assets.inspect_export(a["path"])
    return assets.status()


# ------------------------------------------------------------------ wire

@tool("rb_studio_probe", {"type": "object", "properties": {
    "name": {"type": "string", "description": "probe name; omit to list all probes"},
    "params": {"type": "object", "additionalProperties": {"type": "string"},
               "description": "parameter overrides as Luau expressions, e.g. {\"pattern\": \"\\\"Door\\\"\"}"},
    "run": {"type": "boolean", "description": "run it in Studio now and return the output"},
    "datamodel": {"type": "string", "enum": ["Edit", "Client", "Server"]},
    "studio_id": {"type": "string"}}},
      "Reviewed Luau diagnostics for the Studio MCP's execute_luau: sight lines, area clearance, SurfaceGui "
      "overflow, scene/UI/perf audits, deduped console, comparable camera captures, sound ids. Omit name to "
      "list them; run=true executes one now. Prefer these over writing inspection code.",
      # hide/restore and camera-pin change the edit session (reversibly), so this is not read-only.
      {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False})
def _studio_probe(a):
    from rbforge import probes
    if not a.get("name"):
        return probes.catalog()
    if a.get("run"):
        from rbforge import live
        return live.run_probe(a["name"], a.get("params") or {}, a.get("datamodel"), a.get("studio_id"))
    return probes.render(a["name"], a.get("params") or {})


@tool("rb_studio_push", {"type": "object", "properties": {
    "paths": {"type": "array", "items": {"type": "string"},
              "description": "source files mapped by the Rojo project (absolute or relative to project), or [\"ALL\"]"},
    "project": {"type": "string", "description": "path to default.project.json"},
    "studio_id": {"type": "string", "description": "omit when one Studio is open"},
    "force": {"type": "boolean", "default": False,
              "description": "overwrite scripts edited in Studio since the last push (backed up first)"}},
     "required": ["paths", "project"]},
      "Copy script sources from disk into Studio via the official MCP, checksum-verified inside Studio. "
      "Use instead of pasting scripts into execute_luau. A script edited in Studio since the last push is "
      "refused as a conflict unless force=true.",
      {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False})
def _studio_push(a):
    from rbforge import live
    proj = a["project"]
    base = os.path.dirname(os.path.abspath(proj))
    paths = [p if p == "ALL" or os.path.isabs(p) else os.path.join(base, p) for p in a["paths"]]
    return live.push(paths, proj, a.get("studio_id"), force=bool(a.get("force")))


@tool("rb_traps_review", {"type": "object", "properties": {
    "path": {"type": "string", "description": "project root; omit for cwd"}}},
      "Engine-trap lint: Luau that compiles but breaks a Roblox game (LocalPlayer on the server, "
      "client-created remotes, unprotected DataStore calls, deprecated APIs). Findings carry file, line and fix.")
def _traps_review(a):
    from rbforge import traps
    return traps.review(a.get("path") or ".")


def _j(obj):
    return json.dumps(obj, indent=2, default=str)


def handle(req):
    if not isinstance(req, dict):
        # a bare `[1]` or `"x"` on stdin must not kill the session
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "invalid request: not an object"}}
    method = req.get("method")
    if "id" not in req:
        return None  # notification: never answered, per JSON-RPC 2.0 / MCP
    if method == "initialize":
        params = req.get("params") if isinstance(req.get("params"), dict) else {}
        asked = params.get("protocolVersion")
        version = asked if asked in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0]
        result = {"protocolVersion": version, "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO}
        if version != "2024-11-05":
            result["instructions"] = INSTRUCTIONS  # field introduced in 2025-03-26
        return {"jsonrpc": "2.0", "id": req.get("id"), "result": result}
    if method == "notifications/initialized":
        return None  # already handled above; kept for clarity
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req.get("id"), "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req.get("id"),
                "result": {"tools": [{"name": n, "description": d, "inputSchema": s, "annotations": ann}
                                     for n, (f, s, d, ann) in sorted(TOOLS.items())]}}
    if method == "tools/call":
        params = req.get("params") if isinstance(req.get("params"), dict) else {}
        name = params.get("name")
        args = params.get("arguments") or {}
        entry = TOOLS.get(name)
        if not entry:
            return {"jsonrpc": "2.0", "id": req.get("id"),
                    "error": {"code": -32602, "message": "unknown tool %r" % name}}
        if not isinstance(args, dict):
            return {"jsonrpc": "2.0", "id": req.get("id"),
                    "error": {"code": -32602, "message": "arguments must be an object, got %s"
                              % type(args).__name__}}
        fn = entry[0]
        try:
            out = fn(args)
            return {"jsonrpc": "2.0", "id": req.get("id"),
                    "result": {"content": [{"type": "text", "text": _j(out)}]}}
        except ForgeError as exc:
            return {"jsonrpc": "2.0", "id": req.get("id"),
                    "result": {"content": [{"type": "text", "text": _j(exc.to_dict())}],
                               "isError": True}}
        except Exception as exc:  # noqa: BLE001 - a tool bug must never kill the server
            return {"jsonrpc": "2.0", "id": req.get("id"),
                    "result": {"content": [{"type": "text", "text": _j(
                        {"ok": False, "error": {"code": "RBF-INTERNAL-001",
                                                "message": "%s: %s" % (type(exc).__name__, exc),
                                                "hint": "report this; the tool schema may "
                                                        "not match its implementation"}})}],
                               "isError": True}}
    return {"jsonrpc": "2.0", "id": req.get("id"),
            "error": {"code": -32601, "message": "method not found: %r" % method}}


def serve():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            # JSON-RPC 2.0: unparseable input gets a Parse error with a null id, not silence that
            # leaves the client waiting for a reply until it times out.
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
            continue
        resp = handle(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    serve()
