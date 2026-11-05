# Sight lines through openings

An opening is a window: whatever is behind it becomes part of the interior's
look. Most "there is a weird coloured wall / screen / panel in my tunnel" reports
are not a broken asset - they are the world outside, seen through a hole, lit
flat enough to read as a surface.

## Diagnose in this order

1. **Ask where the camera is, not what the object is.** "It shows from the base
   but not from the city" is a description of a sight line, not a bug in a part.
2. **Compare the pixels.** Sample the RGB in the report's screenshot, then scan
   `workspace` for parts within ~0.06 of that colour. Colour identifies a part in
   one query; a raycast cannot hit a SurfaceGui, and `CanQuery = false` geometry
   (dome panels, decor) is invisible to every ray you cast.
3. **Test by elimination, one system at a time.** Disabling all screens *and* the
   HUD proves nothing - you only learn something when exactly one system changes
   and the pixels change with it.
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
- **Never delete the geometry that seals an opening.** If a generated panel shows
  up where it should not be seen, cut it by its **box overlap** with the opening,
  not by its centre - a 50-stud panel spans a corridor while its centre sits 20
  studs off-axis, which is why centre tests keep "passing". Deleting panels
  blindly opens a hole the owner will report next.

## Build-time traps this exposes

- A runtime world build (terrain carve, generated shell) never persists into the
  saved place: what the owner sees in the editor is the file, not the script. If
  a fix "did nothing", check edit-mode state before touching code.
- Generated geometry is usually `CanQuery = false`, so ray-based tests silently
  miss it. Test with box overlap or colour, not with a ray.
