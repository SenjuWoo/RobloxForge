-- probe: ray-all
-- datamodel: any
-- params: ox=0 oy=10 oz=0 tx=0 ty=10 tz=-100 root=workspace max=12
-- purpose: Everything a sight line passes through, INCLUDING parts workspace:Raycast skips (CanQuery = false,
--   transparent parts carrying SurfaceGuis/Decals). Sorted by distance. Use the capture camera position as the
--   origin and the pixel you are asking about as the target.
local root = {{root}}
local o, target = Vector3.new({{ox}}, {{oy}}, {{oz}}), Vector3.new({{tx}}, {{ty}}, {{tz}})
local dir = (target - o).Unit
local LIMIT = (target - o).Magnitude * 4
local function slab(p)
	local lo, ld = p.CFrame:PointToObjectSpace(o), p.CFrame:VectorToObjectSpace(dir)
	local h = p.Size / 2
	local tmin, tmax = -math.huge, math.huge
	for _, ax in { "X", "Y", "Z" } do
		local a, b, e = lo[ax], ld[ax], h[ax]
		if math.abs(b) < 1e-9 then
			if math.abs(a) > e then return nil end
		else
			local t1, t2 = (-e - a) / b, (e - a) / b
			if t1 > t2 then t1, t2 = t2, t1 end
			tmin, tmax = math.max(tmin, t1), math.min(tmax, t2)
			if tmin > tmax then return nil end
		end
	end
	if tmax < 0 then return nil end
	return math.max(tmin, 0)
end
local hits = {}
for _, p in root:GetDescendants() do
	if p:IsA("BasePart") and not p:IsA("Terrain") then
		local t = slab(p)
		if t and t < LIMIT then table.insert(hits, { p = p, t = t }) end
	end
end
table.sort(hits, function(a, b) return a.t < b.t end)
local out = { string.format("%d parts on the line (first %d):", #hits, math.min(#hits, {{max}})) }
for i = 1, math.min(#hits, {{max}}) do
	local p = hits[i].p
	local extras = {}
	if not p.CanQuery then table.insert(extras, "CanQuery=false") end
	if p.Transparency >= 0.95 then table.insert(extras, "invisible") end
	if p:FindFirstChildWhichIsA("SurfaceGui") then table.insert(extras, "SurfaceGui") end
	if p:FindFirstChildWhichIsA("Decal") or p:FindFirstChildWhichIsA("Texture") then table.insert(extras, "Decal") end
	table.insert(out, string.format("%5.1f  %s  %s", hits[i].t, p:GetFullName(), table.concat(extras, " ")))
end
local r = workspace:Raycast(o, dir * LIMIT)
table.insert(out, "workspace:Raycast says: " .. (r and (r.Instance:GetFullName() .. string.format(" at %.1f", (r.Position - o).Magnitude)) or "nothing"))
table.insert(out, "Nothing here but the artefact is on screen? It is not geometry: run gui-overflow, then bisect with hide.")
return table.concat(out, "\n")
