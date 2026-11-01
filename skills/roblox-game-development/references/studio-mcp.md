# Studio MCP reference (official built-in server)

Verified against a live handshake on Windows 11, Studio 0.735.x, 2026-11-01:
**34 tools**. The surface moves with Studio updates - always confirm via
`list_roblox_studios` + `rb_capabilities`, never from memory. A tool named here
that is absent is absent; say so instead of pretending.

## Tool map

| Group | Tools |
|---|---|
| Scripts | `script_read`, `multi_edit` (creates scripts too), `script_search`, `script_grep` |
| Data model | `search_game_tree`, `inspect_instance` |
| Luau execution | `execute_luau` (datamodel_type: Edit / Client / Server) |
| Playtest | `get_studio_state`, `start_stop_play`, `get_console_output`, `screen_capture` |
| Input | `character_navigation`, `user_keyboard_input`, `user_mouse_input` |
| Generative | `generate_procedural_model`, `generate_mesh`, `generate_texture`, `generate_material`, `generate_scene`, `generate_avatar`, `auto_setup_avatar`, `segment_mesh` |
| Assets | `search_asset`, `insert_asset`, `store_image`, `upload_image` |
| Async | `wait_job_finished` |
| Docs/skills | `http_get`, `skill`, `list_skills`, `create_skill`, `edit_skill` |
| Delegation | `subagent` (`explore`, `playtest`, `screen_capture`, `unit_test`) |
| Sessions | `list_roblox_studios` |

## Argument quirks (these cost real retries)

- **Every call needs `studio_id`** from `list_roblox_studios`. Two open places =
  two ids; pick deliberately. `list_roblox_studios` is the only exception.
- **`datamodel_type` is required, not defaulted**, on `execute_luau`,
  `search_game_tree`, `multi_edit`, `user_keyboard_input`, `user_mouse_input`.
  `Edit` is rejected while a playtest is running - switch with
  `start_stop_play(is_start: false)` first.
- **No `+=`.** The tool pre-parser rejects compound assignment. Write
  `counter = counter + 1`.
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
