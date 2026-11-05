# UI craft: making a HUD that does not read as agent output

Distilled from a tactical HUD that took several rejections to land ("plain colour panels",
"too low quality", "AI slop"), and from the brief that finally pinned it down. The rules are
about *why* a UI looks generated and what to build instead. Pair with `ui-mobile.md` for input
and safe areas; this file is about taste and legibility.

## The tells of agent-made UI

A reviewer spots these instantly. Check your own work against the list before showing it.

1. **Everything is a rounded rectangle** with a 1 px stroke and a soft gradient. Menus may be
   panels; gameplay readouts must not be. If your HUD is a grid of boxes, it is slop.
2. **Default fonts.** Gotham/SourceSans/Arial at default weights is the single loudest tell.
   Use `FontFace` with a real family (a condensed face for labels, a clean sans for body) and
   use weight, size and letterspacing for hierarchy - not boxes.
3. **Centre-stacked composition.** Agent layouts centre everything and fill the middle of the
   screen. A HUD lives on the edges and keeps the centre (aim, threat, horizon) clear.
4. **Rainbow gradients / purple-blue hero gradients / glow everywhere.** Pick 5-6 tokens and
   stay there: ink, surface, border, text, muted, plus one accent for interaction and one for
   threat. Colour carries meaning or it does not appear.
5. **Emoji or asset-store icons** standing in for real iconography. Draw ticks, notches,
   brackets, hazard stripes, arcs and chevrons out of Frames - they scale, recolour and never
   look borrowed.
6. **Uniform spacing and weight.** Real interfaces have rhythm: a tight cluster, a wide gap,
   one heavy number, whisper-quiet labels. Even distribution reads as a template.
7. **Fake progress and fake numbers.** An animated 0-100 % bar that is not tied to real stages,
   or a stat that disagrees with the server, destroys trust faster than an ugly layout.

## Build rules that produced something the owner accepted

- **Legibility without boxes.** Text over bright sky needs a soft dark edge, not a panel:
  `TextStrokeTransparency` around 0.55 with an ink stroke colour. Painters do it this way.
- **Backdrops with a falloff.** When a cluster needs a background, build it from strips with a
  2D falloff (dark at the screen edge, gone toward the centre). One `UIGradient` cannot do a
  rectangle-free falloff, and a plain translucent box is the tell you were trying to avoid.
- **Small-scale furniture.** A tracker needs a ring, a sweep arm, bearing ticks and a heading
  caret; a magazine readout needs one tick per round. Detail at 8-14 px is what separates a
  readout from a placeholder.
- **Motion with intent.** 150-250 ms tweens, eased (Quad/Quint), staggered when a group
  returns. A computer-boot bar over a panel that slides away beats a fade to nothing.
- **Type scale over layout churn.** Three sizes and two weights carry almost everything:
  a heavy number, a compact caps label, a muted caption. Use `string.upper` and a letterspaced
  caption before inventing a new font size.
- **Layout once at 1080p**, then `UIScale` per cluster from the viewport height. Do not sprinkle
  offsets that only work at one resolution.
- **Separate the two views properly.** A third-person HUD belongs in a `ScreenGui`; a visor or
  helmet belongs in 3D panes bound to the camera (`SurfaceGui` with `LightInfluence = 0`,
  depth-tested, FOV-scaled). Rendering a "helmet" as a full-screen overlay fools nobody.
  Recipe that held up: panes about 0.75 studs from the eye (`AlwaysOnTop` panes did not
  render); `depth = D * tan(refFov/2) / tan(fov/2)` so aiming does not resize the visor;
  `PixelsPerStud = 1080 / (2 * depth * tan(fov/2))` to author in 1080p pixels; tilt each pane
  toward the eye by yaw/pitch only (`CFrame.fromEulerAnglesYXZ(-pitch, math.pi - yaw, 0)` - a
  `lookAt` rolls the corner panes); keep the visor locked to the head with at most ~1.5 degrees
  of sway (a lerped "lag" rotation throws panes off-screen on fast mouse turns).
- **A companion that feeds the HUD needs a body.** A drone over the shoulder makes
  third-person intel credible. Key its station to the *camera* heading, not the body, or it
  swings behind the camera on every turn; give it a faint `Highlight` outline so it reads on
  dark and bright backgrounds; build it from few, touching parts and preview it in Edit
  (require a clone of the module, build at a spot in the sky, capture) before Play.
- **Soft backdrops without boxes:** one UIGradient fades in one direction only, so a
  gradient frame shows hard side edges. Stack ~16 horizontal strips, each fading at both
  ends and fainter with distance from the screen edge.
- **Only expose what the server can actually do.** Hide or disable a tab whose backend does not
  exist. A dead button is worse than a missing feature.

## Slop check before you claim the UI is done

- [ ] Screenshot at 1080p **and** at a small window: nothing clipped, nothing overlapping.
- [ ] Screenshot over the brightest scene in the game: every label still readable.
- [ ] Every number on screen traces to a server value or a real client state.
- [ ] Count the instances: a HUD that stopped halfway still photographs as a HUD
      (`hud=true frames=467 labels=151`).
- [ ] No default font, no emoji, no centred paragraph block, no rainbow gradient.
- [ ] The centre of the screen is clear at rest, and clearer while aiming.
- [ ] Loading screens gate on real readiness (world, plot, character, camera) and can fail
      visibly instead of hanging at 99 %.

## Working with a concept image

Mockups are composition and palette references, not screenshots to be flattened into one image.
Read them for: anchor positions, what is emphasised, how much empty space there is, the spacing
rhythm. Then rebuild with native components. Never paste the mockup into an `ImageLabel` and call
it implemented.

When the owner rejects a pass, ask which of these failed - boxes, fonts, composition, colour,
detail, motion - and fix that axis. "Make it better" is not feedback; the axis is.

## A "glass" panel that renders as a black bar

`UIGradient.Transparency` **overrides** the object's `BackgroundTransparency` for
every pixel it covers. A panel set to `BackgroundTransparency = 0.62` with a
gradient whose first keypoint is `0` renders fully opaque at that end - which is
how a translucent HUD ends up sitting on solid black slabs that do not blend with
the scene. Either drop the gradient, or give its keypoints the transparency you
actually want (0.55 to 0.72 reads as tint over gameplay).

The same trap applies to `ImageLabel` tint gradients and to `UIStroke`
transparency keypoints. When a review says "weird black bars", check the gradient
before you touch the layout.
