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

## Verifying things the MCP cannot press

- **Wheel input needs the pointer on the viewport.** `user_mouse_input` with a
  `moveTo` onto the 3D view first, then `scrollUp`, did reach the game's
  `MouseWheel` handler (first-person zoom verified 2026-11-05). A scroll with no
  prior `moveTo` may land nowhere. If a scroll seems ignored, do not call the
  feature dead: read the state it writes (an attribute, a camera distance, a HUD
  flag) and verify that code path. Treat anything needing a focused viewport or
  `MouseBehavior.LockCenter` the same way.
- **A SurfaceGui with `Adornee` lives in PlayerGui, not under its part.** Walking
  the part's children for the gui returns nothing and reads as "no panes
  rendered". Search `PlayerGui` by name or Adornee instead.
- **A client-side feature can be complete and still be invisible in a capture.**
  Studio resets a camera you assign from `execute_luau` before the capture lands.
  Verify state first, picture second.

## Cutting a hole in a curved shell

- **Test the quad, not the centre.** A panel 37 studs wide easily covers a 24-stud
  corridor while its centre sits outside it, so a centre-only test leaves the
  shell hanging inside the tunnel and blocks the view. Test all four corners.
- **Test the height too, or the hole climbs.** On a dome, panels higher up shrink
  toward the axis, so their corners also fall inside a corridor test. Add a height
  gate (a panel whose bottom is above the opening cannot be in it) or you delete
  rings all the way to the oculus.
- **Flatten floors in shell space, not plot space.** A dome offset from its build
  rectangle will rise inside the rectangle-based apron: the wall buries itself in
  the hillside and panels clip through terrain. Flatten out to ~1.25 of the shell's
  own normalised radius before the hill function starts.
- **Trim the panel, do not delete it.** A deleted panel leaves a hole in the
  sky that reads as "the dome is not sealed". Cut the panel at the opening's top
  edge instead (re-centre it and shrink its height by the same fraction) and the
  shell stays continuous above a door, gate or tunnel mouth.
- **Carve terrain only where the structure is meant to be open.** A tunnel that
  is carved along its whole length lies in an open cut with its roof slab
  exposed. Carve the run inside the shell and the far mouth; fill everything
  between and the structure reads as a hillside with an entrance.

- **Match the pixels before the code.** When a user sends a screenshot of a
  "wall", "panel" or "screen effect" that your raycasts say is not there, sample
  the image: read the RGB at the offending surface, then scan `workspace` for
  parts whose `Color` is within ~0.07 of it inside the reported box. That found a
  tunnel blocked by `PineTier` foliage from a treeline ring the same session that
  three geometry hypotheses (panels, skirt, terrain) had already failed on. Colour
  is a part's identity; positions alone will not tell you what you are looking at.
- **A runtime world build does not persist.** Terrain carving, dome panels and
  anything else built by a server script exist only in that session; the saved
  place still holds whatever geometry was there before. A user who reports a
  wall, plug or leftover hill blocking a tunnel they can walk in Play is usually
  looking at **edit mode**, where the carve never happened. Two cheap tells: their
  screenshot has no HUD (scripts are not running) and a Play ray from the same
  spot is clear. Fix it by running the same builder against the **Edit** datamodel
  (`--dm Edit --exec tools/dev_rebuild_all.luau`), then have the owner save the
  place once - without that save the next reopen restores the old state.

- **`SurfaceGui.ClipsDescendants` defaults to false.** Children past the canvas
  render in mid-air beyond the part, one-sided. Oversized parallax/background layers
  then "appear" in doorways and tunnels from one direction only. Set it to `true` on
  every screen-style SurfaceGui. Check this before blaming terrain or geometry.
- **Do not delete a panel that seals a shell.** Split it around the opening (see
  sightlines-and-openings.md); removing it opens a hole the owner reports next.
- **`AlwaysOnTop = true` SurfaceGuis did not render** (Studio captures and Play).
  For camera-bound HUD panes use depth-tested panes about 0.75 studs from the eye.
- **`GetPartBoundsInBox` skips `CanQuery = false` parts**, same as raycasts.

- **Weapon FX that starts at the character instead of the barrel.** `hrp.Position + Vector3.new(0, 1.6, 0)` is the
  chest, and a weapon model's `PrimaryPart` is usually the **grip** - both put the ray and the tracer inside the body, so
  shots look like they come out of the player's sternum and can hit geometry the barrel has already cleared. Name the
  barrel tip on every weapon (`Muzzle`) and resolve it before the raycast: `model:FindFirstChild("Muzzle", true)`, then
  PrimaryPart, then the old offset. First person needs one more step - the body gun is hidden behind the camera, so the
  local tracer must come from the viewmodel's muzzle while remote players keep the body one.

## `tostring(Enum.Material.Grass)` is not `"Grass"`

`tostring()` on an Enum item yields the full path - `"Enum.Material.Grass"` - so a lookup keyed by
plain names (`{ Grass = ... }`) misses every time and falls through to its default. In an impact or
surface-effect payload send `result.Material.Name`, and keep `tostring()` for logs only. The failure is
silent: the effect still plays, it just plays the fallback for every surface.


## Luau syntax that does not exist (and reads like a type error)

- **No default parameter values.** `function f(a: string, b: number? = nil)` is a *syntax* error
  (`Expected ')' ... got '='`) and can cascade into hundreds of bogus diagnostics in one file. Write
  `b: number?` and pass `nil` explicitly at every call site that omits it.
- **A line that starts with `(`** continues the previous expression. `local x = 1` followed by
  `(tbl :: any).field()` is "Ambiguous syntax: this looks like an argument list". Assign to a local
  first, or prefix the statement with `;`.
- **Nullability is not optionality.** `material: Enum.Material?` still requires an argument. A helper
  with four optional parameters has four-argument call sites, so pass the `nil`s.

## Type errors cascade from untyped parameters

`function M.Do(player, id)` gives `player` a generic type, which Luau then unifies against every call
site; the failures are reported *at the callers*, as `Expected this to be 'Player', but got
'{- Character: {- FindFirstChild: ... }}'`. That message means "the parameter was never typed", not
"a wrong value was passed". Annotating the parameter fixes dozens of errors in one edit. See
`typing-luau.md` for the full triage.
