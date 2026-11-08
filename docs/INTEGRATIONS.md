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
| `roblox-map` | **ADAPT** (adapter, not a copy) | A real prover (raycast reachability from movement numbers, plan PNG, `.rbxmx` emitter) — the strongest thing in the pack. It needs `numpy`/`scipy`/`Pillow` and its own JSON spec format, so it runs where it lives: `rbforge map` discovers the install, checks the dependencies, and returns its report unchanged. Nothing of it is copied here. |
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

## Map proving: `rbforge map`

The one part of that pack worth wiring in, because nothing here does reachability proofs from movement
numbers. It runs **where it already lives** - no copy, no fork, no rewrite of its spec or report formats.

```bash
set RBFORGE_SYPHODEV=Z:\path\to\roblox-ai-skills     # repo root, or its skills/roblox-map folder
rbforge map                                          # available? which specs? what is missing?
rbforge map prove minimal --out report.json          # run one spec, keep its report
```

| Behaviour | Detail |
|---|---|
| Discovery | `RBFORGE_SYPHODEV`, accepted at either the repo root or the skill folder. A directory without `scripts/prove.py` and `specs/` is refused, so a wrong path cannot look configured. |
| Dependencies | Probed in the current interpreter (`numpy`, `scipy`, `PIL`). Missing ones make it **unavailable**, not half-working: `rbforge map prove` then exits `DEPENDENCY` and names what is absent. |
| Spec + report | Upstream's own JSON spec and its own report file. The adapter adds `checks_failed` as a summary; it does not reinterpret or rewrite the checks. |
| Studio | Never contacted. The adapter is a subprocess that prints a report; placing a map stays a separate, deliberate step. |
| Exit codes | `0` when upstream says PASS/INFO, `VALIDATION` when it says WARN/FAIL, `DEPENDENCY` when it cannot run at all. |
| Licence | Not redistributed. `status()` carries the attribution line, and `docs/INTEGRATIONS.md` says where it came from. |

**Proven, not described:** against the upstream clone's own `minimal` spec on this machine, `rbforge map`
reported `available: true`, listed its four shipped specs, ran `prove.py`, and returned upstream's report
(`result: WARN`, nine checks with `P1`…`P9`) plus the report path. The dependency probe was also proven
negative: before `scipy` and `Pillow` were installed, it correctly refused.

The remaining skills stay references. Adapters for the generators would each be a second framework, and the
brief forbids that; `roblox-tooling` says where to find them if a project wants one.



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
| Is Blender here, and new enough for the add-on? | `blender.path`, `blender.version`, `blender.short_version`, `meets_addon_minimum` (3.2+) |
| Is the Roblox add-on installed for that Blender? | `roblox_addon.state` = `installed` / `absent` / `unknown`, plus every root searched. `absent` only when a required root existed and held nothing; `unknown` when a root we needed to see was missing |
| Does this export fit Roblox? | `rbforge assets check <file>` — GLB triangles **per mesh** against the 20,000 cap, materials, mesh list |
| How does an asset get into Studio? | `upload_routes`: interactive (add-on OAuth), Studio MCP / importer with Studio-managed authorization, or an Open Cloud creator API key if you choose to use one; plus the no-Blender fallback (Luau parts, or a finished GLB/FBX) |

### What "check" does and does not prove

It reads the glTF **JSON chunk only**. Triangle counts are exact for `TRIANGLES`, `TRIANGLE_STRIP`
(n-2) and `TRIANGLE_FAN` (n-2), indexed or not; vertex data is never decoded, so degenerate faces, inverted
normals and welded/unwelded seams are **not** validated. The report says so with `counts_geometry: false`.

Four outcomes, and the exit code follows them rather than collapsing into success:

| `status` | Meaning | Exit |
|---|---|---|
| `within_limit` | measured, every mesh under the cap | 0 |
| `over_limit` | measured, and named meshes are over `ROBLOX_TRI_LIMIT` | `VALIDATION` (2) |
| `invalid` | not the format it claims, malformed, or unsupported extension | `VALIDATION` (2) |
| `unverified` | recognised but not measured (FBX, OBJ, `.gltf`, a GLB it could not fully account for) | `DEPENDENCY` (4) |

`unverified` is deliberately not a pass: a file whose geometry was never counted cannot close a gate.

### Three ways to authenticate, and why none of them is automatic here

| Route | Who authorizes | Where it belongs |
|---|---|---|
| Blender add-on | OAuth login inside Blender, per creator | Interactive art sessions. The token lives in the add-on, not in this repo |
| Open Cloud Asset API | A creator API key you create in the Creator Hub | Scripted pipelines you control; an API key is **not** universally required |
| Official Studio MCP | Studio-managed authorization for the approved Open Cloud calls, with no key in the agent's hands | Agent-driven work already running through Studio |

An API key pasted into a file is none of these, which is why no uploader is implemented.

Detection never executes Blender, never authenticates and never uploads. `RBFORGE_BLENDER` overrides the
detected path.

**Verified on this machine:** Blender 5.2.0 detected from the Steam layout (`short_version` 5.2, so the
add-on search looks in the folder Blender actually writes), the add-on's state reported honestly rather than
guessed, and GLB validation exercised on generated fixtures: per-mesh pass and fail, two 16k meshes passing
at 32k total, mixed files, all three triangle modes, and eight malformed inputs that must not crash.

## Rejected or deferred

- **Vendoring either project** — licence and maintenance reasons above.
- **A second MCP server** — the forge has one; adding another duplicates transport and tool budget.
- **An uploader** — every route above needs a real authorization, and uploading writes to a real account.
  It stays a human step run from Blender or from Roblox's own tooling; nothing in this repo does it unattended.
- **Adapters for the generator skills** — each would be a second framework. They stay references.
- **Vertex-level validation** — would need a real glTF parser or Blender. Not claimed, not pretended.

## Uninstall

Nothing was installed by this repository. `rbforge assets` and `rbforge map` report what exists on the
machine; remove the Blender add-on in its Preferences, and delete the SyphoDev clone if you stop using it.
No RobloxForge state depends on either, and unsetting `RBFORGE_SYPHODEV` disables the map adapter.
