--!strict
-- Token bucket, one bucket per key (use the player's UserId). Pure: the caller passes the time, so
-- the behaviour is testable without waiting (tests/RateLimiter.spec.luau).
--
--   local limiter = RateLimiter.new(8, 4)            -- 8 per second, bursts of 4 on top
--   if not limiter:allow(player.UserId, os.clock()) then return end
--   limiter:forget(player.UserId)                    -- on PlayerRemoving

local RateLimiter = {}
RateLimiter.__index = RateLimiter

type Bucket = { tokens: number, at: number }

export type RateLimiter = typeof(setmetatable(
	{} :: { rate: number, capacity: number, buckets: { [number | string]: Bucket } },
	RateLimiter
))

function RateLimiter.new(perSecond: number, burst: number): RateLimiter
	return setmetatable({
		rate = perSecond,
		capacity = math.max(1, burst + 1),
		buckets = {},
	}, RateLimiter)
end

function RateLimiter.allow(self: RateLimiter, key: number | string, now: number): boolean
	local bucket = self.buckets[key]
	if not bucket then
		bucket = { tokens = self.capacity, at = now }
		self.buckets[key] = bucket
	end
	local elapsed = math.max(0, now - bucket.at)
	bucket.tokens = math.min(self.capacity, bucket.tokens + elapsed * self.rate)
	bucket.at = now
	if bucket.tokens < 1 then
		return false
	end
	bucket.tokens -= 1
	return true
end

function RateLimiter.forget(self: RateLimiter, key: number | string)
	self.buckets[key] = nil
end

return RateLimiter
