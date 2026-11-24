# Roblox-authored Assistant skills as specialist accelerators

Studio ships skills maintained by Roblox. When the official Studio MCP exposes
`list_roblox_skills` and `get_roblox_skill`, they act like domain sub-agents for
Hermes/Claude/Codex. Their old names, before Studio builds of late 2026:
`list_skills` and `skill` (old names; a client still calling them gets "unknown tool").

## Route by problem

Discover first: `list_roblox_skills` returns what this Studio build exposes, with
when to use each; a creator's own skills appear in the same list. The set below
was verified live on 2026-11-24 (17 skills; 14 on 2026-11-01).

| Need | Load |
|---|---|
| any input/controls work — keyboard, mouse, gamepad, touch, rebinding, InputAction | `rbx-input-action-system` (load BEFORE writing input code) |
| runtime bug, breakpoints, thread inspection | `rbx-debug` |
| unit tests for ModuleScripts | `rbx-unit-test` |
| phone/tablet/console UI layout across form factors | `rbx-device-simulator-lua` |
| CPU/GPU frame spikes | `rbx-perf-profiling` |
| memory growth, leaks, heap snapshots | `rbx-luau-heap-profiling` |
| scene composition, render/memory audit | `rbx-scene-analysis` |
| simulate 3G/4G/packet loss, measure input delay | `rbx-network-simulator` |
| tuning values live without a restart, A/B tests | `rbx-configs-experimentation` |
| funnel/economy analytics events | `rbx-instrument-analytics` |
| Developer Product receipts, ProcessReceipt misuse | `rbx-process-receipt-misuse` |
| enable streaming, fix streaming artifacts | `rbx-convert-to-streaming` |
| accurate API/docs detail | `rbx-docs-search` |
| authoring or editing a custom skill | `rbx-create-skill` |
| import a Blender/Maya/FBX/glTF model through Open Cloud and verify it | `rbx-import-asset` |
| products, passes, assets and settings through `open_cloud_invoke` | `rbx-open-cloud-usage` |
| Open Cloud scopes, 403s, "not granted", HTTP allowlist, data store access | `rbx-permissions` |

## Usage policy

1. `list_roblox_skills` first — never assume a name exists on this build.
2. Load with `get_roblox_skill {"skill_name": "rbx-..."}` **before** writing the code it covers.
3. Use normal Studio tools to implement the fix.
4. Re-test with runtime evidence.
5. Do not load every skill "just in case" — one per problem.

## Delegation beats reading

For multi-step investigation, `subagent` keeps large JSON out of your context:
`explore` (map the place), `playtest` (exercise a scenario), `unit_test` (run
tests), `screen_capture` (visual loops). One shot, no follow-ups — ask for the
exact evidence you want back.

## Fallbacks

- docs skill unavailable -> RobloxForge local creator-docs cache (`rbforge docs search`)
- debug skill unavailable -> playtest + Output + targeted temporary diagnostics
- device skill unavailable -> Studio device emulator/manual evidence
- perf skill unavailable -> MicroProfiler/Stats evidence the surface can expose
- network skill unavailable -> `settings().Network` via `execute_luau`, read the
  measured ping back rather than assuming a preset applied

Never claim use of a Roblox-authored skill unless the current Studio instance
exposed it.
