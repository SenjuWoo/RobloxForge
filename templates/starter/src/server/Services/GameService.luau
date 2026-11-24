--!strict
-- The sample loop, end to end: a client intent arrives, the server checks it, changes state it owns,
-- and publishes the result. Replace the action with your game's; keep the shape.
--
--   client presses        -> Net.event("DoAction"):FireServer()
--   server validates      -> player has a profile, rate limit allows it
--   server changes truth  -> profile.Coins
--   server publishes      -> player:SetAttribute("Coins", n)   (replicates to that player's client)
--   client shows it       -> GetAttributeChangedSignal("Coins")
--
-- Every refusal names its reason. A live test reads it from the return value; in Studio it is also
-- published as the player's `LastRefusal` attribute, so "I pressed it and nothing happened" has an
-- answer without a second playtest. Live servers stay quiet.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Config = require(Shared.Config)
local Net = require(Shared.Net)
local RateLimiter = require(Shared.RateLimiter)
local Rules = require(Shared.Rules)

local DataService = require(script.Parent.DataService)

local GameService = {}

local limiter = RateLimiter.new(Config.ActionsPerSecond, Config.ActionBurst)
local inStudio = RunService:IsStudio()

local function publish(player: Player)
	local profile = DataService.get(player)
	if not profile then
		return
	end
	player:SetAttribute("Coins", profile.Coins)
	player:SetAttribute("Power", profile.Upgrades.Power or 0)
end

-- `false, why` for a refused request; in Studio the reason is also left on the player.
local function refuse(player: Player, action: string, why: string): (boolean, string?)
	if inStudio then
		player:SetAttribute("LastRefusal", `{action}: {why}`)
	end
	return false, why
end

-- Returns whether the action was accepted, and why not. Public so a server test can call it directly.
function GameService.doAction(player: Player): (boolean, string?)
	local profile = DataService.get(player)
	if not profile then
		return refuse(player, "DoAction", "no profile") -- still loading, or already gone
	end
	if not limiter:allow(player.UserId, os.clock()) then
		return refuse(player, "DoAction", "rate limited") -- an autoclicker earns what a fast human does
	end
	local reward = Rules.rewardFor(Config.BaseReward, profile.Upgrades.Power or 0)
	profile.Coins = math.min(profile.Coins + reward, Config.MaxCoins)
	DataService.markDirty(player)
	publish(player)
	return true, nil
end

function GameService.buyUpgrade(player: Player, upgradeId: unknown): (boolean, string?)
	-- Everything after `player` came from the client: check the type before using it.
	if type(upgradeId) ~= "string" then
		return refuse(player, "BuyUpgrade", "upgrade id is not a string")
	end
	local upgrade = Config.Upgrades[upgradeId]
	if not upgrade then
		return refuse(player, "BuyUpgrade", "unknown upgrade")
	end
	local profile = DataService.get(player)
	if not profile then
		return refuse(player, "BuyUpgrade", "no profile")
	end
	local level = profile.Upgrades[upgradeId] or 0
	if level >= upgrade.MaxLevel then
		return refuse(player, "BuyUpgrade", "already at max level")
	end
	-- The price is computed here, from server-side state. The client never sends a price.
	local cost = Rules.upgradeCost(upgrade.BaseCost, upgrade.Growth, level)
	if not Rules.canAfford(profile.Coins, cost) then
		return refuse(player, "BuyUpgrade", "cannot afford")
	end
	profile.Coins -= cost
	profile.Upgrades[upgradeId] = level + 1
	DataService.markDirty(player)
	publish(player)
	return true, nil
end

function GameService.playerAdded(player: Player)
	publish(player)
end

function GameService.playerRemoving(player: Player)
	limiter:forget(player.UserId)
end

function GameService.start()
	Net.event("DoAction").OnServerEvent:Connect(function(player: Player)
		GameService.doAction(player)
	end)
	Net.event("BuyUpgrade").OnServerEvent:Connect(function(player: Player, upgradeId: unknown)
		GameService.buyUpgrade(player, upgradeId)
	end)
end

return GameService
