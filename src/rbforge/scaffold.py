"""Scaffold a new project: a working starter kit, not an empty folder.

`templates/starter` is a complete small game loop - explicit service loader, a named remote registry,
a rate limiter, a data service that cannot overwrite a profile it failed to read, a cleanup helper, a
HUD, and offline specs for every pure module. A new project starts from code that already passes the
gate and already runs, so the first session changes a working loop instead of inventing plumbing.
"""
import os

from .errors import ForgeError
from . import paths
from . import planning

_CHECKLIST = """# Verification checklist ({genre})

What you start with (already working - change it, do not rebuild it):

- `src/server/Main.server.luau` - starts services in a fixed order, owns the player lifecycle
- `src/server/Services/DataService.luau` - load/save; a failed read is never treated as a new player
- `src/server/Services/GameService.luau` - the sample loop: intent -> validate -> change -> publish
- `src/shared/Net.luau` - every remote, named in one list
- `src/shared/RateLimiter.luau`, `Cleaner.luau`, `Rules.luau` - reusable, unit tested
- `src/client/Main.client.luau` - HUD and input; shows server state, sends intents
- `tests/*.spec.luau` - offline specs (Lune); `tests/Starter.server.luau` - live server test

Run `rbforge check .` first - format, lint, types, unit specs and structure without opening Studio.
Then put the code in a place - `rbforge push ALL --project default.project.json` into an open Studio
Baseplate, or `rojo build dev.project.json -o game.rbxl` for a standalone test place with a floor and
a spawn - press Play and run
`rbforge servertest tests/Starter.server.luau --ready workspace.ServerReady=true`.

Slice 1 is DONE only when every box below has real evidence:
- [ ] `rbforge check .` reports pass (or states exactly what it skipped)
- [ ] `rbforge servertest` reports PASS in a Play session
- [ ] player spawns
- [ ] core action works end-to-end (playtested)
- [ ] progression step works
- [ ] failure/death behavior works
- [ ] console clean during all of the above
- [ ] screenshot captured AND inspected
- [ ] rb_verify_receipt written

Expand only after proof. One system per change; add a spec for every new pure module.
"""

# Pinned toolchain so the gate means the same thing on every machine.
# `rokit install` reads this; absent tools are reported as skips, not failures.
_ROKIT = """# Pinned Luau toolchain (rbforge scaffold). Optional: the gate degrades to
# the structural rung when these are absent.
[tools]
rojo = "rojo-rbx/rojo@7.7.1"
selene = "Kampfkarren/selene@0.32.0"
stylua = "JohnnyMorganz/StyLua@2.6.0"
luau-lsp = "JohnnyMorganz/luau-lsp@1.70.1"
lune = "lune-org/lune@0.11.1"
"""

_LUAURC = """{
  "languageMode": "strict",
  "lint": { "*": true },
  "aliases": { "Shared": "src/shared" }
}
"""

_SELENE = 'std = "roblox"\n'

_STYLUA = """indent_type = "Tabs"
column_width = 120
quote_style = "AutoPreferDouble"
"""

_GITIGNORE = """# Build output and editor state
*.rbxl
*.rbxlx
*.rbxl.lock
*.rbxlx.lock
sourcemap.json
/build/
"""

# Each service gets its own folder node instead of a `$path` on the service itself: Rojo then owns
# only `Shared`, `Server` and `Client`, and leaves everything else in the place alone - the map,
# the lighting, models placed by hand.
_PROJECT = """{
  "name": "{genre}-game",
  "tree": {
    "$className": "DataModel",
    "ReplicatedStorage": {
      "Shared": { "$path": "src/shared" }
    },
    "ServerScriptService": {
      "Server": { "$path": "src/server" }
    },
    "StarterPlayer": {
      "StarterPlayerScripts": {
        "Client": { "$path": "src/client" }
      }
    }
  }
}
"""


# A standalone test place: the same code plus a floor and a spawn, so `rojo build` gives something
# a character can stand in. `default.project.json` stays code-only on purpose.
# Placement goes through `CFrame`: Rojo writes only serialized properties and silently drops `Position`,
# which left the floor and the spawn both at the origin with the spawn buried in the floor (found by
# the world-audit probe, 2026-11-18).
_DEV_PROJECT = """{
  "name": "{genre}-game-dev",
  "tree": {
    "$className": "DataModel",
    "Workspace": {
      "Baseplate": {
        "$className": "Part",
        "$properties": {
          "Anchored": true,
          "Size": [512, 4, 512],
          "CFrame": [0, -2, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1],
          "Color": [0.36, 0.38, 0.42],
          "Material": "Concrete"
        }
      },
      "SpawnLocation": {
        "$className": "SpawnLocation",
        "$properties": {
          "Anchored": true,
          "Size": [8, 1, 8],
          "CFrame": [0, 0.5, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1]
        }
      }
    },
    "ReplicatedStorage": {
      "Shared": { "$path": "src/shared" }
    },
    "ServerScriptService": {
      "Server": { "$path": "src/server" }
    },
    "StarterPlayer": {
      "StarterPlayerScripts": {
        "Client": { "$path": "src/client" }
      }
    }
  }
}
"""


def starter_dir():
    return os.path.join(paths.templates_dir(), "starter")


def _starter_files():
    """(relative path, text) for every file of the starter kit."""
    root = starter_dir()
    out = []
    for base, _dirs, names in os.walk(root):
        for name in sorted(names):
            full = os.path.join(base, name)
            with open(full, encoding="utf-8") as fh:
                out.append((os.path.relpath(full, root).replace(os.sep, "/"), fh.read()))
    if not out:
        raise ForgeError("RBF-ARG-002", "starter kit is missing: %r" % root,
                         hint="reinstall RobloxForge; templates/starter ships with it")
    return sorted(out)


# One receipt per task, copied to docs/evidence/<ID>.md. A production project closed its plan rows with
# these: the commit that was proven, what was seen, what was not checked.
_RECEIPT = """# <ID> - <what was proven>

Result: PASS
Tested SHA: <40-hex commit the proof ran on>
Slot: <test save slot, or "owner">
Place: <place id> v<PlaceVersion>, Edit|Play

## Steps

1. <command or action, exactly as run>

## Observed

- <numbers, console lines, bot trace excerpts>
- Not checked: <what this receipt does not prove>

## Captures

- <docs/evidence/<ID>/name.jpg> - looked at: <what it shows>

<!-- Commit the code first, prove that commit, then commit this file. The plan row's Evidence cell reads
`cmd:<the Verify command> @ <sha> exit=<n>`. -->
"""


def scaffold(path, genre="generic"):
    genre = planning.resolve(genre)
    if os.path.isdir(path) and os.listdir(path):
        raise ForgeError("RBF-ARG-002", "target not empty: %r" % path,
                         hint="scaffold into a fresh directory")
    files = {rel: text for rel, text in _starter_files()}
    files.update({
        "VERIFY.md": _CHECKLIST,
        "docs/evidence/TEMPLATE.md": _RECEIPT,
        "rokit.toml": _ROKIT,
        ".luaurc": _LUAURC,
        "selene.toml": _SELENE,
        "stylua.toml": _STYLUA,
        ".gitignore": _GITIGNORE,
        # Rojo map: without it every `require` is unknown to the typechecker, and the project cannot
        # be built from disk at all.
        "default.project.json": _PROJECT,
        "dev.project.json": _DEV_PROJECT,
    })
    for rel, content in files.items():
        full = os.path.join(path, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content.replace("{genre}", genre))
    return {"path": os.path.abspath(path), "genre": genre,
            "files": sorted(files),
            "next": "rbforge check <path>, then put it in a place and run the live server test (VERIFY.md)"}


def new_project(path, genre="generic", premise=""):
    """One entry point for "make me a game": scaffold + slice plan + next steps.

    A user with no Roblox experience cannot sequence scaffold -> plan -> gate ->
    playtest. This does the first three and returns an ordered list of what the
    agent should do next, so the first session starts with intent instead of
    setup.
    """
    from . import optimize

    genre = planning.resolve(genre)
    result = scaffold(path, genre)
    plan = planning.vertical_slice(genre, premise or "a first playable slice")
    # A new project starts small: the profile is computed from the real source, so it reports
    # level A only and says so instead of attaching a pipeline nobody needs yet.
    guidance = optimize.profile(path, premise or genre)

    lines = [
        "# Plan: %s" % (premise or "first slice"),
        "",
        "Genre: %s. Built by RobloxForge; read this before touching the place." % genre,
        "",
        "## What already works",
        "The scaffold is a running loop, not a stub: a service loader, named remotes, a rate limiter, safe",
        "load/save, a HUD and tests (see VERIFY.md). Replace the sample action in",
        "`src/server/Services/GameService.luau` with this game's and keep the shape: intent in, server",
        "decides, state published, client shows it.",
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
        "rbforge audit .        # ranked health report; run before changing code you did not write",
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
            "rbforge push ALL --project <path>/default.project.json   # put the starter kit in the place",
            "Play, then: rbforge servertest <path>/tests/Starter.server.luau --ready workspace.ServerReady=true",
            "Build step 1 of PLAN.md by changing the working starter loop, then playtest it.",
        ],
        "free": "No purchase is needed for any step. See references/free-stack.md.",
    }
