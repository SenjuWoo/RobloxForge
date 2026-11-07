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
    ("streaming", "B", ("large", "open world", "cities", "city", "districts", "district", "maps", "map", "island", "world"),
     (r"\bStreamingEnabled\b", r"\bRequestStreamAroundAsync\b"),
     "large worlds: streaming plus streaming-safe code, or distant content loads all at once"),
    ("networking", "B", ("multiplayer", "pvp", "pvpve", "co-op", "players", "player", "extraction"),
     (r"RemoteEvent", r"RemoteFunction", r"UnreliableRemoteEvent"),
     "network traffic: batch updates, validate payloads, keep the server authoritative"),
    ("npc", "B", ("npc", "npcs", "enemy", "enemies", "companion", "companions", "ai", "hordes", "horde", "boss", "bosses"),
     (r"PathfindingService", r"Humanoid:MoveTo"),
     "many agents: stagger updates, cap population, clean up after death"),
    ("physics", "B", ("physics", "vehicles", "vehicle", "ships", "ship", "ragdoll", "collisions", "collision", "building"),
     (r"AssemblyLinearVelocity", r"ApplyImpulse", r"WeldConstraint"),
     "moving assemblies: simplify collisions, watch network ownership, measure the simulation cost"),
    ("procedural", "B", ("procedural", "generated", "spaceships", "spaceship", "leviathan", "random", "infinite"),
     (r"EditableMesh", r"Terrain:FillRegion", r"for .* do\s*$"),
     "runtime geometry: budget generation, chunk it, keep it deterministic and reusable"),
    ("persistence", "B", ("save", "saves", "progression", "inventories", "inventory", "economy", "profile", "profiles"),
     (r"DataStoreService", r"ProfileStore", r"UpdateAsync"),
     "saved state: UpdateAsync correctness, session locking, migration path"),
    # A single ScreenGui is not an interface-heavy game; it needs more than one signal.
    ("ui", "B", ("hud", "menus", "menu", "interfaces", "interface", "mobile", "touch", "controller", "controllers", "gamepad"),
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


def _has_phrase(text, words):
    """Whole-word or whole-phrase match: 'ai' must not fire on 'terrain', 'map' not on 'bitmap'."""
    for word in words:
        pattern = r"(?<![\w])" + re.escape(word).replace(r"\ ", r"\s+") + r"(?![\w])"
        if re.search(pattern, text):
            return True
    return False


def _strip_comments(source):
    """Comments describe intent, not behaviour; matching on them routes a project by its prose."""
    source = re.sub(r"--\[=*\[.*?\]=*\]", " ", source, flags=re.S)
    return re.sub(r"--[^\n]*", " ", source)


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
            chunks.append(_strip_comments(text))
            total += len(text)
            if total > limit:  # a scan, not a parse: cap it and stop
                return "\n".join(chunks)
    return "\n".join(chunks)


def profile(root=".", premise=""):
    """A small, explainable set of priorities for this project."""
    from .errors import ForgeError

    if not os.path.isdir(root):
        raise ForgeError("RBF-ARG-003", "not a project directory: %s" % root,
                         hint="pass --root with a directory that exists")
    words = (premise or "").lower()
    source = _source_text(root)
    have_source = bool(source.strip())
    items = []
    for rid, level, keywords, patterns, why in _RULES:
        premise_hit = _has_phrase(words, keywords)
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
        "source": "scanned" if have_source else "none",
        "level_a": list(_LEVEL_A),
        "level_b": items,
        "note": "agent-guided routing, not measurement: nothing here claims the project is optimized",
        "next": ("apply level A, then only the level B items above; level C needs a measurement first"
                 if items else
                 ("small project: level A only, skip the optimization machinery" if have_source
                  else "no readable Luau source here, so nothing was inferred: run this from the project "
                       "root (or after the first scripts exist) before trusting a 'small' verdict")),
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
