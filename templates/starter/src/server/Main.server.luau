--!strict
-- Server entry point: the only Script. It starts every system in a fixed order and owns the player
-- lifecycle, so "what runs when" is answered by reading this one file.
--
-- A service is a ModuleScript in Services/ that returns a table of functions. To add a system:
-- write the module, require it here, and add its functions to the lists below.
--   INIT            build own state; must not call another service
--   START           connect remotes and loops; every service is initialised by now
--   PLAYER_ADDED    runs once the player's profile is loaded
--   PLAYER_REMOVING runs while the profile is still readable; DataService goes last

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Net = require(ReplicatedStorage:WaitForChild("Shared").Net)

-- Remotes exist before any service is required, so a service may look them up at any point.
Net.setup()

local DataService = require(script.Parent.Services.DataService)
local GameService = require(script.Parent.Services.GameService)

type Step = { name: string, fn: () -> () }
type PlayerStep = { name: string, fn: (Player) -> () }

-- Explicit lists: no folder scan and no priorities to guess, and every call is one the type checker
-- can follow. Order matters and is visible here.
local INIT: { Step } = {
	{ name = "DataService.init", fn = DataService.init },
}
local START: { Step } = {
	{ name = "DataService.start", fn = DataService.start },
	{ name = "GameService.start", fn = GameService.start },
}
local PLAYER_ADDED: { PlayerStep } = {
	{ name = "GameService.playerAdded", fn = GameService.playerAdded },
}
local PLAYER_REMOVING: { PlayerStep } = {
	{ name = "GameService.playerRemoving", fn = GameService.playerRemoving },
	{ name = "DataService.playerRemoving", fn = DataService.playerRemoving }, -- saves: always last
}

-- One failing step must not take the other systems down, and it must say so loudly.
local function run(name: string, fn: (...any) -> ...any, ...: any)
	local ok, err = xpcall(fn, debug.traceback, ...)
	if not ok then
		warn(`[Boot] {name} failed:\n{err}`)
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
	-- Nothing gameplay-related sees the player until their data exists.
	if not DataService.load(player) then
		return
	end
	for _, step in PLAYER_ADDED do
		run(step.name, step.fn, player)
	end
	player:SetAttribute("Ready", true)
end

Players.PlayerAdded:Connect(onPlayerAdded)
Players.PlayerRemoving:Connect(function(player: Player)
	for _, step in PLAYER_REMOVING do
		run(step.name, step.fn, player)
	end
end)
-- Players who joined while the modules were loading: PlayerAdded already fired for them.
for _, player in Players:GetPlayers() do
	task.spawn(onPlayerAdded, player)
end

-- Tests and tools wait for this instead of guessing with task.wait.
workspace:SetAttribute("ServerReady", true)
