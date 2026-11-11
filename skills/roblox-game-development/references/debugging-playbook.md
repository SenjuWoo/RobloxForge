# Debugging playbook: symptom -> cause -> proof

For agents with a small context and few retries. Do not improvise inspection
code: **`rbforge probe <name>`** (CLI) or the **`rb_studio_probe`** MCP tool
returns a reviewed Luau snippet plus the datamodel to run it in; pass it to the
Studio MCP's `execute_luau`. List them with `rbforge probe`.

| Probe | Answers |
|---|---|
| `console` (`since=60`) | Which errors are NEW since my change? (deduped, counted) |
| `player-state` | "I fly / get launched": is the position actually changing, and did a viewmodel weld grab the assembly? |
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
| `goto` | Put the character somewhere so that area streams in (a pinned camera alone shows an empty streamed world) |
| `capture-quality` | Force full render quality for a capture and report the frame rate; restore with `level=0` |
| `sound-audit` | Which sound ids fail to load, and which exist only in this Studio install |

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

### When the owner says "it's still there"

A reported visual bug is only fixed when the same person, standing in the same
place, in the same view, sees it gone. Compilation success, a passing unit test,
a clean console, or a green number in a metric are not evidence about pixels.

Before editing:

1. **Reproduce from the affected position and view.** Camera mode matters:
   first person hides the body, third person shows it; the same artefact can
   exist in one and not the other. Note the game state (which plot, which phase,
   night vs day, inside or outside).
2. **Record a baseline.** Same pose, same settings, capture before any change.
   Two captures with different poses prove nothing.
3. **Name the responsible object with evidence**, not a hunch: bisect by hiding
   candidate models (`hide` / `restore`), read pixels from the capture, or run a
   ray from the exact camera through the artefact. If you cannot say which
   instance produces it, you are not ready to edit.
4. **Make the smallest change that removes it.** Deleting a system to hide a
   symptom is not a fix.
5. **Return to the exact reproduction pose** and capture again.
6. **Check the neighbours**: the other plots, rooms or gates that share the
   generator, and the second camera mode.
7. **Revert a fix that did not work** instead of adding another layer. Two
   speculative patches on the same artefact produce a state nobody can reason
   about.
8. **Classify the failure before fixing it** - visual (paint, transparency,
   layering), collision, geometry (a hole or a wall where none should be),
   replication (server and client disagree), or persistence (it looks fixed until
   the place reloads). The category decides what evidence can prove it.
9. **Verify Edit, Play and saved/published separately** where relevant. A runtime
   build does not persist; an Edit-mode capture does not run scripts; a Play-mode
   change is discarded when you stop.
10. **Never claim a visual fix from an indirect signal.** "The script ran", "the
    probe returned 0", "the test passed" are supporting facts, not a picture.

If the owner sends a screenshot, treat the screenshot as the reproduction: match
the camera, the height and the view before you touch code.

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
| Frame rate is a flat ~15 fps whatever is in the scene | Studio is in the background and throttled, not the place | `capture-quality` (reports fps); hide your new models and re-measure - if nothing changes it is not your content |
| Boot or a build step "got four times slower" | Same throttle, plus build code that yields one frame per chunk | publish per-step seconds as an attribute; yield on elapsed time, not per chunk |
| Custom sounds silent, stock clicks still play, no error | `rbxasset://sounds/<folder>/...` files live in the versioned Studio install; a Studio update removed them | `sound-audit` |
| A sound that used to be stock is silent | Stock content files are not guaranteed between Studio versions | `sound-audit` |
| Night sky is bright blue while the ground is dark | The `Sky` uses fixed image ids, which do not follow the clock | replace it with a default `Sky` (engine textures) and capture at night |
| Far geometry missing from a Play capture but present in Edit | Automatic quality collapsed the draw distance (throttled Studio), or the area is not streamed in | `capture-quality level=21`, `goto` |
| Distant area is empty in Play although the server built it | StreamingEnabled streams around the character, not a pinned camera | `goto`, then `camera-pin` |
| Props float or sink on terrain | Positioned at the height the terrain was filled to; smooth terrain settles below it | raycast down and stand the prop on the hit |

## Input through the MCP

`user_mouse_input` with a `moveTo` onto the viewport first, then `scrollUp`,
did drive a wheel-zoom into first person (observed 2026-11-05). If a scroll
seems ignored, move the pointer onto the 3D view first and check the state the
feature writes (an attribute or camera distance) rather than calling it broken.
Keyboard input is released at the end of each call: hold-to-sprint needs
keyDown, wait, keyUp in one call.
