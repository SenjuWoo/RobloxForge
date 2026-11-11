# Worldbuilding: terrain, lighting, atmosphere

A graybox reads as a prototype because of lighting more than geometry. Two cheap
passes — terrain height and one lighting preset — move a slice from "test level"
to "place". Both are deterministic Luau you can run through `execute_luau`.

## Terrain generator (heightmap + slope-based materials)

`Terrain:FillBlock(cframe, size, material)` and `Terrain:FillBall(center, radius,
material)` **overwrite** existing terrain in the target volume — that is what
makes them usable for carving as well as building. Never call them per voxel in
one unyielding loop; chunk the work and `task.wait()` between chunks (see the
`execute_luau` chunking rule in `studio-mcp.md`).

```lua
--!strict
-- execute_luau, datamodel_type = "Edit"
-- One chunk of a heightmap terrain. Run for x = -256..256, 64 studs per call.
local terrain = workspace.Terrain
local SIZE = 4          -- voxel size in studs
local CHUNK = 64
local WATER = 0

local function height(x: number, z: number): number
    -- Three octaves of Roblox noise; scale controls hill frequency.
    local h = math.noise(x / 120, z / 120) * 18
    h += math.noise(x / 40, z / 40) * 6
    h += math.noise(x / 12, z / 12) * 1.5
    return h
end

local function materialFor(h: number, slope: number): Enum.Material
    if h < WATER + 1 then return Enum.Material.Sand end
    if slope > 1.4 then return Enum.Material.Rock end
    if h > 14 then return Enum.Material.Snow end
    return Enum.Material.Grass
end

local x0 = -256
for x = x0, x0 + CHUNK - SIZE, SIZE do
    for z = -256, 256, SIZE do
        local h = height(x, z)
        local dh = math.abs(height(x + SIZE, z) - h) + math.abs(height(x, z + SIZE) - h)
        local slope = dh / SIZE
        local top = math.max(h, WATER)
        local cf = CFrame.new(x, (top - 40) / 2, z)
        local size = Vector3.new(SIZE, top + 40, SIZE)
        terrain:FillBlock(cf, size, materialFor(h, slope))
    end
    task.wait()   -- once per chunk column: never per voxel
end
return "chunk done"
```

Notes that prevent the usual disasters:
- **The CFrame is the block's center, not its corner.** `FillBlock` with a
  corner-style CFrame shifts terrain by half a block and everything floats.
- **Water is a separate `Terrain:FillBlock` with `Enum.Material.Water`** at the
  water level; do not try to make "sand + water" in one call.
- **`SpawnLocation` must sit above your highest terrain** or the player starts
  inside rock. Verify after generating: `inspect_instance` the spawn.
- **Chunk it.** A full 512x512 map at 4-stud voxels in one call will freeze Studio
  or drop the MCP connection.

## Lighting presets (pick one, then stop)

Set these through `execute_luau` in Edit mode; they are plain property writes.

```lua
--!strict
-- execute_luau, datamodel_type = "Edit"
local Lighting = game:GetService("Lighting")

-- Golden-hour outdoor: warm key light, cool ambient, readable shadows.
Lighting.ClockTime = 17.2
Lighting.Brightness = 2.4
Lighting.Ambient = Color3.fromRGB(70, 70, 82)
Lighting.OutdoorAmbient = Color3.fromRGB(96, 104, 128)
Lighting.EnvironmentDiffuseScale = 0.4
Lighting.GlobalShadows = true
Lighting.FogEnd = 2200
Lighting.FogStart = 400

local atmosphere = Lighting:FindFirstChildOfClass("Atmosphere")
    or Instance.new("Atmosphere", Lighting)
atmosphere.Density = 0.32
atmosphere.Haze = 1.8
atmosphere.Glare = 0.15
atmosphere.Color = Color3.fromRGB(199, 199, 199)
atmosphere.Decay = Color3.fromRGB(106, 112, 125)

local bloom = Lighting:FindFirstChildOfClass("BloomEffect")
    or Instance.new("BloomEffect", Lighting)
bloom.Intensity = 0.4
bloom.Size = 24
bloom.Threshold = 1.1

local cc = Lighting:FindFirstChildOfClass("ColorCorrectionEffect")
    or Instance.new("ColorCorrectionEffect", Lighting)
cc.Saturation = 0.08
cc.Contrast = 0.12
cc.TintColor = Color3.fromRGB(255, 246, 235)

return "lighting applied"
```

Variants worth having on hand (same block, three numbers changed):

| Mood | ClockTime | Brightness | Atmosphere Density | ColorCorrection Saturation |
|---|---|---|---|---|
| Golden hour | 17.2 | 2.4 | 0.32 | +0.08 |
| Overcast mystery | 9.0 | 1.4 | 0.55 | -0.15 |
| Night neon | 0.2 | 0.8 | 0.18 | +0.25 |

Rules:
- **One preset per place.** Stacking warm `ColorCorrection` on a warm atmosphere
  gives the orange plastic look that reads as AI slop.
- **`FogEnd` beyond the map's diagonal is wasted**; below it, distant geometry pops.
- **Delete existing effects before adding yours** — a place that already has four
  `ColorCorrectionEffect`s will not show your fifth.
- **Verify with a framed screenshot**, not the default viewport ("Framing a
  screenshot as evidence" in `studio-mcp.md`).

## Lighting style

`Lighting.LightingStyle = Enum.LightingStyle.Realistic` (with
`PrioritizeLightingQuality = true`) is writable from `execute_luau` and from the
Rojo project file; `Lighting.Technology` is not writable from script context.
Record lighting in `default.project.json` so a fresh sync keeps it.

## Mechanisms that read as real

A door, gate or shutter sells a place when it has travel time, easing, a state
light and a consequence. Pattern used for an anchored blast gate:

- one collidable leaf part carries the state attributes (`IsOpen`, HP) - the
  existing server contract stays one part;
- every detail part (ribs, stripes, bolts, lettering) is captured once as an
  offset from the leaf and moved with `workspace:BulkMoveTo` each Heartbeat;
- smoothstep easing over ~2.5 s, a tiny lateral shake mid-travel, a dust
  emitter while moving, sparks on the closing slam, status lights amber while
  moving then cyan/red; a token cancels an animation that is interrupted;
- sounds are optional instances created only when an asset id exists.

## Procedural kit habits

- Build in a local frame (`scope(parent, frame)` returning `p`, `beam`, `rod`,
  `post` helpers) so the same code places six plots or a rotated ship.
- One palette per area; jitter colours +-8 % per panel instead of introducing
  new hues. Panelise large surfaces (brick-bond offsets) instead of one slab.
- Every prop must touch something: run the connectivity proof
  (`testing-debugging.md`).
- Isolate private areas from the shared world with sightline blockers (berms,
  terrain, a dome or fog) - a player who can see six other bases from home
  stops believing in either.

## Streaming and large maps

If the map grows past roughly 2 km or 20k parts, enable streaming rather than
fighting replication: `workspace.StreamingEnabled = true` in the place's
properties, then load `skill "rbx-convert-to-streaming"` for the model
requirements (streaming targets, `Model.ModelStreamingMode`, persistence). Turning
streaming on without reading that skill is how "my script disappears" bugs happen.

## Art-direction pass on a prototype world

A world that is "systems done, looks like a test map" is fixed in this order. Each step is cheap, changes every
screenshot at once, and is verified by a capture from a fixed pose before the next one starts.

1. **Look first, geometry second.** Engine `Sky` (so night works), a `Clouds` instance under Terrain, one
   `Atmosphere`, water colour/reflectance/wave size, and `Terrain:SetMaterialColor` for the three or four
   materials in use. Keep per-phase values (clock, ambient, haze, grade, cloud cover) in one config table that
   both the server cycle and any client override read.
2. **Tune in Edit, encode in config.** Apply a candidate profile with a few property writes, capture from two
   fixed poses, adjust, and only then write the numbers into the table. Two calls per iteration instead of a
   Play boot per iteration.
3. **Dress the biggest surface the player always sees** (a perimeter wall, a cliff, a hull). Keep the collision
   core untouched and add rhythm on the visible face: a sloped plinth, a pier on every joint, a taller feature
   every fourth joint, one coloured band, pipes/vents/catwalks that alternate by index, lit windows and a few
   non-shadow spotlights throwing pools. Build each module in the same frame as the slab it decorates, and skip
   or split anything that would cross a doorway.
4. **Give the horizon a destination.** A ring of simple tall masses with a few lit windows, as a `Persistent`
   model, plus a `BillboardGui` glow over it. From the spawn exit the player must be able to see where to go.
5. **Paint routes into the terrain.** `Terrain:ReplaceMaterial(region, 4, Ground, Asphalt)` along a line changes
   no height and leaves water alone; add lane dashes for the first stretch and scatter cover along the edges.
6. **Then the props.** Painted steel is `Metal` with rust as patches and on bottom rails; a box that is
   `CorrodedMetal` all over reads as an orange cube. Corrugation is thin ribs, identity is a stencil on a clear
   carrier just proud of the ribs, and clutter goes against rails and walls so play lanes stay open.

7. **Dress the safe area last, and keep it off the buildable land.** Give it the things people who live there
   would need - fence, power line, water, a generator, stores, crops, lights - placed in the band around the land,
   with dirt painted under each (`ReplaceMaterial` grass to ground also removes the grass blades). Foliage as an
   ellipsoid (a block with a `SpecialMesh` sphere takes the block's size per axis) gives flat crowns and loose
   canopies that stacked cylinders cannot; make it non-solid and non-queryable.

Rules that held: never move or resize the collision geometry while dressing it; seed every random choice from a
position so a rebuild is identical; rerun the route and combat suites after any prop that collides.

## Checklist before calling a world done

- [ ] spawn is above terrain and faces the first objective
- [ ] no part the player can see is unanchored
- [ ] terrain has at least two materials (flat + slope)
- [ ] exactly one lighting preset, applied and screenshotted - at night too
- [ ] a landmark is visible from the spawn exit
- [ ] `screen_capture` framed on the playable area, and actually looked at
