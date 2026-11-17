--!strict
-- Saved data is input: whatever comes out of the data store must become a valid profile.
local ProfileSchema = require("../src/server/ProfileSchema")

local fresh = ProfileSchema.reconcile(nil)
assert(fresh.Coins == 0 and fresh.Schema == ProfileSchema.CURRENT, "nil becomes a fresh profile")
assert(next(fresh.Upgrades) == nil, "a fresh profile has no upgrades")

assert(ProfileSchema.reconcile("corrupt").Coins == 0, "a non-table becomes a fresh profile")
assert(ProfileSchema.reconcile({ Coins = 120.9 }).Coins == 120, "coins are whole numbers")
assert(ProfileSchema.reconcile({ Coins = -5 }).Coins == 0, "coins are never negative")
assert(ProfileSchema.reconcile({ Coins = "lots" }).Coins == 0, "a wrong type falls back to the default")
assert(ProfileSchema.reconcile({ Coins = 0 / 0 }).Coins == 0, "NaN never reaches gameplay")
assert(ProfileSchema.reconcile({ Coins = math.huge }).Coins == 0, "infinity never reaches gameplay")
assert(ProfileSchema.reconcile({ Coins = 1e30 }).Coins == 1e12, "coins are clamped to the cap")

local kept = ProfileSchema.reconcile({ Coins = 7, Upgrades = { Power = 3, [5] = 2, Bad = "x" }, Admin = true })
assert(kept.Coins == 7 and kept.Upgrades.Power == 3, "valid fields survive")
assert(kept.Upgrades.Bad == 0, "a non-number level becomes 0")
assert((kept.Upgrades :: any)[5] == nil, "a non-string upgrade id is dropped")
assert((kept :: any).Admin == nil, "unknown fields are dropped")

-- reconcile returns a copy: saving must never hand the live table to the data store.
local live = ProfileSchema.fresh()
live.Upgrades.Power = 2
local copy = ProfileSchema.reconcile(live)
copy.Upgrades.Power = 99
assert(live.Upgrades.Power == 2, "reconcile must not alias the input")

print("ProfileSchema.spec: ok")
