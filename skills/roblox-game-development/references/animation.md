# Animation: procedural motion and first-person viewmodels

Notes from building a held-weapon viewmodel and a gait layer over R15 on a live
game. Everything here is additive to the Animator, so it layers on whatever the
character is already playing instead of replacing it.

## The additive layer

`Motor6D.Transform` is applied **after** the Animator's output. Setting it every
frame in `RunService.PreSimulation` gives you a procedural pass on top of the
played animation without touching Animator assets:

```lua
RunService.PreSimulation:Connect(function(dt)
    waist.Transform *= CFrame.Angles(pitch * 0.4, 0, -lean * 0.3)
end)
```

Cache the joints once per character (`Waist`, `Neck`, `Root`, `LeftHip`,
`RightHip`, `LeftKnee`, `RightKnee`, `LeftAnkle`, `RightAnkle`, `LeftShoulder`,
`RightShoulder`, `LeftElbow`, `RightElbow`); walking the tree every frame for
every player is the usual performance accident. Do it for **every** character on
the client - shared attributes (`Stance`, `Aim`, `Lean`) are enough to pose
others without any new replication.

## A gait that reads as movement

- **Drive the cycle from real speed**, not input state:
  `Vector3.new(vel.X, 0, vel.Z).Magnitude` from `HumanoidRootPart`. A character
  pushed by physics then walks, and one blocked by a wall stops.
- **Phase advances with speed**: `phase += dt * (idleRate + stride * runRate)`.
  Constant-rate cycles look like treadmills.
- **Two joints make a leg**: hip swings, knee only bends on the back half
  (`-max(0, swing) * 1.15`). Bending both directions reads as a puppet.
- **Arms counter-swing and damp while aiming** - a weapon must not bob with the
  shoulders while the player is trying to hit something.
- **Root bob and roll**, then **counter-rotate the neck** by part of the bob so
  the head stays level. Without that the camera feels like it is on a spring.
- **Airborne**: tuck the knees, and pick the amount from vertical velocity.
- **Landing**: remember `lastVelY`, and on the frame the feet touch down convert
  it into a squash that decays (`land = max(0, land - dt * k)`).
- **Standing still is not frozen**: a slow breath on the root and neck at ~1 Hz
  keeps an idle character alive.

## First-person viewmodel

A viewmodel is a clone of the world weapon parented to the camera, not a UI
image. What matters, in the order it bites:

1. **One anchor, everything welded to it.** Build a small anchored part, weld the
   weapon root to it, and weld every other part to the root. Drive exactly one
   CFrame per frame.
2. **Scale for the eye.** A weapon authored for a character is enormous at one
   stud from the camera. `Model:ScaleTo(0.5-0.65)` before welding, then frame it
   around `CFrame.new(0.32, -0.34, -1.15)`.
3. **Lift the palette and add a key light.** World lighting reaches the back of
   the gun while the eye sees the front - the model renders as a black slab.
   Lerp part colours toward mid grey and put a `PointLight` on the camera.
4. **Hide the whole body, not the arms.** From inside the head, the torso and
   backpack are black wedges across the screen. `LocalTransparencyModifier = 1`
   on every BasePart of the character while the viewmodel is up, restored after.
5. **Hands.** A floating gun reads as a bug; two blocky gloved hands on the grip
   and fore-end read as held. They cost four lines.
6. **Sway, bob, recoil, reload** on springs: sway from the camera's own yaw/pitch
   delta (clamped), bob from horizontal speed, recoil as an impulse the fire path
   calls, and a dip while reloading.

## Verifying it without a mouse

MCP synthetic input cannot turn a mouse wheel, so a zoom-to-first-person feature
cannot be driven from a test. Add a debug attribute the movement code respects:

```lua
local firstPerson = st.zoom == 0 or player:GetAttribute("DebugFirstPerson") == true
```

Then a client `execute_luau` can set it, wait a frame, and assert the viewmodel
exists, the body is hidden and the log is clean. That is a real test of the same
code path the wheel uses.

## Traps

- Welding parts that are still `Anchored` leaves the assembly frozen; unanchor
  every cloned part.
- Cloning a weapon brings its `PointLight`s, `ParticleEmitter`s and any scripts
  with it; strip them or you get a second muzzle flash in the eye.
- `Model:ScaleTo` after welding does not move welds the way you expect - scale
  first, then weld.
- Setting `Motor6D.Transform` on a joint that no animation touches is safe;
  writing `Motor6D.C0` fights the Animator and jitters.
