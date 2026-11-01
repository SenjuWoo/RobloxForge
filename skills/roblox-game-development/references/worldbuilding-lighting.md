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

## Streaming and large maps

If the map grows past roughly 2 km or 20k parts, enable streaming rather than
fighting replication: `workspace.StreamingEnabled = true` in the place's
properties, then load `skill "rbx-convert-to-streaming"` for the model
requirements (streaming targets, `Model.ModelStreamingMode`, persistence). Turning
streaming on without reading that skill is how "my script disappears" bugs happen.

## Checklist before calling a world done

- [ ] spawn is above terrain and faces the first objective
- [ ] no part the player can see is unanchored
- [ ] terrain has at least two materials (flat + slope)
- [ ] exactly one lighting preset, applied and screenshotted
- [ ] `screen_capture` framed on the playable area, and actually looked at
