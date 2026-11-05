-- probe: box-scan
-- datamodel: any
-- params: cx=0 cy=10 cz=0 sx=20 sy=20 sz=20 root=workspace max=40
-- purpose: Every part whose world bounding box touches a region, INCLUDING CanQuery = false parts that
--   GetPartBoundsInBox/GetPartsInPart silently skip. Use it to prove a corridor, doorway or spawn is really clear.
local root = {{root}}
local c, half = Vector3.new({{cx}}, {{cy}}, {{cz}}), Vector3.new({{sx}}, {{sy}}, {{sz}}) / 2
local qmin, qmax = c - half, c + half
local found = {}
for _, p in root:GetDescendants() do
	if p:IsA("BasePart") and not p:IsA("Terrain") then
		local cf, h = p.CFrame, p.Size / 2
		local r, u, b = cf.RightVector, cf.UpVector, cf.LookVector
		-- world AABB of the oriented part (conservative for rotated parts)
		local e = Vector3.new(
			math.abs(r.X) * h.X + math.abs(u.X) * h.Y + math.abs(b.X) * h.Z,
			math.abs(r.Y) * h.X + math.abs(u.Y) * h.Y + math.abs(b.Y) * h.Z,
			math.abs(r.Z) * h.X + math.abs(u.Z) * h.Y + math.abs(b.Z) * h.Z)
		local pmin, pmax = cf.Position - e, cf.Position + e
		if pmin.X <= qmax.X and pmax.X >= qmin.X and pmin.Y <= qmax.Y and pmax.Y >= qmin.Y and pmin.Z <= qmax.Z and pmax.Z >= qmin.Z then
			table.insert(found, p)
		end
	end
end
local engine = #workspace:GetPartBoundsInBox(CFrame.new(c), half * 2)
local out = { string.format("%d parts touch the box (engine query found %d - the difference is CanQuery=false):", #found, engine) }
for i = 1, math.min(#found, {{max}}) do
	local p = found[i]
	table.insert(out, string.format("%s  collide=%s query=%s transp=%.2f", p:GetFullName(), tostring(p.CanCollide), tostring(p.CanQuery), p.Transparency))
end
return table.concat(out, "\n")
