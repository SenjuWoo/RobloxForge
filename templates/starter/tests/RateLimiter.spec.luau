--!strict
local RateLimiter = require("../src/shared/RateLimiter")

-- 2 per second with a burst of 3 on top: capacity 4.
local limiter = RateLimiter.new(2, 3)

local accepted = 0
for _ = 1, 20 do
	if limiter:allow(1, 100) then -- twenty requests in the same instant
		accepted += 1
	end
end
assert(accepted == 4, `a burst is capped at capacity, got {accepted}`)

assert(limiter:allow(1, 100.4) == false, "0.4 s refills 0.8 of a token: still refused")
assert(limiter:allow(1, 100.6) == true, "0.6 s refills 1.2 tokens: one request passes")
assert(limiter:allow(1, 100.6) == false, "and only one")

assert(limiter:allow(2, 100) == true, "another key has its own bucket")

-- A clock that runs backwards (a reset, a bug) must not mint tokens.
local skewed = RateLimiter.new(100, 0)
assert(skewed:allow(9, 50) == true, "first request passes")
assert(skewed:allow(9, 10) == false, "time going backwards refills nothing")

limiter:forget(1)
assert(limiter:allow(1, 100.6) == true, "a forgotten key starts with a full bucket")

print("RateLimiter.spec: ok")
