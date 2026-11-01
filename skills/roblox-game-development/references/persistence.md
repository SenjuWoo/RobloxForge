# Roblox persistence

Use persistence only when the game loop actually needs it.

## Core rules

- `DataStoreService` is server-side.
- Treat load/save failures as normal operational events.
- Use `pcall`/error-aware retry policy.
- Prefer `UpdateAsync` when multiple servers may modify the same logical value.
- Keep a versioned schema for meaningful player data.
- Validate/sanitize before saving.
- Do not persist arbitrary client-provided tables.
- Do not write on every coin tick.

## Studio safety

Roblox documents an important trap: Studio API access can touch the same data as
the live experience. Do **not** casually enable Studio DataStore access against a
production universe. Use a separate test version/universe or deliberate test keys.

## Suggested data shape

Keep one player profile with explicit version and bounded fields:

- schema version
- progression
- inventory identifiers/counts
- settings
- timestamps needed for offline/time systems

Avoid serializing transient Instances or giant nested runtime objects.

## Save strategy

Typical triggers:
- periodic checkpoint at a reasonable interval,
- important irreversible transaction after server validation,
- `PlayerRemoving`,
- server shutdown via `BindToClose` with bounded time.

Never promise a save succeeded until the call actually succeeded.

## Migrations

When schema changes:
1. read old version,
2. validate,
3. migrate in memory,
4. write new version safely,
5. keep migration deterministic and testable.

## Temporary/global state

For frequently changing temporary cross-server state, evaluate MemoryStore rather
than abusing persistent DataStores. Verify current quotas/semantics from official docs.

## Third-party profile libraries

Do not hardcode one community library as eternal truth. If a project already uses
a profile/session-locking library, follow it. Otherwise research current maintenance
and tradeoffs before introducing a dependency.

### The default: ProfileStore, not a hand-written wrapper

Writing session locking yourself is how item duplication happens. `GetAsync`
caches for seconds, `SetAsync` overwrites blindly, and a crashed server can hold
a key forever unless you implement lease stealing. `ProfileStore` (loleris)
already does all of it and is the maintained successor to the archived
ProfileService.

What it buys you, concretely:
- `UpdateAsync`-based session locks with 30-minute lease stealing.
- Auto-save every **300s** by default (ProfileService used 30s) — roughly an
  order of magnitude fewer DataStore calls.
- `MessagingService`-backed lock conflict resolution: the server holding a lock is
  told immediately when another server wants it.
- `ProfileStore:MessageAsync(key, message)` replaces the old `GlobalUpdates` for
  cross-server delivery (gifting, offline mail).
- `profile.LastSavedData` plus `Profile.OnSave` / `OnLastSave` / `OnAfterSave`.
- Full Luau types.

```lua
--!strict
-- Server/Services/DataService.luau  (Priority 10 - everyone else depends on it)
local Players = game:GetService("Players")
local ProfileStore = require(script.Parent.Parent.Packages.ProfileStore)

local TEMPLATE = {
    Schema = 1,
    Coins = 0,
    Tier = 0,
    Inventory = { Coins = 0 } :: { [string]: number },
}

local PlayerStore = ProfileStore.New("PlayerData", TEMPLATE)
local profiles: { [Player]: any } = {}

local DataService = { Name = "DataService", Priority = 10 }

function DataService:Get(player: Player)
    return profiles[player]
end

function DataService:Save(player: Player)
    local profile = profiles[player]
    if profile then profile:Save() end
end

function DataService:Init()
    local function onPlayerAdded(player: Player)
        -- Cancel aborts the wait if the player leaves before the profile loads.
        local profile = PlayerStore:StartSessionAsync(tostring(player.UserId), {
            Cancel = function() return player.Parent ~= Players end,
        })
        if not profile then return end

        profile:AddUserId(player.UserId)   -- GDPR / right-to-erasure tracking
        profile:Reconcile()                -- fills fields missing from TEMPLATE
        profile.OnSessionEnd = function()
            profiles[player] = nil
            player:Kick("Data session ended - please rejoin")
        end
        profile:ListenToRelease(function()
            profiles[player] = nil
            player:Kick("Your data was loaded on another server")
        end)

        if player:IsDescendantOf(Players) then
            profiles[player] = profile
        else
            profile:EndSession()           -- joined and left before we finished
        end
    end

    for _, player in Players:GetPlayers() do task.spawn(onPlayerAdded, player) end
    Players.PlayerAdded:Connect(onPlayerAdded)
    Players.PlayerRemoving:Connect(function(player)
        local profile = profiles[player]
        if profile then profile:EndSession() end   -- releases the lock immediately
    end)
end

return DataService
```

Rules that matter more than the library choice:

- **Never trust `profile.Data` before `Reconcile()`.** A field added to TEMPLATE
  does not exist in old saves until reconciled.
- **Migrations run on load, in memory, keyed by `Schema`.** Bump `Schema`, add a
  step, never rewrite history.
- **`ProfileStore:MessageAsync` needs the key, not the player.** It works while
  the target is offline; that is the point.
- **Studio must not write production data.** Test with a separate universe or a
  distinct store name (`"PlayerData_TEST"`); this is the trap that silently
  corrupts live saves during a playtest.

### The test double (this is the point of the DI split)

Because the service takes its store as an argument, the whole purchase path runs
in Lune with no engine:

```lua
--!strict
-- tests/StoreFake.luau
local StoreFake = {}
StoreFake.__index = StoreFake

function StoreFake.new(template)
    return setmetatable({ data = {} , template = template }, StoreFake)
end

function StoreFake:Get(player)
    self.data[player] = self.data[player] or { Data = table.clone(self.template) }
    return self.data[player]
end

function StoreFake:Save(_player) end

return StoreFake
```

```lua
-- tests/economy.spec.luau   ->  lune run tests/economy.spec.luau
local Economy = require("../src/shared/Economy")

assert(Economy.canAfford({ Coins = 10 }, 5) == true, "affordable purchase rejected")
assert(Economy.canAfford({ Coins = 4 }, 5) == false, "unaffordable purchase allowed")
assert(Economy.priceAfterDiscount(100, 3) == 85, "discount math drifted")

print("economy.spec: 3 assertions passed")
```

`rbforge check` runs every `tests/*.spec.luau` through `lune` when both exist.
