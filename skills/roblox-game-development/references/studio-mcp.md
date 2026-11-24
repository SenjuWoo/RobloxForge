# Studio MCP reference (official built-in server)

Verified against a live handshake on Windows 11, 2026-11-16: **38 tools**
(2026-11-01: 34; added since: `save_place`, `open_cloud_invoke`,
`submit_feedback`, `generate_animation`; none removed). The surface moves with
Studio updates - always confirm via `tools/list`, `list_roblox_studios` and
`rb_capabilities`, never from memory. A tool named here that is absent is
absent; say so instead of pretending.

## Tool map

| Group | Tools |
|---|---|
| Scripts | `script_read`, `multi_edit` (creates scripts too), `script_search`, `script_grep` |
| Data model | `search_game_tree`, `inspect_instance` |
| Luau execution | `execute_luau` (datamodel_type: Edit / Client / Server) |
| Playtest | `get_studio_state`, `start_stop_play`, `get_console_output`, `screen_capture` |
| Input | `character_navigation`, `user_keyboard_input`, `user_mouse_input` |
| Generative | `generate_procedural_model`, `generate_mesh`, `generate_texture`, `generate_material`, `generate_scene`, `generate_avatar`, `generate_animation`, `auto_setup_avatar`, `segment_mesh` |
| Assets | `search_asset`, `insert_asset`, `store_image`, `upload_image` |
| Open Cloud | `open_cloud_invoke` (authenticated Open Cloud requests, multipart file upload) |
| Saving | `save_place` |
| Async | `wait_job_finished` |
| Docs/skills | `http_get`, `skill`, `list_skills`, `create_skill`, `edit_skill` |
| Delegation | `subagent` (`explore`, `playtest`; the argument also accepts `screen_capture`, `unit_test`) |
| Feedback | `submit_feedback` |
| Sessions | `list_roblox_studios` |

## Which place is this?

`list_roblox_studios` tells a cloud place from a local file. Check it before
editing: agents have worked in a stale local `.rbxl` while the owner's real
place was the cloud one.

| Opened as | Entry fields |
|---|---|
| cloud place (incl. Team Create) | `id`, `mode`, `name` ("Name (placeId: N)"), `persistedToCloud: true`, `placeId`, `universeId` |
| local `.rbxl` / `.rbxlx` | `id`, `mode`, `name`, `file`, `persistedToCloud: false`, `state` (no `placeId`) |

`rbforge doctor` prints this as `Name - cloud place N` or
`name.rbxl - local file, not a cloud place`. The first entry after Studio
registers can arrive without `name` for a moment; ask again.

`get_studio_state` answers in text, for example
`- Current Studio Mode: Play` / `- Available DataModels: Client, Server`.
`Server` is only listed during a playtest.

## `save_place`: Ctrl+S, never publish

Saves the open place the way File > Save does. A cloud place gets a new place
version in version history; a local file is written back to disk. It never
publishes, so players see nothing until the owner publishes.

| status | Meaning / what to do |
|---|---|
| `Saved` | done; `version` (cloud) or `filePath` (local) |
| `NotNeeded` | no unsaved changes; nothing written |
| `NeedsUserAction` | Studio needs a dialog (never saved, Save As, script changes from a playtest); relay the message, the owner saves once by hand |
| `Busy` | a playtest, save or publish is running; retry after it ends (stop the playtest first) |
| `Failed` | `message` says why |

Call it when the owner asks to save, or at the end of a change they asked to
have saved. Not after every edit: each cloud save adds a version. `notes` labels
the version only when asked; `notesSaved: false` does not mean the save failed,
so do not save again to retry the notes.

## `open_cloud_invoke`: Open Cloud with the Assistant's permissions

Sends an authenticated request to `https://apis.roblox.com` + `endpoint` (a
path starting with `/`, never a full URL). Auth is automatic, limited to the
scopes the creator granted in Assistant Settings -> MCP Permissions; never pass
an API key or auth header. Pass `scopes` so a missing grant fails with a precise
error. A 403 or a denied scope is the creator's decision: ask them to grant it,
do not work around it. A 401: retry once.

`files` turns the request into multipart/form-data: an **array** of
`{name, path, contentType?}` with absolute paths, at most 5 files of 20 MB.
With `files`, `body` is a JSON object whose keys become form fields. Files must
sit in a directory the creator approved in MCP Permissions; if one is
rejected, ask for the directory to be approved, never copy the file somewhere
else to get around the gate. The asset upload route is in `assets.md`.

## `submit_feedback`

Sends feedback about Studio and its MCP tools to the team that builds them: one
specific issue per call (tool, what you tried, what happened, what would have
worked). Never about the user's game or the user; no source code, personal data
or credentials. Do not call it if the user has opted out, and after a send tell
them in one sentence what it was about and that they can ask you to stop.

## `generate_animation`

Makes an R15 animation from `textPrompt` (pass the user's words unchanged) or
upscales an R6 clip from `inputAssetId`. `instance_path` picks the rig;
without it the selected rig is used, or a default rig is inserted.

## Argument quirks (these cost real retries)

- **Every call needs `studio_id`** from `list_roblox_studios`. Two open places =
  two ids; pick deliberately. `list_roblox_studios` is the only exception.
- **`datamodel_type` is required, not defaulted**, on `execute_luau`,
  `search_game_tree`, `multi_edit`, `user_keyboard_input`, `user_mouse_input`.
  `Edit` is rejected while a playtest is running - switch with
  `start_stop_play(is_start: false)` first.
- **Compound assignment (`+=`) is ordinary Luau and runs.** An earlier note here said the tool
  rejected it; the shipped probes use it and have been run live.
- **`PivotTo` takes a CFrame**, not a Vector3:
  `part:PivotTo(CFrame.new(Vector3.new(x, y, z)))`.
- **`multi_edit` with a nonexistent path CREATES the script**; pass `className`
  (`Script` / `LocalScript` / `ModuleScript`) and start with an empty
  `old_string` to set initial content. Edits apply in sequence and the call is
  atomic - if one `old_string` fails to match, nothing is applied.
- **`multi_edit` is Edit-only.** You cannot restructure a running server's
  scripts mid-playtest; stop play, edit, restart.
- **`execute_luau` freezes Studio's main thread until it yields.** For bulk
  instance creation or terrain work, build a chunk in a container outside the
  DataModel, parent it, then `task.wait()` once per chunk (~1000 instances).
  Parenting a huge subtree is itself one unyielding operation and can drop the
  MCP connection. Any `while not ready do` loop must `task.wait()` inside it.
- **`screen_capture` requires `capture_id`** (`"ScreenCapture_1"`, increment per
  capture). Pass `camera_position` + `look_at_position` (arrays of 3 numbers) or
  you get whatever the user's viewport happens to show - useless as evidence.
- **`generate_*` accepts `async: true`** and returns a `jobId`; poll with
  `wait_job_finished(jobId, timeout)`. Do not busy-loop other tools while a job
  runs, and do not call `wait_job_finished` for a job whose result you do not need.

## Framing a screenshot as evidence

Compute the slice's bounds first, then frame the camera on the subject instead
of the default viewport:

```lua
-- execute_luau, datamodel_type = "Edit"
local part = workspace:FindFirstChild("CourseStart", true)
local cf = part:GetPivot()
local size = part:GetExtentsSize()
local focus = cf.Position
local dist = math.max(size.X, size.Y, size.Z) * 2.2
return {
    pos = {focus.X + dist, focus.Y + dist * 0.6, focus.Z + dist},
    look = {focus.X, focus.Y, focus.Z},
}
```

Then `screen_capture(capture_id = "ScreenCapture_1", camera_position = pos,
look_at_position = look)`. A screenshot you did not look at is not evidence.

## Session behaviour that costs time (second production project, live 2026-11)

- **Bring Studio to the front before `screen_capture`.** With another window over Studio's 3D view the
  capture times out, and a timed-out capture can drop the Studio connection for about half a minute;
  `list_roblox_studios` brings it back. A background Studio also renders at reduced rate and quality.
- **Let the view settle before capturing.** Move the camera (`execute_luau` or a Studio-only camera
  attribute your client reads), wait about 2.5 s, then capture. Captured straight after a move, distant
  terrain shows LOD seams that look like geometry faults but are not.
- **One StudioMCP process owns Studio's connection at a time.** Every `rbforge` live command starts its
  own; the agent's own MCP connection then has to find Studio again. After an `rbforge push`, `exec`,
  `servertest` or `probe` run, call `list_roblox_studios` before the next direct MCP call.
- **Input Actions need a held key.** An instant `keyPress` may not register with an `InputAction`; send
  `keyDown`, wait 150-200 ms, `keyUp` in one call. Keys still queued in a macro keep firing after the
  character dies and respawns. `character_navigation` walks the character to a point; `W` moves relative
  to the camera, not the character.
- **The person at the PC is an input source too.** Play locks their mouse; their clicks and key presses
  reach the game during an automated run. Before calling a stray stamina drain or attack a bug, read
  `UserInputService` input events in the log, and keep automated Play sessions short.
- **GPU-heavy jobs on the same machine starve Studio.** A Blender render or an image model running
  alongside made MCP calls time out. Run one heavy job at a time and render previews only when needed.
- **Read the console filtered.** `get_console_output` can return thousands of asset-load lines; in Play,
  `LogService:GetLogHistory()` filtered by message type or text (probe `console`) is the usable view.
- **`execute_luau` in Edit runs with plugin rights.** `StudioTestService` methods are callable from it:
  `ExecuteMultiplayerTestAsync(2, ...)` returned `ok=true` and opened a server window plus one window per
  client. That is the owner's screen: do not start a multi-client test, a Team Test or a second Studio
  without asking. Puppets and QA slots (`testing-debugging.md`) prove multi-party behaviour in one window.
- **A scripted camera ignores `screen_capture`'s camera arguments in Play.** A game that sets the camera
  every frame overwrites them. In Play, stage the character where the game's own camera sees the subject,
  or give the camera controller a Studio-only override attribute it honours; camera arguments work in Edit.
- **One Studio, one operator.** When another agent or the owner is working in the place, a live call from
  you takes their MCP connection, and Play/Stop changes their session. Verify offline instead, or wait;
  never kill a Studio process you did not start. Select the instance by place id from
  `list_roblox_studios`, not by a remembered session id: session ids change between launches.

## Subagents

| Type | Use it for |
|---|---|
| `explore` | map an unfamiliar place, find scripts, query live state - without flooding your context with `search_game_tree` JSON |
| `playtest` | run a gameplay scenario start to finish; it drives `start_stop_play` itself |
| `screen_capture` | visual verification loops |
| `unit_test` | run Luau unit tests (pairs with `skill "rbx-unit-test"`) |

Subagents are one-shot: they return a final text summary, cannot be asked
follow-ups, and cannot nest. Give the whole task and the exact evidence you want
back in one prompt. Do NOT delegate a single `script_read` - direct is cheaper.

## Enable / connect facts

- Toggle lives in Studio: Assistant -> "..." -> Manage MCP Servers ->
  "Enable Studio as MCP server". Editor-side setting; no tool flips it.
- Launcher: `%LOCALAPPDATA%\Roblox\mcp.bat` (Windows) /
  `/Applications/RobloxStudio.app/Contents/MacOS/StudioMCP` (macOS).
- Green indicator under Manage MCP Servers confirms clients connected.
- Security warning from Roblox applies: connected clients can read AND modify
  your open place. Only connect trusted agents.
