"""Detect installed Studio plugins, and say what each one changes.

Why this exists: some Roblox workflow tools are paid or freemium (ForgeGUI,
Moon Animator, Archimedes, Atmos). RobloxForge must never REQUIRE one, but when
a user already owns one the agent should use it instead of building a
worse version by hand. That is only possible if the agent can find out what is
actually installed, so this module answers that from disk instead of guessing.

Detection is filename-based and therefore approximate: Studio installs
marketplace plugins into %LOCALAPPDATA%/Roblox/Plugins, local plugins are saved
there by hand. A rename breaks the match, so an unmatched plugin is reported as
"unknown" rather than silently ignored - and the free path is always valid when
nothing matches.
"""
import os

from . import paths

# Known tools. `price` is deliberately conservative: "free", "paid", or
# "freemium". Anything we are not sure of says "check listing" instead of a
# guess, because a wrong price claim is worse than no claim.
KNOWN = {
    "forgegui": {
        "label": "ForgeGUI",
        "price": "freemium",
        "match": ("forgegui", "forge gui"),
        "gives": "AI-generated UI designs, 3D models, thumbnails and script drafts",
        "bridge": "Its output is a DESIGN REFERENCE, not importable Instances. Save "
                  "the image, pass it to store_image, then implement the layout as "
                  "Instances/Fusion yourself. Never claim a ForgeGUI design is "
                  "'in the game' until the instances exist and render.",
        "free_alternative": "Fusion 0.3 layout from ui-mobile.md, or GuiForge (free)",
    },
    "guiforge": {
        "label": "GuiForge",
        "price": "free",
        "match": ("guiforge",),
        "gives": "free Roblox UI editor with Figma export",
        "bridge": "Exports can be imported as instances; still verify anchoring, "
                  "scaling and safe-area handling before shipping.",
        "free_alternative": "itself - this is the free path",
    },
    "uilabs": {
        "label": "UI Labs",
        "price": "free",
        "match": ("uilabs", "ui labs", "ui-labs"),
        "gives": "Storybook-style instant UI preview with hot reload",
        "bridge": "Great for iterating on a component without a playtest; it does "
                  "not verify gameplay, so the playtest rule still applies.",
        "free_alternative": "itself - this is the free path",
    },
    "sketch": {
        "label": "Sketch (Figma-like UI editor)",
        "price": "check listing",
        "match": ("sketch",),
        "gives": "visual UI editor inside Studio",
        "bridge": "Use it to arrange layout; the agent should still own the code "
                  "side and confirm the final ScreenGui hierarchy.",
        "free_alternative": "Fusion 0.3 + ui-mobile.md layout rules",
    },
    "moonanimator": {
        "label": "Moon Animator",
        "price": "paid",
        "match": ("moonanimator", "moon animator"),
        "gives": "advanced animation editing",
        "bridge": "If present, the user may hand you animations; you still drive "
                  "them with Animator/AnimationTrack API and verify playback.",
        "free_alternative": "Roblox's built-in Animation Editor (free, built in)",
    },
    "archimedes": {
        "label": "Archimedes",
        "price": "paid",
        "match": ("archimedes",),
        "gives": "CSG mesh/infill tools",
        "bridge": "Use only if the user already owns it; the free path is "
                  "generate_mesh + primitive unions.",
        "free_alternative": "generate_mesh (MCP) and Part unions",
    },
    "atmos": {
        "label": "Atmos",
        "price": "paid",
        "match": ("atmos",),
        "gives": "procedural weather and sky systems",
        "bridge": "If installed, prefer it over hand-rolled effects, but confirm "
                  "the generated instances are anchored and cheap.",
        "free_alternative": "Atmosphere/Clouds/lighting presets in "
                            "worldbuilding-lighting.md",
    },
    "robloxstudio_mcp": {
        "label": "robloxstudio-mcp bridge (Roqer / community Studio MCP)",
        "price": "free",
        # Installed as MCPPlugin / MCPInspectorPlugin by robloxstudio-mcp and by the Roqer desktop agent.
        "match": ("mcpplugin", "mcpinspectorplugin", "roqer", "robloxstudio mcp"),
        "gives": "a second, third-party MCP into Studio with its own tool names (instances, scripts, "
                 "multi-client playtests, profiling)",
        "bridge": "Two MCPs can reach the same place. RobloxForge's live commands (push, probe --run, "
                  "servertest, rb_collect_evidence) speak only to the official Studio MCP: do not mix the "
                  "two tool sets in one plan, and treat an edit made through the bridge as unverified until "
                  "RobloxForge has read it back or a receipt covers it.",
        "free_alternative": "the official Studio MCP built into Roblox Studio (rbforge agent connect)",
    },
    "f3x": {
        "label": "F3X (building tools)",
        "price": "free",
        "match": ("f3x",),
        "gives": "fast manual building/duplication",
        "bridge": "Mostly a human tool; the agent's equivalent is procedural part "
                  "building via execute_luau.",
        "free_alternative": "itself",
    },
}


def plugin_dirs():
    """Every directory Studio loads user plugins from, if it exists."""
    base = os.path.join(paths.local_appdata(), "Roblox", "Plugins")
    out = []
    if os.path.isdir(base):
        out.append(base)
    env = os.environ.get("RBFORGE_PLUGIN_DIR")
    if env and os.path.isdir(paths.expand(env)) and paths.expand(env) not in out:
        out.append(paths.expand(env))
    return out


def _installed_names(dirs):
    names = []
    for base in dirs:
        for entry in sorted(os.listdir(base)):
            low = entry.lower()
            if low.endswith(".rbxm") or low.endswith(".rbxmx"):
                names.append(entry.rsplit(".", 1)[0])
            elif os.path.isdir(os.path.join(base, entry)):
                names.append(entry)
                # local plugins are often saved as Folder/Plugin.rbxm
                for inner in os.listdir(os.path.join(base, entry)):
                    if inner.lower().endswith((".rbxm", ".rbxmx")):
                        names.append(inner.rsplit(".", 1)[0])
    return names


def status():
    """What is installed, what it changes, and the free path either way."""
    dirs = plugin_dirs()
    if not dirs:
        return {
            "plugin_dirs": [],
            "installed": [],
            "known": [],
            "unknown_count": 0,
            "note": "No user plugin folder found - Studio has no third-party "
                    "plugins installed. Every RobloxForge workflow has a free "
                    "path that needs none.",
            "free_path_is_default": True,
        }

    names = _installed_names(dirs)
    lowered = [n.lower().replace("_", " ").replace("-", " ") for n in names]
    matched_ids = set()
    known = []
    for key, meta in KNOWN.items():
        hits = [n for n, low in zip(names, lowered)
                if any(tok in low for tok in meta["match"])]
        if not hits:
            continue
        matched_ids.add(key)
        known.append({
            "id": key,
            "label": meta["label"],
            "price": meta["price"],
            "detected_as": sorted(set(hits)),
            "gives": meta["gives"],
            "bridge": meta["bridge"],
            "free_alternative": meta["free_alternative"],
        })

    unknown = [n for n, low in zip(names, lowered)
               if not any(any(tok in low for tok in m["match"]) for m in KNOWN.values())]
    paid_present = [k["label"] for k in known if k["price"] in ("paid", "freemium")]

    if not names:
        note = ("Plugin folder exists but is empty. Nothing optional is required; "
                "the free path in references/free-stack.md covers every workflow.")
    elif paid_present:
        note = ("Paid/freemium tools detected (%s). Use them because the user "
                "already has them, never make them a requirement, and keep the "
                "free alternative in mind." % ", ".join(paid_present))
    else:
        note = "Only free plugins detected. No purchase is needed for any workflow."

    return {
        "plugin_dirs": dirs,
        "installed": sorted(set(names)),
        "known": known,
        "unknown_count": len(set(unknown)),
        "note": note,
        "free_path_is_default": not known,
    }


def render(info):
    lines = ["Studio plugins (optional, never required)"]
    if not info["plugin_dirs"]:
        lines.append("  none installed - %s" % info["note"])
        return "\n".join(lines)
    for item in info["known"]:
        lines.append("  %-26s %-12s %s" % (item["label"], item["price"],
                                           item["gives"]))
        lines.append("  %-26s bridge: %s" % ("", item["bridge"]))
        lines.append("  %-26s free alternative: %s" % ("", item["free_alternative"]))
    if info["unknown_count"]:
        lines.append("  %d unrecognised plugin(s) also present" % info["unknown_count"])
    lines.append("  " + info["note"])
    return "\n".join(lines)
