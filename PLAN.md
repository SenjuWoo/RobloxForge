# PLAN — 0.21.0 one-instance QA, active ragdoll, shared world state, current APIs

Goal: carry the second production project's newest lessons (2026-11-19 to 2026-11-24) into the forge:
how to prove multiplayer, input-driven and long-timer behaviour inside one Studio instance; what its live
probes measured about joints, ragdolls and input; its cross-server state pattern; and the current API and
platform facts it researched. Close the open field report. The previous plan is in
`docs/archive/PLAN-0.20.0.md`.

Evidence format: `cmd:<command> @ <sha> exit=<n>`. `T=python tests/run_tests.py`.

| ID | Task | Status | Depends on | Verify | Evidence |
|---|---|---|---|---|---|
| FR | Field report: `agents connect` writes a stable interpreter (UABS_PYTHON, then the base Python behind a venv) instead of `sys.executable`; FIELD-REPORTS entry cleared | pending | - | `cmd:RBFORGE_TEST_ONLY="agents: connect writes a stable" T` | - |
| Q1 | testing-debugging.md: proving it in one Studio instance - QA slots that protect the owner's save, puppets (a `Who` that is a player or an actor) for multi-party tests, a Pilot that plays through input bindings and `Player:Move`, policies as a difficulty oracle, a game Clock a suite can advance, fixtures that outlive the test script, the proof ladder; the 0.20.0 "stage and send MCP keys" advice demoted | pending | - | `cmd:RBFORGE_TEST_ONLY="docs: one-instance" T` | - |
| Q2 | studio-mcp.md: `execute_luau` in Edit has plugin rights (StudioTestService), multi-client tests open windows - owner's call; camera arguments of `screen_capture` do nothing against a scripted camera in Play; sharing one Studio between sessions | pending | - | `cmd:RBFORGE_TEST_ONLY="docs: one-instance" T` | - |
| E1 | sharp-edges.md: camera boom entry corrected (non-collidable canopy still hides the hero: fade it locally); `InputAction:Fire` deprecated -> `InputBinding:Fire` on a `Scriptable` binding; firing a Move action moves nobody; impulses on a player's character are applied by its owning client; a local named like a function; selene and `Vector3.yAxis:Cross` | pending | - | `cmd:RBFORGE_TEST_ONLY="docs: one-instance" T` | - |
| E2 | animation.md: active ragdoll on force-based `AnimationConstraint`s (measured torques), throw the whole body, stiff sockets, `IKControl` on constraint rigs | pending | - | `cmd:RBFORGE_TEST_ONLY="docs: one-instance" T` | - |
| E3 | current-engine.md: AnalyticsService `Log*` (the `Fire*` methods are deprecated) and its limits, `AudioPlayer` regions, SLIM level of detail and its preconditions, `EditableMesh` publish switch and ownership, `Players.MaxPlayers` read-only, `TeleportOptions:SetTeleportData` is client-visible; every member checked against the docs cache | pending | - | `cmd:RBFORGE_TEST_ONLY="docs: one-instance" T` | - |
| P2 | persistence.md: state every server shares - deltas, request ids in an applied ring, leases, messages as hints, platform limits, a port with three injected faults | pending | - | `cmd:RBFORGE_TEST_ONLY="docs: one-instance" T` | - |
| D1 | development-loop.md: delegating build work - disjoint paths, the integrator's files, the main session runs the proof, everything that touches Studio stays serial in one session | pending | - | `cmd:RBFORGE_TEST_ONLY="docs: one-instance" T` | - |
| L7 | Trap lint T046 (`docs`): deprecated `AnalyticsService:Fire*` and `InputAction:Fire`, with their replacements | pending | - | `cmd:RBFORGE_TEST_ONLY="traps:" T` | - |
| R1 | Full suite, version 0.21.0, CHANGELOG, README, STATE | pending | all above | `cmd:T` | - |
| R3 | Push, CI green on the SHA, alerts queried, tag + release, skills installed, doctor | pending | R1 | `cmd:gh run list` / `rbforge doctor` | - |

## Decisions

- **No live Studio run this release.** Another session is working in the owner's only Studio instance;
  opening a second window, starting Play or taking the MCP connection would disturb it (the owner's rule
  is one instance). Engine facts are the game project's own dated live probes, each member re-checked
  against the creator-docs cache here; forge code changes are covered offline.
- **Where the game project uses an API the docs now mark deprecated (`InputAction:Fire`), the forge
  teaches the replacement** and reports the finding back instead of copying the pattern.
- Generic lessons only: the game's lore, tuning, milestone gates and asset lists stay in the game.

## Assumptions

- `sys._base_executable` names the base interpreter behind a venv on CPython 3.11+ (stdlib attribute);
  where it is missing the base prefix is searched, then `sys.executable` is kept.

## Risks

- T046 may hit code that only reads the deprecated method name in a string; it scans code with
  comments removed and keeps strings out of the match.
