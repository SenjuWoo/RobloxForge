# Changelog

## 0.14.7 - 2026-11-08

Closes the three defects the 0.14.6 summary claimed were already closed, plus the two that were left
open: the diagnostic map still merged files, the CLI test still never touched its project, and a cached
analyzer was trusted by its filename.

### Fixed
- **The diagnostic map still merged nested same-named files.** 0.14.6 kept the last two path segments,
  which turned `src/Server/init.luau` and `tests/Server/init.luau` into one bucket - the exact case the
  0.14.6 test did not cover. The key is now the whole project-relative path, and containment is a real
  `commonpath` check rather than a string prefix, so `proj2` no longer counts as inside `proj`. A path
  outside the root keeps the name the analyzer printed.
- **The CLI test proved nothing about the path argument.** It built a temporary project and then ran
  `check` against the process cwd, accepting exit 0, 2 or 4 - so a broken positional path passed. It now
  runs `check <path>`, `check --root <path>` and `check <path> --scope static` from a cwd that is not the
  project and asserts `report.root` and `report.rungs_run`, plus one real render whose header must name
  the project.
- **A cached luau-lsp was reused without asking it its version.** `scripts/install_luau_lsp.py` now
  probes `--version`, reuses the binary only when it reports the pin, and reinstalls - naming what the
  cache actually reported - otherwise.

### Changed
- StyLua is stated as **2.6.0** everywhere (skills, `docs/roblox-briefs`, both vendored copies, and the
  knowledge source manifest, which also carried a stale luau-lsp 1.69.0). The scaffold and `rokit.toml`
  already said 2.6.0; the documentation now agrees.
- `STATE.md`: the diagnostic-map and CLI rows describe what their tests actually assert, the duplicated
  "Skill installer (previous)" row is gone, and the test count is current.

### Tests
148 passed, 0 failed, 0 skipped (was 145).

## 0.14.6 - 2026-11-07

Reliability pass on the 0.14.5 work: the documented command did not run, a "skip" counted as a pass,
and the diagnostic map merged same-named files.

### Fixed
- **`rbforge check .` was documented everywhere and accepted nowhere.** The CLI only had `--root`.
  `check` now takes an optional positional project path as well, keeps `--root` working, and refuses
  a positional path that disagrees with `--root` (exit 2, explicit message) instead of silently
  preferring one.
- **A skipped test counted as a pass.** Any non-exception return was green, so the Luau semantic test
  could report success without an analyzer on the machine. `tests/run_tests.py` now has a real SKIP
  status, prints it separately, and reports `N passed, M failed, K skipped`.
- **The doc test did not test the doc.** It embedded a copy of the example. It now extracts the
  canonical block out of `typing-luau.md`, so the reference and the test cannot drift, and a guard
  test proves a returned skip is never counted as a pass.
- **Same-named files were merged in the diagnostic map.** Grouping by basename put
  `src/Server/init.luau` and `src/Client/init.luau` in one bucket - common in Roblox projects. The map
  now groups by repository-relative path and keeps the parent directory.
- **"definitions ok" overclaimed.** File presence is not proof of a successful load; the line now says
  `definitions present` / `sourcemap present`.
- The new definition-using tests restore a pre-existing `RBFORGE_LUAU_DEFINITIONS` value instead of
  deleting it.

### Added
- `scripts/install_luau_lsp.py` - pinned luau-lsp 1.70.1, per-platform asset, `.ci-tools/` (gitignored).
- A dedicated `luau-semantics` CI job on one platform: installs the pinned analyzer, runs the suite
  with `RBFORGE_REQUIRE_LUAU_LSP=1` so the semantic examples execute for real instead of skipping. The
  other matrix legs stay tool-free and fast.

## 0.14.5 - 2026-11-07

Correction pass on 0.14.4's guidance: one explanation was wrong, one recommendation was unsafe, and
the "how to verify" section taught a method that can report a crashed analyzer as clean.

### Fixed
- **The sealed/unsealed explanation was wrong.** Table literals are unsealed by default; a type
  annotation is what seals a variable. A literal still widens into an annotated parameter or
  dictionary index. `typing-luau.md` now shows the four verified cases, keeps the annotation, and
  documents the real cause of the error that started this: a dictionary keyed by an instance type
  reads as `T?`, and assigning a fresh table into that local does not un-optionalise it, so writing it
  back into a non-optional slot fails. Fix with a fresh local, not by deleting the type.
- **`--!strict` on procedural geometry is no longer described as a mistake.** Replaced with a
  decision order (typed config, boundary validation, typed intermediates, narrow casts) and an
  explicit escape-hatch policy: `--!nonstrict` needs concrete evidence in the header comment, every
  `any` needs one line naming the invariant it relies on, and neither removes the tests.
- **`grep -c Error` is gone from the guidance.** `check.py`'s contract is documented instead:
  pass / fail / skip, with abnormal or silent analyzer exits as failures and missing definitions as a
  skip, never a pass.
- **Navmesh advice reconciled.** Wait for the world's ready signal, retry a bounded configurable
  window, then treat `NoPath` as a genuine defect - the "available after a couple of minutes" note was
  a warm-server observation and is no longer presented as a rule.
- **Case studies are labelled as case studies.** Untyped-parameter cascades, config-driven builders
  and the DataStore structural twin are scoped to the project they came from; the general language
  rules are separated from them.

### Added
- **Diagnostic map in the failure detail.** A failing `luau-lsp` rung now prints the blocking count,
  file count, analyzer exit, whether definitions and the sourcemap loaded, the worst files and the
  worst diagnostic kinds - so a weak model can find a root cause instead of reading thousands of
  repeated leaves. Pure formatting over diagnostics already parsed; no second analyzer.
- Tests: a silent abnormal exit cannot be reported clean, the summary names the worst file and kind,
  and the sealed/unsealed examples in `typing-luau.md` are re-run through the pinned analyzer so the
  doc cannot rot back into a wrong claim.

## 0.14.4 - 2026-11-07

Knowledge from taking a real 72-file game from 4,815 type errors to zero, plus the two test-harness
defects that hid failures behind a timeout.

### Added
- **`references/typing-luau.md`.** The triage that actually works: get the diagnostic distribution by
  file and message before editing, then kill the four root causes - untyped parameters (generic
  unification reports the failures at *call sites*), `nil` reassignment killing narrowing, sealed table
  literals refusing to widen, and `--!strict` on procedural geometry. Includes the boundaries where a
  cast is honest (`DataStore:UpdateAsync`'s structural twin, module-boundary tables) and why they need
  a comment.

### Changed
- **`references/sharp-edges.md`** now opens with the Luau syntax that does not exist: no default
  parameter values (`= nil` is a syntax error that cascades into hundreds of diagnostics), a line
  starting with `(` is an ambiguous argument list, and a nullable parameter is still a required
  argument.
- **`references/testing-debugging.md`** documents that the MCP Luau sandbox has its **own `require`
  cache**: module state read there is empty even while the game is running fine, `Script.Source`
  cannot be written from it in Play mode, and live-state tests therefore need a pushed Script. Also
  records that a cold-start `PathStatus.NoPath` is an asynchronous navmesh bake - retry `ComputeAsync`
  for a bounded window instead of treating it as broken geometry.

## 0.14.3 - 2026-11-06

Maintenance pass: two reports that were being dropped, and test scaffolding that leaked.

### Fixed
- **A failed backup migration vanished.** `install()` called `migrate_backups()` and discarded the
  report, so a backup that could not be moved out of a skill root stayed where agents load it as a
  skill, with no word to the caller. `migrate_backups()` now returns per-agent results and `install()`
  appends `migrated N backup(s) ...` or `MIGRATION FAILED: ...` to that agent's line - including the
  skipped and blocked paths.
- **Test scaffolding leaked.** `_prepared_root()` patched `paths.home` with a lambda that created a
  fresh temporary directory on every call and was restored by a separate `_cleanup()` helper that some
  tests bypassed. Both helpers are replaced by one `installed_tree()` context manager: it patches the
  three globals, yields `(src, root, home, agent)`, and restores all of them and deletes the temp
  directories on the way out.

### Tests
138 total (was 136): a migration that raises is surfaced by `install()` with the OSError text while the
backup stays in place, and the context manager restores every patched global and removes its directories.

## 0.14.2 - 2026-11-06

Routing that reads a project instead of a string, and a migration that only touches its own folders.

### Fixed
- **Substring routing.** `ai` matched `terrain`, `map` matched `bitmap` and `roadmapping`. Premises are
  now matched as whole words or whole phrases (plurals included), and the source scan ignores comments,
  so a `-- TODO: PathfindingService` line no longer routes a project to NPC guidance.
- **A nonexistent `--root` was silently "a small project".** It now raises `RBF-ARG-003` and the CLI
  exits 2 with `{"ok": false, "error": ...}`.
- **No readable source was called "small".** The result carries `source: "none"` and says the verdict is
  unavailable until the project has scripts.
- **Backup migration moved anything with `.rbforge-backup-` in its name.** It now only accepts
  `<our-skill>.rbforge-backup-*`, validates every agent name first (`RBF-ARG-001`), moves whole
  directories by rename, and returns `{moved, failed}` instead of swallowing errors.
- **Test isolation:** `_prepared_root()` installed a `paths.home` lambda that created a new temp
  directory on every call and was never restored. One stable home per test now, restored with the other
  patched globals in `_cleanup`.

### Added
- `rbforge new` writes the optimization profile into `PLAN.md` and returns it as `optimization`, so a
  new project starts with guidance that matches its (nearly empty) source instead of boilerplate.
- The primary skill says when to run `rbforge optimize`: project start, a new dominant system, or a
  measured slowdown - not on every change.

### Tests
136 total (was 130): terrain obby -> no NPC, bitmap UI -> no streaming, roadmapping -> no streaming,
comment-only mentions -> nothing, invalid root -> error, no-source wording, migration moves only ours
(contents intact) and refuses an unknown agent.

## 0.14.1 - 2026-11-06

Four trust defects, one of them visible in the agent UI as duplicate skills.

### Fixed
- **Installer backups were written inside skill roots**, where every directory is a loadable skill: a
  `roblox-audio.rbforge-backup-*` folder appeared as a duplicate skill in Hermes, Claude and Grok.
  Backups now go to `%LOCALAPPDATA%\RobloxForge\backups\<skill>.<stamp>`, and `migrate_backups()`
  sweeps leftovers out of every root on each install (12 removed on this machine, 0 left behind).
- **An abnormal analyzer exit could be downgraded to `warn`.** Ordering is now: no process → skip;
  exit not in (0, 1) → fail (luau-lsp documents 1 as "diagnostics"); type errors → fail; lint-only →
  warn; else pass. Exit 127 with readable lint output is a failure, not a warning.
- **Cached type definitions were trusted by size alone.** `discover()` now verifies the pinned sha256
  before using the cache, reports a tampered cache with the refetch command, and memoises the digest on
  (path, size, mtime) so one check does not rehash 850 KB repeatedly.
- **The vendored performance skill still set a universal texture rule** ("1024² max for most"). It now
  asks for a measurement at the target device tier; the amendment is disclosed in
  `THIRD-PARTY-NOTICES.md`, and no other vendored file is modified.
- A format-string bug in the ROLLBACK_FAILED message (two placeholders, one argument) surfaced through
  the new backup-location tests and is fixed.

### Added
- `rbforge optimize --premise "..."`: picks level A always, level B only from evidence (request words
  plus source patterns for streaming, networking, NPCs, physics, procedural generation, persistence,
  UI), and names the measurement level C would need. It says plainly that it is agent-guided routing,
  not measurement.

### State
- `STATE.md` no longer claims luau-lsp never runs; it records what now runs and the pin as the gap.

## 0.14.0 - 2026-11-06

The typecheck rung finally runs, and optimization advice is chosen instead of recited.

### Added
- `rbforge types status|fetch`: downloads the maintained Roblox definitions
  (`JohnnyMorganz/luau-lsp@1.70.1 scripts/globalTypes.d.luau`, 851 KB) into
  `%LOCALAPPDATA%\RobloxForge\types`, **verifies the pinned sha256 before caching**, and never
  executes what it downloads. A project-local `globalTypes.d.luau`, `types/globalTypes.d.luau` or
  `RBFORGE_LUAU_DEFINITIONS` wins over the cache.
- The typecheck rung now resolves definitions in that order, runs `luau-lsp analyze --platform=roblox`,
  and generates a temporary Rojo sourcemap when the project has a `default.project.json` and `rojo` is
  installed - which is what turns every `require` from "unknown" into a checked call.
- `references/optimization-levels.md`: level A (always), level B (feature-driven, with an evidence
  table), level C (profiling required first), and the no-universal-budgets rule.

### Fixed
- The typecheck rung was a permanent skip on every machine: without definitions luau-lsp reports
  `Unknown global 'Instance'` on every line, so the result was noise and got skipped.
- Diagnostics were parsed as `path:line:col` only; luau-lsp prints `path(line,col)`, so real
  diagnostics fell through as "exited 1 without diagnostics".
- `--ignore` for `artifacts/**`, `backups/**`, `.git/**`: recovery copies were being typechecked.
- Lint findings no longer fail the typecheck rung (selene owns lint); only `TypeError`/`SyntaxError`
  block the gate, and lint-only output is a `warn`.
- `rbforge new` now writes `default.project.json`; without it a fresh project could not be built from
  disk and every require was unknown. The server template no longer declares an unused handle.

### Verified
- On DEADZONE: HAVEN the rung now runs against 71 files with the cached definitions and reports real
  errors (e.g. `Viewmodel.luau(169,23): TypeError: Key 'lastYaw' not found`), where yesterday it
  reported nothing at all.

## 0.13.13 - 2026-11-06

One decision rule, one more case, caught by the reproduction rather than by a fresh install.

### Fixed
- **An edited `KNOWLEDGE-PATH.txt` was replaced without a backup.** `_matches_source()` ignores that
  file on purpose - its absolute vendor path differs per machine - so it cannot be used to prove the
  tree is untouched. A `modified` state therefore now goes straight to `backup-and-replace`, whatever
  `_matches_source()` says. Status said `modified`, the plan said `replace`, and the edit vanished.
- The legacy-manifest ownership fix from 0.13.12 is unchanged: a manifest without `dirs` still only
  earns `replace` when the whole tree matches the shipped copy.

### Tests
120 total (was 118): an edited pointer on same-version reinstall, and an edited pointer across a
0.13.10 -> current upgrade, both requiring a backup that contains the user's text. Negative control
with the 0.13.12 decision: `state: modified (KNOWLEDGE-PATH.txt)`, `BACKUPS: []`, edit gone.

## 0.13.12 - 2026-11-06

Two migration defects, found by upgrading a real 0.13.10 install rather than a fresh one.

### Fixed
- **Upgrading a 0.13.10 install deleted user content.** Those manifests carry `files` but no `dirs`,
  and the stale branch of `_plan()` chose `replace` without checking the tree - so a folder or link the
  user had added vanished, with no backup. Ownership is now decided only by `_matches_source()`, which
  compares files **and** directories against the shipped copy; anything else takes
  `backup-and-replace`. A missing `dirs` field is never read as proof of ownership.
- **Adjacent directory links could be missed.** `_manifest_dirs()` called `dirs.remove()` while
  iterating that same list, so pruning one link skipped the next entry. It now iterates a copy and
  prunes traversal afterwards, which matters for three or more adjacent links.

### Tests
118 total (was 115). The migration tests build a real 0.13.10-style manifest (stamp + `files`, no
`dirs`), add a user directory or link, run the upgrade, and require both a backup and the preserved
entry inside it; a third case proves three adjacent links are all inventoried.

## 0.13.11 - 2026-11-06

The inventory now sees everything the user can put inside a skill, not just files.

### Fixed
- **A user-added empty directory was deleted by uninstall.** `_manifest_files()` walked files only, so
  an empty folder was invisible; `remove()` then pruned every empty directory and, at the end,
  `rmtree`d the skill. The inventory records directories (`dirs` in the manifest), uninstall removes
  only manifest-recorded ones, and the recursive fallback is gone: an unrecognised entry now keeps the
  directory and is reported as `kept`.
- **A directory symlink or Windows junction was deleted with its contents unwatched.** Links are now
  inventoried as entries and never descended into, so the target is never touched and the link itself
  survives uninstall. Broken links behave the same.
- **An upgrade replaced such a skill in place, silently dropping the entry.** `_matches_source()` now
  compares directory entries as well as files, so a tree that gained a folder or a link is no longer
  "provably ours" and gets the backup-and-replace path.
- README line 99 no longer says "the two RobloxForge skills".

### Compatibility
- Manifests written before this version have no `dirs` key; they are still accepted and directory
  comparison is skipped until the next install writes a full manifest.

## 0.13.10 - 2026-11-06

Recovery-safety pass: four narrow defects, each reproduced with fault injection before the fix.

### Fixed
- **The in-flight skill was never restored.** The operation was only recorded after its rename
  succeeded, so when `os.replace(stage, dst)` raised, the previous copy stayed in its backup and the
  destination was empty. The operation is now recorded before activation, restored first, then the
  earlier ones roll back in reverse.
- **A restore that also fails is now explicit.** `RBF-SKILL-005` says `ROLLBACK_FAILED`, names the
  skill, and points at the `<name>.rbforge-backup-*` copy that still holds the original - instead of
  reporting a clean undo that did not happen.
- **Half-written staging directories survived.** `copytree` can create the destination and then die;
  every attempted stage is now recorded before the copy and removed on failure.
- **An edited `KNOWLEDGE-PATH.txt` was deleted on uninstall.** The pointer is generated metadata, but
  the user can edit it, so it now goes through the same manifest-hash rule as every other managed
  file: removed only when unchanged, otherwise kept and reported.
- **A version stamp with no manifest reported `current`.** It is now `legacy (no manifest)`, never
  current. Installing migrates it, replacing in place only when every byte is provably ours and
  keeping a backup otherwise.

### Tests
111 total (was 105). New fault-injection matrix: stage failure before/after the destination exists,
backup-move failure, activation failure with a user-edited installation, restore failure during
rollback, edited knowledge pointer, legacy install. README counts corrected, bundle registry already
points at `rbforge skills status`.

## 0.13.9 - 2026-11-06

Safety pass on the manifest-backed installer, driven by an independent reproduction of each defect.

### Fixed
- **Arbitrary file deletion (P0).** `remove()` joined manifest entries straight onto the skill path, so
  a manifest containing `../victim.txt` deleted a file outside the tree. Manifests are now treated as
  untrusted input: `_read_manifest()` validates schema, version, a non-empty file map, the essential
  `SKILL.md`, and every path through `safe_rel()` (absolute, drive-qualified, `..`, empty segments and
  symlink escapes are refused). A rejected manifest means `partial`, never `current`, and the skill is
  refused by `remove()` rather than deleted.
- **Foreign directories were uninstallable.** A directory with a manifest but no version stamp was
  reported `foreign` and then deleted. `remove()` now refuses anything without our stamp.
- **Modified files were deleted.** Uninstall removes only files whose bytes still match the manifest;
  a customized `SKILL.md` stops that file and the directory survives, listed as `kept`.
- **Legacy installs were `rmtree`d.** A stamped directory with no manifest is now refused with
  `legacy or invalid manifest - reinstall first` instead of being removed wholesale.
- **Empty/corrupt manifests reported `current`.** A manifest must be non-empty and name `SKILL.md`;
  `{}` and malformed JSON now report `partial`.
- **Installation was not a transaction.** Per-skill staging could leave the first skills installed when
  a later stage failed. Every skill is now staged and validated before any activation; a failed stage
  reports `nothing was replaced`, and a failed activation restores what was already activated and names
  anything it could not restore.
- **Backup names could collide.** Stage and backup paths carry a random suffix and never overwrite an
  existing backup (`_unique`).
- **Luau precheck still fooled by long brackets.** `_lua_code_only()` now parses `[[`, `[=[`, `[==[` …
  for both strings and comments at any level; dynamic attribute names still pass.

### Documentation
- README: 13 → 17 MCP tools, two → 25 skills, 33 → 105 tests, status heading 0.3.0 → 0.13.9.
- The bundle's companion registry no longer hardcodes two skill names; it points at
  `rbforge skills status` as the single source of truth.

## 0.13.8 - 2026-11-06

The installer is now safe to run twice, and safe to run over work you have already done.

### Fixed
- `skills status` called an agent `current` when only one of its roots was current. Hermes runs one
  skill tree per profile, so "profile A is fine, profile B has never seen it" read as healthy.
  `current` now requires every root, and `by_root` carries each root's state.
- A directory holding only `.rbforge-version` counted as installed. Every skill now carries
  `.rbforge-manifest.json` (relative path + sha256 per file), so `status` distinguishes `partial`
  (payload missing), `modified` (payload changed or user files added), `stale` and `foreign`.
- Reinstalling deleted user files: the old code `rmtree`d any owned directory. A directory we cannot
  prove is byte-identical to the shipped copy is now renamed to `<skill>.rbforge-backup-<stamp>` and
  kept; only a provably identical copy is replaced in place.
- A foreign skill in one root blocked halfway through a batch, after earlier skills were written.
  Preflight now inspects every root and skill first and aborts before the first write.
- Installation stages each skill next to its destination, swaps by rename, and restores the previous
  copy if activation fails; a repeated install reports `already current` and touches nothing.
- `skills remove` deletes only the files in the manifest and leaves a directory that still holds user
  files, instead of removing the tree.
- One skill root spelled two ways (`\\` vs `/`, case) was installed twice; roots are deduplicated by
  normalized path.

### Changed
- `server_test` refuses a test file with no `SetAttribute` call in *executable* code: comments and
  strings no longer count, and a dynamically built attribute name is accepted.
- `scripts/smoke_artifact.py` verifies the whole catalog (25 skills, frontmatter, descriptions)
  instead of the two skills it used to know about, and still checks the MCP handshake (17 tools).
- README no longer claims two skills.

## 0.13.7 - 2026-11-06

Proven end to end in a live Studio session, and one dead end removed.

### Added
- `server_test` refuses a test file that never writes its result attribute. The contract is
  `workspace:SetAttribute(attr, "PASS ..." | "FAIL ...")`; a file that only returns a value used to sit
  for the full 120 s timeout and report `TIMEOUT`, which hid the mistake. It now returns
  `INVALID: the test never sets workspace:<attr>` in 0.00 s with the fix in the message.

### Verified live (sandbox place, not a game)
- Evidence cycle: console read clean, a 250 KB JPEG returned by Studio with a sha256, and a real
  `PASS 1 player(s)` server test produced `verified_playtest`.
- Binding holds both ways: the same observation with a wrong `revision` returns `unverified` and names
  the mismatch; omitting `scenario` does not verify either.

## 0.13.6 - 2026-11-06

Adopted the EL4CTEO Roblox skill pack, so this repository owns the Roblox skill
catalog instead of borrowing it from a general bundle.

### Added
- 23 Agent Skills under `skills/roblox-*` (MIT, October 2026 snapshot), copied
  unmodified with `skills/ROBLOX-SKILLS-LICENSE.txt` and an entry in
  `THIRD-PARTY-NOTICES.md`.
- `OUR_SKILLS` now lists them, so install, update and doctor cover the pack.
- A test that every shipped skill is loadable, attributed **and tracked in git**:
  untracked skills install on this machine and vanish in a fresh clone.

## 0.13.5 - 2026-11-06

Corrective pass on the evidence boundary, console truth, batch safety and agent handoff.

### Fixed
- **Observation reuse by omission.** `receipt()` skipped a binding check when the receipt simply left
  `scenario` (or `revision`) out, so a `smoke-old` observation verified an unrelated task. Omission is no
  longer a match: any recorded identity field must be stated and equal, or the receipt degrades to partial.
  `revision` is now part of the receipt and the MCP schema.
- **Console false negatives.** Classification was anchored to the line start, so Studio's real shapes
  (`[Server] Error: …`, `19:52:36.782  ServerScriptService.Main:4: attempt to index nil`) read as clean.
  Timestamps, `[Tag]` prefixes and `script:line:` locations are stripped before matching; `No error was
  found` still stays clean and unreadable output stays `unknown`.
- **Batches continued after an unrecovered rollback.** `push` now stops on `rollback_failed` and marks the
  remaining files `not_attempted`, naming `ServerStorage.rbforge_backups` in the reason.
- **`rb_collect_evidence` ignored its advertised default.** The schema said `capture_screenshot: true`
  while the library default was `False`, so omitting it silently skipped the capture. The handler applies
  the default and reports `capture: {requested, images, status}`.
- **Rollback edge cases.** The restore readback is now protected (`pcall`) and a class change only reports
  `ROLLED_BACK` when the temporary replacement is verifiably gone.
- **The generated-Luau test could not fail.** The old assertion was a tautology. The gate now uses stylua's
  documented contract (exit 2 = parse error, 1 = formatting only) or selene's parse counter, and a
  deliberately invalid fixture must be rejected.
- **`STATE.md` was four releases stale** (it still said 0.13.1 and "live MCP unverified"). Rewritten into
  proven-offline / proven-live / unit-only / unverified, and a test now fails if the package version, the
  CHANGELOG's top section and STATE's version line disagree.
- **A brand-new scaffold failed its own gate.** The generator wrote CRLF files, so stylua reported
  `Config.lua` as unformatted the moment a user ran `rbforge check`. Files are written with LF now, and a
  test scaffolds a project and requires zero failures.
- **Installed skills could not resolve vendored knowledge.** `rbforge skills install` now writes
  `KNOWLEDGE-PATH.txt` beside the skill with the absolute path, and the skill documents the fallback.

### Verified live (disposable place, this session)
- Real console output containing a nil-index error is classified `errors` (2), not `ok`.
- `rb_collect_evidence` called through the MCP handler with no capture flag returns
  `capture.status = "captured"` and a 253 KB JPEG.
- Push/readback, hierarchy, `servePlaceIds`, `init.luau`, class-change backup and all three rollback
  scenarios remain as verified in 0.13.3/0.13.4.

### Still unit-only / unverified
- `ROLLBACK_FAILED` (a restore that itself fails) and the published-place/multiplayer paths.
- The weak-model benchmark; 1.0.0 stays gated on it.

## 0.13.4 - 2026-11-06

Rollback, proven against a real engine failure instead of a mock.

### Fixed
- **A class-change rollback left the original in the backup folder.** `restore()` checked `created`
  before `backup`, and a class change sets both, so a failed write removed the stand-in and returned
  "new script removed" while the original stayed orphaned in `ServerStorage.rbforge_backups`. The backup
  branch now runs first: destroy the stand-in, move the original home, verify name and parent, and only
  then report `ROLLED_BACK (original restored)`.

### Verified live (disposable place, engine-level failure)

Studio rejects `Source` at 200,000 characters — a genuine write failure, not a simulated one:

| Scenario | Result | Studio state afterwards |
|---|---|---|
| existing script, 210 KB source | `rolled_back` — `ROLLED_BACK write failed` | `Alpha` still a ModuleScript, source byte-identical |
| class change (ModuleScript → Script), 210 KB source | `rolled_back` — `ROLLED_BACK write failed (original restored)` | `Swap` back as ModuleScript with its exact original source; backups folder empty |
| brand-new script, 210 KB source | `rolled_back` — `ROLLED_BACK write failed (new script removed)` | no leftover instance |

Two regression tests lock the ordering and the write-failure branch. 78 tests.

### Known gaps
- `ROLLBACK_FAILED` (a restore that itself fails) is covered only in unit tests: forcing Studio to
  refuse the *restore* of a small source is not reachable through the documented API.
- Multiplayer, published-place path and the weak-model benchmark remain outstanding.

## 0.13.3 - 2026-11-06

Live Studio pass on a disposable sandbox place (Studio `Place1`, unpublished, `PlaceId 0`). Two real
defects only live testing could find, plus the proof the fake-session tests could not give.

### Fixed
- **`screen_capture` was called without `capture_id`.** Studio answers
  `Missing required argument: capture_id`, the collector swallowed it as "no screenshot", and every
  receipt capped at `playtest_observed_partial`. A unique `capture_id` is now passed and the returned
  `image/jpeg` block is decoded, hashed and stored (240 KB capture in the live run).
- **Evidence collection failed in Play mode.** The place name was read from the Edit datamodel, which
  does not exist during a playtest, so `collect_evidence` raised. It now falls back to the Server
  context and records which datamodel answered.

### Verified live (not mocked)
| Check | Result |
|---|---|
| `push` first write | 2 files `synced`, readback digests matched, `Alpha` = ModuleScript, `Runner` = Script |
| same-class overwrite | `synced`, no backup created |
| declared `Model` vs existing `Folder` | `HIERARCHY ServerScriptService.Containers is Folder, the project expects Model`, folder untouched |
| class change | `Swap` ModuleScript → Script `synced`; original preserved as `Swap_rbforge_1793986769000` in `ServerStorage.rbforge_backups` |
| `init.luau` mapping | `Nested` = ModuleScript with `Child` ModuleScript beneath it |
| `servePlaceIds` | wrong place → `RBF-STUDIO-003`; `["invalid"]` → `RBF-ARG-002` |
| `servertest` | PASS → `pass`, FAIL → `fail`, malformed → `unknown`, timeout → `fail`/`TIMEOUT` |
| console | `get_console_output` read, status `ok`, 0 errors |
| `collect_evidence` end to end | `verified_playtest` with a real captured image and a recorded inspection attestation |

Two regression tests were added from these runs (capture_id is sent; Play falls back to Server). 76 tests.

### Removed
- The `zToreviewandintergrateordocument` intake folder: its curated contents now live in
  `knowledge/vendor/` (Forge) and in the pack (`_CANONICAL-SKILLS/roblox-*`,
  `docs/roblox-assistant-briefs/`).

### Still not verified
- Rollback under a genuine Studio write failure was not forced; the code path is covered by unit tests
  and generated-Luau review only.
- Multiplayer, published-place path and the weak-model benchmark remain outstanding.

## 0.13.2 - 2026-11-06

Final corrective pass: verification and push now fail closed, and the docs match the code.

### Fixed
- **Screenshot trust bypass.** `collect_evidence(screenshots=..., screenshots_inspected=True)` let a
  caller-supplied path satisfy the screenshot requirement. A path is now recorded as a *claim*
  (`claimed_screenshots`); only image bytes returned by `screen_capture` become captures, stored under
  `receipts/shots/` with mime, size, and SHA-256. `screenshots_inspected` is only an attestation that
  references a captured digest, and `verified_playtest` additionally requires `console_status == "ok"`.
  Text-only capture responses are kept but marked `verified_image: False`.
- **MCP image blocks were discarded.** `Session.call()` flattened text and dropped images, so a screenshot
  could never be proven. New `Session.call_content()` returns every block; `_save_capture()` decodes
  base64 with size/type limits and rejects malformed data.
- **Console classification.** Substring matching turned "No error was found" into a failure and empty
  output into "clean". Lines must *start* like a failure (`Script error:`, `stack begin`, `attempt to`,
  `fatal:`); output that supports neither conclusion is `unknown`, which can never be verified clean.
- **Incomplete rollback.** `rolled_back` was reported on a successful `pcall`. A restore is now verified by
  reading the source back (or moving the backed-up instance home and re-checking name and parent) before
  `ROLLED_BACK` is returned; otherwise it is `ROLLBACK_FAILED` and the backup stays in
  `ServerStorage.rbforge_backups`. Write and readback are both protected.
- **Folder exemption.** A project declaring `Folder` skipped the class check, so an existing `Model` was
  accepted. Every declared class is compared.
- **`servePlaceIds` failed open.** `["invalid"]` collapsed to an empty list and disabled the guard. Invalid
  entries, non-list values and booleans now raise `RBF-ARG-002` before anything is written; an explicit
  empty list still means "unconstrained" (documented).
- **Rojo validation vs Rojo.** Tested against rojo 7.7.1: `name` is optional (Rojo falls back to the folder
  name) while an empty `tree` is rejected and `{"$className": "DataModel"}` builds. The validator now
  matches that and no longer demands a `name`.
- **CLI/MCP parity.** `--base-ref` was implemented in the core but not exposed; `rb_check`,
  `rb_collect_evidence` and `rb_verify_receipt` schemas now advertise the arguments they accept
  (`changed_only`, `base_ref`, `project`, `scenario`, `revision`, `capture_screenshot`, `studio_id`).

### Added
- Optional third-party packs vendored under `knowledge/vendor/` (MIT `roblox-skills`, 23 skills, plus 23
  Roblox-Assistant briefs) with a routing index. Not installed by `rbforge skills install`.
- Skill guidance: verification levels, screenshot-is-not-inspection, and how to read `push` states.
- Ten regression tests (74 total): claimed screenshot, image-block handling, uninspected capture, console
  classification, Folder enforcement, `servePlaceIds` table, MCP schema/implementation parity.

### Known gaps
- No live Studio: `push`, `collect_evidence`, `screen_capture` and `get_console_output` are proven against
  fake sessions and a real Luau parser only. The live matrix in `STATE.md` is still owed.
- `verify_chain()` cannot detect truncation of the final receipt (documented in the test).
- Weak-model E2E benchmark still not run; 1.0.0 stays gated on it.

## 0.13.1 - 2026-11-06

Hotfix: the push path generated invalid Luau, and several verification shortcuts were still open.

### Fixed
- **Generated Luau was not Luau.** `_push_code` pasted `json.dumps(parent_classes)` straight into the
  script, producing `local classes = {"a.b": "Model"}` - JSON syntax, which Luau cannot parse - so every
  push with a declared parent class failed inside Studio. The map now travels as a JSON *string* through
  `long_string()` and is decoded with `HttpService:JSONDecode`. Every other interpolated value (parent,
  name, class, source) also uses `long_string`, so quotes, backslashes, Unicode and long-bracket
  delimiters survive. A regression test runs the generated script through **selene**, and CI installs a
  pinned selene (`scripts/install_selene.py`) so the parser check is real.
- **Existing parents were never checked.** A `Folder` where the project declares `Model` was accepted.
  Each existing parent is now compared against the declared class and returns
  `HIERARCHY <path> is Folder, the project expects Model` without touching anything.
- **Overwrites were not recoverable.** The previous `Source` is read first; if the readback does not
  match, the old body is restored and the result is `ROLLED_BACK` (or `ROLLBACK_FAILED` when the restore
  itself fails). A newly created script is removed instead of left half-written.
- **Wrong-place pushes.** A project that declares `servePlaceIds` now refuses a Studio session on any
  other place (`RBF-STUDIO-003`) before a single source is written.
- **`record_observation` was a public promotion path.** It is now private; the only way to obtain a
  trusted observation is `collect_evidence`, which reads the place, runs the test and - new - fetches
  `get_console_output` and `screen_capture` through the Studio MCP. Tests inject a fake *session* into
  the real collector instead of fabricating a record.
- **The collector could not verify anything.** `console_logged` was hardcoded `False`, so even a passing
  test could only be partial. Console output is read for real, its error lines are counted from the text,
  and the digest is recorded. A missing tool leaves the receipt partial instead of claiming otherwise.
- **Observations were not bound to a task.** Receipts now require the observation's project and scenario
  to match; an observation from another project, scenario or Studio cannot verify a receipt.
- **Legacy receipts broke the chain.** Pre-0.13 receipts have no `sequence`; sorting them after newer
  ones made every link look broken. The legacy prefix keeps its historical order, sequenced receipts
  follow, and `verify_chain()` checks what a hash chain can actually check.
- **A misleading test.** The old deletion test restored receipt A by writing receipt B into it. Rewritten:
  exact-byte restore, then middle deletion (detected), then final deletion (documented as undetectable
  without an external anchor).
- **`--changed-only` skipped the typechecker** when the change set was empty, and ignored committed work.
  The typechecker always runs; `--base-ref` checks against a commit; the coverage note moved to
  `report["coverage"]` and states the mode, base ref and file count.
- **Rojo validation** now requires a top-level `name` and a non-empty tree.

### Tests
67 total (was 58). New: generated-Luau parsing with selene, existing-class refusal, rollback states,
wrong-place refusal, console-error counting, observation expiry, project/scenario binding, legacy receipt
migration, base-ref change detection, and Rojo `name` validation.

### Known gaps
- No live Studio in this pass: `push`, `collect_evidence` and the console/screenshot tools are proven
  against fake sessions and a real Luau parser. Live integration is still pending.
- `verify_chain()` cannot detect truncation of the final receipt; that is inherent without an external
  anchor and is now stated in the test.
- The weak-model E2E benchmark has still not been run; 1.0.0 stays gated on it.

## 0.13.0 - 2026-11-06

Final reliability audit. Verified status now depends on an observation RobloxForge recorded, not on
anything the caller can assert.

### Fixed
- **Forged provenance.** `provenance="tool"` was an argument, so an agent could manufacture
  `verified_playtest` with invented checks, a fake screenshot path and made-up tests. Trust now comes
  only from `observation_id`, an opaque id returned by `collect_evidence` / `rb_collect_evidence`,
  which runs the Studio queries itself. Observations are bound to Studio id, place, execution context
  and time, expire after 6 hours, and are rejected when unknown, stale or from another Studio. The
  `provenance` argument is recorded but ignored for trust.
- **Contradictory receipts.** A verified receipt could say `screenshot_inspected_by_vision=False` and
  `no_fatal_runtime_errors=False`. One function now decides the level, the observed checks come only
  from the observation, and a verified receipt is downgraded to `playtest_observed_partial` when a
  required observation is missing. New level `playtest_observed_partial`; `playtested_with_errors` is
  reserved for an observed failure, so a missing screenshot is no longer called an error.
- **Forked receipt history.** Two writers could both see `prev_digest=None`. Sequence allocation,
  previous-digest lookup, digest calculation and persistence now run inside one cross-process file
  lock (msvcrt / flock), records carry a monotonic `sequence`, writes go through a temp file, and
  `verify_chain()` checks unique sequence, unbroken links and payload digests.
- **Rojo projects without a tree passed.** `{"name": "has no tree"}` produced a green `project-map`.
  Validation now requires a `tree` object, string `$path`/`$className`, existing targets, no duplicate
  mappings, and script/model/directory targets.
- **Wrong parent classes on push.** A missing parent was always created as `Folder`, so a project
  declaring `Model` got the wrong hierarchy. Declared `$className` values are honoured for
  Folder/Model/Configuration and anything else is refused with a `hierarchy` result instead of a guess.
- **Cross-drive crash.** `os.path.relpath` raised `ValueError` when a source lived on another drive;
  `_rel()` falls back to the absolute path.
- **Release smoke could hang.** `scripts/smoke_artifact.py` bounded every MCP read with a thread
  timeout and a clear failure instead of a blocking `readline()`.

### Added
- `--changed-only` for `rbforge check`: format/lint scoped to changed files, with an explicit note
  that it is not a whole-project audit and skips when nothing changed.
- Real MCP contract test: spawns the server, checks `initialize`/`tools/list`, asserts
  `rb_collect_evidence` exists and `rb_verify_receipt` advertises `observation_id`, replays the forged
  provenance call and requires a non-verified result, and checks that an unknown tool errors.
- Tests for concurrency (six writers, one chain), tampering, deletion, stale/mismatched observations,
  Rojo tree validation, hierarchy refusal, cross-drive paths and changed-only scoping. 58/58.

### Known gaps
- No live Studio in this pass: `collect_evidence`, push readback and server-test parsing are proven
  against fake sessions. Live integration remains open.
- The weak-model E2E benchmark has still not been run; 1.0.0 stays gated on it.

## 0.12.2 - 2026-11-06

Second audit pass: the gate can no longer be satisfied by a tool that did not run, and verification
distinguishes what it observed from what it was told.

### Fixed
- **A crashed linter passed the gate.** selene's exit status was mapped to "warn" for anything that was
  not a clean run with the word "error" in it, so exit 127 `process terminated unexpectedly` left the
  overall gate at PASS. Exit 0 = pass, 1 = findings (fail only for `error[...]`, otherwise warn),
  anything else = tool failure = fail. A tool that cannot execute is a failure, not a skip.
- **Mixed push batches raised `KeyError`.** An unmapped path produced a result without `state`, and the
  aggregation read `r["state"]`. Every row now carries `file`, `target`, `state`, `ok`, `got`, `want`
  (+`why`), with `unmapped` and `unreadable` as first-class states.
- **Receipt chain broke at the third write.** Suffixed filenames sort `-2` before `.`, so the third
  same-second receipt chained to the first. Receipts now reserve names atomically (`O_CREAT|O_EXCL`,
  zero-padded index) and the chain is read in creation order (`mtime`, then name).
- **Evidence was still self-certifiable.** `evidence` was caller-supplied and treated as observed.
  Receipts now carry a provenance: `tool` (produced by `collect_evidence`, which talks to Studio) or
  `agent`. Agent-supplied evidence caps at the new `playtest_claimed` level; `verified_playtest`
  requires tool provenance, a logged console, zero console errors and an inspected screenshot.
- **`limitations="not tested"`** became a list of characters; strings are one item now.
- **MCP schema** for `rb_verify_receipt` gained `evidence`, `provenance` and a string-or-array
  `limitations`; the server also advertised a stale `0.3.1` version and now reports the package version.

### Added
- `scripts/smoke_artifact.py` and a real release step: the archive is unpacked and checked for a working
  import, CLI startup, an offline command, both skills and the MCP `initialize`/`tools/list` handshake.
  The previous step ran a test file that is deliberately not shipped and swallowed the failure.
- Six regression tests (53 total): crashed linter, mixed push batch, three-receipt chain, agent evidence
  cap, limitation coercion, `collect_evidence` provenance.

### Known gaps
- No live Studio run in this pass (MCP was off): `collect_evidence`, `push` readback, `server_test`
  parsing and `init.*` mapping are proven against fake sessions only.
- The weak-model E2E benchmark has still not been run.

## 0.12.1 - 2026-11-06

- `push` no longer destroys a script whose class changed (ModuleScript -> Script). The old instance is renamed
  `<name>_backup_<time>` and moved to `ServerStorage.rbforge_backups`, so a mistaken mapping is recoverable.

## 0.12.0 - 2026-11-06

Corrective audit: the gate no longer reports work it did not do.

### Fixed
- **Typechecker exit status.** `luau-lsp` was judged by counting the word "error" in its output, so a crashed
  typechecker (exit 127, no diagnostics) passed and a clean run printing "0 errors" failed. Exit status decides now;
  non-zero with no diagnostics is a failure, a missing tool is a skip, diagnostics are matched structurally.
- **Verification receipts.** Claims promoted themselves: `checks=[...]` plus `playtest_performed=True` produced
  `verified_playtest` with no evidence behind it. Receipts now separate `claimed_checks` from observed `evidence`
  (studio id, place, execution context, test scenarios with expected/actual, console read, screenshots), and only
  evidence can reach a verified level. Two receipts written in the same second no longer overwrite each other.
- **Push readback.** `push` hashed the string it had just sent, which proves only that Python can hash. It now reads
  `inst.Source` back out of Studio, compares it, and returns `synced`, `mismatch` or `unverified` per file - never a
  pass when the readback failed.
- **Server test parsing.** `"PASS" in out` accepted `NOT_PASS` as a pass. Results parse the first line exactly; unknown,
  malformed, `FAIL`, `NOT_PASS` and `TIMEOUT` never pass.
- **Rojo `init.*` files.** Directory initialisation scripts were skipped, silently dropping whole module trees from
  every push. They now map the directory itself to a Script/LocalScript/ModuleScript, with children nested under it.
- **Malformed project JSON.** An unparseable `default.project.json` returned "no missing paths" and passed the project
  map. It is now a failure that names the parse error.
- **selene on Luau.** With no `selene.toml` selene parses as Lua 5.1 and rejected valid Luau (`+=`, `continue`, types),
  and every warning was promoted to a failure. Projects without a config get the Roblox std; warnings are warnings,
  errors are failures.
- **Session claim.** The module docstring promised session reuse that does not exist; it now states that each CLI
  command opens and closes its own Studio session.
- `push` reported paths relative to the current directory, crashing when the project lived on another drive.

### Added
- Six regression tests: typechecker exit status, malformed project JSON, Rojo `init.*` mapping, exact server-test
  parsing, push readback states, and Luau compound assignment under selene. Two existing verification tests were
  rewritten to supply evidence; a new test asserts that claims alone never verify.
- `debugging-playbook.md`: **"When the owner says it's still there"** - reproduce at the reported pose and camera mode,
  baseline before editing, name the responsible object with evidence, smallest change, re-capture the same pose, check
  neighbours, revert failed fixes, classify visual/collision/geometry/replication/persistence, verify Edit vs Play vs
  saved separately, and never claim a visual fix from an indirect signal.

## 0.11.5 - 2026-11-05

### Added
- `sightlines-and-openings.md`: **search for the mechanism before you build one** (a project that already animates a
  barrier does not need a second flat door; grep gate/door/shutter/barrier first) and **clamp in the coordinate space
  you measured in** (world-space builders clamp against `wallX`, not a local constant - the wrong clamp here moved 159
  parts to the origin and still looked plausible; verify by counting parts either side of the boundary).

## 0.11.4 - 2026-11-05

### Added
- Trap rule **T025**: decorative geometry (tendril, nodule, vein, foliage, cable, rubble) created with collision -
  players snag on it and "is this corridor clear" probes lie. Asserted positive and negative.
- `sightlines-and-openings.md`: **decorative geometry is not structure** - `CanCollide`/`CanQuery` false on decor, and
  clamp generated growth to the room's own bounds at creation, or it renders through the door and under the deck.

## 0.11.3 - 2026-11-05

### Added
- `sightlines-and-openings.md`: **closing an opening** - build the closure in the generator (a saved-place part is lost
  on the next rebuild), pass the plot axis instead of a hardcoded `0` when the builder is world-scoped, prove it by
  reading `Transparency` at two distances and counting parts per plot rather than screenshotting a camera wedged in a
  corridor, and keep exactly one mechanism with a comment naming it.

## 0.11.2 - 2026-11-05

### Added
- Trap rule **T024**: a `Debug*` attribute read without a `RunService:IsStudio()` guard is a switch any client can
  flip in a shipped build. Asserted positive and negative.
- `animation.md`: **framing numbers that read as held** (`SCALE 0.5`, `BASE (0.22, -0.30, -1.20)` = ~12% x 32% of the
  viewport; measure with `WorldToViewportPoint`, do not eyeball) and **one mechanism per job** - pick the fix that
  survives a fresh Play, delete the duplicate, and comment which one is authoritative.

## 0.11.1 - 2026-11-05

### Added
- Trap rules **T022** (a cloned weapon parented to the camera without destroying its `JointInstance`/`Constraint`
  welds - the anchored viewmodel then drags the player) and **T023** (`LocalTransparencyModifier` restored from a
  saved value - the engine owns the local head's value, so the head stays invisible for about a second). Both are
  asserted in the test suite, positive and negative.
- `animation.md`: "Viewmodel traps that only show up in first person" - kill the clone's joints, park the anchor
  before a `WeldConstraint` (it keeps the offset it saw at creation, so the gun ends up hundreds of studs off camera
  and looks like it never rendered), never restore a saved transparency.
- `debugging-playbook.md`: `player-state` gains the "I fly / get launched" case.

## 0.11.0 - 2026-11-05

Diagnosis stops being improvised.

### Added
- **Probes** - 14 reviewed Luau diagnostics with headers (`probe:`, `datamodel:`, `params:`, `purpose:`) in
  `templates/probes/`: `console`, `gui-overflow`, `ray-all`, `box-scan`, `hide`/`restore`, `camera-pin`/`camera-free`,
  `scene-audit`, `ui-audit`, `player-state`, `whereis`, `remotes`, `perf`. `rbforge probe [name] [--run key=value]` and
  MCP `rb_studio_probe` render them with parameter substitution; rendering never executes anything. Every probe exists
  because an agent burned a Studio boot writing the same inspection code wrong - `ray-all` and `box-scan` include
  `CanQuery = false` parts, which engine queries skip.
- **Trap lint** - `rbforge review --kind traps` and MCP `rb_traps_review`: 17 rules for Luau that compiles and still
  breaks a Roblox game (`wait`, `spawn`/`delay`, `LocalPlayer` on the server, `RenderStepped` on the server, and more),
  each carrying severity, why it bites, the fix, and the reference that explains it.
- **`references/debugging-playbook.md`** - symptom -> probe -> cause -> fix, and the fix protocol (reproduce at the
  reported pose, one decisive test, revert failed attempts, never hide a symptom, never unseal to chase a visual bug).
  The router skill now points at it first when something looks wrong.
- **`rbforge live`** (`src/rbforge/live.py`) - one stdio MCP session shared by `push`, `exec`, `probe --run` and
  `servertest`: pushes are checksum-verified against what Studio holds, and a single open Studio is picked
  automatically.

### Changed
- `sharp-edges.md` and `animation.md` corrected against what the engine actually does, not what the previous entries
  claimed.

## 0.10.1 - 2026-11-05

### Fixed (wrong guidance from 0.9.x-0.10.0)
- `live-iteration.md` claimed Edit captures never render SurfaceGuis. False: ordinary SurfaceGuis render; what did not
  render was `AlwaysOnTop = true` SurfaceGuis. Also notes `ImageLabel.IsLoaded` stays false at `ImageTransparency = 1`.
- `sightlines-and-openings.md` now leads with the real cause of a one-direction "flat colour wall": a SurfaceGui with
  `ClipsDescendants = false` (the default) painting oversized children past its part, one-sided. Includes a scan
  snippet, bisect-by-hiding with a fixed capture camera, and the fact that `GetPartBoundsInBox` skips
  `CanQuery = false` parts just like rays. Replaced "cut panels by box overlap" with splitting crossing panels around
  a corridor-sized doorway, constrained on every axis. Added process rules (reproduce at the reported pose, one
  decisive test, revert failed attempts, no symptom-hiding workarounds, never unseal to chase a visual bug).
- `sharp-edges.md`: replaced "blind a screen" with the ClipsDescendants trap, AlwaysOnTop note, query-skip note.

### Added
- `ui-craft.md`: helmet-HUD recipe (pane depth, FOV-invariant depth and PixelsPerStud formulas, yaw/pitch-only pane
  tilt, head-locked sway cap), companion-drone station keyed to the camera, strip-built soft backdrops.

## 0.10.0 - 2026-11-05

### Added
- `references/sightlines-and-openings.md`, linked from the router skill: how to diagnose a flat colour, "screen" or
  panel artefact that only appears from one direction. Covers sampling pixels and matching part colours, testing one
  system at a time, the signature of world geometry seen through an opening (hard edge plus sky strip), and the fixes
  that hold: carry structure past the hole, an approaching player opens the door, cut panels by box overlap never by
  centre, and never delete geometry that seals an opening. Also records the two traps that cost the most time - a
  runtime world build never persists, and generated geometry is `CanQuery = false` so rays miss it.

## 0.9.2 - 2026-11-05

### Added
- `sharp-edges.md`: **match the pixels before the code**. Sample the RGB of the surface in the user's screenshot and
  scan parts by colour proximity in the reported box - positions and raycasts alone cannot identify a visual artefact,
  and colour identifies a part in one query when geometry hypotheses keep failing.

## 0.9.1 - 2026-11-05

### Fixed
- `sharp-edges.md`: a runtime world build (terrain carve, generated geometry) never persists into the saved
  place. A user reporting a wall or plug inside a tunnel playable in Play is usually in edit mode - check for a
  missing HUD in their screenshot and a clear Play ray before touching geometry, then rebuild against the Edit
  datamodel and have the owner save once.


## 0.9.0 - 2026-11-05

Procedural animation and first-person viewmodels.

### Added
- `references/animation.md`, linked from the router skill: the additive layer (`Motor6D.Transform` after the
  Animator, joint caching, drive from real speed), a gait that reads as movement (two-joint legs, damped arm
  counter-swing while aiming, neck counter-rotation, airborne tuck, landing squash, idle breath), and the
  viewmodel recipe (one anchor and welds, scale for the eye, palette lift plus key light, hide the whole body,
  hands, sway/bob/recoil/reload on springs). Also the debug-attribute pattern for verifying states MCP cannot
  drive, and the traps: anchored clones, cloned lights and scripts, scale before welding, C0 vs Transform.


## 0.8.1 - 2026-11-05

Two traps that both read as "the build is broken" in a screenshot.

### Added
- `references/ui-craft.md`: `UIGradient.Transparency` overrides `BackgroundTransparency`, so a "glass"
  panel with a gradient starting at 0 renders as a solid black bar - the cause of the non-blending HUD.
- `references/sharp-edges.md`: cutting a hole in a curved shell - test the quad's corners rather than the
  panel centre (a wide panel covers a corridor its centre misses), gate it by height or the hole climbs
  ring by ring, trim the panel at the opening instead of deleting it (a deleted panel leaves the shell
  unsealed), carve terrain only where a structure is meant to be open, and flatten terrain in
  shell-normalised space so an offset dome does not bury itself.


## 0.8.0 - 2026-11-05

UI craft: why an agent-built HUD reads as slop, and what to build instead.

### Added
- `references/ui-craft.md`, linked from the router skill. Seven tells a reviewer spots
  immediately (everything is a rounded rectangle, default fonts, centre-stacked composition,
  rainbow gradients, emoji icons, uniform spacing, fake progress), the build rules that produced
  a HUD the owner accepted (legibility by text stroke instead of boxes, strip-built backdrops
  with a 2D falloff, small-scale furniture like bearing ticks and per-round ticks, 150-250 ms
  eased motion, three sizes and two weights, 1080p layout plus UIScale, ScreenGui vs 3D visor
  panes, only expose what the server can do), a slop check to run before claiming done, and how
  to read a concept image without flattening it into an ImageLabel.


## 0.7.0 - 2026-11-05

Field notes from a HUD refactor and a companion-drone slice.

### Added
- `references/sharp-edges.md`: what the MCP cannot press - `user_mouse_input`
  scroll does not reach a game's `MouseWheel` handler (a working zoom looks
  broken), a SurfaceGui with `Adornee` lives in PlayerGui rather than under its
  part, and an assigned camera is reset before a capture, so verify state before
  pictures.
- `references/testing-debugging.md`: count the HUD instead of only photographing
  it, and read client errors from `LogService:GetLogHistory()` rather than
  dumping the whole Studio console into context.


## 0.6.0 - 2026-11-04

Field notes from building a projected-sky dome: 225 SurfaceGui panels per plot,
five generated panorama assets uploaded through the Studio MCP, and six plots
rebuilt in edit mode so the editor matched the runtime.

### Added
- `references/sharp-edges.md`: a screen-surface section - which `SurfaceGui.Face`
  a matrix-built panel needs (probe, do not guess), RenderStepped dying on its
  first error, client caches capturing a half-built world, the edit-session
  `require` cache and how to bust it, corner gaps on planar panels over a curved
  shell, the floating base ring of an ellipsoid, and shells that silently wall a
  walk route.
- `references/assets.md`: the generated-image upload loop (`upload_image` wants
  URLs; serve the folder over loopback), the 1024 px clamp, preload plus painted
  fallback, and the equirectangular slice maths for dome projection including the
  round-both-edges rule that keeps seams from crawling.
- `references/testing-debugging.md`: geometry tests must wait for `WorldReady`,
  and the assertion has to carry the failure detail.
- `scripts/serve_assets.py`: loopback static server for the upload loop.

### Why
Each entry above cost a wasted Studio boot in a real session. The dome shipped;
these are the parts that were not obvious until the capture looked wrong.

All notable changes to RobloxForge. Versions are pre-1.0; the skill reference
set and the `rb_*` tool surface are the public contract.

## 0.5.0 — 2026-11-04

Field notes from a long procedural build (a 9,000-part ship, six outposts with
tunnels and an animated blast gate, a rebuilt HUD) driven entirely through the
official Studio MCP. Every item cost at least one wasted round trip first.

### Added
- `references/live-iteration.md`: disk-to-Studio sync without `rojo serve`
  (loopback server + `HttpEnabled` restored in the same call), rebuilding from
  module clones because Edit `require` caches per instance, why a Play-mode
  `require` sees an empty copy of a manager (use a temporary Script or the
  Client datamodel to fire the real remote), what captures cannot show
  (SurfaceGuis in Edit captures; Play captures show the client viewport and
  HUD), restoring the editor camera after `execute_luau`, and saving around the
  automation guard.
- `templates/studio/`: `dev-rebuild.luau`, `connectivity.luau` (union-find
  floating-part proof) and `route-matrix.luau` (pathfinding proof from every
  entry), formatted and selene-clean with their own `selene.toml`/`stylua.toml`.
- `sharp-edges.md` "Engine traps found in real builds": `BulkMoveMode` members,
  SurfaceGui Front is -Z, anchored assemblies ignore welds (move with
  `BulkMoveTo`), lights inside a part's voxel, `LightingStyle` vs `Technology`,
  no audio generator in the Audio API, `FillBlock` overwrites hollow interiors,
  `CorrodedMetal` colour multiplication, pathfinding vs thin collidables, and
  the spawn-before-world race.
- `testing-debugging.md` "Geometry proofs"; `worldbuilding-lighting.md`
  lighting style, believable mechanisms and procedural kit habits (including
  isolating private areas from the shared world).

## 0.4.0 — 2026-11-04

The Forge ships its own pinned Luau toolchain instead of only recommending it.

### Added
- Root `rokit.toml` pinning the full set the template recommends: rojo 7.7.1,
  StyLua 2.6.0, selene 0.32.0, luau-lsp 1.70.1, lune 0.11.1, wally 0.3.2,
  wally-package-types 1.7.0, run-in-roblox 0.3.0.
- `tools/install-toolchain.ps1`: installs rokit via cargo when missing, then
  `rokit self-install`, `rokit add --global` for every pinned tool and
  `rokit install` from the checkout's manifest, and prints each version.
  `Install.ps1 -Toolchain` runs it.
- `rb_toolchain_status` now also searches `~/.rokit/bin`, so a shell started
  before the install still reports the tools as found.

### Why the global manifest matters
The rokit shims in `~/.rokit/bin` resolve a tool from the *nearest* manifest.
`rbforge check` runs in a fixture directory with no manifest at all, so a bare
shim exits with "Failed to find tool" — which the gate reads as a defect (`fail`)
instead of a skip, turning a green run red on any machine that installed rokit
but never added anything globally. The global manifest makes the shims resolve
everywhere; the pinned project's own manifest still wins inside that project.

## 0.3.1 — 2026-11-04

### Fixed
- `Install.ps1`, `Update.ps1` and `Uninstall.ps1` named their helper parameter `$Args`, a PowerShell
  automatic variable, so every `rbforge` call ran with no arguments: the scripts printed usage and installed,
  updated or removed nothing (and skipped `doctor`). The parameter is now `$CliArgs`; a test rejects `$Args`
  parameters in any shipped script.

## 0.3.0 — 2026-11-01

The free-only guarantee, a beginner entry point, and optional plugin awareness.

### Added
- `references/free-stack.md`: the $0 rule as a hard constraint. What is free
  forever, what to never pay for, the free Creator Store filter
  (`scope="creator_store"` + `priceFilter="free"`), free audio rules, and how to
  get quality without money.
- `references/beginner-guide.md`: zero-experience playbook — what the user does
  (one click) vs what the agent does (everything else), session-one walkthrough,
  plain-English vocabulary, and the beginner traps the agent must absorb.
- `rbforge new <dir> --genre <g> --premise "<sentence>"`: scaffold + vertical
  slice plan + ordered next steps in one command, writing `PLAN.md`.
- `rbforge plugins` / `rb_plugins`: detects installed Studio plugins
  (ForgeGUI, GuiForge, UI Labs, Moon Animator, Archimedes, Atmos, F3X), reports
  what each changes and **its free alternative**. Detection is filename-based
  and approximate; an unmatched plugin is reported, never silently ignored.
- `assets.md`: data-driven procedural prop kit (free, no licensing, seeded
  determinism) as the fallback when a generator is unavailable.
- `rbforge plan`, `review`, `project`, `scaffold` are now reachable from the CLI
  (they previously existed only over MCP).

### Changed
- `SKILL.md` rule 8 ($0 by default) and a beginner-mode section.
- Scaffolds ship a pinned `rokit.toml`, `.luaurc`, `selene.toml`, `stylua.toml`.
- `search_asset` documentation corrected: `priceFilter` is lowercase and only
  valid with `scope="creator_store"`. The earlier draft used the wrong spelling
  and would have been rejected at runtime.

### Tests
- 33 checks (was 29): plugin detection and its free-alternative invariant, the
  calm no-plugins answer, live-schema spelling for asset filters, and the
  `new` entry point producing a filled-in plan.

## 0.2.0 — 2026-11-01

The verification gate, and a reference set that matches the live MCP.

### Added
- `rbforge check` (and `rb_check` over MCP, and `scripts/rbx_check.py` for a
  project-local copy): an offline verification gate covering rungs 1-3 of the
  ladder — format/lint/typecheck, pure-Luau unit tests through Lune, and a
  structural audit (missing Rojo `$path` targets, `loadstring`/`fenv`/
  `require(id)`, client-side `DataStoreService`, unanchored geometry, missing
  `--!strict`).
- Exit contract: `0` pass, `2` a defect was proven, `4` tooling missing.
  A missing tool makes the run `incomplete`, never `pass` — a skip is not a
  green light.
- `references/worldbuilding-lighting.md`: terrain heightmap generator, three
  lighting presets, streaming threshold.
- Hash-chained verification receipts (`digest` + `prev_digest`), so a receipt
  folder is an audit trail rather than a pile of claims.
- Scaffolded projects now ship `rokit.toml`, `.luaurc`, `selene.toml`,
  `stylua.toml`.

### Changed
- `references/studio-mcp.md` rewritten against a live handshake: **34 tools**
  (was documented as 27), including `generate_scene`, `generate_texture`,
  `generate_avatar`, `auto_setup_avatar`, `list_skills`, `create_skill`,
  `edit_skill`, and the four `subagent` types.
- `references/assistant-skills.md`: all 14 Roblox-maintained `rbx-*` skills,
  with `list_skills` as the discovery step.
- `references/architecture.md`: three-stage loader (require → priority init →
  isolated start → data-gated player hooks) and the pure-module/service DI split
  that makes headless testing possible.
- `references/persistence.md`: ProfileStore session locking, `MessageAsync`,
  reconcilation rule, migrations, and a Lune test double.
- `references/security-networking.md`: fixed-layout buffer packets and the
  schema-library choice (ByteNet Max / Blink / Zap).
- `references/ui-mobile.md`: Fusion 0.3 scoped API, with the 0.2 habits
  (`:get()`, `[Cleanup]`) called out as runtime errors.
- `references/assets.md`: real generative tool contracts plus a Creator Store
  quarantine sanitizer.
- `references/testing-debugging.md`: the five-rung ladder and console triage.
- `references/game-design.md`: juice matrix and offline economy sanity bounds.
- Toolchain pins verified 2026-11-01 (Rojo 7.7.1, StyLua 2.6.0, Selene 0.32.0,
  luau-lsp 1.70.1, Lune 0.11.1, wally-package-types 1.7.0).

### Fixed
- `doctor` crashed with `TypeError` when a connected Studio reported a place
  with no name; it now falls back to the id.
- The structure rung returned early when a project had no Luau files, silently
  skipping the Rojo `$path` audit.
- README pointed at a non-existent `docs/BENCHMARK.md`.

### Tests
- 29 checks (was 23): gate pass/fail/incomplete behaviour, Rojo path audit,
  reference routing in both directions, receipt chaining, and the doctor
  no-name regression.

## 0.1.1 — 2026-08-25

- `skills/roblox-docs/SKILL.md` shipped truncated with unclosed frontmatter and
  could never be selected. Rewritten; a test now parses every shipped SKILL.md
  as a skill.

## 0.1.0 — 2026-08-22

- Studio + official MCP detection with live handshake probe, creator-docs
  sparse cache with ranked search, doctor/capabilities, agent + skill
  installation, vertical-slice planning, reviews, verification receipts,
  11-tool MCP server, 20 tests.
