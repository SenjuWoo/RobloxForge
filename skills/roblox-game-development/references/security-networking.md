# Roblox security and networking

Official baseline: **everything sent by a client is attacker-controlled**.

A RemoteEvent is a transport mechanism, not permission.

## Server validation layers

For any client-triggered state change, validate the layers that apply:

1. **Type** — correct primitive/table/Instance shape?
2. **Range** — sane numeric/string/table size?
3. **Context** — is this action possible right now?
4. **Permission/ownership** — does this player own/use the target?
5. **Spatial plausibility** — are they near the prompt/target if required?
6. **State transition** — is the requested transition legal?
7. **Rate** — can this be spammed?
8. **Server-derived value** — compute reward/damage/price server-side when possible.

## Bad

Client:
`RewardEvent:FireServer(1000000)`

Server:
`coins.Value += amount`

## Better model

Client:
`RewardEvent:FireServer(actionId)`

Server:
- verifies action exists,
- verifies player completed it,
- reads reward from server-owned config,
- applies reward once,
- records state/cooldown.

## RemoteEvent vs RemoteFunction

Use current docs when semantics matter.

General rule:
- Events are asynchronous notifications/requests.
- Functions are synchronous request/response and can create blocking/error coupling.
- Unreliable remotes are for high-frequency, non-critical data that may be dropped.

Never use an unreliable channel for authoritative purchases, inventory, or progression.

## Other exploitable boundaries

Do not focus only on remotes. Validate server effects triggered through:
- ProximityPrompt
- ClickDetector
- touched parts
- tools
- marketplace receipts
- teleport/admin commands
- trading systems
- physics ownership-sensitive mechanics

## Rate limiting

Rate-limit by action cost/risk, not one global magic number.

Store per-player timestamps/token buckets on the server.
Clean player state on `PlayerRemoving`.

## Creator Store models

Treat inserted scripts as untrusted code:
- inspect descendants,
- inspect Scripts/LocalScripts/ModuleScripts,
- inspect remotes,
- inspect require(assetId),
- delete unexplained behavior before shipping.

## Security completion check

Before calling a multiplayer feature complete:
- can a client award itself value?
- can it target another player's objects?
- can it send NaN/inf/huge strings/tables?
- can it replay the request?
- can it spam the request?
- can it skip required sequence/state?

## High-frequency data: serialize, do not send tables

A Luau table with string keys is expensive on the wire. For anything sent many
times per second (positions, movement intents, hit notifications) pack it into a
`buffer` of fixed-width fields.

```lua
--!strict
-- Shared/Shared/HitPacket.luau
-- 18 bytes: u32 targetUserId | u16 damage*10 | 3 x f32 position
local HitPacket = {}

local SIZE = 18

function HitPacket.encode(userId: number, damage: number, position: Vector3): buffer
    local b = buffer.create(SIZE)
    buffer.writeu32(b, 0, userId)
    buffer.writeu16(b, 4, math.clamp(math.floor(damage * 10), 0, 65535))
    buffer.writef32(b, 6, position.X)
    buffer.writef32(b, 10, position.Y)
    buffer.writef32(b, 14, position.Z)
    return b
end

function HitPacket.decode(b: buffer): (number, number, Vector3)
    return buffer.readu32(b, 0),
        buffer.readu16(b, 4) / 10,
        Vector3.new(buffer.readf32(b, 6), buffer.readf32(b, 10), buffer.readf32(b, 14))
end

return HitPacket
```

Rules that keep this honest:
- **Fixed layout, documented in one comment.** A byte offset written in two
  places drifts; keep encode/decode adjacent and derive both from `SIZE`.
- **Validate on decode.** An exploiter sends arbitrary bytes: clamp damage,
  reject unknown user ids, and never trust the position for authority.
- **Unreliable remotes are for the drop-tolerant subset only** — cosmetics,
  interpolation hints, camera shake. Purchases, inventory and progression go on
  reliable remotes and get a server reply.
- **The hard numbers (from the UnreliableRemoteEvent engine reference):** a
  payload over **1,000 bytes is dropped**, and the event is rate-limited to
  roughly **500 requests/second per client, shared across every
  UnreliableRemoteEvent in the game**. Buffers are compressed before sending, so
  a payload that fits in theory can still exceed the cap after encoding — test
  with the real data shape, and treat 1,000 bytes as the ceiling, not a target.
- Sample the rate yourself. Sending 200 messages/second per player is a design
  decision, not an accident; measure with `skill "rbx-network-simulator"`.

## Do not hand-roll the schema layer

For a project with more than a couple of remotes, a schema library is less code
and fewer bugs than a hand-written `if type(...)` wall. All three below compile
or validate typed schemas into buffer packets; pick one, do not mix:

| Library | Shape | When |
|---|---|---|
| ByteNet Max | pure Luau, `defineNamespace` packets + queries | Studio-native, no build step |
| Blink | `.blink` IDL compiled to Luau | Rojo/managed repo, lowest per-byte cost |
| Zap | `.zap` IDL compiled by a Rust CLI | largest schemas, CI-compiled |

Whatever you pick, the rule stays: **one shared schema module required by both
sides**, and the server re-validates every field it reads. A schema protects the
wire format, not your game rules.
