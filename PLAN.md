# PLAN — 0.20.0 field lessons from a second production project

Goal: the forge carries what a second, independent action-RPG project learned the hard way (engine
traps measured live, Studio MCP behaviour, an asset pipeline, test patterns), corrects the one first-party
tip that the new evidence contradicts, and turns the repeatable lessons into tooling: a world-audit probe,
a lint rule and a push that refuses to run during Play.
The previous plan (0.19.0) is archived in `docs/archive/PLAN-0.19.0.md`.

Evidence format: `cmd:<command> @ <sha> exit=<n>`. `T=python tests/run_tests.py`.

| ID | Task | Status | Depends on | Verify | Evidence |
|---|---|---|---|---|---|
| F1 | studio-mcp.md: capture needs Studio in front and a settle wait (terrain LOD seams); a timed-out capture drops the connection; one StudioMCP owner at a time (CLI vs agent); held keys for Input Actions; the person at the PC is also an input source; GPU-heavy jobs starve Studio | complete | - | `cmd:RBFORGE_TEST_ONLY="docs: field lessons" T` | cmd:python tests/run_tests.py @ fce255c exit=0 (242 passed, 0 failed, 0 skipped) |
| F2 | sharp-edges.md: rays obey collision groups; `PreloadAsync` id strings load as images; network owner is the assembly root (welded gear); `Attachment.WorldCFrame` before a parent; Edit does not re-solve `WeldConstraint`s; Beam axes; camera boom `RespectCanCollide`; literal-union compare in strict mode; `AudioEmitter.PositionType` | complete | - | `cmd:RBFORGE_TEST_ONLY="docs: field lessons" T` | cmd:python tests/run_tests.py @ fce255c exit=0 (242 passed, 0 failed, 0 skipped) |
| F3 | assets.md: GLB through Open Cloud measured facts (axes, scale, per-object MeshParts, materials dropped, vertex colours kept, unanchored); the absolute "+Z, rotate 180°" rule replaced by a measure-first probe | complete | - | `cmd:RBFORGE_TEST_ONLY="docs: field lessons" T` | cmd:python tests/run_tests.py @ fce255c exit=0 (242 passed, 0 failed, 0 skipped) |
| F4 | worldbuilding-lighting.md: terrain filled by distance to the surface (no ribbed cliffs); audit the built world and also look; first-look defaults that read wrong (cyan stock sky, teal haze, wet-black Mud, default glow colours) | complete | - | `cmd:RBFORGE_TEST_ONLY="docs: field lessons" T` | cmd:python tests/run_tests.py @ fce255c exit=0 (242 passed, 0 failed, 0 skipped) |
| F5 | testing-debugging.md: Studio-only test hooks for client auto-behaviour; driving movement in a client test; persistence across a real Play restart; suites change the world (order, reset); staging scenes for real-input runs | complete | - | `cmd:RBFORGE_TEST_ONLY="docs: field lessons" T` | cmd:python tests/run_tests.py @ fce255c exit=0 (242 passed, 0 failed, 0 skipped) |
| F6 | animation.md + ui-mobile.md: blocky R15 from a description (constraint counts, ragdoll), client `Transform` writes pose server-owned rigs, pose contact sheets; prompts follow the last input device and every shown touch hint has a listener | complete | - | `cmd:RBFORGE_TEST_ONLY="docs: field lessons" T` | cmd:python tests/run_tests.py @ fce255c exit=0 (242 passed, 0 failed, 0 skipped) |
| P1 | Probe `world-audit`: floating pieces, pieces inside each other, attachments far from their part, with a skip list that still reports what it skipped | complete | - | `cmd:RBFORGE_TEST_ONLY="probes:" T` | cmd:python tests/run_tests.py @ fce255c exit=0 (242 passed, 0 failed, 0 skipped) |
| L4 | Trap T045: an `Attachment` placed by world position before it has a parent; positive and negative fixtures | complete | - | `cmd:RBFORGE_TEST_ONLY="traps:" T` | cmd:python tests/run_tests.py @ fce255c exit=0 (242 passed, 0 failed, 0 skipped) |
| L5 | `push` refuses while Play is running (Edit sources cannot change mid-playtest) with a clear error instead of a zero-file result | complete | - | `cmd:RBFORGE_TEST_ONLY="live: push" T` | cmd:python tests/run_tests.py @ fce255c exit=0 (242 passed, 0 failed, 0 skipped) |
| R1 | Full suite, version 0.20.0, CHANGELOG, README, STATE | complete | F1-F6, P1, L4, L5 | `cmd:T` | cmd:python tests/run_tests.py @ fce255c exit=0 (242 passed, 0 failed, 0 skipped) |
| R2 | Live: `world-audit` against a disposable place with a planted floater, overlap and stray attachment; push refusal during Play | complete | P1, L5 | `cmd:rbforge probe world-audit` in Studio | live 2026-11-18, disposable local place from the fixed scaffold: `cmd:rbforge probe world-audit --run --dm Edit --set root=workspace.AuditFixture --set skip={"Rail$"}` @ fce255c exit=0 (3 planted faults reported, 3 controls quiet, skip listed); `cmd:rbforge push ALL` in Play exit=4 RBF-PLAY-002, after Stop exit=0 (10 pushed) |
| R3 | Push, CI green on the SHA, alerts queried, tag + release, skills installed, doctor | complete | R1 | `cmd:gh run list` / `rbforge doctor` | CI + Push on main green on fce255c; 0 open Dependabot, code-scanning, secret-scanning alerts; tag/release: see STATE.md log |

## Decisions

- **Source:** the second project's own docs (`VALIDATION.md`, `STATE.md`), its commits and its session notes.
  Only general engine and workflow facts move into the forge; its tuning numbers, layout and lore stay there.
- **Evidence class per item,** as in sharp-edges: what that project measured in Studio is `live` with the
  month; what it inferred once is `field`.
- **Where the new evidence contradicts a first-party tip, the tip is rewritten to "measure it"**, not
  swapped for the new project's number: two projects disagreeing about mesh orientation means the answer
  depends on how the source was authored.
- **The world-audit probe is generic:** it reads any root, reports leads with positions, never edits.

## Assumptions

- A disposable local place can be opened in Studio for R2; if not, R2 is reported unverified.
- `get_studio_state` lists `Server`/`Client` among available datamodels while Play runs (the servertest
  preflight already relies on this wording; unrecognised wording does not refuse).

## Risks

- Overlap detection by bounding boxes reports intended nesting (a sign on a wall); the probe states its
  tolerance and keeps the report a reading list.
- T045 is a regex heuristic over one function body; it ships with a negative fixture.
