# Sight lines through openings

A "weird flat coloured wall / screen effect" that appears from one direction only
has two common causes. **Check the first one before anything else** - it cost one
project about 20 failed fix rounds across three models (terrain carves, shutters,
cut panels, a blast door), all aimed at the wrong cause.

1. **A SurfaceGui painting outside its part.** `SurfaceGui.ClipsDescendants`
   defaults to **false**: any child sized or positioned past the 0..1 canvas
   (parallax layers, oversized backgrounds, a panorama slice with a negative
   offset) is drawn beyond the part's face, in mid-air. SurfaceGuis are
   one-sided, so the artefact shows only from the face's side - which reads
   exactly like "only from the base, not from the city". It is invisible to
   raycasts, box queries and part scans because there is no geometry there.
   **Fix: `gui.ClipsDescendants = true`.** Find offenders with:
   ```lua
   for _, g in model:GetDescendants() do
     if g:IsA("GuiObject") and g:FindFirstAncestorWhichIsA("SurfaceGui") then
       local p, s = g.Position, g.Size
       if p.X.Scale < 0 or p.Y.Scale < 0 or p.X.Scale + s.X.Scale > 1 or p.Y.Scale + s.Y.Scale > 1 then
         print(g:GetFullName())
       end
     end
   end
   ```
2. **The world outside seen through a hole** - a backdrop, terrain or sky lit
   flat enough to read as a surface.

## Diagnose in this order

1. **Ask where the camera is, not what the object is.** "It shows from the base
   but not from the city" is a description of a sight line, not a bug in a part.
2. **Bisect by hiding, with a fixed camera.** Capture with explicit
   `camera_position`/`look_at_position`, reparent one whole model to
   ServerStorage, capture again from the same pose. Artefact gone -> it lives in
   that model; put it back and halve the children by Name. Restore afterwards.
   This finds non-geometry causes (SurfaceGui overflow, Beams, particles) that no
   query can.
3. **Know what your queries skip.** Raycasts AND `GetPartBoundsInBox` /
   `GetPartsInPart` all skip `CanQuery = false` parts (most generated decor and
   screens). An "all clear" from them proves nothing. For a real check iterate
   `GetDescendants()` and test each part's OBB yourself; SurfaceGui content is
   not geometry at all (see cause 1).
4. **Look through the opening, not at it.** Grass, sky, terrain, a neighbouring
   build or a backdrop plane seen through a door all render as a flat rectangle
   with a hard edge and a "sky strip" above it. That combination is the signature.

## Fix the opening, not the artefact

- **Carry the structure past the hole.** A tunnel that ends at the containment
  wall shows the hillside; 24 studs of concrete throat (floor, roof, both walls)
  plus a door turn the same view into architecture. Same trick works for service
  corridors, hangars and airlocks.
- **A door that opens on approach** keeps the exit usable: probe distance to the
  door's world position on a slow loop and lerp it open, rather than a trigger
  volume that can be missed at speed.
- **Never delete the geometry that seals an opening.** When a corridor passes
  through a shell, split each crossing panel (and its backing) into pieces around a
  doorway the size of the corridor: left strip, right strip, top piece. Do not drop
  whole panels - a 40-stud panel removed leaves a 40-stud hole. Any test that
  selects panels to modify must constrain **every** axis: a "|z - cz| small" test
  with no x/side check also hits the opposite side of a dome. Give split pieces
  sub-ranges of the parent's UV/angle attributes so projected images stay continuous.

## Build-time traps this exposes

- A runtime world build (terrain carve, generated shell) never persists into the
  saved place: what the owner sees in the editor is the file, not the script. If
  a fix "did nothing", check edit-mode state before touching code.
- Generated geometry is usually `CanQuery = false`, so ray AND box-overlap tests
  silently miss it. Iterate descendants and test OBBs, or bisect by hiding.

## Process rules (from a bug that survived 20 "fixed" claims)

- **Reproduce at the reported pose before and after.** Put the capture camera where the
  owner stood, looking where they looked. "I zoomed past it and it looked fine" is not proof.
- **One hypothesis, one decisive test.** Before editing, name the cause and the capture
  that would prove it (hide X -> artefact gone). If the test fails, revert that edit; do
  not stack the next workaround on top of it.
- **Workarounds that hide a symptom are not fixes** (shutters that turn transparent on
  approach, doors over the view, recolouring the artefact). They multiply the cases the
  owner reports.
- **Never undo a property the owner relies on** (a sealed shell, collision) to chase a
  visual bug. If a fix must open something, it is the wrong fix.
- **Rebuild then save.** An Edit-mode rebuild changes the open place only; the owner must
  save (Ctrl+S) or the file on disk still holds the old build.

## Closing an opening: the checklist that survives a rebuild

- **Build the closure where it cannot be lost.** Generated worlds (domes, tunnels,
  corridors) are usually rebuilt at runtime from scripts, while a hand-placed part
  lives only in the saved place. If a fix must hold for every session, put it in the
  generator; if it must hold for every *plot*, take the plot's own coordinates.
- **World-space scopes are the quiet killer.** A builder scoped at `CFrame.new()`
  places parts in world space, so a hardcoded `z = 0` puts the closure in exactly one
  plot out of six and nowhere else. Always pass the plot axis (`plan.cz`) explicitly.
- **Prove it with state, not a screenshot.** Read the part's `Transparency` at two
  distances (far = closed, near = open) and count the parts across every plot; a
  third-person camera inside a tight corridor will jam against walls and show you
  nothing useful.
- **One mechanism, and say so in a comment.** If a generator fix and a place fix can
  both own the behaviour, the generator one is authoritative - delete the other and
  write down which survived and why.

## Decorative geometry is not structure

Anything that exists to be looked at - rot, foliage, cables, rubble, decals built as
parts - must be `CanCollide = false` and usually `CanQuery = false`. A collidable
tendril snags the player in a doorway, and a queryable one makes every "is this
corridor clear" probe lie to you.

Generated decor also has to stay inside the volume it decorates. Clamp every node to
the room's own bounds (above the deck, inside the wall face) at the point of creation:
a growth that starts 40 studs outside the wall renders through the exit door and under
the floor, and then reads as a rendering bug rather than a placement one.

- **Search for the mechanism before you build one.** A project that already animates a
  barrier (rams, lamps, alarm, prompt) does not need a second flat door in front of it.
  `grep` the builders for gate/door/shutter/barrier first: replacing a good system with
  a quick one is a regression with extra steps, and the owner will spot it instantly.
- **Clamp in the coordinate space you measured in.** A builder that works in world
  space must clamp against `wallX`, not against a local `-2.5`: the first attempt here
  compared world X to a local constant and dragged 159 parts to the world origin.
  Verify placement by counting parts on each side of the boundary, not by looking at
  the scene - a whole set can move somewhere wrong and still look plausible.
