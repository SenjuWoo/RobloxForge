# Roblox external toolchain — optional, not mandatory

Studio-native + official MCP is enough for prototypes.

For source-controlled/serious projects, current Roblox tooling can materially
improve AI reliability.

## Recommended roles

- **Rokit** — toolchain manager; prefer over archived Aftman for new setups.
- **Rojo** — filesystem/Git <-> Roblox project mapping and sync.
- **StyLua** — Luau formatter.
- **Selene** — Luau linter with Roblox-aware standard library.
- **luau-lsp** — editor/LSP analysis with Roblox sourcemaps.
- **Wally** — package manager.
- **wally-package-types** — generated types for Wally dependencies.
- **Lune** — standalone Luau runtime and Roblox data tooling.
- **run-in-roblox** — run scripts/places in Studio from CLI for automation.

## Current researched versions (verified 2026-11-01 against GitHub releases)

Treat these as a snapshot; verify before pinning a new project.
- Rojo 7.7.1
- Rokit 1.2.0
- StyLua 2.6.0
- Selene 0.32.0
- luau-lsp 1.70.1
- Wally 0.3.2
- Lune 0.11.1
- wally-package-types 1.7.0
- run-in-roblox 0.3.0

Pinned form for a project lives in `templates/source-controlled/rokit.toml`
(`rokit install` reads it). Copy it, do not hand-edit versions from memory.

The Forge checkout pins the same set at its own root `rokit.toml` and can
install it with `tools/install-toolchain.ps1` (or `Install.ps1 -Toolchain`).
That also adds a global rokit manifest, so the tools resolve in *any*
directory — `rbforge check` runs in a fixture dir, not a project dir, and a
bare shim with no manifest errors instead of skipping.

## The gate works without any of this

`rbforge check` degrades honestly: each missing tool is reported as `skip`, and
the overall status becomes `incomplete` rather than a false pass. So a
Studio-native prototype can run the structure rung (rung 3) with zero installs,
and still catch missing Rojo paths, unanchored geometry and client-side
authority. Add the toolchain when you want rungs 1-2, not because a checklist
demands it.

## Do not auto-install everything

Use toolchain when:
- project already has `default.project.json` / Rojo,
- source ownership/Git matters,
- static analysis catches real issues,
- CI automation is desired.

For a user asking "make me an obby in Studio," do not spend the first 20 minutes
installing a full external stack.
