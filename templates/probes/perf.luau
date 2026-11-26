-- probe: perf
-- datamodel: any
-- params: seconds=3
-- purpose: A quick performance snapshot: frame time over a short window, memory, and the instance counts that
--   usually explain a slow place. Compare before and after a change; one snapshot alone means little.
--   Studio throttles an unfocused window to about 66 ms a frame: a flat frame near that is labelled, because it
--   is Studio's cap, not the game's cost (bring Studio to the front and measure again).
local RunService = game:GetService("RunService")
local Stats = game:GetService("Stats")
local frames, worst, best, t0 = 0, 0, math.huge, os.clock()
local conn = RunService.Heartbeat:Connect(function(dt)
	frames += 1
	worst = math.max(worst, dt)
	best = math.min(best, dt)
end)
task.wait({{seconds}})
conn:Disconnect()
local elapsed = os.clock() - t0
local parts, scripts, guis, emitters, lights = 0, 0, 0, 0, 0
for _, d in workspace:GetDescendants() do
	if d:IsA("BasePart") then parts += 1
	elseif d:IsA("BaseScript") then scripts += 1
	elseif d:IsA("LayerCollector") then guis += 1
	elseif d:IsA("ParticleEmitter") then emitters += 1
	elseif d:IsA("Light") then lights += 1 end
end
local avg = elapsed / math.max(frames, 1)
-- Flat and near 66 ms: what an unfocused Studio window looks like. A game that really costs 66 ms looks the
-- same, so this is a label to re-measure in front, not a verdict.
local throttled = avg > 0.055 and avg < 0.08 and (worst - best) < 0.015
return (if throttled then "LIKELY UNFOCUSED-STUDIO THROTTLE (flat ~66 ms frames): not the game's cost; bring Studio to the front and re-run | " else "") .. string.format(
	"heartbeat avg %.1f ms (%.0f fps), worst %.1f ms | memory %.0f MB | instances %d | workspace: parts %d, scripts %d, world guis %d, emitters %d, lights %d",
	elapsed / math.max(frames, 1) * 1000, frames / elapsed, worst * 1000, Stats:GetTotalMemoryUsageMb(),
	Stats.InstanceCount, parts, scripts, guis, emitters, lights)
