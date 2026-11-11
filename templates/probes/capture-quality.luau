-- probe: capture-quality
-- datamodel: Client
-- params: level=21
-- purpose: Force the render quality for a capture, then put it back. Studio left in the background runs at about
--   15 fps; with quality on Automatic that collapses the draw distance, so distant geometry (a skyline, the far
--   wall) is missing from Play captures even though it exists. Run with level=21 before capturing and with
--   level=0 afterwards to restore the owner's setting. The reply also reports the frame rate, so a flat ~15 fps
--   tells you timings measured in this session are inflated about four times.
local RunService = game:GetService("RunService")
local level = {{level}}
local ok, message = pcall(function()
	local rendering = settings().Rendering
	if level == 0 then
		-- The saved level lives in a workspace attribute: _G is not shared between separate command sessions.
		local saved = workspace:GetAttribute("ForgeSavedQuality")
		if saved then
			rendering.QualityLevel = Enum.QualityLevel[saved]
			workspace:SetAttribute("ForgeSavedQuality", nil)
		end
		return (saved and "restored to " or "nothing saved, still ") .. tostring(rendering.QualityLevel)
	end
	if workspace:GetAttribute("ForgeSavedQuality") == nil then
		workspace:SetAttribute("ForgeSavedQuality", rendering.QualityLevel.Name)
	end
	rendering.QualityLevel = Enum.QualityLevel["Level" .. string.format("%02d", level)]
	return "quality " .. tostring(rendering.QualityLevel) .. " (was " .. tostring(workspace:GetAttribute("ForgeSavedQuality")) .. ")"
end)
local frames, t0 = 0, os.clock()
while os.clock() - t0 < 2 do
	RunService.Heartbeat:Wait()
	frames += 1
end
local fps = frames / 2
local note = fps < 20 and " - Studio looks throttled (background window): boot and frame timings are not real" or ""
return (ok and message or ("could not change quality: " .. tostring(message))) .. string.format(" | %.0f fps%s", fps, note)
