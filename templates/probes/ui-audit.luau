-- probe: ui-audit
-- datamodel: Client
-- params: minText=11
-- purpose: Objective UI checks on the live client: text too small to read, elements off-screen or clipped by the
--   window, ScreenGuis that reset on respawn (state lost), duplicates of one HUD. Run it at the target resolution;
--   then still LOOK at a capture - these checks cannot judge taste.
local player = game:GetService("Players").LocalPlayer
local vp = workspace.CurrentCamera.ViewportSize
local out, names = {}, {}
local small, off, total = 0, 0, 0
for _, sg in player.PlayerGui:GetChildren() do
	if sg:IsA("ScreenGui") and sg.Enabled then
		names[sg.Name] = (names[sg.Name] or 0) + 1
		if sg.ResetOnSpawn and #sg:GetDescendants() > 20 then
			table.insert(out, "RESET " .. sg.Name .. " has ResetOnSpawn = true: rebuilt (and state lost) on every respawn")
		end
		for _, g in sg:GetDescendants() do
			if g:IsA("GuiObject") and g.Visible and g.AbsoluteSize.X > 0 then
				total += 1
				local p, s = g.AbsolutePosition, g.AbsoluteSize
				if p.X + s.X < 0 or p.Y + s.Y < -40 or p.X > vp.X or p.Y > vp.Y then
					off += 1
					if off <= 5 then table.insert(out, "OFFSCREEN " .. g:GetFullName()) end
				end
				if (g:IsA("TextLabel") or g:IsA("TextButton")) and not g.TextScaled and g.Text ~= "" and g.TextTransparency < 0.9 then
					-- effective size: multiply every UIScale on the way up to the ScreenGui
					local scale, a = 1, g
					while a and a:IsA("GuiObject") do
						local u = a:FindFirstChildOfClass("UIScale")
						if u then scale *= u.Scale end
						a = a.Parent
					end
					if g.TextSize * scale < {{minText}} then
						small += 1
						if small <= 8 then table.insert(out, string.format("SMALLTEXT %.0fpx %s %q", g.TextSize * scale, g:GetFullName(), g.Text:sub(1, 30))) end
					end
				end
			end
		end
	end
end
for n, c in names do
	if c > 1 then table.insert(out, "DUPLICATE ScreenGui " .. n .. " x" .. c .. " (a script runs twice or the gui is not cleaned up)") end
end
table.insert(out, 1, string.format("viewport %dx%d | visible gui objects %d | small text %d | off-screen %d", vp.X, vp.Y, total, small, off))
return table.concat(out, "\n")
