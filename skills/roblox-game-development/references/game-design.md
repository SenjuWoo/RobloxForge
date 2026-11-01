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
| Reward moment | 0.2s time dilation on level-up, then restore | `workspace.Gravity` unchanged after the effect |

Rules:
- **Pool, do not spawn.** A `ParticleEmitter` and `Sound` per hit leaks instances
  and eventually stalls the client. Create N up front, reuse them.
- **Tween, do not loop.** `RunService.RenderStepped` loops for cosmetic values are
  a common latency bug; `TweenService`/Fusion springs get the same look for free.
- **Every effect ends.** Capture a screenshot after the effect, not during; a
  permanent screen shake is a bug the agent will call "juice".
- **Feedback is server-confirmed.** Show the currency ticker *after* the server
  confirms, or you teach players the UI lies.

## Economy sanity, checked offline

Before shipping a currency loop, assert the math outside the engine (see
`persistence.md` for the Lune harness):

- time-to-first-upgrade ≤ ~90 seconds for a new player,
- cost curve growth between 1.15x and 1.5x per tier (below feels flat, above
  feels like a wall),
- income per action grows slower than cost per tier, or the game solves itself,
- every currency has exactly one source and one sink, written down.

If you cannot state the loop's source and sink in one sentence each, the design
is not ready to implement.
