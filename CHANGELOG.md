# Changelog

All notable changes to RobloxForge. Versions are pre-1.0; the skill reference
set and the `rb_*` tool surface are the public contract.

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
