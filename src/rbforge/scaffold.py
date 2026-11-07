"""Scaffold a new project from a genre template.

Writes the minimal sane layout (see skills references/architecture.md):
server systems module, shared config, client HUD stub, verification
checklist. Studio-native projects get .server/.client/.lua naming that
Rojo understands too.
"""
import os

from .errors import ForgeError

_SERVER = '''--!strict
-- Server entry point. Systems own authoritative state.
local Config = require(game:GetService("ReplicatedStorage"):WaitForChild("Config"))

print("[server] booted with genre=" .. Config.Genre)
'''

_CLIENT = '''--!strict
-- Client presentation. Listens to state; owns no truth.
local Players = game:GetService("Players")
local player = Players.LocalPlayer

local hud = Instance.new("ScreenGui")
hud.Name = "Hud"
hud.ResetOnSpawn = false
hud.Parent = player:WaitForChild("PlayerGui")

local label = Instance.new("TextLabel")
label.Size = UDim2.fromOffset(200, 40)
label.Position = UDim2.fromOffset(16, 16)
label.BackgroundTransparency = 0.4
label.TextColor3 = Color3.new(1, 1, 1)
label.Text = "Ready"
label.Parent = hud
'''

_CONFIG = '''--!strict
-- Shared contracts/config. Required by both sides.
return {
	Genre = "{genre}",
	Version = "0.1.0",
}
'''

_CHECKLIST = """# Verification checklist ({genre})

Run `rbforge check .` first - it catches syntax, types, missing Rojo paths and
unanchored geometry without opening Studio. Then:

Slice 1 is DONE only when every box below has real evidence:
- [ ] `rbforge check .` reports pass (or states exactly what it skipped)
- [ ] player spawns
- [ ] core action works end-to-end (playtested)
- [ ] progression step works
- [ ] failure/death behavior works
- [ ] console clean during all of the above
- [ ] screenshot captured AND inspected
- [ ] rb_verify_receipt written

Expand only after proof.
"""

# Pinned toolchain so the gate means the same thing on every machine.
# `rokit install` reads this; absent tools are reported as skips, not failures.
_ROKIT = '''# Pinned Luau toolchain (rbforge scaffold). Optional: the gate degrades to
# the structural rung when these are absent.
[tools]
rojo = "rojo-rbx/rojo@7.7.1"
selene = "Kampfkarren/selene@0.32.0"
stylua = "JohnnyMorganz/StyLua@2.6.0"
luau-lsp = "JohnnyMorganz/luau-lsp@1.70.1"
lune = "lune-org/lune@0.11.1"
'''

_LUAURC = '''{
  "languageMode": "strict",
  "lint": { "*": true },
  "aliases": { "Shared": "src/shared" }
}
'''

_SELENE = 'std = "roblox"\n'

_STYLUA = '''indent_type = "Tabs"
column_width = 120
quote_style = "AutoPreferDouble"
'''


_PROJECT = """{
  "name": "{genre}",
  "tree": {
    "$className": "DataModel",
    "ReplicatedStorage": { "$path": "src/shared" },
    "ServerScriptService": { "$path": "src/server" },
    "StarterPlayer": {
      "StarterPlayerScripts": { "$path": "src/client" }
    }
  }
}
"""


def scaffold(path, genre="generic"):
    genre = (genre or "generic").lower()
    if genre not in ("generic", "obby", "simulator", "tycoon"):
        raise ForgeError("RBF-ARG-001", "unknown genre %r" % genre,
                         hint="one of: generic, obby, simulator, tycoon")
    if os.path.isdir(path) and os.listdir(path):
        raise ForgeError("RBF-ARG-002", "target not empty: %r" % path,
                         hint="scaffold into a fresh directory")
    dirs = {
        os.path.join(path, "src", "server"): None,
        os.path.join(path, "src", "shared"): None,
        os.path.join(path, "src", "client"): None,
    }
    files = {
        os.path.join(path, "src", "server", "Main.server.lua"): _SERVER,
        os.path.join(path, "src", "shared", "Config.lua"): _CONFIG,
        os.path.join(path, "src", "client", "Hud.client.lua"): _CLIENT,
        os.path.join(path, "VERIFY.md"): _CHECKLIST,
        os.path.join(path, "rokit.toml"): _ROKIT,
        os.path.join(path, ".luaurc"): _LUAURC,
        os.path.join(path, "selene.toml"): _SELENE,
        os.path.join(path, "stylua.toml"): _STYLUA,
        # Rojo map: without it every `require` is unknown to the typechecker, and the project cannot
        # be built from disk at all.
        os.path.join(path, "default.project.json"): _PROJECT,
    }
    for d in dirs:
        os.makedirs(d, exist_ok=True)
    for f, content in files.items():
        with open(f, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content.replace("{genre}", genre))
    return {"path": os.path.abspath(path), "genre": genre,
            "files": sorted(os.path.relpath(f, path).replace(os.sep, "/") for f in files),
            "next": "open Studio with a Baseplate, then follow VERIFY.md slice order"}


def new_project(path, genre="generic", premise=""):
    """One entry point for "make me a game": scaffold + slice plan + next steps.

    A user with no Roblox experience cannot sequence scaffold -> plan -> gate ->
    playtest. This does the first three and returns an ordered list of what the
    agent should do next, so the first session starts with intent instead of
    setup.
    """
    from . import optimize, planning

    result = scaffold(path, genre)
    plan = planning.vertical_slice(genre, premise or "a first playable slice")
    # A new project starts small: the profile is computed from the real (empty-ish) source, so it
    # reports level A only and says so instead of attaching a pipeline nobody needs yet.
    guidance = optimize.profile(path, premise or genre)

    lines = [
        "# Plan: %s" % (premise or "first slice"),
        "",
        "Genre: %s. Built by RobloxForge; read this before touching the place." % genre,
        "",
        "## Core loop",
        plan.get("core_loop", ""),
        "",
        "## Who owns the truth",
    ]
    for what, who in (plan.get("authority") or {}).items():
        lines.append("- **%s**: %s" % (what, who))
    lines += ["", "## Build order (do NOT skip ahead)"]
    for i, item in enumerate(plan.get("build_order") or [], 1):
        lines.append("%d. %s" % (i, item))
    lines += ["", "## Prove it before expanding"]
    for item in plan.get("verification") or []:
        lines.append("- [ ] %s" % item)
    if plan.get("anti_pattern"):
        lines += ["", "## Do not do this", plan["anti_pattern"]]
    lines += [
        "",
        "## Optimization (recheck when a new system lands)",
        optimize.render(guidance),
        "",
        "## Commands",
        "```",
        "rbforge check .        # offline gate; run before every playtest",
        'rbforge optimize --premise "<what this game is>"   # levels for THIS project',
        "```",
        "Rungs 1-3 must be clean (or their skips named) before any Studio playtest.",
        "",
    ]

    plan_path = os.path.join(path, "PLAN.md")
    with open(plan_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))

    return {
        "optimization": guidance,
        "path": result["path"],
        "genre": genre,
        "files": result["files"] + [os.path.relpath(plan_path, path).replace(os.sep, "/")],
        "plan": plan_path,
        "next_steps": [
            "Open Roblox Studio -> New -> Baseplate (leave it open).",
            "In Studio: Assistant -> '...' -> Manage MCP Servers -> Enable Studio as MCP server.",
            "rbforge doctor            # confirm the handshake before building",
            "rbforge check <path>      # gate before any Studio work",
            "Build step 1 of PLAN.md only, then playtest it.",
        ],
        "free": "No purchase is needed for any step. See references/free-stack.md.",
    }
