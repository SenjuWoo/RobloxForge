"""Doctor: every question answered independently, each with its fix."""
import json

from . import agents, capabilities, docs as docs_mod, studio as studio_mod, tooling


def _line(label, value, fix=None):
    width = max(0, 30 - len(label))
    out = "%s %s %s" % (label, "." * width, value)
    if fix:
        out += "\n%s-> fix: %s" % (" " * 34, fix)
    return out


def collect(probe=True, host_vision=None):
    """Everything doctor knows. Machine-readable form."""
    snap = studio_mod.snapshot(probe=probe)
    caps = capabilities.compute(studio_snapshot=snap, probe=False,
                                host_vision=host_vision)
    return {
        "version": _version(),
        "studio": {k: v for k, v in snap.items() if k != "mcp_probe"},
        "mcp_probe": snap.get("mcp_probe"),
        "capabilities": caps,
        "capabilities_by_status": capabilities.summarize(caps),
        "docs": docs_mod.freshness(),
        "toolchain": tooling.status(),
        "agents": agents.status(),
    }


def _version():
    from . import __version__
    return __version__


def render(report):
    """Human-readable doctor output. Optional absences are calm, failures loud."""
    s = report["studio"]
    lines = ["RobloxForge v%s doctor" % report["version"], ""]
    lines.append(_line("Roblox Studio",
                       "installed (%s)" % s["studio_version"] if s["studio_installed"] else "NOT FOUND",
                       "install from roblox.com/create" if not s["studio_installed"] else None))
    running = (s["studio_process"] or {}).get("running")
    lines.append(_line("Studio running", {True: "yes", False: "no", None: "?"}[running]))
    enabled = (s["mcp_enabled_setting"] or {}).get("enabled")
    en_txt = {True: "on", False: "OFF (manual step)", None: "unknown"}[enabled]
    lines.append(_line("Studio MCP setting", en_txt,
                       studio_mod.MANUAL_ENABLE_STEPS if enabled is False else None))
    lines.append(_line("Official MCP launcher",
                       "found" if s["mcp_launcher_found"] else "not found"))

    p = report["mcp_probe"] or {}
    if p.get("responding") is None:
        lines.append(_line("Studio MCP handshake", "not probed (--no-probe)"))
    elif p.get("responding"):
        lines.append(_line("Studio MCP handshake", "responding (%d tools)" % p["tool_count"]))
        places = s.get("active_places") or []
        # str() because a Studio with an unsaved place can report no name at all;
        # that used to raise inside join() and take the whole report down.
        lines.append(_line("Active place(s)", ", ".join(str(p) for p in places if p) if places else
                           "(none - open a place to build)",
                           "open a place in Studio" if not places else None))
        if s.get("multiple_studio_sessions"):
            lines.append(_line("Multiple sessions", "yes - address by studio_id"))
    else:
        err = p.get("error") or {}
        lines.append(_line("Studio MCP handshake", "FAILED: %s" % (err.get("message") or "timeout"),
                           err.get("message") and studio_mod.MANUAL_ENABLE_STEPS))

    d = report["docs"]
    if d["present"]:
        age = "%.1fh old" % d["age_hours"] if d["age_hours"] is not None else "?"
        stale = "STALE - run rbforge docs update" if d["stale"] else ""
        lines.append(_line("Creator docs cache", "%d docs, %s %s" %
                           (d["indexed_documents"] or 0, age, stale)))
    else:
        lines.append(_line("Creator docs cache", "absent", "run: rbforge docs update"))

    for name, info in report["toolchain"].items():
        lines.append(_line(name, info["path"] if info["found"] else
                           "optional / absent"))

    for name, info in report["agents"].items():
        conf = info.get("configured")
        note = info.get("note")
        val = {True: "configured", False: "not configured"}.get(conf, "?")
        if info.get("installed") is False:
            val += " (agent not installed)"
        lines.append(_line("%s integration" % name, val, note))

    lines.append("")
    lines.append("Capabilities: " + ", ".join(
        "%s=%d" % (k, len(v)) for k, v in
        sorted(report["capabilities_by_status"].items())))
    return "\n".join(lines)
