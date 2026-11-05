# Debugging playbook: symptom -> cause -> proof

For agents with a small context and few retries. Do not improvise inspection
code: **`rbforge probe <name>`** (CLI) or the **`rb_studio_probe`** MCP tool
returns a reviewed Luau snippet plus the datamodel to run it in; pass it to the
Studio MCP's `execute_luau`. List them with `rbforge probe`.

| Probe | Answers |
|---|---|
| `console` (`since=60`) | Which errors are NEW since my change? (deduped, counted) |
| `gui-overflow` | Is a SurfaceGui painting outside its part / an AlwaysOnTop gui not rendering? |
| `ray-all` | What does this sight line pass through, including CanQuery=false and invisible parts? |
| `box-scan` | Is this doorway / corridor / spawn really empty? (engine queries skip CanQuery=false) |
| `hide` / `restore` | Bisect: is the artefact inside this model? |
| `camera-pin` / `camera-free` | Hold the Play camera still so before/after captures compare |
| `scene-audit` | Loose parts, invisible walls, scripts in containers where they never run, light counts |
| `ui-audit` | Text too small, off-screen elements, ResetOnSpawn guis, duplicated HUDs |
| `player-state` | Position, velocity, humanoid state, floor, every attribute - instead of guessing from a picture |
| `whereis` | Where is the instance called X, in which datamodel? |
| `remotes` | Which remotes exist (compare to the names your code uses) |
| `perf` | Frame time and the counts that explain a slow place |

Static side: **`rbforge review --kind traps`** (MCP `rb_traps_review`) flags Luau
that compiles but breaks in Roblox, with the line, the fix and a reference.

## The fix protocol (do not skip steps)

1. **Reproduce at the reported pose.** Put the capture camera where the owner
   stood (`screen_capture` with `camera_position`/`look_at_position` in Edit,
   `camera-pin` in Play). Save that pose; every later capture uses it.
2. **Read the console** (`console`), then name ONE cause and the ONE test that
   would prove it ("hide model X -> artefact gone").
3. **Run the test.** No change in pixels -> wrong cause: revert anything you
   edited for it, pick the next cause. Never stack a second workaround on an
   unproven first one.
4. **Fix the cause in source**, push to Studio, rebuild if the world is
   generated, recapture from the saved pose, `console since=60` = 0 new errors.
5. **Say what is not verified** (and that the owner must save the place if you
   changed it in Edit).

## Symptom table

| Symptom | Usual cause | Prove it with |
|---|---|---|
| Flat colour wall / "screen effect" seen from one side only | SurfaceGui child larger than its canvas (`ClipsDescendants` defaults to false), one-sided | `gui-overflow`, then `hide` the model |
| Same, from both sides, with a sky strip above it | World outside seen through an opening | `ray-all` from the camera |
| "Fix did nothing" in the editor | Runtime-generated world never saved; or Studio's require cache served the old module | rebuild with fresh module clones; ask the owner to save |
| execute_luau `require` gives old behaviour | execute_luau has its own require cache | clone the ModuleScript and require the clone |
| Door/gate never moves, no visible error | Script error inside a `task.spawn` loop (e.g. an undefined global) | `console` - errors in spawned threads still log |
| Part falls through the map or drifts | Unanchored, unwelded | `scene-audit` (loose) |
| Player walks into nothing | Invisible collidable part | `scene-audit` (invisible-wall), `box-scan` |
| LocalScript never runs | It sits in Workspace / ServerScriptService | `scene-audit` |
| Remote does nothing | Name typo, created on the client, server never connected | `remotes`, `rbforge review --kind traps` |
| Character spawns in the void or falls on join | Spawned before the world/plot existed | `player-state` right after join; gate CharacterAutoLoads on WorldReady |
| HUD vanishes or duplicates after death | `ResetOnSpawn = true`, or the builder script runs twice | `ui-audit` |
| Image is blank | Wrong asset type (Decal id vs Image id), not loaded, or `ImageTransparency = 1` (never reports IsLoaded) | `ContentProvider:GetAssetFetchStatus(id)` |
| SurfaceGui never shows | Wrong `Face`, `AlwaysOnTop = true`, gui under a part outside Workspace | `gui-overflow` (AlwaysOnTop count), check `Face` |
| Raycast "misses" an obvious part | Part is `CanQuery = false`, or direction not multiplied by distance | `ray-all` |
| Edit DM tool fails with "not available in Play mode" | Studio is in Play | `start_stop_play is_start=false`, then push |
| Camera jumps between captures | Game camera script or the Assistant resets it | `camera-pin` |
| Slow frame rate | Shadow-casting lights, emitters, part count, per-frame remote spam | `perf`, `scene-audit`, traps lint T013 |

## Input through the MCP

`user_mouse_input` with a `moveTo` onto the viewport first, then `scrollUp`,
did drive a wheel-zoom into first person (observed 2026-11-05). If a scroll
seems ignored, move the pointer onto the 3D view first and check the state the
feature writes (an attribute or camera distance) rather than calling it broken.
Keyboard input is released at the end of each call: hold-to-sprint needs
keyDown, wait, keyUp in one call.
