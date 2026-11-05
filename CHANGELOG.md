# Changelog

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
