-- probe: perf
-- datamodel: any
-- params: seconds=3
-- purpose: A quick performance snapshot: frame time over a short window, memory, and the instance counts that
--   usually explain a slow place. Compare before and after a change; one snapshot alone means little.
local RunService = game:GetService("RunService")
local Stats = game:GetService("Stats")
local frames, worst, t0 = 0, 0, os.clock()
local conn = RunService.Heartbeat:Connect(function(dt)
	frames += 1
	worst = math.max(worst, dt)
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
return string.format(
	"heartbeat avg %.1f ms (%.0f fps), worst %.1f ms | memory %.0f MB | instances %d | workspace: parts %d, scripts %d, world guis %d, emitters %d, lights %d",
	elapsed / math.max(frames, 1) * 1000, frames / elapsed, worst * 1000, Stats:GetTotalMemoryUsageMb(),
	Stats.InstanceCount, parts, scripts, guis, emitters, lights)
