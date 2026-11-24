--!strict
-- Live server test: runs inside a Play session and exercises the real modules the game loaded.
--
--   rbforge servertest tests/Starter.server.luau --ready workspace.ServerReady=true
--
-- It reports through an attribute; a test that only returns a value reports nothing.
local Players = game:GetService("Players")
local ServerScriptService = game:GetService("ServerScriptService")

local function report(ok: boolean, detail: string)
	script:SetAttribute("RbforgeTest", (if ok then "PASS " else "FAIL ") .. detail)
end

local ok, err = pcall(function()
	local services = (ServerScriptService :: any).Server.Services
	local GameService = require(services.GameService) :: any
	local DataService = require(services.DataService) :: any

	local deadline = os.clock() + 20
	local player = Players:GetPlayers()[1]
	while (not player or player:GetAttribute("Ready") ~= true) and os.clock() < deadline do
		task.wait(0.2)
		player = Players:GetPlayers()[1]
	end
	assert(player and player:GetAttribute("Ready") == true, "no player became Ready within 20 s")

	local profile = DataService.get(player)
	assert(profile, "a Ready player must have a profile")
	assert(player:GetAttribute("Coins") == profile.Coins, "the Coins attribute must mirror the profile")

	task.wait(1) -- let the rate limiter's bucket refill fully
	local before = profile.Coins
	assert(GameService.doAction(player) == true, "one action must be accepted")
	assert(profile.Coins > before, "an accepted action must add coins")
	assert(player:GetAttribute("Coins") == profile.Coins, "the attribute must follow the profile")

	local accepted = 0
	for _ = 1, 200 do
		if GameService.doAction(player) then
			accepted += 1
		end
	end
	assert(accepted < 20, `200 instant requests must be rate limited, {accepted} were accepted`)

	local refusedOk, refusedWhy = GameService.buyUpgrade(player, "NoSuchUpgrade")
	assert(
		refusedOk == false and refusedWhy == "unknown upgrade",
		`an unknown upgrade id is refused by name ({refusedWhy})`
	)
	assert(
		player:GetAttribute("LastRefusal") == "BuyUpgrade: unknown upgrade",
		"in Studio the refusal reason is readable on the player"
	)
	assert(GameService.buyUpgrade(player, 12345) == false, "a non-string upgrade id is refused")
	assert(GameService.buyUpgrade(player, { "Power" }) == false, "a table upgrade id is refused")

	profile.Coins = 0
	local poorOk, poorWhy = GameService.buyUpgrade(player, "Power")
	assert(poorOk == false and poorWhy == "cannot afford", `an upgrade is refused without the coins ({poorWhy})`)
	profile.Coins = 25
	local level = profile.Upgrades.Power or 0
	assert(GameService.buyUpgrade(player, "Power") == true, "an affordable upgrade is bought")
	assert(profile.Upgrades.Power == level + 1, "the level rises by exactly one")
	assert(profile.Coins == 0, "the price is deducted exactly once")
end)

report(ok, if ok then "starter loop: action, rate limit, validation, purchase" else tostring(err))
