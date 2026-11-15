"""Honest capability matrix.

Statuses are *derived from probes*, never asserted from a table. The rule that
matters: an executable existing on disk is not a working capability. Autonomous
playtesting is only `verified` when the live MCP handshake actually offered the
tools that perform it.

  verified          probed this run and proven to work
  installed         the artifact is on disk, but nothing was proven with it
  configured        wired into a client's config, not necessarily running
  available         RobloxForge implements it locally, no external dependency
  runtime_required  would work, but something must be running (usually Studio)
  manual_step       a human must flip a switch RobloxForge cannot flip
  optional          nice to have, absent, and that is fine
  unavailable       a hard dependency is missing
  unsupported       not implemented in this build, on purpose
"""
import copy

from . import docs as docs_mod
from . import studio as studio_mod
from . import tooling as tooling_mod

# Tools the official MCP must expose for a capability to count as real.
_LIVE_CONTROL_TOOLS = {"execute_luau", "multi_edit", "search_game_tree", "inspect_instance"}
_PLAYTEST_TOOLS = {"start_stop_play", "get_studio_state", "get_console_output"}
_INPUT_TOOLS = {"character_navigation", "user_keyboard_input", "user_mouse_input"}
_VISUAL_TOOLS = {"screen_capture"}
_SUBAGENT_TOOLS = {"subagent"}


def _cap(status, note=None, **extra):
    entry = {"status": status}
    if note:
        entry["note"] = note
    entry.update(extra)
    return entry


def compute(studio_snapshot=None, probe=True, host_vision=None, toolchain=None):
    """Build the matrix from real evidence.

    host_vision: whether the *calling model* can actually look at an image.
    RobloxForge cannot detect this, so it stays None unless the caller says.
    toolchain: a `tooling.status()` result the caller already has (each call spawns every tool).
    """
    snap = studio_snapshot or studio_mod.snapshot(probe=probe)
    mcp = snap.get("mcp_probe") or {}
    live_tools = set(mcp.get("tools") or [])
    responding = bool(mcp.get("responding"))
    matrix = {}

    # --- the live engine, owned by Roblox -------------------------------
    if responding:
        matrix["official_studio_mcp"] = _cap(
            "verified", "handshake succeeded; %d tools offered" % (mcp.get("tool_count") or 0),
            server=mcp.get("server_info"), tools=sorted(live_tools))
    elif snap.get("mcp_launcher_found"):
        enabled = (snap.get("mcp_enabled_setting") or {}).get("enabled")
        if enabled is False:
            matrix["official_studio_mcp"] = _cap(
                "manual_step", "launcher present but Studio's MCP server is turned off",
                fix=studio_mod.MANUAL_ENABLE_STEPS)
        elif not (snap.get("studio_process") or {}).get("running"):
            matrix["official_studio_mcp"] = _cap(
                "runtime_required", "launcher present; Roblox Studio is not running",
                fix="open Roblox Studio with a place, then re-run rbforge doctor")
        else:
            matrix["official_studio_mcp"] = _cap(
                "unavailable", "launcher present but the handshake did not complete",
                error=mcp.get("error"), fix=studio_mod.MANUAL_ENABLE_STEPS)
    else:
        matrix["official_studio_mcp"] = _cap(
            "unavailable", "official MCP launcher not found",
            fix="install or update Roblox Studio")

    def _from_live(required, absent_note):
        if responding and required <= live_tools:
            return _cap("verified", "offered by the live official MCP",
                        tools=sorted(required))
        if responding:
            missing = sorted(required - live_tools)
            return _cap("unavailable", "official MCP is connected but lacks %s" % missing)
        return _cap("runtime_required", absent_note)

    need_studio = "requires a connected Roblox Studio MCP session"
    matrix["studio_live_control"] = _from_live(_LIVE_CONTROL_TOOLS, need_studio)
    matrix["autonomous_playtest"] = _from_live(_PLAYTEST_TOOLS, need_studio)
    matrix["input_simulation"] = _from_live(_INPUT_TOOLS, need_studio)
    matrix["studio_subagents"] = _from_live(_SUBAGENT_TOOLS, need_studio)

    # Screenshots are the classic false-confidence trap: capturing an image is
    # not the same as a model having looked at it.
    capture = _from_live(_VISUAL_TOOLS, need_studio)
    if capture["status"] == "verified":
        if host_vision is True:
            capture["note"] = "screen_capture available and host model reports vision"
        elif host_vision is False:
            capture["status"] = "manual_step"
            capture["note"] = ("screen_capture available, but the host model cannot see "
                               "images; a human must inspect the screenshot")
        else:
            capture["note"] = ("screen_capture available; whether the screenshot is "
                               "actually inspected depends on the host model's vision")
    matrix["visual_verification"] = capture

    # --- knowledge ------------------------------------------------------
    fresh = docs_mod.freshness()
    if not fresh["present"]:
        matrix["docs_search"] = _cap("unavailable", "creator-docs cache not downloaded yet",
                                     fix="run: rbforge docs update")
    elif fresh["stale"]:
        matrix["docs_search"] = _cap("available", "cache present but %.0fh old" %
                                     (fresh["age_hours"] or 0), freshness=fresh)
    else:
        matrix["docs_search"] = _cap("verified", "%d documents indexed, %.1fh old" %
                                     (fresh["indexed_documents"] or 0, fresh["age_hours"] or 0),
                                     freshness=fresh)
    matrix["docs_refresh"] = (_cap("available", "git available for incremental refresh")
                              if docs_mod._git() else
                              _cap("unavailable", "git not found",
                                   fix="install git to fetch or refresh Roblox documentation"))

    # --- things RobloxForge itself implements ---------------------------
    matrix["architecture_review"] = _cap(
        "available", "static heuristics over Luau sources; not a runtime proof")
    matrix["security_review"] = _cap(
        "available", "static heuristics for client-authority and unvalidated remotes")
    matrix["scaffolding"] = _cap("available", "generic, obby, simulator and tycoon templates")
    matrix["verification_contract"] = _cap("available", "plans and receipts, evidence-gated")
    matrix["project_analysis"] = _cap(
        "available", "filesystem projects; live-only places need the official MCP")

    # --- optional toolchain ---------------------------------------------
    tools = toolchain if toolchain is not None else tooling_mod.status()
    for name, info in tools.items():
        if info["found"]:
            matrix[name] = _cap("installed", "%s at %s" % (info.get("version") or "version unknown",
                                                           info["path"]))
        else:
            matrix[name] = _cap("optional", "not installed; only needed for the "
                                            "source-controlled workflow")

    matrix["source_controlled_workflow"] = (
        _cap("installed", "rojo present") if tools.get("rojo", {}).get("found")
        else _cap("optional", "install rojo to sync a filesystem project into Studio"))

    return matrix


def snapshot(**kw):
    return copy.deepcopy(compute(**kw))


def summarize(matrix):
    """Group by status so a human or a weak model can read it at a glance."""
    by_status = {}
    for name, entry in sorted(matrix.items()):
        by_status.setdefault(entry["status"], []).append(name)
    return by_status
