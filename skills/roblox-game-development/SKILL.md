---
name: roblox-game-development
description: Use when building, fixing, testing, or reviewing any Roblox game or Roblox Studio work - Roblox, Roblox Studio, Luau, obby, tycoon, simulator, Roblox UI, Roblox combat, DataStore, RemoteEvent, Roblox multiplayer, Studio MCP. Router skill; load the matching reference for the task.
---

# Roblox Game Development (RobloxForge)

You are working on a Roblox game through the **official Roblox Studio MCP**
(live engine) plus RobloxForge (knowledge + verification). Non-negotiables
first; references carry the detail.

## What counts as proof

| Level | Evidence behind it |
|---|---|
| `unverified` | nothing |
| `static_only` | `rbforge check` passed; no runtime evidence |
| `playtest_claimed` | you say you tested; RobloxForge observed nothing |
| `playtest_observed_partial` | a real run, but a test, console read, image or inspection is missing |
| `playtested_with_errors` | an observed run reported errors |
| `verified_playtest` | a test passed, the console was read clean, and Studio returned an image you inspected |

- A successful tool call is not proof of gameplay. Read the console; look at the image.
- **Screenshot captured is not screenshot inspected.** If you did not look, it is partial.
- Unknown evidence (no console output, no image) means partial or unverified - never "clean".
- `rb_collect_evidence` is the only way to record a real observation; `rb_verify_receipt` needs its
  `observation_id` and refuses a receipt for another project or scenario.
- Deep engine detail beyond this skill: read `KNOWLEDGE-PATH.txt` next to this SKILL.md to find
  `knowledge/vendor/roblox-skills/<topic>/SKILL.md` (MIT, third-party). If that file says the pack was
  not shipped, fall back to this skill's own `references/` and the official Creator Hub docs.

## Safe push

`rbforge push` writes studio sources and reads them back:

- `synced` - bytes match what Studio stored.
- `hierarchy` - the project declares a class the place does not have; fix it, never force it.
- `rolled_back` / `rollback_failed` - the write failed and the previous source was (or was not) restored.
  A `rollback_failed` means **stop**: the original may sit in `ServerStorage.rbforge_backups`.
- A per-file result is not a transaction: a batch can be partly applied. Push, then verify the ones
  that failed before touching anything else.

## The loop (never skip steps)

```
rb_doctor / rb_capabilities   -> is Studio actually connected? (probe, don't assume)
rbforge check .               -> offline gate: format, lint, types, structure (types need `rbforge types fetch` once)
inspect current place          -> search_game_tree / inspect_instance BEFORE writing anything
plan smallest vertical slice   -> one playable loop, not the whole game
implement                      -> server owns truth; client owns input/presentation
rbforge check .               -> re-run after every edit batch (seconds, not a playtest)
playtest via official MCP      -> start_stop_play, character_navigation, get_console_output
read console output            -> errors are data, fix them
screen_capture + INSPECT       -> only claim visual success if you actually looked
fix, re-run, THEN expand       -> vertical slice proven before adding systems
```

## When to ask for optimization guidance

Run `rbforge optimize --premise "<what the game is>"` (JSON, or `--text`) at three moments only:

- when a project starts - `rbforge new` already writes the profile into `PLAN.md`;
- when a new system lands that could dominate cost (streaming, NPC crowds, physics assemblies,
  procedural generation, persistence);
- when something is measurably slow, before choosing a fix.

It returns level A always, level B only for what the request and source actually contain, and the
measurement level C would need. It is routing, not proof: nothing in it says a game is optimized,
and a small obby gets no pipeline. If the root has no readable source it says so instead of guessing.

## Hard rules

1. **Vertical slices only.** Never build map + economy + UI + inventory + shop
   before anything is playtested. One loop, proven, then expand.
2. **Server owns truth.** Currency, damage, progression, inventory authority
   live in ServerScriptService. A client request is a *suggestion* the server
   validates. `RemoteEvent != authorization`.
3. **Probe, don't assume.** Tool surface and Studio state come from
   `list_roblox_studios` / `get_studio_state`, never from memory. The surface
   moves with Studio updates.
4. **"Scripts exist" is not "game works".** Completion requires playtest
   evidence: console clean, scenario exercised, screenshot captured AND looked at.
5. **Check `rb_capabilities` before playtesting.** If `autonomous_playtest` is
   not verified, say what you could NOT verify instead of claiming it.
6. **Gate before the engine.** Run `rbforge check .` (or `scripts/rbx_check.py`)
   after every edit batch and before any `start_stop_play`. A Studio boot to
   discover a typo costs 10-30s and a context window; the gate costs
   milliseconds. `incomplete` means checks were skipped - never report that as
   verified.
7. **Every mutation is reversible.** Before a batch of `execute_luau` (Edit) or
   `multi_edit` calls, record what you are about to change and how to undo it.
   Studio's ChangeHistoryService is the undo; name the waypoint. A failed slice
   is rolled back, not patched forward.
8. **$0 by default.** Roblox Studio, the official MCP, and everything this skill
   recommends are free. Never buy, never ask the user to buy, never require a
   paid plugin or marketplace asset. Generated assets, part kits and the free
   Creator Store pool cover every workflow. See `references/free-stack.md`.

## Working with someone who has never made a game

Assume zero Roblox experience unless told otherwise — and do not turn that into
a tutorial. You operate Studio; they describe what they want. One instruction at
a time, in plain words, with the exact click ("Studio → Assistant → `...` →
Manage MCP Servers → Enable"). Never hand them code to paste. Full playbook:
`references/beginner-guide.md`.

## Ask Roblox before you write (cheapest win available)

Studio ships 14 maintained `rbx-*` skills and four subagent types. They encode
current APIs that model memory gets wrong.

```
list_skills                       -> what is actually available right now
skill "rbx-input-action-system"   -> read it BEFORE writing input code
subagent(explore)                 -> map an unfamiliar place without flooding context
subagent(unit_test)               -> run Luau unit tests
subagent(playtest)                -> scenario testing; it drives start_stop_play itself
```

Route by need in `references/assistant-skills.md`. Never claim you used one
without calling it.

## References (load only what the task needs)

**Inspecting a live place?** Never improvise inspection Luau: `rbforge probe <name>` / MCP
`rb_studio_probe` returns a reviewed snippet (console, gui-overflow, ray-all, box-scan, hide/restore,
camera-pin, scene-audit, ui-audit, player-state, whereis, remotes, perf) for `execute_luau`.
Before Studio, run `rbforge review --kind traps` (MCP `rb_traps_review`).

- `references/debugging-playbook.md` - START HERE when something looks or behaves wrong: symptom -> cause -> probe, and the fix protocol
- `references/studio-mcp.md` - all 34 live tools, exact argument quirks, subagents
- `references/live-iteration.md` - disk-to-Studio sync, require-cache rebuilds, capture limits, camera restore
- `references/development-loop.md` - the vertical-slice method per genre
- `references/architecture.md` - ownership, three-stage loader, dependency injection
- `references/security-networking.md` - remotes, buffer serialization, validation
- `references/persistence.md` - ProfileStore session locking, migrations, test doubles
- `references/ui-mobile.md` - Fusion 0.3 scoped UI, safe area, touch
- `references/ui-craft.md` - HUD craft: what reads as agent slop and what to build instead
- `references/animation.md` - procedural gait and first-person viewmodels on R15
- `references/sightlines-and-openings.md` - openings show the world: diagnose flat colour/screen artefacts and seal them with structure
- `references/testing-debugging.md` - five-rung verification ladder, console triage
- `references/sharp-edges.md` - the traps that break AI-built games
- `references/game-design.md` - loop design and game-feel ("juice") matrices
- `references/performance.md` - MicroProfiler-first optimization, known traps
- `references/optimization-levels.md` - pick level A/B/C from project evidence; no universal budgets
- `references/typing-luau.md` - take a `--!strict` project to zero `luau-lsp` errors: root causes, syntax that does not exist, and which boundaries deserve a cast
- `references/assets.md` - generative 3D/materials, procedural prop kits, Creator Store sanitization
- `references/worldbuilding-lighting.md` - terrain generators and lighting presets
- `references/free-stack.md` - the $0 rule, what is free, what to never pay for
- `references/beginner-guide.md` - zero-experience walkthrough and vocabulary
- `references/tooling.md` - pinned Rokit toolchain and what each tool buys you
- `references/assistant-skills.md` - routing to Roblox's 14 built-in rbx-* skills

## When unsure about an API

Do not trust model memory. `rb_docs_search "TweenService:Create"` against the
official creator-docs cache, then `rb_docs_read` the hit. If the cache is absent,
`rbforge docs update` once (sparse clone, ~27MB) - or `skill "rbx-docs-search"`
for the live web fetch. Current official documentation beats your training data
every time.
