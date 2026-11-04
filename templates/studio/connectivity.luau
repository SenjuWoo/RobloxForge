--!strict
-- Floating-geometry proof. Paste into execute_luau (Edit or Server) or run from a test Script.
-- Union-find over every queryable BasePart in ROOT: parts whose boxes touch within MARGIN join one component.
-- Anything outside the component that contains ANCHOR is floating. Target: floating == 0.
-- Mark invisible carriers (SurfaceGui text planes, trigger volumes) CanQuery = false so they are ignored.
local ROOT_NAME = "POI_Name" -- model to check
local ANCHOR_NAME: string? = nil -- part that is "the ground" (defaults to the model's PrimaryPart)
local MARGIN = 0.25

local root = assert(workspace:FindFirstChild(ROOT_NAME, true), ROOT_NAME .. " missing") :: Model
local parts: { BasePart } = {}
local index: { [BasePart]: number } = {}
for _, d in root:GetDescendants() do
	if d:IsA("BasePart") and d.CanQuery then
		table.insert(parts, d)
		index[d] = #parts
	end
end
local parent = table.create(#parts, 0)
for i = 1, #parts do
	parent[i] = i
end
local function find(i: number): number
	while parent[i] ~= i do
		parent[i] = parent[parent[i]]
		i = parent[i]
	end
	return i
end
local params = OverlapParams.new()
params.FilterType = Enum.RaycastFilterType.Include
params.FilterDescendantsInstances = { root }
params.MaxParts = 400
local grow = Vector3.new(MARGIN, MARGIN, MARGIN) * 2
for i, p in parts do
	for _, hit in workspace:GetPartBoundsInBox(p.CFrame, p.Size + grow, params) do
		local j = index[hit]
		if j then
			local a, b = find(i), find(j)
			if a ~= b then
				parent[a] = b
			end
		end
	end
	if i % 600 == 0 then
		task.wait() -- keep Studio responsive on large models
	end
end
local anchor = (
	ANCHOR_NAME and root:FindFirstChild(ANCHOR_NAME, true) or root.PrimaryPart
) :: BasePart?
assert(anchor and index[anchor], "anchor part missing or not queryable")
local main = find(index[anchor])
local frame = root:GetPivot()
local floating = {}
for i, p in parts do
	if find(i) ~= main then
		local l = frame:PointToObjectSpace(p.Position)
		table.insert(
			floating,
			string.format(
				"%s/%s @%.0f,%.0f,%.0f",
				p.Parent and p.Parent.Name or "?",
				p.Name,
				l.X,
				l.Y,
				l.Z
			)
		)
		if #floating >= 40 then
			break
		end
	end
end
return { checked = #parts, floating = #floating, sample = floating }
