# Roblox architecture — where code and authority belong

Roblox is client/server by default. The server is the authority for shared game state. Engine-level
detail (replication, streaming, service catalogue) is in the `roblox-architecture` skill; this file
is the shape to build.

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

Everything in `ReplicatedStorage`, `Workspace`, `StarterGui` and `StarterPlayer` is downloaded by
every client and readable by exploiters. Secrets, drop tables and anti-cheat thresholds stay in
`ServerScriptService` / `ServerStorage`.

## Script types

- `Script`: server execution unless RunContext deliberately says otherwise.
- `LocalScript`: client execution in supported containers.
- `ModuleScript`: reusable code; authority depends on who requires it.

## Small-game baseline

One server Script, one client LocalScript, everything else ModuleScripts - what `rbforge new` writes:

- `ServerScriptService/Server/Main.server.luau`
- `ServerScriptService/Server/Services/...`
- `ReplicatedStorage/Shared/...` (config, pure rules, remote registry)
- `StarterPlayer/StarterPlayerScripts/Client/Main.client.luau`

## Anti-patterns

- one 2,000-line Script owning every system
- authoritative currency in LocalScripts
- client tells server how much damage/reward to apply
- RemoteEvent per tiny implementation detail
- replicated secrets/server-only configs
- loops scanning all descendants every frame
- scripts sprinkled randomly through Workspace
- adding Knit/Matter/Fusion/etc. because they are popular rather than needed
- a server script that rebuilds the whole static map on every start (see "Authored or generated")
- one builder or one HUD module that keeps growing: past ~800 lines it is several systems

Use architecture proportional to the game.

## The loader: explicit lists, isolated steps

Framework ceremony is a trap (Knit is archived and hides types across module boundaries). What a game
needs is a deterministic start order and failure isolation. The scaffold (`rbforge new`) ships this
file as `src/server/Main.server.luau`; read it there, running, rather than retyping it.

```lua
--!strict
-- ServerScriptService/Server/Main.server.luau  (the only Script)
local Players = game:GetService("Players")

local DataService = require(script.Parent.Services.DataService)
local GameService = require(script.Parent.Services.GameService)

type Step = { name: string, fn: () -> () }
type PlayerStep = { name: string, fn: (Player) -> () }

-- Order is the list. No folder scan, no priorities, and the type checker follows every call.
local INIT: { Step } = { { name = "DataService.init", fn = DataService.init } }
local START: { Step } = {
	{ name = "DataService.start", fn = DataService.start },
	{ name = "GameService.start", fn = GameService.start },
}
local PLAYER_ADDED: { PlayerStep } = { { name = "GameService.playerAdded", fn = GameService.playerAdded } }
local PLAYER_REMOVING: { PlayerStep } = {
	{ name = "GameService.playerRemoving", fn = GameService.playerRemoving },
	{ name = "DataService.playerRemoving", fn = DataService.playerRemoving }, -- saves: always last
}

local function run(name: string, fn: (...any) -> ...any, ...: any)
	local ok, err = xpcall(fn, debug.traceback, ...)
	if not ok then
		warn(`[Boot] {name} failed:\n{err}`) -- never swallow: a silent pcall hides the real bug
		workspace:SetAttribute("BootError", name)
	end
end

for _, step in INIT do
	run(step.name, step.fn)
end
for _, step in START do
	run(step.name, step.fn)
end

local function onPlayerAdded(player: Player)
	if not DataService.load(player) then -- gameplay never sees a player without data
		return
	end
	for _, step in PLAYER_ADDED do
		run(step.name, step.fn, player)
	end
end

Players.PlayerAdded:Connect(onPlayerAdded)
Players.PlayerRemoving:Connect(function(player: Player)
	for _, step in PLAYER_REMOVING do
		run(step.name, step.fn, player)
	end
end)
for _, player in Players:GetPlayers() do -- joined before this line ran
	task.spawn(onPlayerAdded, player)
end

workspace:SetAttribute("ServerReady", true) -- tests wait for this, not for task.wait(5)
```

Rules the loader encodes:

- **`init` builds a service's own state and calls nobody.** Cross-service calls in `init` are where
  circular start-up deadlocks come from. `start` may call anything.
- **A failure is logged with a traceback and named in an attribute.** `pcall(fn)` with the result
  thrown away turns a typo into a feature that silently never runs.
- **Existing players and existing characters.** `PlayerAdded` and `CharacterAdded` only fire for
  what arrives *after* the connection. Always handle what is already there:

```lua
local function onCharacter(character: Model) end

player.CharacterAdded:Connect(onCharacter)
if player.Character then
	onCharacter(player.Character)
end
```

- **A readiness attribute, set last.** Tests, loading screens and tools wait on it.
- A service is a table of functions in one ModuleScript. One shape for the whole project - do not mix
  singletons, classes with `.new` and scripts that run on require.

## Everything that starts must end

Most leaks are a connection, a loop or an instance created per character, per round or per open
screen that nothing ends. Give each lifetime one owner (the scaffold's `Shared/Cleaner.luau`, or
Trove/Janitor if the project already uses one):

```lua
local cleaner = Cleaner.new()
cleaner:add(humanoid.Died:Connect(onDied))
cleaner:add(RunService.Heartbeat:Connect(step))
cleaner:add(effectPart)
character.Destroying:Connect(function()
	cleaner:clean()
end)
```

- A table keyed by `Player` is cleared in `PlayerRemoving`. Always.
- A `RunService` connection made inside `CharacterAdded` is disconnected when that character goes.
- `Destroy()` an instance you are done with; `Parent = nil` keeps it and its connections alive.

## Authored or generated

Two ways to get a world, and they are not interchangeable:

| | Authored (default) | Generated at runtime |
|---|---|---|
| Where it lives | built in Edit, saved in the place | a server script builds it on every start |
| Use for | maps, buildings, props, lighting - anything that is the same every session | roguelike levels, player-built structures, per-round arenas |
| Start-up | instant | the build runs before anyone can spawn |
| Editing | by hand in Studio, or by a script run once in Edit | only by changing code |
| Streaming | works with `StreamingEnabled` as designed | needs care: build order, persistence modes |

Build static content **once**: run the builder through `execute_luau` in the Edit datamodel, look at
it, and have the place saved (`save_place`). Keep the builder script in the repo as a tool, not as
start-up code. A server that rebuilds a fixed map of tens of thousands of parts on every boot pays
for it on every boot, cannot be touched up by hand, and forces a spawn gate (`CharacterAutoLoads =
false` until the world exists) that an authored world never needs. `rbforge audit` reports when a
project is built this way, so the choice is a decision instead of an accident.

The same applies to UI: a HUD authored under `StarterGui` (by hand, or by a script run once in Edit)
with a small controller is easier to restyle than thousands of lines of `Instance.new`. If the UI is
built in code, build it as small components - one module per panel - not one builder.

## Dependency injection (this is what makes tests possible)

Any module that touches a Roblox singleton cannot be unit-tested outside the engine. Split every
system in two:

- **Pure rule module** in `ReplicatedStorage/Shared` (or `ServerScriptService` if it is secret) - no
  `game:GetService`, no `Instance`, deterministic input to output. This is what specs exercise.
- **Service** - owns instances, remotes and time, and calls the pure module for every decision.

```lua
--!strict
-- Shared/Economy.luau  (pure: runs in Lune, no engine)
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

The service reads state, asks the pure module, applies the answer. The scaffold's `Rules.luau`,
`RateLimiter.luau` and `ProfileSchema.luau` are this pattern with their specs; `persistence.md`
carries a store fake for services that take their store as an argument.
