# PLAN — 0.19.0 knowledge audit and gap fill

Goal: an agent that starts a Roblox game from nothing, or takes over an existing one, gets correct
current guidance, a working starting point and a lint that names the defects weak models actually ship.
The first-party references grew out of one production project whose core was written by a weak model;
this pass separates what is engine fact from what was that project's habit.

Evidence format: `cmd:<command> @ <sha> exit=<n>`. `T=python tests/run_tests.py`.

| ID | Task | Status | Depends on | Verify | Evidence |
|---|---|---|---|---|---|
| K1 | persistence.md: ProfileStore sample matches upstream API (signal `OnSessionEnd:Connect`, no `ListenToRelease`, real constants); failed read is never a new player; contradiction removed | complete | - | `cmd:RBFORGE_TEST_ONLY="docs: persistence" T` | cmd:python tests/run_tests.py @ 5184530 exit=0 (238 passed, 0 failed, 0 skipped) |
| K2 | architecture.md: loader sets readiness, isolates Init, handles existing players/characters, logs instead of swallowing; one service shape; authored-world and module-size rules; cleanup pattern | complete | - | `cmd:RBFORGE_TEST_ONLY="docs: reference samples" T` | cmd:python tests/run_tests.py @ 5184530 exit=0 (238 passed, 0 failed, 0 skipped) |
| K3 | animation.md + assets.md: authored-vs-procedural decision first; joint helper used from the first sample; viewmodel light advice no longer contradicts sharp-edges; audio/asset id statement corrected | complete | - | `cmd:RBFORGE_TEST_ONLY="docs: reference samples" T` | cmd:python tests/run_tests.py @ 5184530 exit=0 (238 passed, 0 failed, 0 skipped) |
| K4 | sharp-edges.md: general traps only, each with its evidence class; project case notes moved to sightlines-and-openings.md; `CharacterAdded` rule corrected | complete | - | `cmd:RBFORGE_TEST_ONLY="docs: sharp-edges" T` | cmd:python tests/run_tests.py @ 5184530 exit=0 (238 passed, 0 failed, 0 skipped) |
| K5 | live-iteration.md, worldbuilding-lighting.md, game-design.md, security-networking.md, ui-mobile.md, performance.md: stale or project-specific advice corrected (see Decisions) | complete | - | `cmd:RBFORGE_TEST_ONLY="docs: stale" T` | cmd:python tests/run_tests.py @ 5184530 exit=0 (238 passed, 0 failed, 0 skipped) |
| K6 | New references: `existing-projects.md` (taking over a codebase), `current-engine.md` (what model memory gets wrong, each class checked against the docs cache) | complete | - | `cmd:RBFORGE_TEST_ONLY="docs: current-engine" T` | cmd:python tests/run_tests.py @ 5184530 exit=0 (238 passed, 0 failed, 0 skipped) |
| K7 | Router SKILL.md: task -> specialist skill -> first-party reference table; 38 tools; new references listed; under the existing size budget | complete | K1-K6 | `cmd:RBFORGE_TEST_ONLY="skill: router" T` | cmd:python tests/run_tests.py @ 5184530 exit=0 (238 passed, 0 failed, 0 skipped) |
| L1 | Trap lint: new rules (failed-read default profile, test/debug remote, missed existing players, ungated input, client-supplied value, deprecated calls, purchase granted outside ProcessReceipt, name-keyed store, InvokeClient); T022 narrowed; project-specific T025 removed; T004 downgraded | complete | - | `cmd:RBFORGE_TEST_ONLY="traps:" T` | cmd:python tests/run_tests.py @ 5184530 exit=0 (238 passed, 0 failed, 0 skipped) |
| L2 | Structure rung and reviews skip snapshot directories and git-ignored files (field report) | complete | - | `cmd:RBFORGE_TEST_ONLY="check: snapshot" T` | cmd:python tests/run_tests.py @ 5184530 exit=0 (238 passed, 0 failed, 0 skipped) |
| L3 | `rbforge audit` / MCP `rb_audit`: ranked health report for an existing project (data safety, authority, remotes table, lifecycle, size, runtime-built world/UI, tests) with a fix order | complete | L1, L2 | `cmd:RBFORGE_TEST_ONLY="audit:" T` | cmd:python tests/run_tests.py @ 5184530 exit=0 (238 passed, 0 failed, 0 skipped) |
| S1 | Scaffold ships a working starter kit (loader, remotes registry, rate limiter, safe data service, cleanup, HUD, pure rules + specs) that passes its own gate | complete | - | `cmd:RBFORGE_TEST_ONLY="scaffold:" T` | cmd:python tests/run_tests.py @ 5184530 exit=0 (238 passed, 0 failed, 0 skipped) |
| S2 | Genres: shooter, round, towerdefense, rpg, horror, survival in plan/scaffold/templates | complete | S1 | `cmd:RBFORGE_TEST_ONLY="plan:" T` | cmd:python tests/run_tests.py @ 5184530 exit=0 (238 passed, 0 failed, 0 skipped) |
| Q1 | Docs sample gate: every fenced Luau block in the first-party references parses (StyLua), with a negative control | complete | K1-K6 | `cmd:RBFORGE_TEST_ONLY="docs: reference samples" T` | cmd:python tests/run_tests.py @ 5184530 exit=0 (238 passed, 0 failed, 0 skipped) |
| R1 | Full suite, self-check, version 0.19.0, CHANGELOG, README, STATE, field reports cleared | complete | all | `cmd:T` and `cmd:python src/rbforge_cli.py check . --scope static` | cmd:python tests/run_tests.py @ 5184530 exit=0 (238 passed, 0 failed, 0 skipped); repo-root `check . --scope static` is not a project gate (probe templates carry placeholders) - the scaffold's own `rbforge check` is: exit=0 |
| R2 | Live: scaffolded project built, opened in Studio, Play, console clean, starter loop exercised | complete | S1 | `cmd:rbforge servertest` against the scaffold | run on the tree that became 5184530, live Studio Play, disposable local place: `cmd:rbforge servertest tests/Starter.server.luau --ready workspace.ServerReady=true` exit=0 (PASS, twice); Client `DoAction` 0 -> 2 coins; capture inspected; console clean |
| R3 | Push, CI green on the SHA, alerts queried, tag + release, skills installed, doctor | complete | R1 | `cmd:gh run list` / `rbforge doctor` | v0.19.0 @ 1abefb5: CI green, 0 open alerts, asset sha256 verified, smoke OK, skills current, doctor v0.19.0 |

## Decisions

- **Specialist skills are the API authority; first-party references are workflow and field evidence.**
  The 24 vendored skills are typechecked against the current API. Where a first-party reference
  duplicated one with weaker content (persistence, UI framework, remotes), it is cut to the rule plus a
  pointer rather than maintained twice.
- **Authored world by default.** Static geometry is built once in Edit and saved with the place; a
  server script rebuilds only what is genuinely dynamic or procedural per session. The runtime-builder
  workflow stays documented as the route for procedural games, not as the default.
- **Authored animation by default, procedural as a measured choice.** Per-frame joint writes for every
  NPC are a CPU cost that needs distance LOD; the references say so and give the decision table.
- **Plain typed remote arguments by default.** Buffer packets and schema compilers are level C in
  `optimization-levels.md`; `security-networking.md` now agrees with it.
- **No UI framework by default.** Fusion stays as an optional section; the default is instances plus a
  small controller, which is what a weak model can verify.
- **Evidence classes on every trap:** `docs` (official reference), `live` (observed in Studio, dated),
  `field` (one project report). A `field` item is a lead, not a rule, and the lint severity follows it.
- **Starter kit has no package dependency.** Its data service is a correct single-server pattern
  (retrying load, refuses to save a profile that never loaded, `UpdateAsync`, `BindToClose`) and says
  when to move to ProfileStore.
- **`audit` is a ranked reading list, not a verdict**, like the other static reviews.

## Assumptions

- StyLua can parse every documentation sample that claims to be Luau; fragments that cannot stand
  alone are fenced as `text`.
- Studio can be started from the command line with a local place for R2; if it cannot, R2 is reported
  unverified and nothing else depends on it.

## Risks

- The MCP catalog has a character budget (10,600); `rb_audit` must fit.
- New lint rules are regex heuristics; each ships with a negative fixture to bound false positives, and
  is run against a 35k-line production project before release.
- The `execute_luau` "no compound assignment" note cannot be re-checked without a live session.
