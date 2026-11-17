# Roblox game-design intelligence for coding agents

Before systems, identify the loop:

**ACTION -> FEEDBACK -> REWARD/PROGRESS -> REASON TO REPEAT**

For every game, define:
- first action within ~30 seconds,
- first meaningful reward,
- first visible progression,
- failure/friction,
- next short-term goal.

## Weak-model failure

"Simulator" -> pets + rebirths + 8 currencies + shops + codes + quests before the
basic action is satisfying.

## Better

One action feels good -> one server-authoritative reward -> one upgrade changes the
action -> UI clearly communicates it -> then add retention/progression layers.

## Roblox presentation

Prioritize:
- readable spawn,
- obvious first objective,
- strong feedback (animation/VFX/SFX/UI),
- landmarks,
- consistent palette,
- scale and traversal appropriate to avatars,
- short time-to-fun.

Do not polish a broken loop. Do not ship a technically working graybox if the loop
is proven and the tools allow inexpensive polish.

## Game feel ("juice") matrix

Polish is not decoration; it is feedback that makes the action legible. Add these
in this order — each one is cheap and independently testable:

| Beat | Cheap implementation | Prove it with |
|---|---|---|
| Hit confirmation | camera FOV spring (70 → 76 → 70 over 0.12s), brief hit-stop (freeze 0.04s) | `screen_capture` two frames apart; console clean |
| Impact | particle burst at contact point, `SoundService` pool of 6 pre-loaded sounds | audio plays once, no duplicate on rapid hits |
| Numbers | floating damage text with `TweenService` up + fade | count text instances after 10 hits — must not grow |
| Currency | UI number ticker springing to the new value, not snapping | value equals server value after the tick |
| Movement | small acceleration + landing squash, `Humanoid` walk speed ramp | walk speed returns to base, no drift |
| Reward moment | a short sting, a burst, the number that grew scaling up and settling | everything returns to its rest state; nothing stays scaled |

Rules:
- **Reuse, do not spawn per hit.** A new `ParticleEmitter` and `Sound` for every
  hit grows the instance count until the client stalls. Keep a small pool, or
  `Emit(n)` on an emitter that already exists.
- **Tween one-shot changes; step only what is continuous.** A fade, a slide or a
  pop is a `TweenService` call. A spring that follows a moving target needs a
  per-frame step - keep it to one connection per system and disconnect it when
  the thing it drives is gone.
- **Every effect ends.** Capture a screenshot after the effect, not during; a
  permanent screen shake is a bug the agent will call "juice".
- **Local feedback immediately, authoritative numbers after the server.** The
  press animates and sounds at once; the currency counter moves when the
  server's value arrives. A counter that runs ahead of the server teaches
  players the UI lies.
- **No global slow motion.** There is no per-player time scale in a shared
  server; fake it locally with animation speed and camera, never by changing
  gravity or walk speed for a moment.

## Economy sanity, checked offline

Before shipping a currency loop, assert the math outside the engine (see
`persistence.md` for the Lune harness):

- time-to-first-upgrade ≤ ~90 seconds for a new player,
- cost curve growth between 1.15x and 1.5x per tier (below feels flat, above
  feels like a wall),
- income per action grows slower than cost per tier, or the game solves itself,
- every currency has its sources and sinks written down, and at least one sink
  that scales with progress - a currency with nowhere to go is a number, not a
  system.

These are starting points to tune from playtests, not laws. If you cannot state
where a currency comes from and where it goes in one sentence each, the design
is not ready to implement.
