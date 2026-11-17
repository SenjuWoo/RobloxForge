--!strict
-- Pure rules: no game, no Instance, no service. Everything here runs in Lune in milliseconds
-- (tests/Rules.spec.luau), so put every formula the game depends on in a module like this one.

local Rules = {}

-- Coins granted by one action at a given upgrade level.
function Rules.rewardFor(baseReward: number, powerLevel: number): number
	return math.max(1, math.floor(baseReward * (1 + math.max(0, powerLevel))))
end

-- Price of the next level of an upgrade. Grows geometrically; never below 1.
function Rules.upgradeCost(baseCost: number, growth: number, currentLevel: number): number
	return math.max(1, math.floor(baseCost * growth ^ math.max(0, currentLevel)))
end

function Rules.canAfford(coins: number, cost: number): boolean
	return coins == coins and cost == cost and coins >= cost -- x == x rejects NaN
end

return Rules
