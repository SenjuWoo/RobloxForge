# Roblox architecture — where code and authority belong

Roblox is client/server by default. The server is the authority for shared game state.

## Mental model

**SERVER OWNS TRUTH**
- currency
- inventory
- damage
- rewards
- progression
- matchmaking/round state
- ownership/permissions
- DataStores

**CLIENT OWNS INPUT + PRESENTATION**
- keyboard/gamepad/touch input
- camera
- local UI
- animation/effects that do not establish authoritative state
- prediction where the server still validates the result

**SHARED OWNS CONTRACTS + CONFIG**
- immutable/shared constants
- types
- utility modules safe for both sides
- network message schemas

## Service placement

| Location | Good uses |
|---|---|
| `ServerScriptService` | authoritative systems and server entry points |
| `ServerStorage` | server-only templates/assets not meant to replicate |
| `ReplicatedStorage` | shared modules, remotes, replicated assets/contracts |
| `StarterPlayerScripts` | client controllers/input/camera |
| `StarterCharacterScripts` | per-character client/server behavior when appropriate |
| `StarterGui` | ScreenGuis and client presentation |
| `Workspace` | live world/physics objects; not a dumping ground for application logic |

## Script types

- `Script`: server execution unless RunContext deliberately says otherwise.
- `LocalScript`: client execution in supported containers.
- `ModuleScript`: reusable code; authority depends on who requires it.

## Small-game baseline

Prefer a few coherent modules over framework ceremony:

- `ServerScriptService/Server/Game.server.luau`
- `ServerScriptService/Server/Systems/...`
- `ReplicatedStorage/Shared/...`
- `ReplicatedStorage/Remotes/...`
- `StarterPlayer/StarterPlayerScripts/Client.client.luau`
- `StarterGui/...`

## Anti-patterns

- one 2,000-line Script owning every system
- authoritative currency in LocalScripts
- client tells server how much damage/reward to apply
- RemoteEvent per tiny implementation detail
- replicated secrets/server-only configs
- loops scanning all descendants every frame
- scripts sprinkled randomly through Workspace
- adding Knit/Matter/Fusion/etc. because they are popular rather than needed

Use architecture proportional to the game.

## Three-stage module loader (the default for anything past a prototype)

Framework ceremony is a trap: Knit is archived and obscures type inference
across module boundaries. What you actually need is deterministic boot order and
failure isolation, which is ~40 lines.

Stage 1 — **Require + sort**. Never iterate `GetDescendants()` and hope; sort by
an explicit `Priority` so persistence and networking come up before gameplay.

```lua
--!strict
-- ServerScriptService/Server/Bootstrap.server.luau
local ServerScriptService = game:GetService("ServerScriptService")
local Players = game:GetService("Players")

local services = {}
for _, module in ServerScriptService.Server.Services:GetChildren() do
    if module:IsA("ModuleScript") then
        local ok, service = pcall(require, module)
        if ok and type(service) == "table" then
            table.insert(services, service)
        else
            warn(("service %s failed to require: %s"):format(module.Name, tostring(service)))
        end
    end
end
table.sort(services, function(a, b) return (a.Priority or 100) < (b.Priority or 100) end)
```

Stage 2 — **Init then Start, both isolated**. `Init` builds local state and
connects its own remotes; it must not call other services, which is what creates
circular-init deadlocks. `Start` may call others, and one failure must not kill
the boot.

```lua
for _, service in services do
    if service.Init then
        local ok, err = pcall(service.Init, service)
        if not ok then warn(("Init %s: %s"):format(service.Name, tostring(err))) end
    end
end

local ready = Instance.new("BoolValue")
ready.Name = "ServerReady"
ready.Parent = game:GetService("ReplicatedStorage")

for _, service in services do
    if service.Start and not service._failed then
        local ok, err = xpcall(service.Start, debug.traceback, service)
        if not ok then
            service._failed = true
            warn(("Start %s: %s"):format(service.Name, tostring(err)))
        end
    end
end
```

Stage 3 — **player/character hooks, gated on loaded data**. Never run
`SetupPlayer` before the player's profile exists; never leave a per-character
connection alive after respawn.

```lua
local function afterProfile(player: Player, profile)
    for _, service in services do
        if service.SetupPlayer then pcall(service.SetupPlayer, service, player, profile) end
    end
    player.CharacterAdded:Connect(function(character)
        for _, service in services do
            if service.SetupCharacter then
                pcall(service.SetupCharacter, service, player, character)
            end
        end
    end)
end
```

A service is a plain table with `Name`, `Priority`, and any of `Init`, `Start`,
`SetupPlayer`, `SetupCharacter`, `Destroy`. Comment it, keep it under ~300 lines,
and delete its connections in `Destroy`.

## Dependency injection (this is what makes tests possible)

Any module that touches a Roblox singleton cannot be unit-tested outside the
engine. Split every system in two:

- **Pure rule module** in `ReplicatedStorage/Shared` — no `game:GetService`, no
  `Instance`, deterministic input → output. This is what tests exercise.
- **Server service** in `ServerScriptService` — owns instances, remotes and time,
  and *accepts its collaborators as constructor arguments*.

```lua
--!strict
-- Shared/Shared/Economy.luau  (pure: runs in Lune, no engine)
local Economy = {}

export type Inventory = { [string]: number }

function Economy.canAfford(inventory: Inventory, cost: number): boolean
    return (inventory.Coins or 0) >= cost
end

function Economy.priceAfterDiscount(base: number, tier: number): number
    return math.max(0, math.floor(base * (1 - math.min(tier, 5) * 0.05)))
end

return Economy
```

```lua
--!strict
-- Server/Services/PurchaseService.luau  (impure: store injected)
local Economy = require(game:GetService("ReplicatedStorage").Shared.Economy)

local PurchaseService = { Name = "PurchaseService", Priority = 40 }

function PurchaseService.new(store)
    local self = setmetatable({}, { __index = PurchaseService })
    self.store = store          -- { Get = function(player), Save = function(player) }
    return self
end

function PurchaseService:buy(player: Player, itemId: string)
    local profile = self.store:Get(player)
    if not profile then return false, "no profile" end
    local cost = Economy.priceAfterDiscount(100, profile.Data.Tier or 0)
    if not Economy.canAfford(profile.Data.Inventory, cost) then return false, "poor" end
    profile.Data.Inventory.Coins = profile.Data.Inventory.Coins - cost
    self.store:Save(player)
    return true
end

return PurchaseService
```

Now the test can inject a fake store and assert the rule without Studio.
`references/persistence.md` carries the matching fake.
