"""Pick the optimization guidance a project has actually earned.

This is routing, not measurement. It reads the user's premise and the project's source to decide which
of the shipped references apply, and it says so plainly rather than pretending the levels were
automatic. Nothing here claims a project is optimized; level C always requires a measurement first.

    rbforge optimize --premise "large multiplayer city with NPCs"
"""
import os
import re

# Each rule: id, level, premise words, source patterns, and why it fires.
_RULES = (
    ("streaming", "B", ("large", "open world", "city", "district", "map", "island", "world"),
     (r"\bStreamingEnabled\b", r"\bRequestStreamAroundAsync\b"),
     "large worlds: streaming plus streaming-safe code, or distant content loads all at once"),
    ("networking", "B", ("multiplayer", "pvp", "pvpve", "co-op", "players", "extraction"),
     (r"RemoteEvent", r"RemoteFunction", r"UnreliableRemoteEvent"),
     "network traffic: batch updates, validate payloads, keep the server authoritative"),
    ("npc", "B", ("npc", "enemy", "enemies", "companion", "ai", "horde", "boss"),
     (r"PathfindingService", r"Humanoid:MoveTo"),
     "many agents: stagger updates, cap population, clean up after death"),
    ("physics", "B", ("physics", "vehicle", "ship", "ragdoll", "collision", "building"),
     (r"AssemblyLinearVelocity", r"ApplyImpulse", r"WeldConstraint"),
     "moving assemblies: simplify collisions, watch network ownership, measure the simulation cost"),
    ("procedural", "B", ("procedural", "generated", "spaceship", "leviathan", "random", "infinite"),
     (r"EditableMesh", r"Terrain:FillRegion", r"for .* do\s*$"),
     "runtime geometry: budget generation, chunk it, keep it deterministic and reusable"),
    ("persistence", "B", ("save", "progression", "inventory", "economy", "profile"),
     (r"DataStoreService", r"ProfileStore", r"UpdateAsync"),
     "saved state: UpdateAsync correctness, session locking, migration path"),
    # A single ScreenGui is not an interface-heavy game; it needs more than one signal.
    ("ui", "B", ("hud", "menu", "interface", "mobile", "touch", "controller", "gamepad"),
     (r"ScreenGui", r"UIGridLayout", r"UIListLayout", r"UserInputService"),
     "interface-heavy: measure layout cost, scale for device and input"),
)

# Rules that need more than one code hit before they are worth raising.
_MIN_HITS = {"ui": 2}

_LEVEL_A = (
    "server owns truth; client owns input and presentation",
    "module boundaries match the ownership split",
    "connections and instances cleaned up on death/respawn",
    "no per-frame work that only needs to happen on change",
    "client requests validated (type, range, distance, ownership, cooldown)",
    "played, console read, screenshot inspected before claiming success",
)

_LEVEL_C = {
    "streaming": "measure load time and memory before/after enabling streaming",
    "networking": "measure bytes per second before batching or writing a custom protocol",
    "npc": "measure script CPU with the population you intend to ship",
    "physics": "measure simulation time before merging or disabling collisions",
    "procedural": "measure generation time and instance growth before chunking or pooling",
}


def _source_text(root, limit=400_000):
    chunks, total = [], 0
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in {".git", "Packages", "node_modules", "artifacts",
                                                "backups", "DevPackages", "ServerPackages"}]
        for name in files:
            if not (name.endswith(".luau") or name.endswith(".lua")):
                continue
            try:
                with open(os.path.join(base, name), encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            chunks.append(text)
            total += len(text)
            if total > limit:  # a scan, not a parse: cap it and stop
                return "\n".join(chunks)
    return "\n".join(chunks)


def profile(root=".", premise=""):
    """A small, explainable set of priorities for this project."""
    words = (premise or "").lower()
    source = _source_text(root)
    items = []
    for rid, level, keywords, patterns, why in _RULES:
        premise_hit = any(word in words for word in keywords)
        code_hits = sum(1 for pattern in patterns if re.search(pattern, source))
        if not premise_hit and code_hits < _MIN_HITS.get(rid, 1):
            continue
        evidence = []
        if premise_hit:
            evidence.append("request")
        if code_hits:
            evidence.append("%d code pattern(s)" % code_hits)
        items.append({"id": rid, "level": level, "why": why,
                      "evidence": ", ".join(evidence),
                      "measure_first": _LEVEL_C.get(rid)})
    return {
        "root": os.path.abspath(root),
        "level_a": list(_LEVEL_A),
        "level_b": items,
        "note": "agent-guided routing, not measurement: nothing here claims the project is optimized",
        "next": ("apply level A, then only the level B items above; level C needs a measurement first"
                 if items else "small project: level A only, skip the optimization machinery"),
    }


def render(prof):
    lines = ["Level A (always):"]
    lines += ["  - " + item for item in prof["level_a"]]
    if prof["level_b"]:
        lines.append("Level B (this project):")
        for item in prof["level_b"]:
            lines.append("  - %s [%s] - %s" % (item["id"], item["evidence"], item["why"]))
            if item["measure_first"]:
                lines.append("      before level C: " + item["measure_first"])
    else:
        lines.append("Level B: nothing activated - this project does not need it yet.")
    lines.append(prof["next"])
    return "\n".join(lines)
