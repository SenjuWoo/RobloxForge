# External integrations — what was evaluated, what was taken

Two upstream projects were evaluated for this repository. Both were cloned and read at source; neither is
vendored here. This file records the classification and the reasons, so a later session does not redo the
work or quietly re-add something that was rejected.

Evaluated: `Roblox/roblox-blender-plugin` (MIT) and `SyphoDev-yt/roblox-ai-skills` (custom free licence).

## The line this repository keeps

**RobloxForge** owns planning, standards, orchestration, documentation and verification.
**Roblox Studio's official MCP** owns the live DataModel and the supported Open Cloud calls.
**External generators** (Blender, a texture generator, a map tool) own asset production.

Anything that uploads, authenticates or edits a game stays with the pieces Roblox ships. That is why the
integration below detects and validates instead of reimplementing an uploader.

## SyphoDev skills

Eleven skills, each a workflow with scripts rather than prose. Classification:

| Skill | Class | Why |
|---|---|---|
| `roblox-map` | **REFERENCE** | A real prover (raycast reachability from movement numbers, plan PNG, `.rbxmx` emitter) — the strongest thing in the pack. It needs `numpy`/`scipy`/`Pillow` and its own JSON spec format, so it is a separate tool, not a forge module. Nothing here duplicates its reachability proof. |
| `roblox-3d-model` | **REFERENCE** | Text-prompt → Blender → mesh. Needs Blender; overlaps this repo's new asset route at the export/validate boundary, which is where we do integrate. |
| `roblox-ui`, `roblox-vfx`, `roblox-animation`, `roblox-texture-gen`, `roblox-sfx` | **REFERENCE** | Workflows with their own generators and opinions. Adopting them wholesale would fork RobloxForge's architecture, which the brief forbids. |
| `roblox-code`, `create-roblox-game`, `roblox-build-orchestrator` | **SKIP** | Competing development architectures. `roblox-code` also assumes conventions (Knit-style layouts) that must not be forced onto existing projects. |
| `roblox-skills-setup` | **SKIP** | A Claude-side installer. Running one agent's installer as another agent's is exactly the failure this repository exists to avoid. |

**Licence.** The pack is free to use and modify, may not be sold or bundled for sale, and asks for a link
back to the SyphoDev channel when shared. It is therefore **not vendored**: no copy is redistributed here,
and no file in this repo is derived from it. Install it beside your skills if you want it:

```
git clone --depth 1 https://github.com/SyphoDev-yt/roblox-ai-skills
```

Then point your agent at `skills/` inside that clone. RobloxForge's `roblox-tooling` skill says when that is
worth doing and when the built-in route is enough.

## Roblox Blender plugin

A Blender add-on (3.2+) that uploads selected objects through Roblox's Open Cloud API, with OAuth login and
a per-creator "Upload to:" picker. MIT, published by Roblox as a reference implementation.

**What it is good for:** interactive art iteration inside Blender, and the only supported route that keeps
an artist in one window.

**Why it is not wrapped:** it is a Blender add-on, not a library. Driving its UI from an agent means driving
Blender's UI; its useful surface (login, upload, update an existing package) is exactly the part that must
stay a deliberate human action.

**What was built instead** — `rbforge assets`:

| Question | Answer |
|---|---|
| Is Blender here, and new enough for the add-on? | `blender.path`, `blender.version`, `meets_addon_minimum` (3.2+) |
| Is the Roblox add-on installed for that Blender? | `roblox_addon.path` / `.installed`, found by manifest name, not folder name |
| Does this export fit Roblox? | `rbforge assets check <file>` — GLB triangles per mesh against the 20,000 cap, materials, mesh list |
| How does an asset get into Studio? | `upload_routes`: interactive (add-on), scripted (Studio importer / Open Cloud with an approved key), and the no-Blender fallback (Luau parts, or import a finished GLB/FBX) |

Detection never executes Blender, never authenticates and never uploads. `RBFORGE_BLENDER` overrides the
detected path.

**Verified on this machine:** Blender 5.2.0 detected from the Steam layout, add-on not installed (reported
as `false`, not guessed), GLB validation exercised on generated fixtures over and under the cap.

## Rejected or deferred

- **Vendoring either project** — licence and maintenance reasons above.
- **A second MCP server** — the forge has one; adding another duplicates transport and tool budget.
- **An uploader** — Open Cloud upload needs an API key and writes to a real account. It stays a human step
  run from Blender or from Roblox's own tooling; nothing in this repo will do it unattended.
- **Map proving** — genuinely useful, genuinely a different tool. Deferred to the `roblox-map` skill rather
  than reimplemented; revisit only if its spec format becomes a burden.

## Uninstall

Nothing was installed. `rbforge assets` reports what exists; remove the add-on in Blender's Preferences and
delete the SyphoDev clone if you stop using it. No RobloxForge state depends on either.
