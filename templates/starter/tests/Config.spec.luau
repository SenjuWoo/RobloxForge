--!strict
-- Config is data, and data has rules too: a typo here is a broken economy with no error.
local Config = require("../src/shared/Config")

assert(Config.Genre == "{genre}", "Config.Genre must match the scaffolded genre")
assert(string.match(Config.Version, "^%d+%.%d+%.%d+$") ~= nil, "Config.Version must be semver")
assert(Config.ActionsPerSecond > 0 and Config.ActionBurst >= 0, "rate limit must allow play")
for id, upgrade in Config.Upgrades do
	assert(upgrade.BaseCost >= 1, `{id}: BaseCost must be at least 1`)
	assert(upgrade.Growth > 1, `{id}: Growth must be above 1 or the price never rises`)
	assert(upgrade.MaxLevel >= 1, `{id}: MaxLevel must be at least 1`)
end

print("Config.spec: ok")
