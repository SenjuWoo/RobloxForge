# Sharp edges (things that bite every agent at least once)

Each item says what stands behind it:

- **(docs)** the official engine reference;
- **(live)** observed in a Studio session, with the month;
- **(field)** reported once from one project and not reproduced elsewhere - a lead to test, not a rule.

Case notes from one procedural-dome project (panel faces, shell openings, skirts) moved to
`sightlines-and-openings.md`; they are specific to that kind of build.

## Players and characters

- **Handle what already exists.** `PlayerAdded` and `CharacterAdded` fire only for arrivals after the
  connection. Connect, then loop `Players:GetPlayers()` / check `player.Character`. A script that
  only connects works in a published game and fails in Studio, where the player is often already
  there. (docs)
- **Per-character connections die with the character - only if you end them.** Anything connected in
  `CharacterAdded` (Humanoid events, RunService steps) must be disconnected when that character is
  removed, or every respawn adds another copy. (docs)
- `Humanoid.Died` over polling `Health <= 0`. (docs)
- **Spawn-before-world races** exist only when a script builds the world at start-up. Then set
  `Players.CharacterAutoLoads = false`, build, assign a real `RespawnLocation`, and
  `LoadCharacterAsync`. An authored world does not need any of this (`architecture.md`). (live 2026-11)
- **Avatars may have no `Motor6D`.** Current R15 avatars can be joined by `AnimationConstraint`
  (15 of them and zero `Motor6D`s on a default avatar). Motor6D-only joint code silently does
  nothing; `C0`/`C1` are read-only there. Details: `animation.md`. (live 2026-11)
- **Ragdoll swap leaves floating decals and lights** unless the hidden original's LayerCollectors,
  Lights, ParticleEmitters and Highlights are disabled. (live 2026-11)

## Instances and CFrames

- `Model:PivotTo(cf)` moves the whole model; setting one part's `CFrame` moves that part. Welded
  unanchored parts follow their assembly root; anchored parts never follow a weld. (docs)
- **Tweening an anchored part does not move parts welded to it.** Move an anchored assembly with
  `workspace:BulkMoveTo(parts, cframes)` from offsets captured once, or unanchor everything but the
  root. (docs)
- **`Enum.BulkMoveMode` has `FireAllEvents` and `FireCFrameChanged` only.** (docs)
- `WaitForChild` "infinite yield possible" means a wrong name or an instance nobody creates. Find it;
  do not add a timeout around it. (docs)
- `Touched` fires many times per contact: debounce per character, and never trust it for authority
  without a server-side distance check. (docs)
- **`CFrame.lookAt` between two points on the same vertical is degenerate** - pass an explicit up
  vector, or use a separate helper for vertical posts. (docs)
- **Wedge orientation:** a `WedgePart`'s tall edge is its local +Z and the slope falls toward -Z; a
  `CornerWedgePart` peaks at (+X, -Z). Measure with two downward rays before building from memory.
  (live 2026-11)
- **`tostring(Enum.Material.Grass)` is `"Enum.Material.Grass"`**, not `"Grass"`. Use `.Name` for
  lookups and payloads. (docs)
- **`WeldConstraint` keeps the offset the parts had when it was created.** Position first, weld
  second. (docs)
- **Spatial queries and raycasts skip `CanQuery = false` parts.** A clear `GetPartBoundsInBox` does
  not prove an area is empty (`box-scan` probe). (docs)
- **Raycasts obey collision groups.** A ray cast with the default `RaycastParams` (group `Default`)
  passes straight through parts whose group does not collide with `Default`. To hit a creature kept
  in its own group, set `params.CollisionGroup` to a group that meets it; a ray-only `Probe` group
  works. (docs) (live 2026-11)
- **Set an `Attachment`'s world position after it has a parent.** Writing `WorldCFrame` or
  `WorldPosition` on an unparented attachment stores those numbers as its local offset; once
  parented it sits that far from the part (cables 150 studs up in the sky). Parent first, or set
  `CFrame` in the part's space. Lint T045; probe `world-audit`. (live 2026-11)
- **Edit mode does not re-solve `WeldConstraint`s when a joint changes.** Parts welded to a limb
  stayed behind in an Edit pose sheet when the limb's `Motor6D.C0` changed; an explicit `Weld` with
  its own `C0` followed. In Play both follow the assembly. (live 2026-11)
- **A `Beam`'s width runs along its attachments' Y axis** (with `FaceCamera` off), and the texture's
  vertical axis runs along the beam's length. A curtain built with the attachments' Y pointing
  sideways lies flat. (live 2026-11)
- **Network ownership belongs to the assembly root, and welding can change the root.** A large part
  welded onto a server-controlled NPC (a shield) can become the root, ownership then goes to the
  nearest player and the NPC falls over on that client. Give the `HumanoidRootPart` `RootPriority`
  127 and gear -127, and call `SetNetworkOwner(nil)` again after anything is welded on. (docs) (live
  2026-11)

## Rendering, lighting, materials

- **`Lighting.Technology` is not scriptable** - assigning it throws. `Lighting.LightingStyle` and
  `PrioritizeLightingQuality` are. (docs)
- **A `Sky` with fixed image ids never gets dark**: the textures are drawn as-is at midnight. A fresh
  `Instance.new("Sky")` on engine textures follows `ClockTime`. Raise night ambient enough to read
  silhouettes. (live 2026-11)
- **`SurfaceGui.ClipsDescendants` defaults to false**: children larger than the canvas render in
  mid-air beyond the part, one-sided. Set it on every screen-style SurfaceGui. (live 2026-11)
- **`SurfaceGui.Face = Front` is the part's -Z face.** `CFrame.lookAt(pos, pos + n)` points -Z along
  `n`. Probe before painting many panels. (docs)
- **A SurfaceGui with `Adornee` lives where you parented it** (often `PlayerGui`), not under its
  part. (docs)
- **`UIGradient.Transparency` replaces the object's background transparency** under the gradient - a
  "glass" panel with a keypoint at 0 renders opaque. (live 2026-11)
- **Material textures tile in world studs.** On a first-person viewmodel a few texels of `Fabric`
  cover the whole arm; use an untextured material there. (live 2026-11)
- **Bright material textures multiply the part colour** (`CorrodedMetal` turns mid orange into
  salmon). Use darker base colours. (live 2026-11)
- **A light inside a part's voxel can emit nothing** on voxel lighting. Put the emitter on an
  invisible part clear of the fixture. (live 2026-11)
- **A `PointLight` carried by the camera lights the world**, not just the held object. Keep it weak
  and short, or give the held object real mid-tone colours instead. (live 2026-11)
- **Thin overhead structure casts real shadows** as dark lines on the ground; set
  `CastShadow = false` on decorative framing. (live 2026-11)
- **GUIs are not fogged, parts are.** A `BillboardGui` stays visible through `Atmosphere` haze. (live
  2026-11)
- **AlwaysOnTop SurfaceGuis did not render in one project's captures.** Not reproduced elsewhere; if
  yours does not show, try a depth-tested pane close to the camera. (field)

## Audio and assets

- **The Audio API has no oscillator or noise generator** (`AudioPlayer`, `AudioEmitter`,
  `AudioListener`, effects and `Wire` exist). Hums and alarms need real audio assets. (docs)
- **Every sound, image and mesh needs an uploaded asset id** the experience is allowed to use.
  A guessed id is silence or a grey square, with no error. (docs)
- **`rbxasset://` files you add exist only in one Studio build** and never reach a player. Upload
  real assets; `sound-audit` lists the ones that fail. (live 2026-11)
- **Stock `rbxasset://sounds/` files are not a contract** between Studio versions. (live 2026-11)
- **An `ImageLabel` at `ImageTransparency = 1` never reports `IsLoaded`.** Fade from 0.99 or use
  `ContentProvider:GetAssetFetchStatus`. (live 2026-11)
- **Uploaded audio is reviewed before it plays.** "Uploaded" is not "usable"; check the asset state.
  (live 2026-11)
- **`ContentProvider:PreloadAsync` with bare id strings requests images.** Sound ids passed as
  strings came back "Asset type does not match requested type" and were treated as failed (54 valid
  sounds skipped). Preload sounds through `Sound` instances. (live 2026-11)
- **New Audio API properties can exist in the class list before the engine enables them.** Writing
  `AudioEmitter.PositionType` threw "not enabled yet". `pcall` the write or leave the property out,
  and re-check with the class reference before relying on a new member. (live 2026-11)

## Terrain and building

- **`Terrain:FillBlock` / `FillBall` overwrite everything in the volume**, including the inside of
  a room built from parts. Fill around hollow spaces. (docs)
- **Smooth terrain does not sit exactly at the height you filled to.** Stand props on a downward
  raycast hit, not on the fill height. (live 2026-11)
- **Thin floating collidable slabs and props in door corners break pathfinding.** Give furniture a
  floor-standing hull, make decor non-collidable, and test routes in both directions. (live 2026-11)
- **Yield on elapsed time, not once per chunk**, in a long build:
  `if os.clock() - last > 0.03 then task.wait() last = os.clock() end`. (live 2026-11)
- **Seeded randomness (`Random.new(seed)`) for anything placed procedurally**, and draw the same
  values for every candidate before deciding to reject it - otherwise moving one exclusion zone
  reshuffles everything after it. (live 2026-11)
- **A world built at runtime is not saved.** What a server script builds exists only in that
  session; the place file still holds what was there before. (docs)

## Luau syntax and types

- **No default parameter values.** `function f(a, b: number? = nil)` is a syntax error that
  cascades into hundreds of bogus diagnostics. (docs)
- **A line that starts with `(`** continues the previous expression ("ambiguous syntax"). Assign
  to a local first. (docs)
- **`number?` is nullable, not optional at the call site** under `--!strict`: pass the `nil`. (docs)
- **Untyped parameters report errors at the callers.** `Expected this to be 'Player', but got {...}`
  usually means the function's parameter was never annotated. See `typing-luau.md`. (live 2026-11)
- **A state field narrowed by one comparison cannot be compared again.** With
  `state: "Idle" | "Stagger" | ...`, `if f.state == "Stagger" then ... elseif f.state == "Idle"`
  can report "Type 'Stagger' cannot be compared with 'Idle'" after a call that may change the
  state. Read it through a function (`local function stateOf(f): State return f.state end`) where
  the value can change between checks. (live 2026-11)
- **Renaming a local that shadowed a global leaves the global behind.** After `local tick` became
  `local frame`, a forgotten `pcall(tick)` still ran - against the deprecated global `tick`, so
  neither the type checker nor the tests failed. Search for the old name after a rename. (live
  2026-11)
- **A reference named like a function shadows it.** A controller kept a HUD label under the same
  name as its draught-count function: the drink key threw "attempt to call a Instance value" while
  the same action from a button worked. Give instance references noun names (`countLabel`) and
  functions verb names (`countDraughts`). (live 2026-11)
- **selene's Roblox standard library lags the engine.** `Vector3.yAxis:Cross(v)` runs but failed
  selene; `Vector3.new(0, 1, 0):Cross(v)` passes both. When selene rejects an API the docs list,
  rewrite the expression rather than turning the lint off. (live 2026-11)
- Deprecated globals still run and are still wrong: `wait`, `spawn`, `delay`, `tick`,
  `:connect`, `Instance.new(class, parent)`, `SetPrimaryPartCFrame`, body movers, `FindPartOnRay`,
  `Humanoid:LoadAnimation`. The trap lint lists each with its replacement. (docs)

## Client code

- **An error in a per-frame callback aborts the rest of that call, every frame - the connection
  itself keeps firing** (a Heartbeat handler that threw on its first call ran 35 more times in
  0.6 s and stayed connected). One function that does camera, HUD and effects loses all three to a
  nil in the first, and the console gets one error per frame. Keep optional visual passes on their
  own connections and publish a failure to an attribute you can read back. (live 2026-11)
- **A `UIListLayout` created from code sorts by `Name`**, not `LayoutOrder`, until you set
  `SortOrder = Enum.SortOrder.LayoutOrder`: three elements with orders 1-2-3 came out alphabetical.
  (live 2026-11)
- **`UserInputService.InputBegan` passes `gameProcessed`.** Ignore it and typing in chat fires the
  ability. (docs)
- **A custom camera's occlusion ray should respect `CanCollide`, and what it ignores must fade.**
  Counting every queryable part pulls the camera in for leaves, banners and ropes a body walks
  through (camera in the hero's hair under trees); `RaycastParams.RespectCanCollide = true` keeps
  only what blocks a body. But the ignored canopy then sits between camera and hero: a
  non-collidable pine bough 5 studs down a 12-stud boom blacked the hero out. Cast the boom a
  second time for non-collidable parts and set their `LocalTransparencyModifier` on this client,
  restoring it once they clear. A client suite at that spot failed before the fade and passed
  after. (docs) (live 2026-11)
- **A player's character is simulated by that player's client.** A server-side impulse or
  ragdoll throw on it is overwritten by the owner's next physics step. Replicate the push (an
  attribute with a counter) and let the owning client apply it; the server applies pushes only to
  creatures and puppets it owns. (docs) (live 2026-11)
- **Firing an input action does not walk the character.** `InputAction:Fire` (deprecated; use
  `InputBinding:Fire` on a `Scriptable` binding) updates the action's state and signals, but the
  stock control script moves the character through `Player:Move`. Measured: firing `Move` alone
  moved the character 0.00 studs in a second; `Player:Move` from a render step walked 19.0. (docs)
  (live 2026-11)
- **Editing `StarterGui` at runtime does nothing for players already in the game** - their copies
  live in `PlayerGui`. (docs)
- **Two handlers on one input action both run.** A climb controller and an interact controller each
  connected to the same action's `Pressed`; standing by a creature's body and a loot sack, one press
  can start a climb and send the take request together. Signals do not arbitrate.
  Give each action one owner that decides what the press means (nearest valid target, a priority
  list), or bind the second meaning to its own action. (field) Read from a production project's code,
  2026-11.
- **A client cache built while the server is still creating things is wrong forever.** Wait for a
  server-set readiness attribute or count, and refresh when it changes. (live 2026-11)
- **Never restore a saved `LocalTransparencyModifier`.** The engine also writes it for the local
  head; set hidden parts back to 0. (live 2026-11)

## Studio and MCP workflow

- `execute_luau` needs `datamodel_type` (Edit / Client / Server). Edit cannot see play state and
  play cannot see edit state. (live 2026-11)
- Every tool takes `studio_id`; get it from `list_roblox_studios`. (live 2026-11)
- **Edit-mode `require` caches a ModuleScript for the whole session**; changing `Source` does not
  invalidate it. Require a clone (`live-iteration.md`). (live 2026-11)
- **`execute_luau` in Play has its own module cache**: a `require` there returns a fresh copy with
  empty state. Test live state with `rbforge servertest`. (live 2026-11)
- **`_G` is not shared between separate `execute_luau` calls.** Park cross-call state in an
  attribute. (live 2026-11)
- **Background Studio runs at about 15 fps** and Automatic quality collapses the draw distance.
  Timings and "missing far geometry" measured there are the throttle, not the place
  (`capture-quality` probe). (live 2026-11)
- Console output is cumulative - read what is new since your change (`console since=60`). (live)
- Wheel input through the MCP needs a `moveTo` onto the viewport first; verify the state the input
  writes rather than calling the feature dead. (live 2026-11)

## Agent traps (the meta-failures)

- Declaring done when scripts exist but nothing was playtested.
- "Visually verified" without having inspected a screenshot.
- Building 15 systems before proving one loop.
- Trusting client-sent numbers because "it's just a prototype" - prototypes get published.
- Copying the pattern the project already uses without asking whether it was a good one. An existing
  codebase is evidence of what was built, not of what works (`existing-projects.md`).
- Turning one project's workaround into a rule for every project.
- **Match the pixels before the code.** When a screenshot shows something your raycasts say is not
  there, read the colour at that pixel and search for parts of that colour.
- **Weapon effects start at the muzzle**, not at the character's chest or the weapon's grip: name a
  `Muzzle` attachment and resolve it before the raycast and the tracer.
