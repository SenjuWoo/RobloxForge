--!strict
-- What a saved player looks like, and how anything read from the data store becomes that shape.
-- Pure (no game, no service) so tests/ProfileSchema.spec.luau proves it without Studio.
--
-- Adding a field: add it to Profile and fresh(), read it in reconcile() with a type check.
-- Changing the meaning of a field: bump CURRENT and add a step to migrate(). Never edit an old step.

local ProfileSchema = {}

export type Profile = {
	Schema: number,
	Coins: number,
	Upgrades: { [string]: number },
}

ProfileSchema.CURRENT = 1

local MAX_COINS = 1e12
local MAX_LEVEL = 1000

function ProfileSchema.fresh(): Profile
	return { Schema = ProfileSchema.CURRENT, Coins = 0, Upgrades = {} }
end

-- A finite, whole, clamped number - or the fallback. Saved data can hold anything: an old version,
-- a hand-edited value, NaN from a bug. None of it may reach gameplay unchecked.
local function whole(value: any, low: number, high: number, fallback: number): number
	if type(value) ~= "number" or value ~= value or math.abs(value) == math.huge then
		return fallback
	end
	return math.clamp(math.floor(value), low, high)
end

local function migrate(raw: { [any]: any }): { [any]: any }
	-- if raw.Schema == 1 then raw.NewField = default; raw.Schema = 2 end
	return raw
end

-- Any value in, a valid Profile out. Unknown fields are dropped; missing ones take the default.
function ProfileSchema.reconcile(raw: any): Profile
	local profile = ProfileSchema.fresh()
	if type(raw) ~= "table" then
		return profile
	end
	local data = migrate(raw)
	profile.Coins = whole(data.Coins, 0, MAX_COINS, 0)
	if type(data.Upgrades) == "table" then
		for id, level in data.Upgrades do
			if type(id) == "string" and #id <= 40 then
				profile.Upgrades[id] = whole(level, 0, MAX_LEVEL, 0)
			end
		end
	end
	return profile
end

return ProfileSchema
