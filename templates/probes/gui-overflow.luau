-- probe: gui-overflow
-- datamodel: any
-- params: root=workspace
-- purpose: Find SurfaceGui/BillboardGui content drawn outside its canvas (ClipsDescendants is false by default, so
--   oversized children paint in mid-air, one-sided) and AlwaysOnTop SurfaceGuis (did not render in testing).
--   Run this FIRST for any "flat wall / screen effect seen from one side only" report.
local root = {{root}}
local out, guis = {}, {}
local function consider(g)
	if g:IsA("SurfaceGui") or g:IsA("BillboardGui") then guis[g] = true end
end
for _, d in root:GetDescendants() do consider(d) end
local lp = game:GetService("Players").LocalPlayer
if lp and lp:FindFirstChild("PlayerGui") then
	for _, d in lp.PlayerGui:GetDescendants() do consider(d) end
end
local nOver, nTop = 0, 0
for g in guis do
	if g:IsA("SurfaceGui") and g.AlwaysOnTop then
		nTop += 1
		if nTop <= 10 then table.insert(out, "ALWAYSONTOP " .. g:GetFullName()) end
	end
	if not g.ClipsDescendants then
		for _, c in g:GetDescendants() do
			if c:IsA("GuiObject") and c.Visible and c.Parent == g then
				local p, s = c.Position, c.Size
				local x0, y0 = p.X.Scale - c.AnchorPoint.X * s.X.Scale, p.Y.Scale - c.AnchorPoint.Y * s.Y.Scale
				if x0 < -0.01 or y0 < -0.01 or x0 + s.X.Scale > 1.01 or y0 + s.Y.Scale > 1.01 then
					nOver += 1
					if nOver <= 20 then
						table.insert(out, string.format("OVERFLOW %s  (x %.2f..%.2f, y %.2f..%.2f of canvas 0..1)", c:GetFullName(), x0, x0 + s.X.Scale, y0, y0 + s.Y.Scale))
					end
				end
			end
		end
	end
end
table.insert(out, 1, string.format("guis scanned %d | overflowing children %d | AlwaysOnTop SurfaceGuis %d", (function() local n = 0 for _ in guis do n += 1 end return n end)(), nOver, nTop))
if nOver > 0 then table.insert(out, "FIX: set ClipsDescendants = true on those SurfaceGuis (or keep children inside 0..1).") end
return table.concat(out, "\n")
