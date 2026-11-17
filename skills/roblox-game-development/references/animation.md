# Animation: authored clips, procedural layers, first-person viewmodels

API detail for rigs, the Animator and constraints is in the `roblox-characters-animation` skill. This
file is how to choose a route and the traps on each.

## Choose the route first

| Route | Use it for | Cost |
|---|---|---|
| **Authored clips** played through the `Animator` (default) | characters, NPCs, weapons, doors - anything with a fixed motion | none per frame in your code; the engine blends, replicates and culls |
| `generate_animation` (Studio MCP) | a first pass of an R15 clip from a text prompt | needs a look and often a retime |
| **Additive procedural layer** over clips | aim offsets, leaning, look-at, recoil, breathing | a few joint writes per frame, per character you run it on |
| **Fully procedural rig** (code poses every joint) | creatures with no clip pipeline, legs that must plant on uneven ground | every joint, every frame, every instance - needs distance LOD from day one |

Default to clips. A fully procedural animator is hundreds of lines per creature type and a per-frame
bill that grows with the crowd; choose it when planted feet or a non-humanoid body justify it, write
down that you chose it, and budget it:

- run it on the **client** only - the server moves a root part and publishes state (attributes);
- animate only what is near and on screen: skip rigs past a distance, step far ones at a lower rate;
- one shared update loop for all rigs, not one connection per rig;
- measure with 30+ instances before building the second creature on the same pattern.

## Authored clips in practice

```lua
local animator = humanoid:FindFirstChildOfClass("Animator") :: Animator
local track = animator:LoadAnimation(animation) -- Humanoid:LoadAnimation is deprecated
track.Priority = Enum.AnimationPriority.Action
track:Play(0.1)
```

- Load a track once per character and keep it; loading inside the input handler stutters and leaks.
- An animation asset plays only in experiences of its owner (the user or group that uploaded it). A
  clip that works in Studio and is silent in the live game is usually an ownership mismatch.
- A track played on a character the client owns replicates to everyone; a server NPC plays its
  tracks on the server's Animator.
- Tie gameplay to animation with markers (`track:GetMarkerReachedSignal("Hit")`), not with
  `task.wait(0.3)` - but the **server** still decides whether the hit counts.
- Stop looping tracks when the state ends.

## Joints: Motor6D or AnimationConstraint

Current R15 avatars can be joined by `AnimationConstraint`s instead of `Motor6D`s (checked live
2026-11-16: a default player avatar in Play had 15 `AnimationConstraint`s, 14
`BallSocketConstraint`s and **zero** `Motor6D`s). Code that searches only for `Motor6D` silently
does nothing on them. Look for both, everywhere:

```lua
local function joint(model: Model, name: string): (Motor6D | AnimationConstraint)?
	local j = model:FindFirstChild(name, true)
	if j and (j:IsA("Motor6D") or j:IsA("AnimationConstraint")) then
		return j
	end
	return nil
end
-- offset: Motor6D -> j.C0 ; AnimationConstraint -> j.Attachment0.CFrame (C0/C1 are read-only there)
-- pose:   both    -> j.Transform
```

## The additive layer

`Transform` is written by the Animator each frame; multiplying it afterwards in
`RunService.PreSimulation` adds a procedural pass on top of whatever clip is playing:

```lua
RunService.PreSimulation:Connect(function()
	waist.Transform *= CFrame.Angles(pitch * 0.4, 0, -lean * 0.3)
end)
```

- Cache the joints once per character; walking the tree every frame for every player is the usual
  performance accident.
- Shared attributes (`Stance`, `Aim`, `Lean`) are enough to pose other players' characters on each
  client without new replication.
- Write `Transform`, not `C0`: writing `C0` every frame fights the Animator and jitters.
- `IKControl` results are applied by the Animator. If your code also poses those joints, it
  overwrites the solve and the limb ignores its target. Drive each joint from one system.

## A procedural gait that reads as movement

- **Drive the cycle from real speed**: `Vector3.new(vel.X, 0, vel.Z).Magnitude` of the root. A
  character pushed by physics then walks, and one blocked by a wall stops.
- **Phase advances with speed**: `phase += dt * (idleRate + stride * runRate)`. Constant-rate cycles
  look like treadmills.
- **Two joints make a leg**: the hip swings, the knee bends only on the back half.
- **Arms counter-swing and damp while aiming.**
- **Root bob and roll**, then counter-rotate the neck by part of the bob so the head stays level.
- **Airborne**: tuck the knees by vertical velocity. **Landing**: turn the last downward speed into
  a squash that decays.
- **Standing still is not frozen**: a slow breath at ~1 Hz.

## First-person viewmodel

A viewmodel is a clone of the world weapon parented to the camera, not a UI image. In the order it
bites:

1. **Strip the clone.** It carries the welds that bind it to the hand, plus lights, emitters and
   scripts. Destroy every `JointInstance` and `Constraint` in it before adding your own - an anchored
   viewmodel still welded to the live character flings the player.
2. **One anchor, everything welded to it.** Park the anchor on the weapon root
   (`anchor.CFrame = body.CFrame`), **then** weld: a `WeldConstraint` keeps the offset it saw at
   creation, and an anchor left at the origin puts the gun hundreds of studs away.
3. **Scale for the eye.** `Model:ScaleTo(0.5-0.65)` before welding, framed around
   `CFrame.new(0.22, -0.30, -1.20)` in camera space: about 12 % of the width and 32 % of the height,
   lower right. Measure with `Camera:WorldToViewportPoint`.
4. **Make it readable without lighting the world.** World light reaches the back of the gun while
   the eye sees the front. Lift the part colours toward mid tones and use untextured materials
   (world-stud material tiling turns cloth into planks at this scale). A light on the camera also
   lights every wall near the player: if you use one, keep it weak and short (about 0.6 brightness,
   4 studs).
5. **Hide the whole body, not the arms**: `LocalTransparencyModifier = 1` on every BasePart of the
   character while the viewmodel is up. On exit set them back to `0` - never to a saved value (the
   engine also writes it for the local head), and never touch `HumanoidRootPart`.
6. **Hands.** Two blocky gloved hands on the grip and fore-end read as held; a floating gun reads as
   a bug.
7. **Sway, bob, recoil, reload** on springs: sway from the camera's yaw/pitch delta (clamped), bob
   from horizontal speed, recoil as an impulse, a dip while reloading.

## Ragdoll leftovers

When a death hides the original model and swaps in a ragdoll copy, hiding parts is not enough:

```lua
for _, d in original:GetDescendants() do
	if d:IsA("LayerCollector") or d:IsA("Light") or d:IsA("ParticleEmitter") or d:IsA("Highlight") then
		d.Enabled = false
	end
end
```

## Verifying without a mouse

Add a debug attribute the movement code respects, gated to Studio:

```lua
local forced = RunService:IsStudio() and player:GetAttribute("DebugFirstPerson") == true
local firstPerson = zoom == 0 or forced
```

A client `execute_luau` can then set it, wait a frame, and assert the viewmodel exists, the body is
hidden and the log is clean - the same code path the wheel uses.
