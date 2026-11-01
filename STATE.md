# STATE — RobloxForge

Live source of truth. Update at every milestone.

## Goal

Make RobloxForge take an agent from "has Studio control" to "ships a working
vertical slice" with the fewest wasted Studio boots, and make every success
claim checkable.

## Version

0.3.0 (pre-1.0; 1.0.0 is gated on the E2E weak-model benchmark).

## Done (verified)

- `rbforge check` gate: rungs 1-3 offline (format/lint/types, Lune unit specs,
  structural audit). Verified against a negative fixture that triggers
  `loadstring`, client-side `DataStoreService`, a missing Rojo `$path` and an
  unanchored part — all four reported with file:line, exit code 2.
- Missing tooling yields `incomplete` + exit 4; a test asserts a skip can never
  read as `pass`.
- `rbforge new` turns one sentence into a scaffolded project plus a filled-in
  `PLAN.md` (core loop, authority table, numbered build order, proof checklist)
  and ordered next steps — the beginner entry point.
- $0 guarantee: `references/free-stack.md` plus SKILL rule 8. No step in any
  workflow requires a purchase.
- `rbforge plugins` / `rb_plugins`: detects ForgeGUI, GuiForge, UI Labs, Moon
  Animator, Archimedes, Atmos, F3X; every detected entry carries a free
  alternative, and "no plugins installed" is a normal, calm answer.
- Live MCP surface documented at 34 tools from an actual handshake (2026-11-01,
  Studio 0.735.x), including the four `subagent` types and all 14 `rbx-*`
  skills.
- `doctor` renders end-to-end against a live Studio place; the no-name crash is
  fixed and covered by a test.
- Verification receipts hash-chain (`prev_digest`).
- Reference set rewritten for concrete patterns: three-stage loader + DI,
  ProfileStore, buffer packets, Fusion 0.3 scopes, generative assets,
  procedural prop kits, worldbuilding/lighting, five-rung ladder, juice matrix,
  beginner playbook.
- Toolchain pins verified against upstream releases; `rokit.toml` shipped in
  the source-controlled template and in scaffolds.
- Creator-docs cache populated on this machine (2,214 docs, sparse clone) — so
  `rb_docs_search` / `rb_docs_read` actually answer.
- Skills installed into every Hermes profile root plus Claude/Codex/Grok
  (multi-profile discovery fixed; earlier builds only knew the default root).
- 33/33 tests pass.

## Next

- Run the E2E weak-model benchmark (`tests/agent-benchmarks/01-weak-model-obby.md`)
  — the only thing blocking 1.0.0.
- Optional and deliberate: install the pinned toolchain so rungs 1-2 stop
  reporting `incomplete` — `winget install rokit` (or cargo), then
  `rokit install` inside a project that has `rokit.toml`.

## Known gaps (honest)

- No Luau toolchain on PATH, so `rbforge check` currently exercises the
  structural rung only and reports `incomplete`. That is the designed
  behaviour, not a silent pass.
- `verification.py` receipts are static evidence records; there is no automated
  Studio checkpoint/undo. Rule 7 in `SKILL.md` asks the agent to name a
  ChangeHistoryService waypoint before mutating; it is not enforced in code.
- The E2E benchmark has still never been run, so the behavioural-improvement
  claim stays unproven.

## Build / run

```
python src\rbforge_cli.py doctor
python src\rbforge_cli.py check . [--scope static unit structure] [--json]
python src\rbforge_cli.py scaffold <dir> --genre obby
python tests\run_tests.py
python mcp_server\server.py        # stdio MCP, 12 tools
```

## Log

- 2026-11-01 — 0.3.0: $0 guarantee (`free-stack.md`), beginner playbook,
  `rbforge new`, plugin detection with free alternatives, procedural prop kits,
  33 tests green.
- 2026-11-01 — 0.2.0: gate added, references rewritten against live MCP (34
  tools), doctor crash fixed, receipts chained, docs cache populated, skills
  installed across all agent roots, 29 tests green.
- 2026-08-25 — 0.1.1: roblox-docs skill repaired.
- 2026-08-22 — 0.1.0: initial core, CLI, MCP server, skills, tests.
