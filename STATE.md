# STATE — RobloxForge

Live source of truth. Update at every milestone.

## Goal

Make RobloxForge take an agent from "has Studio control" to "ships a working
vertical slice" with the fewest wasted Studio boots, and make every success
claim checkable.

## Version

0.13.1 (pre-1.0; 1.0.0 is gated on the E2E weak-model benchmark).

## Gaps to close (next session)

1. **Live MCP integration is unverified for 0.12.x.** Studio was closed when the audit landed, so `push` readback,
   `server_test` parsing and `init.*` mapping are proven by unit tests with a fake session only. Re-run one real
   `rbforge push` and one `rbforge servertest` against an open place before trusting them.
2. **E2E weak-model benchmark** (`tests/agent-benchmarks`) has not been run - it is the 1.0.0 gate.
3. **`luau-lsp` skip** is still the normal case: no `globalTypes.d.luau` on this machine, so the type rung never runs
   here. Install definitions (or set `RBFORGE_LUAU_DEFINITIONS`) to exercise the exit-status fix against a real tool.
4. **The test suite needs `selene`.** The generated-Luau test fails (not skips) without it, by design; both CI and
   the release workflow install a pinned copy via `scripts/install_selene.py`.
5. **Receipt provenance is an id, not a signature.** An observation id proves the record came from
   `collect_evidence`, but an agent that can run that tool can also run a throwaway test; the guard is the
   expiry, the Studio/place binding and the honest levels, not cryptography. An agent with full write access
   to the receipts directory can still forge files.
5. **Historical note (0.12.x).** `collect_evidence()` is the only path that sets
   `provenance="tool"`, and agent evidence caps at `playtest_claimed` - but a caller can still pass
   `provenance="tool"` by hand. Real tamper-resistance needs the tool to sign its observations.

## Done (verified)

- 0.13.1: `_push_code` emits valid Luau (class map travels as a JSON string, decoded with
  `HttpService:JSONDecode`; every string uses `long_string`), existing parents are checked against the declared
  class, an overwrite restores the previous `Source` on a failed readback (`ROLLED_BACK`/`ROLLBACK_FAILED`),
  `servePlaceIds` blocks the wrong place before writing, `record_observation` is private and `collect_evidence`
  reads `get_console_output`/`screen_capture` for real, observations bind to project+scenario, legacy receipts keep
  their chain, `--changed-only` always runs the typechecker and takes `--base-ref`. 67 tests.
- 0.13.0: verified status requires an observation recorded by RobloxForge (`rb_collect_evidence` ->
  `observation_id`), not a caller-asserted provenance; one function decides the level so receipts cannot
  contradict themselves; new `playtest_observed_partial`; receipts are serialized under a file lock with a
  monotonic sequence and `verify_chain()`; Rojo projects without a `tree` fail; push honours declared parent
  classes and refuses ambiguous hierarchy; `--changed-only` linting. 58/58 tests.
- 0.12.2: second audit pass. A crashed linter fails instead of warning; mixed push batches report
  `unmapped`/`unreadable` without raising; receipts reserve names atomically and chain in creation order;
  evidence carries provenance (`tool` via `collect_evidence`, `agent` otherwise) and agent evidence caps at
  `playtest_claimed`; the release gate now smoke-tests the real archive. 53/53 tests.
- 0.12.1 / 0.12.0: corrective audit. Typechecker judged by exit status (a crashed tool is never a pass); receipts
  separate agent claims from observed evidence and never collide; `push` reads Source back out of Studio and returns
  synced/mismatch/unverified; server-test PASS parsed exactly (NOT_PASS no longer passes); Rojo `init.*` files map their
  directory; malformed project JSON fails; selene gets a Roblox std when the project ships none and warnings stay
  warnings; a class change backs the old script up to `ServerStorage.rbforge_backups`. 48/48 tests.
- 0.11.0: probes (14, engine-query-safe), trap lint (17 rules) wired to CLI and MCP; `references/debugging-playbook.md`.
  Each CLI command opens and closes its own Studio session - `push` reuses one session for all of its files, and no
  command reuses another's. 40/40 tests.
- 0.10.1: SurfaceGui `ClipsDescendants` is the one-sided flat-colour wall; query helpers skip `CanQuery = false`.
- 0.10.0 / 0.9.1 / 0.9.2: sight-line diagnosis, runtime builds do not persist, match the pixels before the code.

- 0.9.0: `references/animation.md` - procedural gait, viewmodel recipe, debug-attribute testing, and the welding/scale traps.

- 0.8.1: gradient-vs-background transparency trap and curved-shell opening rules (quad corners, height gate, shell-space flattening).

- 0.8.0: `references/ui-craft.md` - UI slop tells, build rules, the slop check, and how to use a concept image.

- 0.7.0: MCP input-verification limits (wheel scroll never reaches the game), Adornee'd SurfaceGui lookup, and HUD counting plus LogService error reads.

- 0.6.0: screen-surface traps (SurfaceGui face direction, RenderStepped death, stale client caches, edit-session require cache, planar panel gaps, floating base ring, shells that wall routes), the generated-image upload loop with the equirectangular slice maths, geometry-test readiness rules, and `scripts/serve_assets.py`.

- 0.5.0: live-iteration reference, engine traps, geometry proofs and
  `templates/studio/` snippets from a real procedural build; snippets pass
  stylua + selene through `rbforge check` (luau-lsp skipped: no definitions).

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
- 0.4.0 (2026-11-04): the checkout ships its own pinned `rokit.toml` and
  `tools/install-toolchain.ps1` (also `Install.ps1 -Toolchain`), which installs
  rokit via cargo, adds a *global* manifest so the shims resolve everywhere,
  and `rokit install`s the pin. `rb_toolchain_status` also searches
  `~/.rokit/bin`. Verified on Windows: all 8 tools resolve and report versions,
  `rbforge check` runs rung 1 for real, test suite 34/34.
  Related bug found and fixed: a bare rokit shim in a fixture dir exits
  "Failed to find tool", which the gate read as `fail` instead of `skip` —
  that is why the global manifest is part of the installer, not a detail.
- Creator-docs cache populated on this machine (2,214 docs, sparse clone) — so
  `rb_docs_search` / `rb_docs_read` actually answer.
- Skills installed into every Hermes profile root plus Claude/Codex/Grok
  (multi-profile discovery fixed; earlier builds only knew the default root).
- 33/33 tests pass.

## Next

- Run the E2E weak-model benchmark (`tests/agent-benchmarks/01-weak-model-obby.md`)
  — the only thing blocking 1.0.0.

## Known gaps (honest)

- The toolchain is shipped but not installed on every machine. `rbforge check`
  reports `incomplete` wherever `tools/install-toolchain.ps1` has not been run.
  That is the designed behaviour, not a silent pass. CI runners are in this
  state by default (no Roblox, no network in the gate job).
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
