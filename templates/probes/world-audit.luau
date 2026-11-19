-- probe: world-audit
-- datamodel: any
-- params: root=workspace gap=1 overlap=0.35 reach=40 skip={} max=25
-- purpose: Placement audit of a built world: anchored pieces with nothing under or beside them (floating), pieces
--   whose parts stand inside another piece's parts (a tent in a tower, stones through a wagon), and attachments
--   far from their part (set by world position before they had a parent). A piece is a direct child of root, or
--   of a Folder under it. Every line names the piece and a position; every line is a lead, not a verdict. Names
--   in skip (Luau patterns) are left out of the floating check and listed, so a skip never hides silently.
--   Run after every world rebuild, then still look at a capture.
local root = {{root}}
local GAP, OVERLAP, REACH, MAX = {{gap}}, {{overlap}}, {{reach}}, {{max}}
local SKIP = {{skip}}
local Players = game:GetService("Players")

local last = os.clock()
local function breathe()
	-- execute_luau holds Studio's main thread until it yields; yield on elapsed time.
	if os.clock() - last > 0.05 then
		task.wait()
		last = os.clock()
	end
end
local function where(p)
	return string.format("(%.0f, %.0f, %.0f)", p.X, p.Y, p.Z)
end

-- Pieces ----------------------------------------------------------------------------------------
local pieces = {}
local function moving(inst)
	if inst:IsA("Model") then
		if Players:GetPlayerFromCharacter(inst) or inst:FindFirstChildOfClass("Humanoid") then
			return true
		end
	end
	return false
end
local function collect(container)
	for _, c in container:GetChildren() do
		if c:IsA("Folder") then
			collect(c)
		elseif (c:IsA("Model") or c:IsA("BasePart")) and not c:IsA("Terrain") and not moving(c) then
			table.insert(pieces, c)
		end
	end
end
collect(root)

local function partsOf(piece)
	local list = {}
	if piece:IsA("BasePart") then
		table.insert(list, piece)
	end
	for _, d in piece:GetDescendants() do
		if d:IsA("BasePart") and d.Transparency < 1 then
			table.insert(list, d)
		end
	end
	return list
end
local function anchored(parts)
	for _, p in parts do
		if p.Anchored then
			return true
		end
	end
	return false
end
local function boxOf(piece)
	if piece:IsA("BasePart") then
		return piece.CFrame, piece.Size
	end
	return piece:GetBoundingBox()
end
local function skipped(name)
	for _, pattern in SKIP do
		if string.find(name, pattern) then
			return true
		end
	end
	return false
end

-- 1. Floating: no ray below the footprint meets anything within GAP, and nothing touches the box ----
local floating, skippedNames = {}, {}
for _, piece in pieces do
	breathe()
	local parts = partsOf(piece)
	if #parts > 0 and anchored(parts) then
		if skipped(piece.Name) then
			table.insert(skippedNames, piece.Name)
		else
			local cf, size = boxOf(piece)
			local params = RaycastParams.new()
			params.FilterType = Enum.RaycastFilterType.Exclude
			params.FilterDescendantsInstances = { piece }
			local bottom = cf.Position - Vector3.new(0, size.Y / 2, 0)
			local hx, hz = size.X * 0.4, size.Z * 0.4
			local held = false
			for _, o in { Vector3.zero, cf.RightVector * hx, -cf.RightVector * hx, cf.LookVector * hz, -cf.LookVector * hz } do
				local from = bottom + Vector3.new(o.X, 0.5, o.Z)
				if workspace:Raycast(from, Vector3.new(0, -(GAP + 0.5), 0), params) then
					held = true
					break
				end
			end
			if not held then
				-- Hung on a wall or tied to a neighbour: anything else inside the slightly grown box holds it.
				local overlapParams = OverlapParams.new()
				overlapParams.FilterType = Enum.RaycastFilterType.Exclude
				overlapParams.FilterDescendantsInstances = { piece }
				held = #workspace:GetPartBoundsInBox(cf, size + Vector3.new(GAP, GAP, GAP) * 2, overlapParams) > 0
			end
			if not held then
				local hit = workspace:Raycast(bottom, Vector3.new(0, -2000, 0), params)
				local drop = hit and (bottom.Y - hit.Position.Y) or math.huge
				table.insert(floating, { piece = piece, at = bottom, drop = drop })
			end
		end
	end
end

-- 2. Inside each other: part pairs from different pieces whose boxes share more than OVERLAP of the smaller ---
-- Estimated in both parts' frames and the smaller estimate kept, so a rotated thin wall does not swallow
-- whatever stands beside it.
local function corners(cf, size)
	local h = size / 2
	local out = {}
	for _, sx in { -1, 1 } do
		for _, sy in { -1, 1 } do
			for _, sz in { -1, 1 } do
				table.insert(out, cf * Vector3.new(h.X * sx, h.Y * sy, h.Z * sz))
			end
		end
	end
	return out
end
local function sharedIn(a, b)
	-- volume of a's box shared with b's box as seen axis-aligned in a's frame
	local h = a.Size / 2
	local lo, hi = Vector3.one * math.huge, -Vector3.one * math.huge
	for _, w in corners(b.CFrame, b.Size) do
		local l = a.CFrame:PointToObjectSpace(w)
		lo, hi = lo:Min(l), hi:Max(l)
	end
	local dx = math.min(h.X, hi.X) - math.max(-h.X, lo.X)
	local dy = math.min(h.Y, hi.Y) - math.max(-h.Y, lo.Y)
	local dz = math.min(h.Z, hi.Z) - math.max(-h.Z, lo.Z)
	if dx <= 0 or dy <= 0 or dz <= 0 then
		return 0
	end
	return dx * dy * dz
end
local function worldBox(cf, size)
	local lo, hi = Vector3.one * math.huge, -Vector3.one * math.huge
	for _, w in corners(cf, size) do
		lo, hi = lo:Min(w), hi:Max(w)
	end
	return lo, hi
end

local boxes = {}
for _, piece in pieces do
	local cf, size = boxOf(piece)
	local lo, hi = worldBox(cf, size)
	table.insert(boxes, { piece = piece, lo = lo, hi = hi })
end
table.sort(boxes, function(x, y)
	return x.lo.X < y.lo.X
end)
local partCache = {}
local function cachedParts(piece)
	-- each entry: { part, lo, hi } with the part's world bounds, computed once
	local p = partCache[piece]
	if not p then
		p = {}
		for _, part in partsOf(piece) do
			local lo, hi = worldBox(part.CFrame, part.Size)
			table.insert(p, { part = part, lo = lo, hi = hi })
		end
		partCache[piece] = p
	end
	return p
end
local function touches(x, lo, hi)
	return x.lo.X < hi.X and x.hi.X > lo.X and x.lo.Y < hi.Y and x.hi.Y > lo.Y and x.lo.Z < hi.Z and x.hi.Z > lo.Z
end
local function within(list, lo, hi)
	-- only the parts of one piece that reach into the other piece's bounds
	local out = {}
	for _, e in list do
		if touches(e, lo, hi) then
			table.insert(out, e)
		end
	end
	return out
end
local inside = {}
for i = 1, #boxes do
	local A = boxes[i]
	for j = i + 1, #boxes do
		local B = boxes[j]
		if B.lo.X > A.hi.X then
			break -- sorted by min X: nothing further along can touch A
		end
		breathe()
		if B.lo.Y < A.hi.Y and B.hi.Y > A.lo.Y and B.lo.Z < A.hi.Z and B.hi.Z > A.lo.Z then
			local worst, at = 0, nil
			local candB = within(cachedParts(B.piece), A.lo, A.hi)
			for _, ea in within(cachedParts(A.piece), B.lo, B.hi) do
				for _, eb in candB do
					local pa, pb = ea.part, eb.part
					local va, vb = pa.Size.X * pa.Size.Y * pa.Size.Z, pb.Size.X * pb.Size.Y * pb.Size.Z
					local small = math.min(va, vb)
					if small > 0.5 and touches(ea, eb.lo, eb.hi) then
						local shared = math.min(sharedIn(pa, pb), sharedIn(pb, pa))
						local ratio = shared / small
						if ratio > worst then
							worst, at = ratio, (if va < vb then pa.Position else pb.Position)
						end
					end
				end
			end
			if worst > OVERLAP then
				table.insert(inside, { a = A.piece, b = B.piece, ratio = worst, at = at })
			end
		end
	end
end
table.sort(inside, function(x, y)
	return x.ratio > y.ratio
end)

-- 3. Stray attachments ----------------------------------------------------------------------------
local stray, attachments = {}, 0
for _, d in root:GetDescendants() do
	if d:IsA("Attachment") and d.Parent and d.Parent:IsA("BasePart") then
		attachments += 1
		local part = d.Parent
		local off = (d.WorldPosition - part.Position).Magnitude
		if off > part.Size.Magnitude / 2 + REACH then
			table.insert(stray, { a = d, off = off })
		end
		breathe()
	end
end

-- Report --------------------------------------------------------------------------------------------
local leads = #floating + #inside + #stray
local out = {
	string.format(
		"WORLD-AUDIT %s: %d pieces, %d attachments under %s (gap %.1f, overlap %.2f, reach %d)",
		leads == 0 and "clean" or (leads .. " leads"),
		#pieces,
		attachments,
		root:GetFullName(),
		GAP,
		OVERLAP,
		REACH
	),
}
local function section(title, list, line)
	if #list == 0 then
		return
	end
	table.insert(out, string.format("%s (%d):", title, #list))
	for i = 1, math.min(#list, MAX) do
		table.insert(out, "  " .. line(list[i]))
	end
	if #list > MAX then
		table.insert(out, string.format("  ... %d more", #list - MAX))
	end
end
section("FLOATING", floating, function(f)
	return string.format(
		"%s bottom at %s, %s",
		f.piece:GetFullName(),
		where(f.at),
		f.drop == math.huge and "nothing below" or string.format("%.1f studs above what is below", f.drop)
	)
end)
section("INSIDE", inside, function(o)
	return string.format("%s / %s share %.0f%% near %s", o.a:GetFullName(), o.b:GetFullName(), o.ratio * 100, where(o.at))
end)
section("STRAY ATTACHMENT", stray, function(s)
	return string.format("%s %.0f studs from its part, at %s", s.a:GetFullName(), s.off, where(s.a.WorldPosition))
end)
if #skippedNames > 0 then
	table.sort(skippedNames)
	table.insert(out, string.format("SKIPPED from the floating check (%d): %s", #skippedNames, table.concat(skippedNames, ", ", 1, math.min(#skippedNames, MAX))))
end
return table.concat(out, "\n")
