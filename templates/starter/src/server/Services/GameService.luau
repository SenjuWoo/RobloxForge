--!strict
-- The sample loop, end to end: a client intent arrives, the server checks it, changes state it owns,
-- and publishes the result. Replace the action with your game's; keep the shape.
--
--   client presses        -> Net.event("DoAction"):FireServer()
--   server validates      -> player has a profile, rate limit allows it
--   server changes truth  -> profile.Coins
--   server publishes      -> player:SetAttribute("Coins", n)   (replicates to that player's client)
--   client shows it       -> GetAttributeChangedSignal("Coins")

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Config = require(Shared.Config)
local Net = require(Shared.Net)
local RateLimiter = require(Shared.RateLimiter)
local Rules = require(Shared.Rules)

local DataService = require(script.Parent.DataService)

local GameService = {}

local limiter = RateLimiter.new(Config.ActionsPerSecond, Config.ActionBurst)

local function publish(player: Player)
	local profile = DataService.get(player)
	if not profile then
		return
	end
	player:SetAttribute("Coins", profile.Coins)
	player:SetAttribute("Power", profile.Upgrades.Power or 0)
end

-- Returns whether the action was accepted. Public so a server test can call it directly.
function GameService.doAction(player: Player): boolean
	local profile = DataService.get(player)
	if not profile then
		return false -- still loading, or already gone
	end
	if not limiter:allow(player.UserId, os.clock()) then
		return false -- an autoclicker gets the same income as a fast human
	end
	local reward = Rules.rewardFor(Config.BaseReward, profile.Upgrades.Power or 0)
	profile.Coins = math.min(profile.Coins + reward, Config.MaxCoins)
	DataService.markDirty(player)
	publish(player)
	return true
end

function GameService.buyUpgrade(player: Player, upgradeId: unknown): boolean
	-- Everything after `player` came from the client: check the type before using it.
	if type(upgradeId) ~= "string" then
		return false
	end
	local upgrade = Config.Upgrades[upgradeId]
	local profile = DataService.get(player)
	if not upgrade or not profile then
		return false
	end
	local level = profile.Upgrades[upgradeId] or 0
	if level >= upgrade.MaxLevel then
		return false
	end
	-- The price is computed here, from server-side state. The client never sends a price.
	local cost = Rules.upgradeCost(upgrade.BaseCost, upgrade.Growth, level)
	if not Rules.canAfford(profile.Coins, cost) then
		return false
	end
	profile.Coins -= cost
	profile.Upgrades[upgradeId] = level + 1
	DataService.markDirty(player)
	publish(player)
	return true
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
