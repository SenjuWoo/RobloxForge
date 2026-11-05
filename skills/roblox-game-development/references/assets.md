# Assets & Creator Store safety

## Default to primitives

Five Parts beat a giant free model for prototypes: faster, auditable,
no script payload. Build with Parts/MeshParts first; import assets when
the design actually needs them.

## Before using any inserted asset

1. `inspect_instance` / `search_game_tree` the hierarchy - unexpected
   folders, huge Part counts?
2. `script_grep` for Script/LocalScript/ModuleScript inside it - count them,
   read them. Free models ship backdoors (RemoteEvents wired to nothing
   good, HttpService posts, loadstring).
3. Remove every script you did not intend. A decorative model does not need
   executable code.
4. Check for remotes, `HttpService`, `loadstring`, obfuscated strings.
5. Re-verify after insertion - assets can be repacked by their owners.

## If the host model cannot see

Insert -> capture viewport -> you cannot honestly say "looks good" without
inspecting pixels. Say "captured, unverified visually."

## Audio/images

Audio above ~6 seconds requires upload/asset IDs you own or licensed
marketplace audio. Images used as Decals need uploaded IDs. Generate via
MCP (`upload_image`, `generate_mesh`) rather than guessing IDs - a guessed
ID is a broken texture at best.

## Generative 3D: the actual tool contracts

Creator Store assets look like a shortcut until one arrives with a backdoor
script. The MCP's own generators are the better default for anything
decorative: they produce clean instances you own.

| Goal | Tool | Required args |
|---|---|---|
| Blocky structures, modular builds | `generate_procedural_model` | `prompt` (+ `attachedImageUri` to guide from an image) |
| Organic props, weapons, statues | `generate_mesh` | `textPrompt` (`maxTriangles` to cap cost) |
| PBR surface variants | `generate_material` | `materialPattern`, `materialId`, `baseMaterial`, `materialDescription` |
| Re-skin an existing mesh | `generate_texture` | `textPrompt` + `instance_path` or `model` |
| A whole scene from a prompt | `generate_scene` | `textPrompt` and/or `images`; optional `boundingBoxPosition` / `boundingBoxSize` |
| Rigged character | `generate_avatar` | `textPrompt` |
| Rig an existing Model as R15 | `auto_setup_avatar` | `instance_path` (+ `studio_id`) |
| Split a mesh into named parts | `segment_mesh` | `parts` (max 5 names) |

Working sequence with an image reference (the one that actually saves retries):

1. `store_image(filePath)` → returns an `IMAGEID_<id>` URI.
2. `generate_procedural_model(prompt = "...", attachedImageUri = "IMAGEID_<id>",
   async = true)` → `jobId`.
3. `wait_job_finished(jobId, timeout = 300)`.
4. `inspect_instance` the result: part count, size, `Anchored`.

Conventions that keep output from looking like AI slop:
- **Prompt the material, not just the shape.** "weathered concrete, chipped
  corners, moss in seams" produces a usable surface; "a wall" produces plastic.
- **Generate materials once, reuse as `MaterialVariant`.** Six `generate_material`
  calls across a whole map beats sixty mesh variants for coherence and cost.
- **Cap polygons.** `maxTriangles` on `generate_mesh`; a 200k-triangle prop is a
  performance bug you inherit.
- **Anchor and weld.** Every generated static part gets `Anchored = true`; dynamic
  assemblies get `WeldConstraint`s, not loose parts.
- **Verify visually.** Generate → `screen_capture` with explicit camera framing →
  look at it. A generator returning success is not a scene that reads.

## Quarantine gate for Creator Store inserts

`insert_asset` drops whatever the asset contains into your place, including
scripts. Never parent an inserted asset straight into `Workspace`.

```lua
--!strict
-- execute_luau, datamodel_type = "Edit", after insert_asset
local assetId = 1234567  -- replace with the inserted asset's id
local quarantine = Instance.new("Folder")
quarantine.Name = "Quarantine"

local inserted: Instance? = nil
for _, inst in workspace:GetDescendants() do
    if inst:GetAttribute("AssetId") == assetId then inserted = inst; break end
end
if not inserted then return "insert not found - inspect the tree first" end

inserted.Parent = quarantine

local removed = {}
for _, inst in inserted:GetDescendants() do
    if inst:IsA("BaseScript") then
        table.insert(removed, inst:GetFullName())
        inst:Destroy()          -- decorative assets need no code
    end
end

-- Normalize physics for static environment geometry.
local parts = 0
for _, inst in inserted:GetDescendants() do
    if inst:IsA("BasePart") then
        parts = parts + 1
        inst.Anchored = true
        inst.CanTouch = false
        inst.CanQuery = false
    end
end

inserted.Parent = workspace
quarantine:Destroy()
return { parts = parts, scripts_removed = removed }
```

Then `script_grep` for `HttpService`, `require(` and `loadstring` inside the
result before you trust it. If the count is non-zero after the strip, do not ship
the asset.

## Procedural props are free and always available

The AI generators are convenient, not guaranteed: if `generate_mesh` returns an
entitlement or quota error, **that is not a reason to buy anything** (see
`free-stack.md`). Fall back to a data-driven part kit — it costs nothing and
runs in a single `execute_luau` call.

One table in, a coherent prop out:

```lua
--!strict
-- execute_luau, datamodel_type = "Edit"
-- A prop is a list of parts; every field has a default so a kit entry stays short.
type Piece = {
    size: Vector3,
    offset: Vector3?,
    color: Color3?,
    shape: Enum.PartType?,
    material: Enum.Material?,
}

local PALETTE = {
    wood = Color3.fromRGB(120, 83, 51),
    metal = Color3.fromRGB(117, 122, 128),
    cloth = Color3.fromRGB(168, 61, 61),
}

local KITS: { [string]: { Piece } } = {
    crate = {
        { size = Vector3.new(4, 4, 4), color = PALETTE.wood, material = Enum.Material.Wood },
        { size = Vector3.new(4.2, 0.3, 4.2), offset = Vector3.new(0, 1.6, 0), color = PALETTE.metal },
    },
    bench = {
        { size = Vector3.new(6, 0.4, 2), offset = Vector3.new(0, 1.6, 0), color = PALETTE.wood },
        { size = Vector3.new(0.4, 1.6, 2), offset = Vector3.new(-2.6, 0.8, 0), color = PALETTE.metal },
        { size = Vector3.new(0.4, 1.6, 2), offset = Vector3.new(2.6, 0.8, 0), color = PALETTE.metal },
    },
}

local function build(kitName: string, at: Vector3, heading: number): Model
    local kit = KITS[kitName]
    if not kit then error("unknown kit: " .. kitName) end
    local model = Instance.new("Model")
    model.Name = kitName
    model.Parent = workspace
    for _, piece in kit do
        local part = Instance.new("Part")
        part.Size = piece.size
        part.Shape = piece.shape or Enum.PartType.Block
        part.Color = piece.color or PALETTE.wood
        part.Material = piece.material or Enum.Material.SmoothPlastic
        part.Anchored = true          -- static props never fall
        part.CanCollide = true
        part.CFrame = CFrame.new(at + (piece.offset or Vector3.zero))
            * CFrame.Angles(0, heading, 0)
        part.Parent = model
    end
    return model
end

build("crate", Vector3.new(0, 2, 0), 0)
build("bench", Vector3.new(12, 0, 0), math.rad(90))
return "props built"
```

Why this beats importing a model:
- **It is yours.** No scripts, no licence, no quarantine pass needed.
- **It is cheap.** A 3-part bench is 3 parts; a marketplace bench is often 200.
- **It is editable.** Change `PALETTE` and the whole set re-skins coherently.

Rule of thumb for a coherent world without spending anything:

| Element | Free source |
|---|---|
| Structural (walls, floors, platforms) | part kits like the above |
| 3-5 hero objects | `generate_mesh` |
| Surface detail | `generate_material` variants applied across many parts |
| Foliage/rocks | `generate_procedural_model` or part kits with random rotation/scale |
| Terrain | `worldbuilding-lighting.md` heightmap |
| Lighting | one preset from the same file |

Randomise with a **seeded** generator (`Random.new(seed)`), never `math.random`
for layout: a re-run must reproduce the same world, or you cannot tell a
regression from a reshuffle.

## Uploading generated images through the Studio MCP

`upload_image` takes **http(s) URLs**, not file paths, and uploads into the
signed-in account. The loop that works:

1. Generate the PNG locally (Pillow + numpy are enough; nothing is bought).
2. Serve the folder: `python -m http.server 8791 --bind 127.0.0.1`, or
   `python scripts/serve_assets.py --dir <folder> --port 8791`.
3. Call `upload_image` with `http://127.0.0.1:8791/<name>.png` for every file;
   it returns `{url: "rbxassetid://<id>"}`.
4. Store the ids in config. Never re-upload on every run — the account asset
   list is the record.
5. `ContentProvider:PreloadAsync(ids)` on the client, and keep a painted
   fallback underneath every ImageLabel: 225 slices still stream in over ~15 s,
   and Studio edit mode does not fetch textures at all.

Constraints that shaped the design:

- Roblox clamps an upload to **1024 px** on its longest side, so a panorama is
  1024x512, not 4096x2048. Across 32 segments that is ~32 px per panel: sharp at
  distance, visibly pixelated up close - which is exactly what a simulated
  display should look like.
- Uploading is a real write to the owner's account. Ask before the first one and
  record the ids in the repo so nobody has to repeat it.

### Equirectangular projection onto a dome

For azimuth `th` and elevation `phi` (0 at the horizon, pi/2 at the zenith),
each panel takes its slice of one shared panorama:

```
u0 = th0 / (2*pi)          u1 = th1 / (2*pi)
v0 = 1 - phi1 / (pi/2)     v1 = 1 - phi0 / (pi/2)
ImageRectOffset = (round(u0*W), round(v0*H))
ImageRectSize   = (max(1, round(u1*W) - round(u0*W)),
                   max(1, round(v1*H) - round(v0*H)))
```

Round **both edges** from the shared boundary, never the width: rounding widths
independently makes each seam drift a pixel and the joins visibly crawl. Keep
the generator seamless in `u` (integer-frequency sine sums, or blur the noise
field with a wrap) and the seam hides behind a strut.
