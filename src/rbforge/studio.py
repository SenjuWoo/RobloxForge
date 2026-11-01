"""Roblox Studio + official built-in MCP server detection.

Every question is answered independently. "Studio is installed" is NEVER
allowed to imply "the MCP server works" - that conflation is the single most
common reason an agent thinks it has Studio control when it does not.

Ground truth used here (verified on Windows 11, Studio 0.735.x):
  launcher     %LOCALAPPDATA%\\Roblox\\mcp.bat  ->  <version dir>\\StudioMCP.exe
  enable flag  %LOCALAPPDATA%\\Roblox\\AssistantSettings\\<userId>.json
               -> {"mcp-server": {"enabled": true}}
  studio exe   registry roblox-studio protocol handler, else newest version dir
"""
import glob
import json
import os
import subprocess
import sys
import threading
import time

from . import paths
from .errors import ForgeError

WINDOWS = sys.platform.startswith("win")
MACOS = sys.platform == "darwin"

ASSISTANT_SETTINGS_GLOB = os.path.join("AssistantSettings", "*.json")

MANUAL_ENABLE_STEPS = (
    "In Roblox Studio: open Assistant -> click the '...' menu -> "
    "Manage MCP Servers -> turn on 'Enable Studio as MCP server'. "
    "This is an editor-side setting; no tool can flip it for you."
)


# --------------------------------------------------------------- installation

def roblox_local_dir():
    """%LOCALAPPDATA%\\Roblox (or the platform equivalent), if it exists."""
    d = os.path.join(paths.local_appdata(), "Roblox")
    return d if os.path.isdir(d) else None


def _registry_studio_path():
    if not WINDOWS:
        return None
    try:
        import winreg
    except ImportError:  # pragma: no cover - non-Windows
        return None
    keys = [
        (winreg.HKEY_CURRENT_USER, "Software\\Classes\\roblox-studio\\shell\\open\\command"),
        (winreg.HKEY_CLASSES_ROOT, "roblox-studio\\shell\\open\\command"),
    ]
    for root, sub in keys:
        try:
            with winreg.OpenKey(root, sub) as key:
                raw, _ = winreg.QueryValueEx(key, "")
        except OSError:
            continue
        # value looks like:  "C:\...\RobloxStudioBeta.exe" %1
        if raw.startswith('"'):
            parts = raw.split('"')
            candidate = parts[1] if len(parts) > 1 else ""
        else:
            candidate = raw.split(" %")[0].strip()
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def _versions_studio_path():
    base = roblox_local_dir()
    if not base:
        return None
    hits = glob.glob(os.path.join(base, "Versions", "version-*", "RobloxStudioBeta.exe"))
    if not hits:
        hits = glob.glob(os.path.join(base, "Versions", "version-*", "RobloxStudio.exe"))
    if not hits:
        return None
    # newest wins; name is a deterministic tiebreak
    hits.sort(key=lambda p: (os.path.getmtime(p), p))
    return hits[-1]


def find_studio():
    """Locate Roblox Studio. Returns dict or None. Ordered and deterministic."""
    override = paths.expand(os.environ.get("RBFORGE_STUDIO", ""))
    if override:
        if not os.path.isfile(override):
            raise ForgeError(
                "RBF-STUDIO-003",
                "RBFORGE_STUDIO points at %r which is not a file" % override,
                hint="unset RBFORGE_STUDIO or point it at RobloxStudioBeta.exe")
        return {"path": override, "source": "env:RBFORGE_STUDIO"}
    if MACOS:
        mac = "/Applications/RobloxStudio.app/Contents/MacOS/RobloxStudio"
        if os.path.isfile(mac):
            return {"path": mac, "source": "applications"}
    found = _registry_studio_path()
    if found:
        return {"path": found, "source": "registry:roblox-studio"}
    found = _versions_studio_path()
    if found:
        return {"path": found, "source": "versions-dir"}
    return None


def studio_version(studio_path):
    """Version folder name - what Roblox itself keys installs on."""
    if not studio_path:
        return None
    parent = os.path.basename(os.path.dirname(studio_path))
    return parent if parent.startswith("version-") else None


# --------------------------------------------------------------- mcp launcher

def find_mcp_launcher():
    """The official launcher. On Windows this is mcp.bat in the Roblox dir."""
    override = paths.expand(os.environ.get("RBFORGE_MCP_LAUNCHER", ""))
    if override and os.path.isfile(override):
        return {"path": override, "source": "env:RBFORGE_MCP_LAUNCHER"}
    if MACOS:
        mac = "/Applications/RobloxStudio.app/Contents/MacOS/StudioMCP"
        if os.path.isfile(mac):
            return {"path": mac, "source": "applications"}
        return None
    base = roblox_local_dir()
    if base:
        bat = os.path.join(base, "mcp.bat")
        if os.path.isfile(bat):
            return {"path": bat, "source": "roblox-local"}
    det = find_studio()
    if det:
        exe = os.path.join(os.path.dirname(det["path"]), "StudioMCP.exe")
        if os.path.isfile(exe):
            return {"path": exe, "source": "beside-studio"}
    return None


def mcp_command():
    """argv that starts the official MCP server, matching Roblox's own docs."""
    launcher = find_mcp_launcher()
    if not launcher:
        raise ForgeError(
            "RBF-MCP-001", "official Roblox Studio MCP launcher not found",
            hint="install or update Roblox Studio; the launcher ships with it at "
                 "%LOCALAPPDATA%\\Roblox\\mcp.bat")
    target = launcher["path"]
    if target.lower().endswith(".bat"):
        return ["cmd.exe", "/c", target]
    return [target]


# --------------------------------------------------------------- enable switch

def mcp_enabled_setting():
    """Read Studio's own 'Enable Studio as MCP server' flag.

    enabled=None means the setting file does not exist yet, which normally
    means Assistant has never been opened - NOT that the server is disabled.
    """
    base = roblox_local_dir()
    if not base:
        return {"enabled": None, "source": None, "accounts": 0,
                "note": "Roblox local data directory not found"}
    files = sorted(glob.glob(os.path.join(base, ASSISTANT_SETTINGS_GLOB)))
    if not files:
        return {"enabled": None, "source": None, "accounts": 0,
                "note": "no AssistantSettings file yet; open Assistant in Studio once"}
    states = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        server = data.get("mcp-server")
        if isinstance(server, dict) and "enabled" in server:
            states.append((path, bool(server["enabled"])))
    if not states:
        return {"enabled": None, "source": files[-1], "accounts": len(files),
                "note": "AssistantSettings present but carries no mcp-server key"}
    enabled_paths = [p for p, value in states if value]
    return {"enabled": bool(enabled_paths), "accounts": len(states),
            "source": enabled_paths[0] if enabled_paths else states[-1][0]}


# --------------------------------------------------------------- process state

def studio_running():
    """Is a Studio process live? running=None means we could not tell."""
    names = _process_names()
    if names is None:
        return {"running": None, "processes": [], "note": "process listing unavailable"}
    studio = [n for n in names if n.lower().startswith("robloxstudio")]
    return {"running": bool(studio), "processes": sorted(set(studio))}


def mcp_processes():
    """Live StudioMCP processes - roughly one per connected MCP client."""
    names = _process_names()
    if names is None:
        return {"count": None}
    return {"count": sum(1 for n in names if n.lower().startswith("studiomcp"))}


def _process_names():
    try:
        if WINDOWS:
            done = subprocess.run(["tasklist", "/fo", "csv", "/nh"],
                                  capture_output=True, text=True, timeout=20)
            if done.returncode != 0:
                return None
            out = []
            for line in done.stdout.splitlines():
                line = line.strip()
                if line.startswith('"'):
                    out.append(line[1:].split('"', 1)[0])
            return out
        done = subprocess.run(["ps", "-A", "-o", "comm="],
                              capture_output=True, text=True, timeout=20)
        if done.returncode != 0:
            return None
        return [os.path.basename(l.strip()) for l in done.stdout.splitlines() if l.strip()]
    except (OSError, subprocess.SubprocessError):
        return None


# -------------------------------------------------------------- live handshake

PROTOCOL_VERSION = "2024-11-05"


def probe_mcp(timeout=25.0, list_studios=True):
    """Actually speak MCP to the official server.

    This is the only honest way to answer "is Studio MCP working". Returns a
    dict and never raises for a plain "not working" outcome, because doctor
    wants to report the failure rather than abort on it.
    """
    result = {"launcher": None, "spawned": False, "responding": False,
              "tool_count": None, "tools": [], "server_info": None,
              "studios": None, "error": None}
    try:
        cmd = mcp_command()
    except ForgeError as exc:
        result["error"] = {"code": exc.code, "message": exc.message}
        return result
    result["launcher"] = cmd[-1]

    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                errors="replace", bufsize=1)
    except OSError as exc:
        result["error"] = {"code": "RBF-MCP-002",
                           "message": "cannot start launcher: %s" % exc}
        return result
    result["spawned"] = True

    lines = []

    def reader():
        try:
            for line in proc.stdout:
                lines.append(line)
        except (OSError, ValueError):
            pass

    threading.Thread(target=reader, daemon=True).start()
    try:
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": PROTOCOL_VERSION,
                                "capabilities": {},
                                "clientInfo": {"name": "rbforge-doctor",
                                               "version": "0.1.1"}}})
        init = _await_id(lines, 1, proc, timeout)
        if init is None:
            result["error"] = {
                "code": "RBF-MCP-003",
                "message": "no initialize response within %.0fs" % timeout}
            return result
        result["server_info"] = (init.get("result") or {}).get("serverInfo")
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        listed = _await_id(lines, 2, proc, timeout)
        if listed is None:
            result["error"] = {
                "code": "RBF-MCP-004",
                "message": "initialize succeeded but tools/list timed out"}
            return result
        tools = ((listed.get("result") or {}).get("tools")) or []
        result["responding"] = True
        result["tool_count"] = len(tools)
        result["tools"] = sorted(t.get("name", "?") for t in tools)
        if list_studios and "list_roblox_studios" in result["tools"]:
            _send(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                         "params": {"name": "list_roblox_studios", "arguments": {}}})
            result["studios"] = _parse_studios(_await_id(lines, 3, proc, timeout))
    finally:
        _terminate(proc)
    return result


def _send(proc, obj):
    try:
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()
    except (OSError, ValueError):
        pass


def _await_id(lines, want_id, proc, timeout):
    deadline = time.time() + timeout
    seen = 0
    while time.time() < deadline:
        while seen < len(lines):
            raw = lines[seen].strip()
            seen += 1
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if msg.get("id") == want_id:
                return msg
        if proc.poll() is not None and seen >= len(lines):
            return None
        time.sleep(0.05)
    return None


def _parse_studios(msg):
    if not msg:
        return None
    content = ((msg.get("result") or {}).get("content")) or []
    for part in content:
        if part.get("type") != "text":
            continue
        try:
            data = json.loads(part.get("text") or "")
        except ValueError:
            continue
        studios = data.get("studios")
        if isinstance(studios, list):
            return studios
    return None


def _terminate(proc):
    try:
        proc.stdin.close()
    except (OSError, ValueError):
        pass
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except (OSError, subprocess.SubprocessError):
        try:
            proc.kill()
        except OSError:
            pass


def snapshot(probe=True, timeout=25.0):
    """Everything doctor needs about Studio, each fact independent."""
    det = find_studio()
    launcher = find_mcp_launcher()
    out = {
        "studio_installed": bool(det),
        "studio_path": det["path"] if det else None,
        "studio_path_source": det["source"] if det else None,
        "studio_version": studio_version(det["path"]) if det else None,
        "mcp_launcher_found": bool(launcher),
        "mcp_launcher_path": launcher["path"] if launcher else None,
        "mcp_enabled_setting": mcp_enabled_setting(),
        "studio_process": studio_running(),
        "mcp_processes": mcp_processes(),
    }
    if probe:
        out["mcp_probe"] = probe_mcp(timeout=timeout)
        studios = out["mcp_probe"].get("studios")
        # A connected Studio can report a place with no name (unsaved, or a
        # version that omits it). Fall back to the id instead of joining None,
        # which used to take the whole doctor down.
        out["active_places"] = [
            str(s.get("name") or s.get("id") or "unnamed")
            for s in studios or [] if isinstance(s, dict)]
        out["multiple_studio_sessions"] = bool(studios and len(studios) > 1)
    else:
        out["mcp_probe"] = {"responding": None, "note": "probe skipped"}
        out["active_places"] = []
        out["multiple_studio_sessions"] = None
    return out
