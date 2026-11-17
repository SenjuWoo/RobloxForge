# Live iteration: source on disk, slice checked in Studio

How to move code and world changes into Studio through the official MCP without wasting round
trips. Verified on Studio 0.735-0.74x, Windows 11, November 2026.

## Two kinds of content, two loops

**Code** lives in `src/` on disk and is pushed into Studio. **Static world and UI** are authored in
the place (in Edit) and saved with it. A server script builds only what is dynamic. See "Authored or
generated" in `architecture.md` - mixing the two up is the most expensive mistake in this file.

### Code loop

1. Edit files on disk.
2. `rbforge check .` (seconds).
3. `rbforge push <files> --project default.project.json` - sets each script's `Source`, reads it
   back, and refuses to overwrite a script someone edited in Studio (`conflict`). `ALL` pushes every
   mapped file. No Rojo server and no HTTP setting changes are needed.
4. Play only for runtime proof: `start_stop_play`, then `rbforge servertest`, console, capture.

`rojo serve` with the Studio plugin is the alternative when a human keeps Studio open all day; do not
run both against the same place.

### World loop (authored content)

1. Change the place in **Edit**: `execute_luau` with `datamodel_type = "Edit"` for scripted builds,
   the generators, or hand edits by the owner.
2. Frame a capture on what changed and look at it.
3. `save_place` when the owner asked for the change to be kept. Nothing done in Play survives Stop.

A builder you run once in Edit is a tool: keep it in `tools/`, not in server start-up.

### World loop (generated at runtime)

Only for worlds that really are procedural. Then the builder modules are code (loop one), and:

- never hand-edit parts a builder regenerates - Play throws them away;
- rebuild one slice in Edit from **fresh module clones** to preview (below);
- gate tests and spawning on a readiness attribute the builder sets last.

## `require` caches in Edit: rebuild from clones

In Edit, `require(moduleScript)` returns the first result for that instance for the rest of the
session. Changing `.Source` does **not** invalidate it - a rebuild silently runs the old code
(symptom: the error you just fixed comes back verbatim). Clone the module tree into a scratch folder
and require the clones; sibling `require(script.Parent.X)` calls resolve inside the folder.

```lua
local SS = game:GetService("ServerStorage")
local sys = game:GetService("ServerScriptService").Server.Services
local old = SS:FindFirstChild("DevRebuild")
if old then
	old:Destroy()
end
local f = Instance.new("Folder")
f.Name = "DevRebuild"
f.Parent = SS
for _, n in { "MapKit", "MapBuilder" } do
	sys[n]:Clone().Parent = f
end
local Builder = require(f.MapBuilder) -- fresh code every time
```

Delete the scratch folder before saving.

## Runtime state in Play is a different module instance

In Play, a command-bar or `execute_luau` `require` of a service returns a **separate copy** from the
one the game loaded - its tables are empty. To test against live server state use
`rbforge servertest` (it runs your file as a real Script and reads an attribute back), or assert on
replicated facts: attributes, instance counts, HUD text.

To exercise a real remote path, fire it from the **Client** datamodel and read the outcome from the
Server datamodel:

```lua
-- execute_luau, datamodel_type = "Client"
game.ReplicatedStorage.Remotes.DoAction:FireServer()
```

## Captures: what they can and cannot show

- Edit captures render ordinary SurfaceGuis, signs and lettering.
- **An `ImageLabel` at `ImageTransparency = 1` never reports `IsLoaded`.** Start a fade-in at 0.99,
  or accept `ContentProvider:GetAssetFetchStatus(id) == Enum.AssetFetchStatus.Success`.
- **A Play capture with no camera arguments shows the client viewport**, ScreenGuis included - this
  is how to review a HUD.
- Pass `camera_position` + `look_at_position` for world evidence, and keep the camera out of
  geometry: a camera inside a shelf shows a wall of texture that looks like a rendering bug.
- Lighting at capture time is whatever the clock says. Set `ClockTime` for review captures and
  restore it.
- Streaming shows what is near the **character**, not near a pinned camera: use the `goto` probe
  first.

## The editor camera after `execute_luau`

The MCP restores `Camera.CameraType` after each command, which can leave the owner's editor camera
stuck. A plain assignment is overwritten; a delayed one survives:

```lua
local cam = workspace.CurrentCamera
task.delay(1, function()
	cam.CameraType = Enum.CameraType.Custom
end)
```

## Saving

- `save_place` saves like File > Save: a new version for a cloud place, the file for a local one. It
  never publishes. Statuses and what to do with each are in `studio-mcp.md`.
- Save when the owner asked for it or at the end of a change they wanted kept - not after every edit.
- Remove probes (`DevRebuild`, temp Scripts, test parts) before any save.
- A change made in Edit that is not saved is gone at the next reopen. Say so in the report.

## Debug switches

A `Debug*` attribute a test can set is useful; in a shipped build it is a switch any client can flip.
Gate every one: `RunService:IsStudio() and player:GetAttribute("DebugX")`.

## Ready-made snippets

`templates/studio/` in the RobloxForge checkout: `dev-rebuild.luau` (clone-and-rebuild one slice),
`connectivity.luau` (floating-part proof), `route-matrix.luau` (walkability proof).

## Budget rules that kept sessions short

- Batch independent captures into one message; they are read-only.
- After a fix, re-run only the check that failed, then the full gate once.
- Rebuild or re-test one area, not the world.
