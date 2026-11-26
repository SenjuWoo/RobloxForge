-- probe: device-layout
-- datamodel: Edit
-- params: devices={} forms={"Phone","Tablet","Console"} minTarget=44 keep=false
-- purpose: Edit-mode layout check across real device presets through StudioDeviceSimulatorService (plugin
--   context: execute_luau has it). For each device (names in devices, else the smallest preset of each form in
--   forms) it sets the device, reads the viewport and reports StarterGui elements off-screen and buttons smaller
--   than minTarget pixels. Then it stops simulation unless keep=true (keep the last device for a screen_capture).
--   UI built at runtime is not in StarterGui: set the device in Edit, then Play and capture (setters error in
--   the Play server). Source: Roblox's rbx-device-simulator-lua skill (get_roblox_skill).
local svc = game:GetService("StudioDeviceSimulatorService")
local StarterGui = game:GetService("StarterGui")
local WANT, FORMS, MIN, KEEP = {{devices}}, {{forms}}, {{minTarget}}, {{keep}}

local infos = {}
for _, id in svc:GetDeviceListAsync() do
	local ok, info = pcall(function()
		return svc:GetDeviceInfoAsync(id)
	end)
	if ok then
		table.insert(infos, info)
	end
end
local chosen = {}
if #WANT > 0 then
	for _, name in WANT do
		for _, info in infos do
			if info.Name == name then
				table.insert(chosen, info)
			end
		end
	end
else
	for _, form in FORMS do
		local best
		for _, info in infos do
			if info.DeviceForm.Name == form and (not best or info.Width * info.Height < best.Width * best.Height) then
				best = info
			end
		end
		if best then
			table.insert(chosen, best)
		end
	end
end

local function check(vp)
	local issues = {}
	for _, sg in StarterGui:GetChildren() do
		if sg:IsA("ScreenGui") and sg.Enabled then
			for _, obj in sg:GetDescendants() do
				if obj:IsA("GuiObject") and obj.Visible then
					local p, s = obj.AbsolutePosition, obj.AbsoluteSize
					local path = sg.Name .. string.sub(obj:GetFullName(), #sg:GetFullName() + 1)
					if p.X < -2 or p.Y < -2 or p.X + s.X > vp.X + 2 or p.Y + s.Y > vp.Y + 2 then
						table.insert(issues, string.format("  OFF-SCREEN %s (%.0f,%.0f)-(%.0f,%.0f)", path, p.X, p.Y, p.X + s.X, p.Y + s.Y))
					end
					if (obj:IsA("TextButton") or obj:IsA("ImageButton")) and (s.X < MIN or s.Y < MIN) then
						table.insert(issues, string.format("  SMALL TARGET %s %.0fx%.0f", path, s.X, s.Y))
					end
				end
			end
		end
	end
	return issues
end

local out = { string.format("device-layout: %d preset(s) available, %d checked", #infos, #chosen) }
for i, info in chosen do
	local ok, err = pcall(function()
		svc:SetDeviceAsync(info.DeviceId)
	end)
	task.wait(0.3)
	if not ok then
		table.insert(out, string.format("%s: could not set (%s)", info.Name, tostring(err)))
	else
		local vp = workspace.CurrentCamera.ViewportSize
		local issues = check(vp)
		table.insert(out, string.format("%s (%s %dx%d): viewport %.0fx%.0f, %d issue(s)", info.Name, info.DeviceForm.Name,
			info.Width, info.Height, vp.X, vp.Y, #issues))
		for j = 1, math.min(#issues, 15) do
			table.insert(out, issues[j])
		end
	end
	if i < #chosen or not KEEP then
		pcall(function()
			svc:StopSimulationAsync()
		end)
		task.wait(0.2)
	end
end
table.insert(out, KEEP and "kept the last device active: capture now, then StopSimulationAsync()" or "simulation stopped: Studio back to its own viewport")
return table.concat(out, "\n")
