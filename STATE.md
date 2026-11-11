# STATE — RobloxForge

Live source of truth. Update at every milestone.

## Goal

Make RobloxForge take an agent from "has Studio control" to "ships a working
vertical slice" with the fewest wasted Studio boots, and make every success
claim checkable.

## Version

0.16.0 (pre-1.0; 1.0.0 is gated on the E2E weak-model benchmark).

## What is proven, and how

| Area | Evidence |
|---|---|
| CLI surface | `check <path>`, `check --root <path>` and `check <path> --scope static` are run from a cwd that is **not** the project, and each report's `root` and `rungs_run` are asserted; a positional/`--root` conflict exits 2 (tests `cli: ...`) |
| Luau semantic examples | extracted from `typing-luau.md` and re-analysed by pinned luau-lsp 1.70.1; CI job `luau-semantics` runs them with `RBFORGE_REQUIRE_LUAU_LSP=1` |
| Diagnostic map | keyed by the whole project-relative path, so `src/Server/init.luau` and `tests/Server/init.luau` are two files; containment is `commonpath`, so a sibling `proj2` is not inside `proj` (tests `check: same-named files at different depths...`, `check: a sibling directory...`) |
| Offline gate (`check`, traps, probes, review) | 148 automated tests + fixture projects |
| Generated Luau | parsed by stylua/selene in tests **and** in CI, with a negative control that must fail |
| Receipts / observations | unit tests, including omission, mismatch, expiry, replay and tamper cases |
| Skill installer | 31 tests: manifest path traversal refused, foreign/legacy/modified dirs preserved, empty+corrupt manifests never `current`, transactional staging and activation rollback, backup-name uniqueness, per-profile `current`, backup instead of delete, preflight abort, idempotent re-run, root dedupe; live across 10 Hermes roots + claude/codex/grok |
| Release artifact | `smoke_artifact.py` checks all 25 skills, frontmatter and the 18-tool MCP handshake |
| Live Studio: push + readback | disposable place, 2026-11-06: `synced` digests matched, ModuleScript/Script classes correct |
| Live Studio: hierarchy + `servePlaceIds` | `HIERARCHY … is Folder, expects Model`; `RBF-STUDIO-003`; `RBF-ARG-002` |
| Live Studio: class-change backup | original preserved as `Swap_rbforge_<ms>` in `ServerStorage.rbforge_backups` |
| Live Studio: `init.luau` nesting | `Nested` ModuleScript with `Child` beneath it |
| Live Studio: server tests | PASS, FAIL, malformed and TIMEOUT all classified correctly; a test that never reports is refused as `INVALID` in 0.00 s |
| Live Studio: full trust ladder | one observation produced `verified_playtest` (real PASS + clean console + inspected 250 KB JPEG); wrong `revision` and omitted `scenario` both degraded to `unverified` |
| Live Studio: console + screenshot | `get_console_output` read; a real 240 KB `image/jpeg` captured and hashed |
| Live Studio: rollback | engine refused a 210 KB `Source`; existing-script, new-script and class-change pushes all `rolled_back` with the previous state verified afterwards |
| Live typecheck | `rbforge types fetch` + `luau-lsp analyze --platform=roblox` with a generated Rojo sourcemap; real diagnostics on the Haven project |
| Unit-only | `ROLLBACK_FAILED` (a restore that itself fails) — not reachable through the documented API |
| Unverified | published-place path, multiplayer, mobile, weak-model benchmark |

## Gaps to close (next session)

1. **Weak-model E2E benchmark** (`tests/agent-benchmarks`) has not been run — the 1.0.0 gate.
2. **Published-place and multiplayer paths** are untested; the live work used an unpublished disposable place.
3. **`luau-lsp` runs** since 0.14.0: `rbforge types fetch` caches the pinned definitions and the rung generates a Rojo sourcemap, so it produces real diagnostics (measured on the Haven project). Remaining gap: the pinned definitions are 1.70.1 until the pin is bumped.
4. **The test suite needs a Luau parser** (`stylua` and/or `selene`); CI and the release install a pinned selene.
5. **Provenance is an id, not a signature.** An observation proves RobloxForge recorded a run; an agent with write
   access to the receipts directory can still forge files. Documented, not hidden.
6. **`ROLLBACK_FAILED` is unit-only** — forcing Studio to reject a *restore* of a small source is not possible
   through the documented API.

## Done (verified)

- 0.16.0: probes `goto`, `capture-quality`, `sound-audit` (17 probes), each run against a live Play session;
  an art-direction pass in `worldbuilding-lighting.md`; ten silent-failure entries in `sharp-edges.md`; nine
  symptom rows in the playbook.

- 0.15.3: `mapkit.prove` no longer hands back a path into the temp workdir it just deleted - the report is
  inline and `report_path` is null unless `--out` was given, in which case it is the file that was written.
  A GLB whose header declares length 0 is a mismatch like any other, not a pass. `_publish` stages through
  `mkstemp` so two concurrent publishes cannot collide, and cleans up without touching an existing report.
  163 tests.

- 0.15.2: three false-success paths closed. Malformed glTF metadata (null accessors, list `attributes`,
  non-array `primitives`, boolean modes) reports `invalid` instead of raising `AttributeError` through the
  CLI; negative accessor indices are rejected instead of wrapping to the last accessor; and a GLB whose
  header lies about its length can no longer pass. `rbforge.mapkit.prove` writes every run to a fresh temp
  report, validates its shape and result, reconciles it with the exit code, and only then publishes to
  `--out`, leaving an older report intact on failure. Blender on `PATH` is found via `shutil.which`.
  163 tests.

- 0.15.1: four reproduced asset defects fixed - the triangle cap is applied **per mesh** (two legal 16k
  meshes now pass at 32k total), the add-on folder uses Blender's `5.2` not `5.2.0` and the search covers
  user/extension/portable/install roots, an unmeasured file can no longer pass (`unverified` exits
  `DEPENDENCY`), and malformed GLBs return structured errors instead of raising `struct.error`. Triangle
  counting follows the glTF mode: TRIANGLES n/3, STRIP and FAN n-2, points/lines 0, unknown mode unverified.
  `rbforge map` / `rbforge.mapkit` run the external SyphoDev `roblox-map` prover where it lives (env
  `RBFORGE_SYPHODEV`), probe numpy/scipy/Pillow, return its own report, never touch Studio, and go
  `DEPENDENCY` when a dependency is missing. Proven against upstream's `minimal` spec on this machine.
  157 tests.

- 0.15.0: the optional 3D route is detection and validation only. `rb_assets` / `rbforge assets` report
  Blender (version, add-on minimum), the "Upload to Roblox" add-on found by manifest name, and a GLB's
  per-mesh triangle count against the 20,000 cap; nothing authenticates or uploads. `docs/INTEGRATIONS.md`
  records the classification of the SyphoDev pack and the Blender plugin, including why the pack is not
  vendored and why no uploader was written. 152 tests.

- 0.14.7: the diagnostic summary is keyed by the whole project-relative path (`commonpath` containment,
  not a string prefix), so nested same-named files and sibling directories sharing the root's name are
  counted separately; the CLI test runs `check <path>`, `--root <path>` and `--scope static` from a
  foreign cwd and asserts the report's `root` and `rungs_run` instead of accepting any exit code; the
  cached luau-lsp is reused only when its own `--version` matches the pin, and reinstalls otherwise; StyLua
  2.6.0 and luau-lsp 1.70.1 are the single stated pins across skills, briefs, vendored copies and the
  knowledge manifest. 148 tests.
- 0.13.5: receipts must state the observation's project, scenario and revision (omission no longer matches);
  console classification handles `[Server] Error:` and timestamped/located lines; a batch stops after an
  unrecovered `rollback_failed` and marks the rest `not_attempted`; `rb_collect_evidence` applies its advertised
  `capture_screenshot=true`; the parser test has a real contract plus a negative control; installed skills carry
  a `KNOWLEDGE-PATH.txt` so vendored references resolve outside the checkout.
- 0.13.2: push is transaction-like (preflight, backup, verified restore, `ROLLED_BACK` only after a
  readback), declared Folder/Model class is enforced on existing parents, `servePlaceIds` fails closed,
  screenshots are trusted only as Studio-returned image bytes with a digest, console output has an explicit
  `unknown` state, `--base-ref` and the MCP schemas match the implementation, Rojo validation was tested
  against rojo 7.7.1 (name optional, empty tree rejected), and the optional third-party skill packs are
  vendored under `knowledge/vendor`. 74 tests.
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
  stylua + selene through `rbforge check`; luau-lsp also runs once `rbforge types fetch` has cached the definitions.

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

## Still unverified (do not claim these)

- Weak-model end-to-end benchmark: no baseline-versus-Forge run yet. This gates 1.0.0.
- Published-place workflow (Open Cloud upload, live server) - untested.
- Multiplayer behaviour with more than one real client - untested.
- Mobile device testing (touch UI, memory, thermal) - untested.
