# STATE — RobloxForge

Live source of truth. Update at every milestone.

## Goal

Make RobloxForge take an agent from "has Studio control" to "ships a working
vertical slice" with the fewest wasted Studio boots, and make every success
claim checkable.

## Version

0.22.0 (pre-1.0; 1.0.0 is gated on the E2E weak-model benchmark).

NEXT ACTION: first live use of `servertest --repeat N --restart` (a place the owner says may be restarted;
Shattered Nations' R03 streak is the intended first run), then record what `get_console_output` held
for a failed Client run in the proven table. PLAN.md (0.22.0) rows S1-R3.

## What is proven, and how

| Area | Evidence |
|---|---|
| Streaks / forensics / run ledger (0.22.0) | offline only: a session double whose `get_studio_state`, `start_stop_play` and `get_console_output` answer in the formats read live on 2026-11-24 (Edit `Available DataModels: Edit`, console plain text, oldest first, no timestamps). Tests: restart order from Edit and from Play, the failed run's console sliced at its marker (earlier runs and older noise excluded), Play untouched after a failure, keep-going counts, a Play that never comes up (`RBF-PLAY-003`), unreadable state refused before any Stop, execute_luau errors become `error` outcomes with console, ledger rates/streaks/torn lines, git sha + dirty flag, CLI round trip under an isolated home. **No live run**: the only Studio holds the owner's production place |
| Studio MCP surface (0.22.0) | live `tools/list` 2026-11-24 (read-only, Edit mode): 41 tools; `get_roblox_skill`/`list_roblox_skills` replace `skill`/`list_skills`; new `video_capture`, `list_plugin_actions`, `open_plugin`; `list_roblox_skills` returned 17 `rbx-*` skills. A docs test fails on any old name taught as current |
| Starter refusal reasons (0.22.0) | scaffold gate (StyLua, selene, luau-lsp strict) passes with `(boolean, string?)` returns; the extended live starter test has not run in Studio |
| Field lessons (0.21.0) | from the second production project's specs, builder guide, platform research, receipts and source headers (2026-11-19..24, read-only; another session was working in it). Every API member named re-read from the creator-docs cache at `a23352b` (presence and Deprecated/ReadOnly tags); doc-page claims (SLIM requirements and avatar scope, analytics limits, EditableMesh publish switch, messaging best effort, data store per-key budget, 45-day MemoryStore expiry, teleport data) checked in the cached pages; one claim corrected against them (SLIM avatars include StarterCharacter, exclude NPCs). No live Studio run: the owner's only Studio instance was in use |
| T046 (0.21.0) | fixtures incl. a BindableEvent control; run read-only over the production project: 12 hits, all real `InputAction:Fire` calls |
| Agent connect interpreter (0.21.0) | fixtures: UABS_PYTHON wins, a missing one is ignored, inside a venv the base interpreter is written even when `_base_executable` reports the venv, outside a venv `sys.executable` stays; TOML keeps forward slashes |
| Field lessons (0.20.0) | from a second production project's VALIDATION/STATE, commits and session notes; new engine claims (`RaycastParams.CollisionGroup`/`RespectCanCollide`, `BasePart.RootPriority`, `PreloadAsync` takes instances) checked against the creator-docs cache; a docs test asserts each lesson is present and the contradicted 180-degree yaw tip is gone |
| `world-audit` probe (0.20.0) | parses and typechecks (luau-lsp, Roblox definitions); live 2026-11-18 on a disposable place with planted faults: Floater (20 studs up), Crate inside Wagon (100%), CableEnd 100 studs from its post all reported; controls quiet (sign hung on a wall, box beside a 45-degree thin wall), skipped ShieldRail listed; on the whole place it exposed the scaffold's buried spawn (fixed, re-run clean) |
| T045 (0.20.0) | positive/negative fixtures incl. comparison and reassignment; the bug itself reproduced live: an attachment given `WorldCFrame` before its parent landed 240 studs (then 100 after the fixture moved) from its post |
| Push during Play (0.20.0) | live 2026-11-18: `rbforge push ALL` in Play -> `RBF-PLAY-002`, exit 4, nothing sent; after Stop -> 10 pushed, 0 failed; fakes cover Edit, Play and unrecognised state wording |
| Scaffold dev place (0.20.0) | `dev.project.json` placement through `CFrame` (Rojo drops `Position`); rebuilt with Rojo 7.7.1, opened in Studio, world-audit shows floor and spawn no longer overlapping |
| Starter kit (0.19.0) | offline: scaffold -> `rbforge check` PASS (StyLua, selene, luau-lsp strict 0 errors, 4 Lune specs, structure), `rbforge audit` 0 leads, the kit trips none of its own lint. Live, 2026-11-17, disposable local place built with `rojo build dev.project.json`: `servertest tests/Starter.server.luau --ready workspace.ServerReady=true` -> `PASS starter loop: action, rate limit, validation, purchase` (twice, the second after a `push`); Client datamodel fired `DoAction` and `Coins` went 0 -> 2; HUD labels read back; capture inspected (character on the floor, HUD bottom centre, order Coins / Collect / Power after the `SortOrder` fix the first capture exposed); console held only the expected "in memory" data warning |
| `rbforge audit` (0.19.0) | fixture tests (tier order, T038 first, handler table with delegated guards, snapshots skipped, clean scaffold = no leads) and a 35k-line production project: the real failed-read-defaults data bug ranked first, 9 of 9 remote handlers listed, 16 builder modules reported, 29 snapshot files skipped |
| Trap lint T026-T044 (0.19.0) | each rule has a positive and a negative fixture; run against the production project: 0 hits for the removed/narrowed rules that produced 5 false positives before |
| Docs samples (0.19.0) | every fenced Luau block in the first-party references parses under StyLua, with a negative control; `current-engine.md` class names checked against the creator-docs cache |
| Engine claims re-checked live (2026-11-17) | compound assignment runs in `execute_luau`; a Heartbeat handler that errors keeps firing (36 calls, still connected); a script-made `UIListLayout` sorts by Name |
| ProfileStore API (0.19.0) | `persistence.md` checked against upstream `ProfileStore.luau` @ 45c9847: signals, methods and constants |
| CLI surface | `check <path>`, `check --root <path>` and `check <path> --scope static` are run from a cwd that is **not** the project, and each report's `root` and `rungs_run` are asserted; a positional/`--root` conflict exits 2 (tests `cli: ...`) |
| Luau semantic examples | extracted from `typing-luau.md` and re-analysed by pinned luau-lsp 1.70.1; CI job `luau-semantics` runs them with `RBFORGE_REQUIRE_LUAU_LSP=1` |
| Diagnostic map | keyed by the whole project-relative path, so `src/Server/init.luau` and `tests/Server/init.luau` are two files; containment is `commonpath`, so a sibling `proj2` is not inside `proj` (tests `check: same-named files at different depths...`, `check: a sibling directory...`) |
| Offline gate (`check`, traps, probes, review) | 245 automated tests + fixture projects |
| Generated Luau | parsed by stylua/selene in tests **and** in CI, with a negative control that must fail |
| Push guard (0.17.0) | the exact push code is executed under Lune against `tests/lune/mock_datamodel.luau`: new script, first push (backup), unchanged ledger (no backup), Studio edit (`CONFLICT`, source untouched), `force` (backup + write), other place (first-push rules); Luau stamp equals Python `adler` |
| MCP wire | negotiation (2025-06-18/2025-03-26/2024-11-05), parse error -32700, non-object arguments -32602, annotations on every tool, catalog <= 10,800 chars (19 tools) |
| Receipts / observations | unit tests, including omission, mismatch, expiry, replay and tamper cases |
| Skill installer | 31 tests: manifest path traversal refused, foreign/legacy/modified dirs preserved, empty+corrupt manifests never `current`, transactional staging and activation rollback, backup-name uniqueness, per-profile `current`, backup instead of delete, preflight abort, idempotent re-run, root dedupe; live across 10 Hermes roots + claude/codex/grok |
| Clean-machine lifecycle (0.17.1) | sandboxed profile (temp USERPROFILE/LOCALAPPDATA/RBFORGE_HOME, no agent CLIs on PATH, no UTF-8 mode): `Install.ps1` exit 0 and 25 skills into `~/.claude/skills`; `agent disconnect all` skips all five agents, exit 0; `Uninstall.ps1 -RemoveState` exit 0, 0 skills left, state dir removed |
| Non-ASCII stdio (0.17.1) | MCP request with a `jogo_é_п` path and CLI text output for a Cyrillic path, both run with `-X utf8=0` |
| Release artifact | `smoke_artifact.py` checks all 25 skills, frontmatter and the MCP handshake |
| Live Studio: push + readback | disposable place, 2026-11-06: `synced` digests matched, ModuleScript/Script classes correct |
| Live Studio: push conflict guard (2026-11-15, Place1, unpublished) | first push `synced`, no backup; unchanged and file-only re-push `synced`; Studio edit -> `conflict`, Studio source untouched; `--force` -> `synced` + `Guard_rbforge_<ms>` holding the Studio edit in `ServerStorage.rbforge_backups`; next push `synced`, no backup; a source ending in `]=` read back exact |
| Live Studio: session discovery | a new StudioMCP lists 0 Studios for 2.7-3.6 s after spawn (4 sessions measured); sessions and the doctor probe now poll; three back-to-back `doctor` runs all saw Place1 |
| Live Studio: published place, read-only (2026-11-15) | real PlaceId: `servePlaceIds` wrong id refused (`RBF-STUDIO-003`), real id passes as int and string, using unmapped files so nothing could be written (none was); evidence collection read console + a 310 KB JPEG, receipt `playtest_observed_partial`, mismatched scenario `unverified`; doctor names the place after the name wait |
| Live Studio MCP surface (2026-11-16) | fresh handshake: 38 tools; new `save_place`, `open_cloud_invoke`, `submit_feedback`, `generate_animation`; none of the 34 from 2026-11-01 removed; schemas recorded in `studio-mcp.md` |
| Live Studio: servertest 0.18.0 (2026-11-16, disposable local place) | Edit mode -> `RBF-PLAY-001` exit 4; `script:SetAttribute` read; `--ready` unmet -> `NOT_READY`, met -> PASS; `--dm Client` PASS; suite of 4 -> 3 pass / 1 fail, exit 1; Destroy, `Parent=nil` and `Disabled` each kill a test's deferred thread (also one started in a required module); `--grace 2` and `--keep` let it finish |
| Live Studio: avatar joints (2026-11-16) | default R15 avatar in Play: 15 AnimationConstraint, 14 BallSocketConstraint, 0 Motor6D; `AnimationConstraint.C0` read-only, `Transform` writable |
| Live doctor (2026-11-16) | local place shown as `<file> - local file, not a cloud place`; Claude shown as `reachable via toolbox` |
| Live Studio: hierarchy + `servePlaceIds` | `HIERARCHY … is Folder, expects Model`; `RBF-STUDIO-003`; `RBF-ARG-002` |
| Live Studio: class-change backup | original preserved as `Swap_rbforge_<ms>` in `ServerStorage.rbforge_backups` |
| Live Studio: `init.luau` nesting | `Nested` ModuleScript with `Child` beneath it |
| Live Studio: server tests | PASS, FAIL, malformed and TIMEOUT all classified correctly; a test that never reports is refused as `INVALID` in 0.00 s |
| Live Studio: full trust ladder | one observation produced `verified_playtest` (real PASS + clean console + inspected 250 KB JPEG); wrong `revision` and omitted `scenario` both degraded to `unverified` |
| Live Studio: console + screenshot | `get_console_output` read; a real 240 KB `image/jpeg` captured and hashed |
| Live Studio: rollback | engine refused a 210 KB `Source`; existing-script, new-script and class-change pushes all `rolled_back` with the previous state verified afterwards |
| Live typecheck | `rbforge types fetch` + `luau-lsp analyze --platform=roblox` with a generated Rojo sourcemap; real diagnostics on a production game project |
| Unit-only | `ROLLBACK_FAILED` (a restore that itself fails) — not reachable through the documented API |
| Unverified | writes to a published place (deliberately not tested on a live project), Open Cloud publishing, multiplayer, mobile, weak-model benchmark |

## Gaps to close (next session)

1. **Weak-model E2E benchmark** (`tests/agent-benchmarks`) has not been run — the 1.0.0 gate.
2. **Writes to a published place and multiplayer** are untested. Published-place reads (place guard, evidence,
   doctor) were verified read-only on 2026-11-15; pushes were exercised only in an unpublished disposable place.
   Data point, not proof: a production game project has set `Script.Source` through `execute_luau` in a
   `persistedToCloud` place many times with Adler-32 readback, and the changes persisted on save. That is
   not `rbforge push`. Plan for closing it: publish a throwaway place to a test universe, map one
   ModuleScript, then `push` (first push), Studio edit -> `push` (conflict), `push --force` (backup),
   `save_place` (status `Saved`, new version), reopen the place and read the Source back.
3. **`luau-lsp` runs** since 0.14.0: `rbforge types fetch` caches the pinned definitions and the rung generates a Rojo sourcemap, so it produces real diagnostics (measured on a production game project). Remaining gap: the pinned definitions are 1.70.1 until the pin is bumped.
4. **The test suite needs a Luau parser** (`stylua` and/or `selene`) and Lune for the push-guard run; CI and the
   release install pinned selene, StyLua and Lune (`scripts/install_*.py`).
5. **Provenance is an id, not a signature.** An observation proves RobloxForge recorded a run; an agent with write
   access to the receipts directory can still forge files. Documented, not hidden.
6. **`ROLLBACK_FAILED` is unit-only** — forcing Studio to reject a *restore* of a small source is not possible
   through the documented API.

## Done (verified)

- 0.22.0 (2026-11-24): `servertest --repeat/--restart/--keep-going`, failure console capture
  (`console_log`), per-project run ledger and `rbforge runs`, `rbforge --version`, starter refusal reasons
  (`LastRefusal`), 41-tool Studio MCP reference with the renamed skill tools, streak/oracle/fixture/bot
  lessons. Tests: see PLAN.md evidence.

- 0.21.0 (2026-11-24): one-instance QA (QA slots, puppets, Pilot, Clock, proof ladder), active ragdoll,
  shared world state, delegation, current APIs (`InputBinding:Fire`, `Log*` analytics, SLIM), lint
  T046, camera-boom entry corrected, field report closed (`rbforge agent connect` interpreter). 245 tests.

- 0.20.0 (2026-11-18): field lessons from a second production project (PLAN.md; previous plan in
  `docs/archive/PLAN-0.19.0.md`). New `world-audit` probe, lint T045, push refuses during Play
  (`RBF-PLAY-002`), references extended (studio-mcp, sharp-edges, assets, worldbuilding, testing,
  animation, ui-mobile, playbook). Corrected: unconditional mesh 180-degree yaw tip, deprecated
  `Instance.new(class, parent)` in lighting samples. Fixed: scaffold dev place buried its spawn
  (Rojo drops `Position`). 242 tests.

- 0.19.0 (2026-11-17): knowledge audit and gap fill (PLAN.md). The first-party references came out of
  one production project with a weak-model core; engine fact was separated from that project's habits.
  Wrong tips removed (no `+=`, dying RenderStepped, `CharacterAdded` instead of `Character`, no save
  tool, HTTP push, ProfileStore `ListenToRelease`), defaults restated (authored world, clip animation,
  plain remotes, plain UI), every trap tagged docs/live/field. New: `rbforge audit` + `rb_audit`, a
  working starter kit, six genres, lint T026-T044, `existing-projects.md`, `current-engine.md`, a
  specialist routing table in the router, a docs-sample parse gate. Fixed: structure rung and reviews
  auditing snapshots (field report), `code_only` swallowing code after a `-- [x]` comment, T022/T025
  false positives. Three field reports closed. 238 tests.

- 0.18.0 (2026-11-16): servertest preflight/ready/client/grace/keep/suites, script-attribute results,
  doctor cloud-vs-local places and gateway reach, 38-tool MCP reference, production-project knowledge
  (Open Cloud assets, Blender rigs, AnimationConstraint, IKControl, ragdolls, test placement). 217 tests.

- 0.17.3 (2026-11-15): doctor waits briefly for a just-registered Studio's place name. Published-place
  read-only checks recorded above. 205 tests.

- 0.17.2 (2026-11-15): live commands no longer fail with "0 Studio instances open" right after a session
  starts (StudioMCP registers with Studio 2.7-3.6 s after spawn; sessions and the doctor probe poll for it).
  Push conflict guard proven in live Studio. 204 tests.

- 0.17.1 (2026-11-15): whole-project audit; every fix reproduced first and covered by a test that failed
  before it. Agent connect/disconnect no longer crash on an absent Hermes/Claude (Uninstall left later agents
  wired), repeat connect is a no-op, agent configs are replaced atomically; `docs update` no longer deletes the
  cache before a clone succeeded; UTF-8 stdio in the MCP server and CLI; `--changed-only` in a repo
  subfolder; `long_string` early close; traps T014 crash; security-review `==` false positives; `RBF-TYPES`
  exit 4; stale-definitions skip reason; servertest attribute validation; doctor `--no-probe` 15.6 s -> 5.2 s
  (concurrent agent status, one toolchain probe); `rbforge.cmd` launcher; `Uninstall.ps1 -RemoveState` and
  the true state location in README/uninstall; installers require Python 3.11. 202 tests.
  Note for test authors: an agent-wiring test must run under `_fake_user_home()` and `_isolated_home()` -
  one that did not edited the real `~/.claude.json` during this audit (reverted entry by entry).

- 0.17.0: audit fixes (StudioMCP leak on a failed Session, `check` silently auditing zero files under a
  `*Packages*` path, comment/string false positives, missing-directory `incomplete`, `Foo.spec.luau` pushed into
  `Foo`, suffix-matched checksums, tracebacks on missing files, an idle evidence session, Kimi Code skill root)
  and two Roqer-derived ideas written fresh: push conflict guard with backup-before-overwrite, and MCP
  annotations/instructions/catalog budget; `rbforge new` ships a Lune spec so a fresh project can gate `pass`; Hermes `.deleted` profile no longer an install root. 187 tests. StudioMCP measured exiting 0.16 s after stdin EOF, so the
  new tree-kill fallback adds no latency.

- 0.16.2: three more silent-failure entries (overhead shadows, vertical `lookAt`, scatter reshuffle) and step 7 of
  the art-direction pass.

- 0.16.1: three more silent-failure entries (viewmodel material tiling, viewmodel fill light, fixed-window
  foley cuts) and two playbook rows.

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
  — the only thing blocking 1.0.0. The starter kit and `audit` changed what a weak model starts
  from, so the baseline-versus-Forge comparison is now worth more than before.
- Starter kit: genre-specific sample services (the kit ships one generic action loop; each genre gets
  a plan and a recipe, not its own code yet). Data service against a real store: save, rejoin, a
  forced read failure -> kick (only the Studio in-memory path ran live).
- `audit`: the handler table follows one level of delegation inside one file; cross-file delegation
  reads as "no guard seen".
- Still `field` class (one report, not reproduced): AlwaysOnTop SurfaceGuis not rendering.
- `world-audit` has run on a small fixture place only; measure its time on a dressed world of a few
  thousand pieces before recommending it in a per-build loop.

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
python src\rbforge_cli.py audit <dir> [--json]      # existing project: ranked fix order
python src\rbforge_cli.py new <dir> --genre shooter --premise "..."
python tests\run_tests.py         # RBFORGE_TEST_ONLY=<substring> runs a subset locally
python mcp_server\server.py        # stdio MCP, 19 tools
python src\rbforge_cli.py servertest <file> --repeat 3 --restart   # live streak (needs Studio)
python src\rbforge_cli.py runs --text                              # run ledger for the cwd's project
rbforge.cmd <command>              # same CLI, from the checkout
```

## Log

- 2026-11-24 — 0.22.0: streaks, failure forensics, run ledger, 41-tool MCP surface, starter refusal
  reasons, field lessons from a production milestone (read-only). Offline only. Run ledger and failure
  logs live in `RBFORGE_HOME/runs/` (`%LOCALAPPDATA%\RobloxForge\runs`).
- 2026-11-24 — 0.21.0: field lessons (one-instance QA, ragdoll, shared state, APIs), T046,
  `rbforge agent connect` interpreter fix; 245 tests; offline only (Studio in use by another session).
  Released v0.21.0 from 8bc6095 (CI green on dec6642 and 8bc6095; 0 open Dependabot, code-scanning
  and secret-scanning alerts). Published zip sha256-verified (79faa378...727aae), `smoke_artifact.py`
  OK from the extracted asset (25 skills, 19 MCP tools); skills `current` in every agent root (350);
  `rbforge doctor --no-probe` reports v0.21.0 (the probe was skipped to leave the busy Studio alone).

- 2026-11-18 — 0.20.0: field lessons from a second production project; world-audit probe, T045,
  push refuses during Play, scaffold dev place fix; 242 tests; probe and push refusal proven live.
  Released v0.20.0 from c9586c0 (CI green on fce255c and c9586c0; a timing-flaky agents test that failed
  on 0778564 now asserts overlapping probes instead of a wall-clock budget; 0 open Dependabot,
  code-scanning and secret-scanning alerts). Published zip sha256-verified (85fa7a72...5b0ccb),
  `smoke_artifact.py` OK from the extracted asset (25 skills, 19 MCP tools); skills `current` in every
  agent root (350 installs); `rbforge doctor` reports v0.20.0.

- 2026-11-17 — 0.19.0: knowledge audit, audit command, starter kit, genres, lint T026-T044; 238 tests;
  starter loop proven in live Studio Play.
  Released v0.19.0 from 1abefb5 (CI + CodeQL green on 5184530 and 1abefb5; 0 open Dependabot,
  code-scanning and secret-scanning alerts). Published zip sha256-verified
  (976c933c...74c3e8), `smoke_artifact.py` OK from the extracted asset (25 skills, 19 MCP tools),
  `new` + `check` PASS and `audit` clean run from it; skills updated and `current` in every agent
  root; `rbforge doctor` reports v0.19.0.
  Known quirk, not fixed in this release: `python -I src/rbforge_cli.py` cannot import `rbforge`
  (isolated mode drops the script directory from `sys.path`); the `rbforge` launcher is unaffected.

- 2026-11-16 — 0.18.0: servertest upgrades, doctor place identity, 38-tool MCP surface; 217 tests.

- 2026-11-15 — 0.17.3: place-name wait; published place verified read-only; 205 tests.

- 2026-11-15 — 0.17.2: Studio discovery wait; push guard verified live in Place1; 204 tests.

- 2026-11-15 — 0.17.1: audit fixes (see Done), 202 tests green.
  Released v0.17.1 from 3fc5aab (CI + CodeQL green on that SHA, 0 open alerts); published zip
  sha256-verified, smoke-tested, doctor run from it; skills updated and `current` in all five agents.

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
