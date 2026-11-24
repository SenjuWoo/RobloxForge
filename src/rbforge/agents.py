"""Agent integration: connect/disconnect the official Roblox Studio MCP
in supported agent CLIs, and report status.

Design rule from the brief: prefer the provider's own CLI over config-file
surgery. Hermes and Claude both have one; Codex/Grok/Kimi get JSON/TOML
editing with backup + idempotency, or are reported unsupported.

Every mutation: backup -> mutate -> verify parseable. Never touch unrelated
entries. Repeated connect is a no-op.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

from . import paths
from .errors import ForgeError

PROVIDERS = ("hermes", "claude", "codex", "grok", "kimi")


def _mentions(text):
    """True when output names OUR server. Deliberately does NOT match
    'roblox-studio'/'roblox_studio' - that is the official Studio MCP, a
    different registration, and conflating the two would report the forge
    as configured on machines that only ever added the official one."""
    if not text:
        return False
    return "robloxforge" in text.lower()


# ------------------------------------------------------------------ helpers

def _run(cmd, timeout=120, feed=None):
    """feed: stdin text for CLIs that prompt (e.g. hermes mcp add's Y/n).

    Without a feed, stdin is closed: inside the MCP server it is the JSON-RPC stream, and a child
    that read it would swallow requests. Output is decoded as UTF-8 with replacement, so a CLI that
    prints an emoji cannot raise UnicodeDecodeError past this function.
    """
    kwargs = {"input": feed} if feed is not None else {"stdin": subprocess.DEVNULL}
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, **kwargs)
    except (OSError, subprocess.SubprocessError) as exc:
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": str(exc)})()


# The forge's own MCP registration. Every provider wires it DISABLED so the
# rb_* tool schemas do not ride along in unrelated sessions; users flip
# it on for Roblox work (see README "Token discipline").
FORGE_SERVER = "robloxforge"


def _forge_argv():
    """[python, <repo>/mcp_server/server.py] resolved from THIS checkout,
    so a clone anywhere works. Forward slashes: valid in Windows argv AND
    valid inside TOML basic strings (backslashes would need escaping and
    `\\U` in `C:\\Users` is a unicode escape that bricks codex's config)."""
    from . import paths
    script = os.path.join(paths.REPO_ROOT, "mcp_server", "server.py")
    return [_stable_python().replace("\\", "/"), script.replace("\\", "/")]


def _stable_python():
    """An interpreter that outlives the process that wrote the config.

    The MCP server is stdlib-only, so any Python 3 runs it. `sys.executable` alone pinned whatever
    launched `connect`: run from an agent app's private venv it wrote that venv's python.exe into the
    agent config, the app replaced the venv on its next update and the server went dead (field report,
    2026-11-23). Order: UABS_PYTHON (the machine's shared runtime), the base interpreter behind a venv,
    then sys.executable.
    """
    shared = os.environ.get("UABS_PYTHON")
    if shared and os.path.isfile(shared):
        return shared
    if sys.prefix != sys.base_prefix:
        base = getattr(sys, "_base_executable", None)
        if base and os.path.isfile(base) and os.path.normcase(base) != os.path.normcase(sys.executable or ""):
            return base
        for cand in (os.path.join(sys.base_prefix, "python.exe"), os.path.join(sys.base_prefix, "bin", "python3")):
            if os.path.isfile(cand):
                return cand
    return sys.executable or "python"


def _toml_block(name, argv):
    """A TOML table for one stdio MCP server. argv MUST be forward-slashed."""
    safe = [a.replace("\\", "/") for a in argv]
    return ('\n[mcp_servers.%s]\ncommand = "%s"\nargs = ["%s"]\n'
            "enabled = false\n" % (name, safe[0], safe[1]))


def _toml_remove(text, name):
    """Delete ONLY the named server's keys from a TOML doc.

    Line-based, because blocks contain `args = [...]` whose `[` defeats any
    'up to next bracket' regex - and that regex variant also ate unrelated
    tables (it deleted the official Roblox_Studio entry). Never touches
    anything outside the named table.
    """
    out, skipping = [], False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("["):
            skipping = stripped == "[mcp_servers.%s]" % name
        if not skipping:
            out.append(line)
    return "".join(out)


def _toml_enabled(text, name):
    """enabled state of a parsed TOML table; None when absent/unparseable."""
    try:
        import tomllib
        data = tomllib.loads(text)
    except Exception:  # ValueError on py3.11-, tomllib.TOMLDecodeError subclass
        return None
    table = data.get("mcp_servers", {}).get(name)
    if not isinstance(table, dict):
        return None
    return bool(table.get("enabled", True))


def _which(name):
    return paths.which(name)


def _atomic_write(path, text):
    """Replace `path` with `text` through a sibling temp file.

    Agent configs are rewritten by the agents themselves while they run (Claude Code rewrites
    ~/.claude.json constantly), so an in-place `open(path, "w")` that is interrupted, or interleaved
    with the agent's own write, leaves a truncated file. os.replace is all-or-nothing.
    """
    tmp = "%s.rbforge-%d.tmp" % (path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# ------------------------------------------------------------- provider CLIs

def _hermes():
    exe = _which("hermes")

    def installed():
        return bool(exe)

    def status(_cfg=None):
        if not exe:
            return None
        done = _run([exe, "mcp", "list"])
        return {"configured": _mentions(done.stdout),
                "detail": (done.stdout or done.stderr).strip()[-300:]}

    def connect(_cfg=None):
        st = status()
        if st and st["configured"]:
            return "already configured"
        argv = _forge_argv()
        # `hermes mcp add` prompts "Enable all tools? [Y/n]" interactively;
        # pipe 'y' or it cancels silently.
        done = _run([exe, "mcp", "add", FORGE_SERVER, "--command", argv[0],
                     "--args", *argv[1:]], timeout=180, feed="y\n")
        if "Saved" not in (done.stdout or ""):
            raise ForgeError(
                "RBF-AGENT-002", "hermes mcp add did not save the server",
                hint="run manually: hermes mcp add %s --command %s --args \"%s\" "
                     "(answer Y at the tool-enable prompt), then: "
                     "hermes config set mcp_servers.%s.enabled false "
                     "(off by default; enable for Roblox sessions)"
                     % (FORGE_SERVER, argv[0], argv[1], FORGE_SERVER))
        _run([exe, "config", "set", "mcp_servers.%s.enabled" % FORGE_SERVER,
              "false"])
        return "added via `hermes mcp add`, disabled by default"

    def disconnect(_cfg=None):
        _run([exe, "mcp", "remove", FORGE_SERVER])
        return "removed via `hermes mcp remove`"

    return {"installed": installed, "status": status, "connect": connect, "disconnect": disconnect}


def _claude():
    exe = _which("claude")

    def installed():
        return bool(exe)

    def status(_cfg=None):
        if not exe:
            return None
        done = _run([exe, "mcp", "list"])
        out = {"configured": _mentions(done.stdout),
               "detail": (done.stdout or done.stderr).strip()[-300:]}
        if not out["configured"]:
            via = _claude_proxy(os.path.join(os.path.expanduser("~"), ".claude.json"))
            if via:
                out["reachable_via"] = via
        return out

    def connect(_cfg=None):
        st = status()
        if st and st["configured"]:
            return "already configured"
        argv = _forge_argv()
        # user scope so it is not tied to one project directory
        if not _run([exe, "mcp", "add", "--scope", "user", FORGE_SERVER,
                     "--", *argv]).returncode == 0:
            raise ForgeError("RBF-AGENT-003", "claude mcp add failed",
                             hint="run manually: claude mcp add --scope user %s -- %s"
                                  % (FORGE_SERVER, " ".join(argv)))
        # Claude has no global off-switch: seed every known project entry
        # (and future sessions inherit from these) with the disable array.
        # New directories start enabled - documented in README.
        cfg_file = os.path.join(os.path.expanduser("~"), ".claude.json")
        try:
            n = _claude_disable_everywhere(cfg_file)
            return ("added via `claude mcp add --scope user`; disabled in %d "
                    "known project(s) - toggle on per-session with /mcp" % n)
        except (OSError, ValueError):
            return "added via `claude mcp add --scope user` (could not auto-disable)"

    def disconnect(_cfg=None):
        _run([exe, "mcp", "remove", "-s", "user", FORGE_SERVER])
        return "removed via `claude mcp remove`"

    return {"installed": installed, "status": status, "connect": connect, "disconnect": disconnect}


def _claude_proxy(cfg_file):
    """Name of a Claude MCP server that launches RobloxForge on demand, or None.

    A tool-gateway server (one MCP entry that starts project tools when asked) can expose the forge
    without a `robloxforge` entry, so `claude mcp list` alone reported "not configured" while the
    18 tools were reachable. Such a gateway is recognised by the ROBLOX_FORGE_ROOT it is given, or
    by launching a RobloxForge `mcp_server/server.py`. Read-only: the config is never written here.
    """
    try:
        with open(cfg_file, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    tables = [data.get("mcpServers")]
    tables += [p.get("mcpServers") for p in (data.get("projects") or {}).values() if isinstance(p, dict)]
    for table in tables:
        if not isinstance(table, dict):
            continue
        for name, cfg in table.items():
            if name == FORGE_SERVER or not isinstance(cfg, dict):
                continue
            env = cfg.get("env") if isinstance(cfg.get("env"), dict) else {}
            argv = " ".join(str(a) for a in [cfg.get("command") or ""] + list(cfg.get("args") or []))
            if "ROBLOX_FORGE_ROOT" in env or "mcp_server/server.py" in argv.replace("\\", "/"):
                return name
    return None


def _claude_disable_everywhere(cfg_file):
    """Add the forge to every known project's disabledMcpServers; returns how many changed.

    Backed up first, then replaced atomically: ~/.claude.json holds every project's history and
    settings, and Claude Code writes it while it runs.
    """
    _backup(cfg_file)
    with open(cfg_file, encoding="utf-8") as handle:
        data = json.load(handle)
    n = 0
    for proj in (data.get("projects") or {}).values():
        if not isinstance(proj, dict):
            continue
        arr = proj.setdefault("disabledMcpServers", [])
        if FORGE_SERVER not in arr:
            arr.append(FORGE_SERVER)
            n += 1
    if n:
        _atomic_write(cfg_file, json.dumps(data, indent=2))
    return n


def _codex():
    cfg_path = os.path.join(os.path.expanduser("~"), ".codex", "config.toml")

    def installed():
        # The agent creates this folder on first run; no folder means no agent to wire.
        return os.path.isdir(os.path.dirname(cfg_path))

    def status(cfg=None):
        cfg = cfg or cfg_path
        if not os.path.isfile(cfg):
            return None
        text = open(cfg, encoding="utf-8", errors="replace").read()
        return {"configured": _mentions(text), "path": cfg}

    def connect(cfg=None):
        cfg = cfg or cfg_path
        st = status(cfg)
        if st and st["configured"]:
            return "already configured"
        block = _toml_block(FORGE_SERVER, _forge_argv())
        _backup(cfg)
        with open(cfg, "a", encoding="utf-8") as handle:
            handle.write(block)
        if _toml_enabled(open(cfg, encoding="utf-8").read(), FORGE_SERVER) is None:
            raise ForgeError("RBF-AGENT-004",
                             "wrote %s but the file no longer parses as TOML" % cfg,
                             hint="restore from the .bak next to it and report this")
        return ("appended [mcp_servers.%s] (enabled=false) to %s (backup saved); "
                "flip enabled=true for Roblox sessions" % (FORGE_SERVER, cfg))

    def disconnect(cfg=None):
        cfg = cfg or cfg_path
        if not os.path.isfile(cfg):
            return "nothing to remove"
        _backup(cfg)
        text = open(cfg, encoding="utf-8", errors="replace").read()
        out = _toml_remove(text, FORGE_SERVER)
        _atomic_write(cfg, out)
        return "removed robloxforge block from %s (official entries untouched; backup saved)" % cfg

    return {"installed": installed, "status": status, "connect": connect, "disconnect": disconnect}


def _generic_unsupported(name):
    def status(_cfg=None):
        return {"configured": False, "note":
                "%s support not implemented; add the official MCP yourself:\n"
                '  command: cmd.exe  args: ["/c", "%%LOCALAPPDATA%%\\Roblox\\mcp.bat"]' % name}
    return {"status": status, "connect": None, "disconnect": None}


def _grok():
    cfg_path = os.path.join(os.path.expanduser("~"), ".grok", "config.toml")

    def installed():
        # The agent creates this folder on first run; no folder means no agent to wire.
        return os.path.isdir(os.path.dirname(cfg_path))

    def status(cfg=None):
        cfg = cfg or cfg_path
        if not os.path.isfile(cfg):
            return None
        text = open(cfg, encoding="utf-8", errors="replace").read()
        present = _toml_enabled(text, FORGE_SERVER) is not None
        return {"configured": present,
                "enabled": _toml_enabled(text, FORGE_SERVER),
                "detail": "off by default; grok mcp enable robloxforge to use"}

    def connect(cfg=None):
        cfg = cfg or cfg_path
        st = status(cfg)
        if st and st["configured"]:
            return "already configured"
        _backup(cfg)
        with open(cfg, "a", encoding="utf-8") as fh:
            fh.write(_toml_block(FORGE_SERVER, _forge_argv()))
        return "added [mcp_servers.%s] (enabled=false) to %s" % (FORGE_SERVER, cfg)

    def disconnect(cfg=None):
        cfg = cfg or cfg_path
        if not os.path.isfile(cfg):
            return "nothing to remove"
        _backup(cfg)
        text = open(cfg, encoding="utf-8", errors="replace").read()
        out = _toml_remove(text, FORGE_SERVER)
        _atomic_write(cfg, out)
        return "removed robloxforge block from %s (backup saved)" % cfg

    return {"installed": installed, "status": status, "connect": connect, "disconnect": disconnect}


_kimi = lambda: _generic_unsupported("kimi")


# ------------------------------------------------------------------ backup

def _backup(path):
    if not os.path.isfile(path):
        return None
    target_dir = paths.backups_dir()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = os.path.basename(path)
    target = os.path.join(target_dir, "%s.bak-rbforge-%s" % (base, stamp))
    shutil.copy2(path, target)
    return target


# ------------------------------------------------------------------ public API

def _as_names(provider):
    """Accept str | list | None everywhere; validate once."""
    if provider is None:
        return list(PROVIDERS)
    names = [provider] if isinstance(provider, str) else list(provider)
    bad = [n for n in names if n not in PROVIDERS]
    if bad:
        raise ForgeError("RBF-ARG-001", "unknown provider %r" % bad,
                         hint="one of: %s" % ", ".join(PROVIDERS))
    return names


def status(provider=None):
    """Each agent's wiring. The CLI-backed checks take seconds each (`claude mcp list` health-checks
    every server), so they run concurrently; the result keeps the provider order."""
    from concurrent.futures import ThreadPoolExecutor

    names = _as_names(provider)

    def one(name):
        st = globals()["_%s" % name]()["status"]()
        entry = st or {"installed": False}
        entry.setdefault("agent_installed", st is not None)
        return entry

    with ThreadPoolExecutor(max_workers=len(names) or 1) as pool:
        entries = list(pool.map(one, names))
    return dict(zip(names, entries))


def connect(provider):
    results = {}
    for name in _as_names(provider):
        impl = globals()["_%s" % name]()
        if not impl.get("connect"):
            results[name] = {"provider": name,
                             "error": "automatic connect for %r is not supported yet" % name,
                             "hint": "add the official MCP manually; see README"}
            continue
        if not impl["installed"]():
            # Not an error: `all` wires (or un-wires) the agents that exist, and one absent agent
            # must never stop the rest - Uninstall.ps1 runs `disconnect all`.
            results[name] = {"provider": name, "skipped": "%s is not installed" % name}
            continue
        try:
            results[name] = {"provider": name, "result": impl["connect"](),
                             "verify": "restart %s, then run: rbforge doctor" % name}
        except ForgeError as exc:
            results[name] = exc.to_dict()
    return results[provider] if isinstance(provider, str) else results


def disconnect(provider):
    results = {}
    for name in _as_names(provider):
        impl = globals()["_%s" % name]()
        if not impl.get("disconnect"):
            results[name] = {"provider": name,
                             "error": "disconnect for %r not supported" % name}
            continue
        if not impl["installed"]():
            # Not an error: `all` wires (or un-wires) the agents that exist, and one absent agent
            # must never stop the rest - Uninstall.ps1 runs `disconnect all`.
            results[name] = {"provider": name, "skipped": "%s is not installed" % name}
            continue
        try:
            results[name] = {"provider": name, "result": impl["disconnect"]()}
        except ForgeError as exc:
            results[name] = exc.to_dict()
    return results[provider] if isinstance(provider, str) else results
