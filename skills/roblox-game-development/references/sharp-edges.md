# Sharp edges (things that bite every agent at least once)

Hard-won, verified against live Studio + MCP sessions. Read before your
first build session.

## MCP tool pre-parser quirks

- **No `+=` / `-=` / `*=` in tool-call code strings.** The pre-parser
  rejects augmented assignment. Write `x = x + 1`.
- Attribute access on results is unreliable across wrappers - prefer
  explicit indexing/locals in executed Luau.
- `execute_luau` needs `datamodel_type` (Edit / Client / Server). Server
  truth requires Server context; Edit context runs in edit mode where
  Players don't exist.

## Instance / math traps

- `Model:PivotTo(CFrame)` moves the whole model; `Part.CFrame = ...` moves
  one part. Setting PrimaryPart CFrame on a model does NOT move the rest.
- `WaitForChild` infinite-yield = wrong name or missing instance. Fix the
  cause; don't nil-guard around it reflexively.
- Kill bricks / Touched: debounce or the event refires every physics step.
- `Humanoid.Died` vs `Humanoid.Health <= 0` polling: prefer the event.
- Character may not exist yet when the player joins - use
  `player.CharacterAdded`, not `player.Character` at connect time.

## Engine traps found in real builds

- **`Enum.BulkMoveMode` has `FireAllEvents` and `FireCFrameChanged` only.** There
  is no "fast without events" member; using one throws at runtime.
- **SurfaceGui `Face = Front` is the part's -Z face.** `CFrame.lookAt(pos, pos + n)`
  points -Z along `n`, so that orientation shows the text on the side facing `n`.
  If your helper thinks "+Z is the visible side", flip the carrier by
  `CFrame.Angles(0, math.pi, 0)` once, inside the helper.
- **Tweening an anchored part does not move parts welded to it** - anchored parts
  ignore welds. Move an anchored assembly with `workspace:BulkMoveTo(parts,
  cframes)` from offsets captured once (`root.CFrame:ToObjectSpace(part.CFrame)`).
- **Light emitters inside a part's voxel can emit nothing** on voxel lighting.
  Put the light on an invisible emitter a few studs below a ceiling fixture, not
  on the fixture embedded in the slab. SpotLights barely register there.
- **`Lighting.LightingStyle` is script-writable; `Lighting.Technology` is not**
  from MCP/command context. Guides that say "set Technology = Future in a
  script" are stale.
- **The Audio API has no generator.** `AudioOscillator`/`AudioNoise` do not exist
  (`AudioPlayer`, `AudioEmitter`, `AudioFader`, effects and `Wire` do). Motor
  hums, alarms and clangs need real audio assets; plan the asset step.
- **`Terrain:FillBlock` overwrites everything in the box**, including the inside
  of a tunnel or room you built from parts. Fill around hollow volumes, never
  through them.
- **`CorrodedMetal` (and other bright textures) multiply the part colour.** Mid
  oranges render as salmon camouflage; use dark rust colours (around
  RGB 50-65, 27-34, 21-24) and keep it to a minority of panels.
- **Thin floating collidable slabs and props in doorway corners break
  `PathfindingService`** at AgentRadius 2. Make furniture collide through a
  floor-standing invisible hull, set decor `CanCollide = false`, keep door
  corners clear, and test routes from both approach directions.
- **Spawn-before-world races.** With `CharacterAutoLoads = true` a player can
  load before a procedural world exists and fall through, or spawn under a floor
  and respawn normally on death. Disable auto-load, build the world and assign a
  real `RespawnLocation`, then `LoadCharacterAsync`.

## Workflow traps

- Editing StarterGui at runtime does nothing for existing players - edit
  PlayerGui copies.
- Edit-mode `execute_luau` cannot see play-mode state and vice versa.
- Multiple Studio sessions: every tool takes `studio_id`. Get it from
  `list_roblox_studios` first; guessing targets the wrong place.
- Console output is cumulative - filter by timestamp/your run, don't
  re-read ancient errors and "fix" them again.

## Agent traps (the meta-failures)

- Declaring done when scripts exist but nothing was playtested.
- "Visually verified" without having inspected a screenshot.
- Building 15 systems before proving one loop.
- Trusting client-sent numbers because "it's just a prototype" - prototypes
  get published.

## Screen surfaces (dome walls, billboards, in-world displays)

Field notes from building a 225-panel projection dome across six plots. Each one
was invisible in the code and obvious in the capture.

- **`SurfaceGui.Face` is not "the side you can see".** A panel built with
  `CFrame.fromMatrix(centre, right, up)` has its LookVector along `right × up`,
  which on an inward-facing shell points *outward*, so the screen belongs on
  `Enum.NormalId.Back`. Probe before painting 200 panels:
  `panel.CFrame.LookVector:Dot((centre - panel.Position).Unit)`. Negative means
  the LookVector points away from the interior: use `Back`.
- **A RenderStepped connection dies on its first error**, silently and
  permanently. Everything after the throw stops for the rest of the session.
  Put optional visual passes on their own connection, wrap the body in `pcall`,
  and write the message to a workspace attribute you can read back.
- **A client cache built during world construction is permanently wrong.** A
  display pass scanned the dome while it was still being built, cached 62 of 225
  panels, and because the table was non-empty it never refreshed — the whole
  feature did nothing with no error. Publish a `PanelCount` attribute on the
  server after building and recache whenever the client's count disagrees.
- **Edit `require` caches a ModuleScript for the whole session.** Pushing new
  source into Studio does not invalidate it: a rebuild used a `GameConfig` from
  before a field existed and died with `attempt to index nil with 'Ground'`.
  Bust it by cloning the module, parenting the clone under the same name,
  destroying the original, then requiring the clone.
- **Planar panels on a curved shell leave wedge gaps at the corners**, and the
  world sky leaks through as bright spikes on a bright screen. Fix both ends:
  overlap each panel ~12 % past its true quad, and put a dark backing slab behind
  it so any pinhole reads as bezel instead of sky.
- **An ellipsoid's base ring does not touch the ground.** When the dome centre
  sits at courtyard height, the wall floats and players walk out underneath. Add
  a skirt ring and leave exactly one opening, skipping segments whose
  *endpoints* fall in the corridor — a midpoint-only test skipped nothing and
  walled the tunnel.
- **Any new collidable shell can invalidate walk routes.** After adding a skirt,
  wall or gate, re-run the route test: the tunnel went `NoPath` on all six plots
  while the capture looked perfect.
