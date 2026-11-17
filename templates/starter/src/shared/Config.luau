--!strict
-- Shared tuning. Numbers live here so a balance change never touches logic.
-- Both sides may read this; nothing in it is secret. Server-only values belong in src/server.

export type Upgrade = { BaseCost: number, Growth: number, MaxLevel: number }

local Config = {
	Genre = "{genre}",
	Version = "0.1.0",

	-- The sample loop: an action earns coins, an upgrade makes the action earn more.
	BaseReward = 1,
	MaxCoins = 1e12,
	ActionsPerSecond = 8, -- sustained rate the server accepts from one player
	ActionBurst = 4, -- extra requests allowed in a burst before the rate applies

	Upgrades = {
		Power = { BaseCost = 25, Growth = 1.35, MaxLevel = 50 },
	} :: { [string]: Upgrade },
}

return Config
