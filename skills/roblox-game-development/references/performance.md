# Roblox performance — measure first

Performance problems span script CPU, rendering, physics, memory, network and loading. Optimize the
measured bottleneck. Pick the level before the technique (`optimization-levels.md`); engine detail
is in the `roblox-performance` skill and the official guide
(`rb_docs_read performance-optimization/improve.md` - it lists common problems, mitigations and the
MicroProfiler scope names for each area).

## Procedure

1. Reproduce the slow moment in a **foreground** Studio window or on a device. Background Studio is
   throttled to about 15 fps and collapses draw distance: numbers from it are the throttle
   (`capture-quality` probe reports the frame rate).
2. Capture evidence: the `perf` probe for counts and frame time, `scene-audit` for the scene,
   Studio skill `rbx-perf-profiling` for a MicroProfiler read, `rbx-scene-analysis` for composition.
3. Name the dominant subsystem: script, physics, humanoids, rendering, network, memory, load time.
4. Fix one thing in that subsystem.
5. Capture again under the same conditions and compare. Record device, graphics level, player count.

"Use fewer parts" is not a performance analysis. There are no universal part, texture or FPS
budgets here - record a measurement and compare like with like.

## What usually turns out to be the cause

**Script time**
- work every frame that only needs to happen on change (polling a value instead of its changed
  signal; rebuilding a list every `Heartbeat`);
- walking `GetDescendants()` / `GetChildren()` of a large tree in a loop - cache, or tag with
  `CollectionService` and keep the list;
- one per-frame connection per object instead of one loop over a list;
- AI decisions at render frequency: decide at 5-10 Hz, move and animate every frame;
- unbounded `task.spawn` per event; connections made per respawn and never disconnected.

**Humanoids and NPC crowds** (from the official guide)
- a `Humanoid` is expensive: disable the `HumanoidStateType`s an NPC never uses
  (`Humanoid:SetStateEnabled`), and do not use one for an NPC that only stands and animates - an
  `AnimationController` is enough;
- play NPC animations on the **client**; server-played animation is simulated and replicated for
  every NPC;
- pool NPC models instead of destroying and re-creating them; spawn only near players;
- for procedural posing write `Transform`, never `C0`/`C1`, and attach extra parts outside the
  character model;
- the server owns NPC physics (`SetNetworkOwner(nil)` on the root), or ownership flips between
  nearby clients and the NPC stutters.

**Physics**
- anchor everything that does not need to move; unanchored decor is simulated;
- `CollisionFidelity` = `Box` or `Hull` on meshes unless precise collision is the point;
- `CanCollide`, `CanTouch`, `CanQuery` off on decor; collision groups for things that never
  interact.

**Rendering**
- draw calls: many different meshes, materials and textures cost more than many instances of the
  same one - reuse MeshIds and `SurfaceAppearance`/`MaterialVariant`s;
- shadow-casting lights and large overlapping light ranges; `Shadows = false` on fill lights,
  `CastShadow = false` on thin decor;
- large transparent surfaces layered over each other (overdraw); particle counts and large
  particles close to the camera;
- always-on `Highlight`s and `ViewportFrame`s.

**Network**
- remotes fired every frame (`T013` in the trap lint): send on change or batch at 5-10 Hz;
- sending state the client can derive, or whole tables when one field changed;
- attributes and replicated values that change every frame.

**Memory and loading**
- unique large textures and meshes that could be shared; preloading everything with
  `ContentProvider:PreloadAsync` instead of what the first screen needs;
- a map built by a server script at start-up: the first spawn waits for it, and none of it streams
  the way authored content does (`architecture.md`, "Authored or generated");
- with `StreamingEnabled`, client code must tolerate parts that are not there yet.

## Streaming

`Workspace.StreamingEnabled` is on by default in new places and is set in Studio, not from a
script. Leave it on for any large map and write client code for it: `WaitForChild`, added/removed
signals, `Model.ModelStreamingMode` (`Atomic`, `Persistent`) for things that must arrive whole or
always exist. Studio skill `rbx-convert-to-streaming` before turning it on in an old place.

## Claims

"Optimized" needs a before and an after from the same scenario. Without both, say "not measured".
