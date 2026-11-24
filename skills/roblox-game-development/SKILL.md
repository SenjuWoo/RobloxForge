---
name: roblox-game-development
description: Use when building, fixing, testing, or reviewing any Roblox game or Roblox Studio work - Roblox, Roblox Studio, Luau, obby, tycoon, simulator, Roblox UI, Roblox combat, DataStore, RemoteEvent, Roblox multiplayer, Studio MCP. Router skill; load the matching reference for the task.
---

# Roblox Game Development (RobloxForge)

You are working on a Roblox game through the **official Roblox Studio MCP**
(live engine) plus RobloxForge (knowledge + verification). Non-negotiables
first; references carry the detail.

## Start here

| Situation | First move |
|---|---|
| New game | `rbforge new <dir> --genre <genre> --premise "<one sentence>"` - writes a **working** starter loop (service loader, named remotes, rate limiter, safe load/save, HUD, tests) and a slice plan. Change that loop; do not rebuild plumbing. Genres: obby, simulator, tycoon, shooter, round, towerdefense, rpg, horror, survival, generic. |
| Existing game, any origin | `rbforge audit <dir>` before the first edit - a ranked list (player-data loss, exploitable remotes, runtime faults, missing tests, monoliths, cost) and every server remote handler with the guards it shows. Then `references/existing-projects.md`. The code that is already there is evidence of what was built, not of what works: do not copy its patterns forward without asking whether they were good ones. |
| A place that exists only in Studio | inspect with the official MCP (`search_game_tree`, `script_grep`), then the same order of concerns as the audit. |

Two defaults that weak output gets backwards: **the static world is authored in Edit and saved
with the place** - a server script builds only what differs per session - and **characters are
animated by clips through the Animator**; per-frame procedural rigs are a measured exception
(`references/architecture.md`, `references/animation.md`).

## Where the knowledge is

Twenty-four specialist skills are installed beside this one. They are typechecked against the
current API and are the authority on API facts; the references in this skill are workflow, field
evidence and the rules that decide whether the game survives. Load the specialist for the system
you are building:

| Building | Specialist skill | This skill's reference |
|---|---|---|
| Module layout, loader, replication, streaming | `roblox-architecture` | `references/architecture.md` |
| Remotes, validation, exploits | `roblox-networking`, `roblox-security` | `references/security-networking.md` |
| Saving, sessions, migrations | `roblox-data-stores` | `references/persistence.md` |
| Currency, XP, rounds, combat, inventory, shops | `roblox-game-systems` | `references/development-loop.md`, `references/game-design.md` |
| NPCs, pathfinding, enemies | `roblox-npc-ai` | `references/performance.md` (crowds) |
| Rigs, animation, viewmodels | `roblox-characters-animation` | `references/animation.md` |
| Screens, HUD, devices | `roblox-ui`, `roblox-input` | `references/ui-mobile.md`, `references/ui-craft.md` |
| Maps, terrain, lighting | `roblox-world-building` | `references/worldbuilding-lighting.md` |
| Moving parts, vehicles, constraints | `roblox-physics` | `references/sharp-edges.md` |
| Sound | `roblox-audio` | `references/assets.md` |
| Purchases, passes, products | `roblox-monetization` | - |
| Chat, filtering | `roblox-text-chat` | - |
| Places, servers, queues | `roblox-teleport-matchmaking` | - |
| Frame time, memory | `roblox-performance` | `references/performance.md`, `references/optimization-levels.md` |
| Luau types and idioms | `roblox-luau` | `references/typing-luau.md`, `references/current-engine.md` |
| Tests | `roblox-testing` | `references/testing-debugging.md` |
| Review before merge | `roblox-code-review` | `rbforge audit`, `rbforge review --kind all` |
| Driving Studio through the MCP | `roblox-studio-mcp` | `references/studio-mcp.md`, `references/live-iteration.md` |
| Analytics, live ops, Open Cloud, toolchain | `roblox-analytics-liveops`, `roblox-open-cloud`, `roblox-tooling` | `references/tooling.md` |

If a specialist and a reference here disagree on an API fact, the specialist and the official docs
(`rb_docs_search`) win; report the disagreement.

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
- `conflict` - someone edited that script in Studio after the last push; nothing was written. Read the
  Studio source (`script_read`), carry the change into the file, push again. Use `--force` only when the
  Studio edit should be discarded; the Studio copy is cloned into `ServerStorage.rbforge_backups` first.
- `backed_up` - push replaced a source it had not written (a first push, or `--force`) and kept the old one.
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

Studio ships 17 maintained `rbx-*` skills (2026-11-24) and four subagent types. They encode
current APIs that model memory gets wrong.

```
list_roblox_skills                                  -> what is actually available right now
get_roblox_skill {"skill_name": "rbx-input-action-system"}  -> read it BEFORE writing input code
subagent(explore)                 -> map an unfamiliar place without flooding context
subagent(unit_test)               -> run Luau unit tests
subagent(playtest)                -> scenario testing; it drives start_stop_play itself
```

Route by need in `references/assistant-skills.md`. Never claim you used one
without calling it.

## References (load only what the task needs)

**Inspecting a live place?** Never improvise inspection Luau: `rbforge probe <name>` / MCP
`rb_studio_probe` returns a reviewed snippet (console, gui-overflow, ray-all, box-scan, hide/restore,
camera-pin, capture-quality, goto, scene-audit, sound-audit, ui-audit, player-state, whereis, remotes, perf)
for `execute_luau`.
Before Studio, run `rbforge review --kind traps` (MCP `rb_traps_review`).

- `references/debugging-playbook.md` - START HERE when something looks or behaves wrong: symptom -> cause -> probe, and the fix protocol
- `references/existing-projects.md` - taking over a codebase: audit order, characterization tests, strangler refactors, patterns to question
- `references/current-engine.md` - what model memory gets wrong: replaced APIs and engine features newer than most training data
- `references/studio-mcp.md` - all 41 live tools, exact argument quirks, subagents, video capture
- `references/live-iteration.md` - code loop (`rbforge push`) vs world loop (Edit + `save_place`), require-cache rebuilds, capture limits
- `references/development-loop.md` - the vertical-slice method per genre
- `references/architecture.md` - ownership, the explicit loader, lifetimes and cleanup, authored vs generated worlds, dependency injection
- `references/security-networking.md` - the handler shape, validation layers, when buffers are worth it
- `references/persistence.md` - a failed read is not a new player; ProfileStore session locking, migrations, test doubles
- `references/ui-mobile.md` - plain-instance UI, safe areas, touch, input; Fusion 0.3 only if the project uses it
- `references/ui-craft.md` - HUD craft: what reads as agent slop and what to build instead
- `references/animation.md` - choosing clips vs procedural, joints on current avatars, first-person viewmodels
- `references/sightlines-and-openings.md` - openings show the world: diagnose flat colour/screen artefacts; case notes for panelled shells
- `references/testing-debugging.md` - five-rung verification ladder, console triage
- `references/sharp-edges.md` - engine traps, each tagged docs / live / field
- `references/game-design.md` - loop design and game-feel ("juice") matrices
- `references/performance.md` - MicroProfiler-first optimization, known traps
- `references/optimization-levels.md` - pick level A/B/C from project evidence; no universal budgets
- `references/typing-luau.md` - take a `--!strict` project to zero `luau-lsp` errors: root causes, syntax that does not exist, and which boundaries deserve a cast
- `references/assets.md` - generative 3D/materials, procedural prop kits, Creator Store sanitization
- `references/worldbuilding-lighting.md` - terrain generators and lighting presets
- `references/free-stack.md` - the $0 rule, what is free, what to never pay for
- `references/beginner-guide.md` - zero-experience walkthrough and vocabulary
- `references/tooling.md` - pinned Rokit toolchain and what each tool buys you
- `references/assistant-skills.md` - routing to Roblox's 17 built-in rbx-* skills

## When unsure about an API

Do not trust model memory. `rb_docs_search "TweenService:Create"` against the
official creator-docs cache, then `rb_docs_read` the hit. If the cache is absent,
`rbforge docs update` once (sparse clone, ~27MB) - or `get_roblox_skill` `rbx-docs-search`
for the live web fetch. Current official documentation beats your training data
every time.
