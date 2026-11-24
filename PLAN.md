# PLAN — 0.22.0 streaks, failure forensics, run ledger, current Studio MCP surface

Goal: remove the live-QA steps a production project burned whole sessions on. Closing one of its
milestones needed "three passes in a row with Play restarted between runs": the agent restarted Play by
hand, counted passes in its head ("8 of 12 runs"), and a failure ("the sack was still there 5 s later")
left nothing behind to diagnose because the evidence went away when Play stopped. The forge now runs the
streak itself, keeps the console of every failed run before anything is stopped, and keeps a per-project
ledger of every live run. The Studio MCP surface moved again (41 tools; two renamed) and the knowledge is
brought up to it, with the generic lessons from that milestone. The previous plan is in
`docs/archive/PLAN-0.21.0.md`.

Evidence format: `cmd:<command> @ <sha> exit=<n>`. `T=python tests/run_tests.py`.

| ID | Task | Status | Depends on | Verify | Evidence |
|---|---|---|---|---|---|
| S1 | `servertest --repeat N [--restart] [--keep-going]`: N runs of one test or a whole `--suite`; `--restart` gives every run a fresh Play session (stop, wait for Edit, start, wait for the datamodels) and starts Play from Edit; stops at the first failure and leaves that Play session running for inspection unless `--keep-going`; exit 0 only for N passes in a row | complete | - | `cmd:RBFORGE_TEST_ONLY="streak" T` | cmd:python tests/run_tests.py @ d22a96e exit=0 (258 passed, 0 failed, 0 skipped) |
| S2 | Failure forensics: each run prints a unique marker; a failed, timed-out or errored run reads `get_console_output` before anything else happens, keeps what follows the marker in `RBFORGE_HOME/runs/logs/` and puts the last lines in the result | complete | - | `cmd:RBFORGE_TEST_ONLY="forensics" T` | cmd:python tests/run_tests.py @ d22a96e exit=0 (258 passed, 0 failed, 0 skipped) |
| S3 | Run ledger: every CLI servertest run (single, suite, streak) appends one JSON line per test to `RBFORGE_HOME/runs/<project>.jsonl` (time, project SHA and dirty flag, test, datamodel, outcome, first result line, seconds, restarted, batch id, log path); `rbforge runs [--root] [--test] [--last] [--text]` reports per test runs, passes, pass rate, current and best streak, last result | complete | S1, S2 | `cmd:RBFORGE_TEST_ONLY="runs" T` | cmd:python tests/run_tests.py @ d22a96e exit=0 (258 passed, 0 failed, 0 skipped) |
| V1 | `rbforge --version` | complete | - | `cmd:RBFORGE_TEST_ONLY="cli: --version" T` | cmd:python tests/run_tests.py @ d22a96e exit=0 (258 passed, 0 failed, 0 skipped) |
| M1 | `studio-mcp.md` brought to the live 41-tool surface (2026-11-24 handshake): `skill`/`list_skills` renamed `get_roblox_skill`/`list_roblox_skills`; new `video_capture`, `list_plugin_actions`, `open_plugin`; 17 `rbx-*` skills; every stale name in the router, `assistant-skills.md` and other references replaced; a test that fails on the old names | complete | - | `cmd:RBFORGE_TEST_ONLY="docs: studio mcp surface" T` | cmd:python tests/run_tests.py @ d22a96e exit=0 (258 passed, 0 failed, 0 skipped) |
| K1 | Field lessons, generic only: streaks and flake numbers from the ledger, failure context captured before Stop, a refusal reason for every guarded server handler (and a Studio-only way for a suite to read it), test oracles that match the design (a sack that keeps what does not fit), one owner per input action, fixtures that rebuild the world a player would have (not a refilled one), bot navigation hygiene (ground probe before backing off, an unreachable timeout, heal only when safe, release a lock and face a prompt), a tuning-attempt budget that turns a stuck fight into a measurement and an owner question | complete | S1, S3 | `cmd:RBFORGE_TEST_ONLY="docs: streak lessons" T` | cmd:python tests/run_tests.py @ d22a96e exit=0 (258 passed, 0 failed, 0 skipped) |
| R1 | Full suite, version 0.22.0, CHANGELOG, README, STATE | complete | all above | `cmd:T` | cmd:python tests/run_tests.py @ d22a96e exit=0 (258 passed, 0 failed, 0 skipped); CI (4 test legs + luau-semantics) and CodeQL green on d22a96e; scaffold gate pass 9/0/0, audit fix_order [] |
| R3 | Push, CI green on the SHA, alerts queried, tag + release, skills installed, doctor | pending | R1 | `cmd:gh run list` / `rbforge doctor` | - |

## Decisions

- **No new MCP tool.** The catalog is at 10,677 of its 10,800-character budget; `rb_runs` would break it
  for a read an agent gets from `rbforge runs`. The ledger stays a CLI feature.
- **`--restart` restarts before every run, including the first.** Earlier manual pokes in a running session
  contaminate run one otherwise; the requirement it serves is "a fresh Play session per run".
- **A failed streak leaves Play running.** The state that failed is the evidence; stopping it is the agent's
  next decision, not the runner's. A completed streak also leaves Play as the last run left it.
- **Forensics read the console, never more.** No screenshot or extra Luau on failure: the console is
  read-only and costs one call; a capture needs a framed camera the runner cannot choose.
- **The ledger is written only from the CLI layer.** `server_test`/`run_suite` stay side-effect free for
  callers and tests; the CLI records what it ran.
- **No live Studio run this release.** The only Studio instance holds the owner's production place and its
  data; this session only read its tool list, studio state and console (read-only calls). The new live
  paths are covered by session doubles that answer `get_studio_state`, `start_stop_play` and
  `get_console_output` the way the live handshake showed.
- Generic lessons only: the production project's names, tuning and milestones stay in that project.

## Assumptions

- `get_console_output` returns the Output log as plain text with no timestamps, oldest first, and holds both
  server and client lines in a solo playtest (read live 2026-11-24; the client half rests on Studio's Output
  window merging both, observed in earlier sessions).
- `start_stop_play` may return before the datamodels exist; the runner polls `get_studio_state`.

## Risks

- A console truncated by Studio may no longer contain the marker; the runner then keeps the last 200 lines
  and says the marker was not found.
- Stopping Play discards unsaved Play-time state by design; `--restart` is opt-in and documented as such.
