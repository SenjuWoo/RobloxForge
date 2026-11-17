--!strict
-- Offline unit spec: `rbforge check` runs every tests/*.spec.luau through Lune, no Studio needed.
-- One spec per pure module. A spec that cannot fail proves nothing: assert exact values.
local Rules = require("../src/shared/Rules")

assert(Rules.rewardFor(1, 0) == 1, "base reward at level 0")
assert(Rules.rewardFor(1, 3) == 4, "each power level adds one base reward")
assert(Rules.rewardFor(1, -5) == 1, "a negative level must not reduce the reward")

assert(Rules.upgradeCost(25, 1.35, 0) == 25, "first level costs the base price")
assert(Rules.upgradeCost(25, 1.35, 1) == 33, "second level: floor(25 * 1.35)")
assert(Rules.upgradeCost(25, 1.35, 10) > Rules.upgradeCost(25, 1.35, 9), "price must rise every level")
assert(Rules.upgradeCost(0, 1.35, 0) == 1, "price never drops below 1")

assert(Rules.canAfford(25, 25) == true, "exact coins is enough")
assert(Rules.canAfford(24, 25) == false, "one short is not enough")
assert(Rules.canAfford(0 / 0, 25) == false, "NaN coins never afford anything")
assert(Rules.canAfford(100, 0 / 0) == false, "a NaN price is never affordable")

print("Rules.spec: ok")
