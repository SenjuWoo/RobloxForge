# Roblox persistence

Use persistence only when the game loop actually needs it. API detail, quotas and the full
ProfileStore walkthrough live in the `roblox-data-stores` skill; this file is the rules that decide
whether players keep their data.

## The rule that matters most: a failed read is not a new player

```lua
-- WRONG: this is how games wipe inventories.
local ok, data = pcall(function() return store:GetAsync(key) end)
local profile = (ok and data) or DEFAULT      -- outage -> defaults
-- ...player leaves -> the defaults are saved over the real data
```

`GetAsync` returning `nil` means "no data yet". `pcall` returning `false` means "we do not know".
They must end differently:

- read succeeded, value `nil` -> new player, use the template;
- read failed -> retry with backoff; if it still fails, **kick with a rejoin message** and never
  create a profile for that player;
- never save for a player whose load did not succeed.

`rbforge review --kind traps` flags the pattern as `T038`, and `rbforge audit` puts it first. The
scaffold's `DataService.luau` is a small correct implementation to copy from.

## Core rules

- `DataStoreService` is server-side only.
- Every data store call can throw (throttling, outage): `pcall`, bounded retry, and a decision for the
  failure case that does not invent data.
- Key by `player.UserId`, never by name.
- `UpdateAsync` over `SetAsync` for anything two servers could write.
- Save on a timer, on `PlayerRemoving`, and in `game:BindToClose` - shutdown exits before
  `PlayerRemoving` saves finish unless `BindToClose` waits for them.
- Do not write on every coin tick. Mark dirty, save in batches.
- Sanitize on the way in **and** on the way out: saved data is input. Type, range, finite, whole.
- Do not persist arbitrary client-provided tables, Instances, or runtime objects.
- Never tell the player a save succeeded until the call returned without error.

## Studio safety

Studio with API access enabled talks to the **same** data stores as the live game. Use a different
store name in Studio (`RunService:IsStudio()`), or a separate test universe. Without API access (or in
an unpublished place) data store calls throw: detect that once and run the session in memory - in
Studio only. A live server whose store is failing must never fall back to in-memory defaults.

## Data shape

One profile per player, versioned, with bounded fields: schema version, progression, inventory
ids/counts, settings, timestamps needed for offline systems. Keep the template, the reconcile function
and the migrations in one pure module so they are unit tested offline.

Migrations run on load, in memory, keyed by the schema version: read old, validate, migrate, then the
next save writes the new shape. Bump the version and add a step; never edit an old step.

## Temporary and cross-server state

Frequently changing cross-server state (matchmaking queues, live leaderboards, server lists) belongs
in MemoryStore, not a persistent data store. Check current quotas in the official docs
(`rb_docs_search "MemoryStore"`).

## Session locking: ProfileStore

One server holding a player's data at a time is the assumption every simple save loop makes. It
breaks with fast server hopping, teleports between places, and trading - that is where item
duplication comes from. `ProfileStore` (MadStudioRoblox/ProfileStore, the successor to the archived
ProfileService) implements the session lock. Use it once the game has anything worth duplicating; do
not hand-write a lock.

API checked against the upstream source (`ProfileStore.luau`, commit `45c9847`):

- `ProfileStore.New(storeName, template)` -> store; `store.Mock` is an in-memory twin for tests.
- `store:StartSessionAsync(key, { Cancel = fn })` -> profile or `nil`.
- `profile.Data`, `profile:Reconcile()`, `profile:AddUserId(id)`, `profile:Save()`,
  `profile:EndSession()`, `profile:IsActive()`.
- **Signals, connected with `:Connect`:** `profile.OnSessionEnd`, `profile.OnSave`,
  `profile.OnLastSave`, `profile.OnAfterSave`. There is no `ListenToRelease` - that was
  ProfileService.
- `store:MessageAsync(key, message)` delivers to a profile that may be offline (gifts, mail);
  `profile:MessageHandler(fn)` receives.
- Defaults: auto-save every 300 s; a session conflict is resolved by the waiting server taking the
  session after 40 s; a session with no updates for 630 s is treated as a crashed server.

```lua
--!strict
-- ServerScriptService/Server/Services/DataService.luau
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ProfileStore = require(script.Parent.Parent.Packages.ProfileStore)

local TEMPLATE = {
	Schema = 1,
	Coins = 0,
	Upgrades = {} :: { [string]: number },
}

local STORE_NAME = if RunService:IsStudio() then "PlayerData_Studio" else "PlayerData"
local PlayerStore = ProfileStore.New(STORE_NAME, TEMPLATE)
local profiles: { [Player]: any } = {}

local DataService = {}

function DataService.get(player: Player)
	return profiles[player]
end

local function onPlayerAdded(player: Player)
	-- Cancel stops the wait if the player leaves before the session starts.
	local profile = PlayerStore:StartSessionAsync(`Player_{player.UserId}`, {
		Cancel = function()
			return player.Parent ~= Players
		end,
	})
	if not profile then
		-- No session: not a new player. Do not hand out the template.
		player:Kick("Your data could not be loaded. Please rejoin.")
		return
	end

	profile:AddUserId(player.UserId) -- right-to-erasure requests find the key
	profile:Reconcile() -- fills fields added to TEMPLATE since this profile was saved

	profile.OnSessionEnd:Connect(function()
		profiles[player] = nil
		player:Kick("Your data session ended. Please rejoin.")
	end)

	if player.Parent == Players then
		profiles[player] = profile
	else
		profile:EndSession() -- left while loading
	end
end

function DataService.start()
	for _, player in Players:GetPlayers() do
		task.spawn(onPlayerAdded, player)
	end
	Players.PlayerAdded:Connect(onPlayerAdded)
	Players.PlayerRemoving:Connect(function(player: Player)
		local profile = profiles[player]
		if profile then
			profile:EndSession() -- saves and releases the lock
		end
	end)
end

return DataService
```

Rules that matter more than the library:

- **Never read `profile.Data` before `Reconcile()`.** A field added to the template does not exist
  in old saves until then.
- **`MessageAsync` takes the key, not the player.** It works while the target is offline.
- ProfileStore handles `BindToClose` itself; do not add a second shutdown save around it.

## The test double

A service that takes its store as an argument runs in Lune with no engine:

```lua
--!strict
-- tests/StoreFake.luau
local StoreFake = {}
StoreFake.__index = StoreFake

function StoreFake.new(template)
	return setmetatable({ data = {}, template = template }, StoreFake)
end

function StoreFake:get(player)
	self.data[player] = self.data[player] or { Data = table.clone(self.template) }
	return self.data[player]
end

return StoreFake
```

```lua
-- tests/economy.spec.luau   ->  lune run tests/economy.spec.luau
local Economy = require("../src/shared/Economy")

assert(Economy.canAfford({ Coins = 10 }, 5) == true, "affordable purchase rejected")
assert(Economy.canAfford({ Coins = 4 }, 5) == false, "unaffordable purchase allowed")

print("economy.spec: ok")
```

`rbforge check` runs every `tests/*.spec.luau` through Lune. What Lune cannot prove - a real read
failing, two sessions competing, save on shutdown - needs a Studio test against a **test** store with
an injected failure, and a live rejoin. Say which of those ran.
