--!strict
-- Player data: load on join, save on leave, on a timer and on shutdown.
--
-- The rule this file exists to keep: A FAILED READ IS NOT A NEW PLAYER. If the data store is down
-- and the game hands out a default profile, that default is saved over the real one when the player
-- leaves. So a profile exists only after a read succeeded, and nothing is ever written for a player
-- whose read failed - they are asked to rejoin instead.
--
-- Scope: correct for one server holding a player at a time. It has no cross-server session lock, so
-- before the game has trading, server hopping with valuable items or several places, move to
-- ProfileStore (see the roblox-data-stores skill). The API below is small on purpose so that swap
-- stays inside this file.

local DataStoreService = game:GetService("DataStoreService")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local ProfileSchema = require(script.Parent.Parent.ProfileSchema)

type Profile = ProfileSchema.Profile
type Entry = { profile: Profile, dirty: boolean, saving: boolean }

-- Studio and the live game never share a store: a play test must not be able to touch real saves.
local STORE_NAME = if RunService:IsStudio() then "PlayerData_Studio_v1" else "PlayerData_v1"
local LOAD_ATTEMPTS = 4
local AUTOSAVE_SECONDS = 120
local SHUTDOWN_BUDGET = 25 -- BindToClose gives 30 s in total

local DataService = {}

local entries: { [Player]: Entry } = {}
local store: DataStore? = nil
-- False only in Studio without API access (an unpublished place, or the setting off): the session
-- then runs in memory and writes nothing. In a live server a broken store never falls back to this.
local persistent = false

local function keyFor(player: Player): string
	return "Player_" .. player.UserId -- UserId, never Name: names change
end

local function readWithRetry(player: Player): (boolean, any)
	local dataStore = store :: DataStore
	for attempt = 1, LOAD_ATTEMPTS do
		local ok, result = pcall(function()
			return dataStore:GetAsync(keyFor(player))
		end)
		if ok then
			return true, result -- nil here means a genuinely new player
		end
		warn(`[Data] read failed for {player.UserId} (attempt {attempt}/{LOAD_ATTEMPTS}): {result}`)
		if attempt < LOAD_ATTEMPTS then
			task.wait(2 ^ attempt)
		end
		if player.Parent ~= Players then
			return false, nil
		end
	end
	return false, nil
end

-- Yields. True when the player now has a profile; false when they were kicked or left.
function DataService.load(player: Player): boolean
	if entries[player] then
		return true
	end
	if not persistent then
		entries[player] = { profile = ProfileSchema.fresh(), dirty = false, saving = false }
		return true
	end
	local ok, raw = readWithRetry(player)
	if not ok then
		if player.Parent == Players then
			player:Kick("Your data could not be loaded. Nothing was lost - please rejoin.")
		end
		return false
	end
	if player.Parent ~= Players then
		return false
	end
	entries[player] = { profile = ProfileSchema.reconcile(raw), dirty = false, saving = false }
	return true
end

-- The live profile, or nil while it is loading. Every caller must handle nil.
function DataService.get(player: Player): Profile?
	local entry = entries[player]
	return if entry then entry.profile else nil
end

-- Call after changing a profile. Saving is batched; this never yields.
function DataService.markDirty(player: Player)
	local entry = entries[player]
	if entry then
		entry.dirty = true
	end
end

local function save(player: Player): boolean
	local entry = entries[player]
	if not entry or not persistent then
		return false
	end
	if not entry.dirty or entry.saving then
		return true
	end
	entry.saving = true
	entry.dirty = false
	local snapshot = ProfileSchema.reconcile(entry.profile) -- a sanitized copy, not the live table
	local dataStore = store :: DataStore
	local ok, err = pcall(function()
		dataStore:UpdateAsync(keyFor(player), function()
			return snapshot, { player.UserId }
		end)
	end)
	entry.saving = false
	if not ok then
		entry.dirty = true -- try again on the next pass; never report a save that did not happen
		warn(`[Data] save failed for {player.UserId}: {err}`)
	end
	return ok
end

-- Main calls this last in PLAYER_REMOVING, after every other service has seen the player leave, so
-- they can still read the profile and their last changes are in the final save.
function DataService.playerRemoving(player: Player)
	save(player)
	entries[player] = nil
end

function DataService.init()
	local ok, result = pcall(function()
		local dataStore = DataStoreService:GetDataStore(STORE_NAME)
		dataStore:GetAsync("__probe") -- throws when the place has no data store access
		return dataStore
	end)
	if ok then
		store = result
		persistent = true
	elseif RunService:IsStudio() then
		warn("[Data] no data store access in this Studio session: progress is kept in memory only.")
	else
		-- Live server: keep the store and let each load retry and kick. Never play on defaults.
		store = DataStoreService:GetDataStore(STORE_NAME)
		persistent = true
		warn(`[Data] data store probe failed: {result}`)
	end
end

function DataService.start()
	task.spawn(function()
		while true do
			task.wait(AUTOSAVE_SECONDS)
			for player in entries do
				task.spawn(save, player)
				task.wait(0.2) -- spread the writes instead of bursting the request budget
			end
		end
	end)

	-- Shutdown kicks everyone and exits; without this the last PlayerRemoving saves are cut off.
	game:BindToClose(function()
		local pending = 0
		for player in entries do
			pending += 1
			task.spawn(function()
				save(player)
				pending -= 1
			end)
		end
		local deadline = os.clock() + SHUTDOWN_BUDGET
		while pending > 0 and os.clock() < deadline do
			task.wait(0.1)
		end
	end)
end

return DataService
