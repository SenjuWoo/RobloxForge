# PLAN — 0.23.0 long-run QA: detached runs, tested-commit snapshots, field notes triage

Goal: triage a production project's field notes (one Studio instance, 35 live suites) into fixes, docs and
skill updates. What 0.22.x already ships is cited, not rebuilt. The previous plan is in
`docs/archive/PLAN-0.22.0.md`.

Evidence format: `cmd:<command> @ <sha> exit=<n>`. `T=python tests/run_tests.py`.

## Triage

| Note | Verdict |
|---|---|
| A1 detach | build: `servertest --detach`, `rbforge runs --job ID [--wait]`, a live-connection lock |
| A2 two sessions | shipped in 0.22.0 as `--repeat 2 --restart` (reports "run N/M"); add `--sessions N` as its name for the release proof |
| A3 snapshot | build: sources read once at load, commit and dirty flag captured at start, manifest digest |
| A4 worktrees | shipped in 0.22.1 (`project.excluded` skips any dir holding `.git`, a worktree's `.git` file included) |
| A5 exec silence | build: "(no return value)" on stderr, help text |
| A6 slot / save_place | build: probe `save-check` with the attribute names as parameters; the forge cannot block the MCP `save_place`, the docs say so |
| A7 device emulation | build: `StudioDeviceSimulatorService` is scriptable from `execute_luau` (read in the skill, proven live); probe `device-layout`; offline thumb-zone spec as the fallback |
| A8 unfocused perf | build: perf probe labels a flat ~66 ms frame "consistent with an unfocused-Studio throttle" (no focus signal assumed) |
| A9 toolbox args | `is_start`, `capture_id`, `NotNeeded` already in studio-mcp.md; session ids change already there |
| A10 sed quoting | docs (sharp-edges agent traps) |
| B1 UV-less GLB | build: `assets check` reports meshes without `TEXCOORD_0`; `--require-uv` fails on them (vertex-colour pipelines stay valid) |
| B2 decimate without weld | Asset-Forge's (field report already filed there); weld-then-decimate in docs |
| B3-B6 | docs (assets.md) |
| C1-C7 | docs (testing, npc, ui, performance) |
| D1 receipts | template in docs and the scaffold; checker cut (the forge's "receipts" already name another thing) |
| D2, D3 | docs (release discipline; integrator edits exist in development-loop) |

| ID | Task | Status | Depends on | Verify | Evidence |
|---|---|---|---|---|---|
| J1 | Detached runs: `servertest --detach` starts the same command in a background process, writes a job record and log under `RBFORGE_HOME/runs/jobs/`, returns the job id; the child writes its result atomically; `rbforge runs --job ID` reports running / done / died (pid gone, no result); `--wait --wait-timeout S` exits 0/1 with the run, 5 while still running; live commands refuse while a detached job holds the Studio connection | complete | - | `cmd:RBFORGE_TEST_ONLY="jobs:" T` | cmd:python tests/run_tests.py @ 1758d46 exit=0 (271 passed, 0 failed, 0 skipped) |
| S1 | Snapshots: suite and single entries carry their source read at load; every run uses it; commit, dirty flag and manifest digest captured before the first run and written to the report and the ledger; `--sessions N` = `--repeat N --restart` | complete | - | `cmd:RBFORGE_TEST_ONLY="snapshot:" T` | cmd:python tests/run_tests.py @ 1758d46 exit=0 (271 passed, 0 failed, 0 skipped) |
| X1 | `exec` prints "(no return value)" on stderr when the script returns nothing | complete | - | `cmd:RBFORGE_TEST_ONLY="cli: exec" T` | cmd:python tests/run_tests.py @ 1758d46 exit=0 (271 passed, 0 failed, 0 skipped) |
| P3 | Probes: `save-check` (QA attributes, Play state, verdict); `perf` labels a throttled frame; `device-layout` (per-preset viewport, off-screen, small targets) | complete | - | `cmd:RBFORGE_TEST_ONLY="probes:" T` | cmd:python tests/run_tests.py @ 1758d46 exit=0 (271 passed, 0 failed, 0 skipped) |
| U1 | `assets check` reports GLB/glTF meshes without UVs; `--require-uv` fails them | complete | - | `cmd:RBFORGE_TEST_ONLY="assets: uv" T` | cmd:python tests/run_tests.py @ 1758d46 exit=0 (271 passed, 0 failed, 0 skipped) |
| K1 | Docs: field notes B, C, D, A6-A10 in assets, testing-debugging, studio-mcp, sharp-edges, ui-mobile, performance, npc guidance; receipt template in docs and scaffold | complete | - | `cmd:RBFORGE_TEST_ONLY="docs: long-run" T` | cmd:python tests/run_tests.py @ 1758d46 exit=0 (271 passed, 0 failed, 0 skipped) |
| R1 | Full suite, version 0.23.0, CHANGELOG, README, STATE | complete | all above | `cmd:T` | cmd:python tests/run_tests.py @ 1758d46 exit=0 (271 passed, 0 failed, 0 skipped) |
| R2 | Live: detached suite on a disposable place, job status/wait, lock refusal, `save-check`, snapshot fields | complete | J1, S1, P3 | `cmd:rbforge servertest --detach` | live 2026-11-26, disposable place (no other Studio running, closed by its PID): `cmd:rbforge servertest --suite tests/suites.json --sessions 2 --detach` exit=0, then `runs --job --wait` exit=0 (PASS 2/2, tested commit and source sha256 in the report); exec during the run RBF-STUDIO-004; installed rbforge, no Studio: job running from a separate call, done RBF-STUDIO-001 at 46 s; save-check no -> yes; device-layout found the planted faults per preset; code at 1758d46 |
| R3 | Push, CI green, alerts, tag + release, skills, doctor | complete | R1 | `cmd:gh run list` | CI + Push on main green on 1758d46; 0 open Dependabot, code-scanning, secret-scanning alerts; tag v0.23.0 from 17fff50, asset sha256 verified, smoke OK, 375 skill installs current, doctor v0.23.0 |

## Decisions

- A detached job is the same CLI command in a child process, not a second implementation: the run, the
  ledger and the forensics stay one code path.
- The lock protects the one Studio connection from other `rbforge` live commands; direct MCP calls from an
  agent cannot be stopped by the forge, so the docs say not to make them during a detached run.
- `--sessions N` is an alias, not a new mode: `--repeat N --restart` already restarts Play between runs.

## Assumptions

- No Studio is running at start (checked); a disposable place opened for R2 is closed by its own PID only.

## Risks

- Windows background processes: `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`, stdio to the log file,
  no inherited console; POSIX uses `start_new_session`.
