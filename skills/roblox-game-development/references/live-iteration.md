# Live iteration: source on disk, slice rebuilt in Studio

Field notes from building a large procedural world (a 9,000-part ship, six
outposts, tunnels, HUD) through the official Studio MCP. Each item below cost at
least one wasted round trip before it was understood. Verified on Studio
0.735.x, Windows 11, November 2026.

## The loop that works

1. Source of truth is `src/` on disk (Rojo layout). Studio is a mirror.
2. Push changed files into Studio without Rojo serve (below).
3. Rebuild only the slice you changed, in Edit, from **fresh module clones**.
4. Frame a capture on the slice and look at it.
5. Start Play only for runtime proof (routes, remotes, console, HUD).

Never hand-edit Workspace parts that a builder module regenerates at server
start - Play throws them away. Edit the module, then rebuild.

## Pushing source into Studio without Rojo

When `rojo serve` is not running, serve `src/` on loopback and let one
`execute_luau` pull each file. Restore `HttpEnabled` before the call returns.

```bash
python -I -m http.server 8765 --bind 127.0.0.1 --directory src
```

```lua
-- execute_luau, datamodel_type = "Edit"
local Http = game:GetService("HttpService")
local sys = game:GetService("ServerScriptService").Systems
local was = Http.HttpEnabled
Http.HttpEnabled = true
local ok, err = pcall(function()
	for _, name in { "WorldBuilder", "OutpostBuilder" } do
		local body = Http:GetAsync("http://127.0.0.1:8765/server/Systems/" .. name .. ".luau")
		local m = sys:FindFirstChild(name) or Instance.new("ModuleScript")
		m.Name, m.Parent = name, sys
		m.Source = body:gsub("\r\n", "\n")
	end
end)
Http.HttpEnabled = was -- never leave a security setting changed
return ok and "synced" or tostring(err)
```

Stop the server afterwards. A new ModuleScript the project maps (Rojo) must also
be added to `default.project.json`, or the next Rojo sync deletes it.

## `require` caches in Edit: rebuild from clones

In Edit, `require(moduleScript)` returns the first result for that instance for
the rest of the session. Changing `.Source` does **not** invalidate it - the
rebuild silently runs the old code (symptom: the error you just fixed comes
back verbatim). Clone the module tree into a scratch folder and require the
clones; sibling `require(script.Parent.X)` calls resolve inside the folder.

```lua
local SS = game:GetService("ServerStorage")
local sys = game:GetService("ServerScriptService").Systems
local old = SS:FindFirstChild("DevRebuild"); if old then old:Destroy() end
local f = Instance.new("Folder"); f.Name = "DevRebuild"; f.Parent = SS
for _, n in { "OutpostKit", "OutpostBuilder" } do sys[n]:Clone().Parent = f end
local Builder = require(f.OutpostBuilder) -- fresh code every time
```

Delete the scratch folder before saving.

## Runtime state in Play is a different module instance

In Play, a command-bar / `execute_luau` `require` of a manager returns a
**separate copy** from the one `GameServer` loaded - its registries are empty.
To test against live server state (combat, plots, profiles), create a temporary
`Script` at runtime that requires the managers, runs the check and writes the
result to an attribute; read the attribute, then destroy the Script. Prefer
asserting on replicated facts (attributes, instance counts, prompt kinds) where
that is enough.

To exercise a real remote path, fire it from the **Client** datamodel:

```lua
-- execute_luau, datamodel_type = "Client"
game.ReplicatedStorage.Remotes.ToggleGate:FireServer(3)
```

then read the outcome from the Server datamodel a few seconds later.

## Captures: what they can and cannot show

- **Edit captures DO render ordinary SurfaceGuis** (dome panoramas, signs,
  lettering all show). An earlier note here claimed the opposite; it was wrong
  and sent a session chasing terrain. What did not render in captures (Edit or
  Play) is **`AlwaysOnTop = true` SurfaceGuis**: use depth-tested panes instead
  (see ui-craft.md, helmet HUD).
- **An `ImageLabel` at `ImageTransparency = 1` never reports `IsLoaded`.**
  Start a fade-in at 0.99, or also accept
  `ContentProvider:GetAssetFetchStatus(id) == Enum.AssetFetchStatus.Success`.
- **A Play capture with no camera arguments shows the client viewport**,
  including ScreenGuis - this is how to review a HUD.
- Always pass `camera_position` + `look_at_position` for world evidence, and
  keep the camera out of geometry: a camera inside a shelf shows a ceiling of
  giant diamond-plate texture that looks like a rendering bug.
- Lighting at capture time is whatever the clock says. A dusk preview makes
  everything orange; set `ClockTime` for review captures and restore it.

## The editor camera after `execute_luau`

The MCP restores `Camera.CameraType` after each command, which can leave the
owner's editor camera stuck (right-drag does nothing). A plain assignment is
overwritten; a delayed one survives:

```lua
local cam = workspace.CurrentCamera
task.delay(1, function() cam.CameraType = Enum.CameraType.Custom end)
```

Do this after any command that touched the camera, then verify on the next call.

## Saving

- There is no save tool. The owner saves (File > Save, or Download a Copy for a
  local `.rbxl`). Verify the file's size/time or embedded sources before
  claiming a checkpoint.
- Studio's automation guard blocks scripted save/menu input while the owner is
  using the mouse/keyboard. Ask for ~30 s idle instead of retrying.
- Remove probes (`DevRebuild`, temp Scripts, test parts) before any save.

## Ready-made snippets

`templates/studio/` in the RobloxForge checkout: `dev-rebuild.luau` (clone-and-
rebuild one slice), `connectivity.luau` (floating-part proof),
`route-matrix.luau` (walkability proof). Fill in the names at the top.

## Budget rules that kept sessions short

- Batch independent captures into one message; they are read-only.
- Rebuild one plot / one POI, not the world (`BuildWorld` with terrain can take
  a minute).
- After a fix, re-run only the check that failed, then the full gate once.
