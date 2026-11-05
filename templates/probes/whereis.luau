-- probe: whereis
-- datamodel: any
-- params: pattern="Door" root=game limit=30
-- purpose: Find instances by name (Lua pattern, case-insensitive) with class, path and world position. Cheaper
--   than reading the explorer tree, and it tells you which datamodel actually has the thing.
local root, pattern, LIMIT = {{root}}, string.lower({{pattern}}), {{limit}}
local out, n = {}, 0
for _, d in root:GetDescendants() do
	local ok, name = pcall(function() return d.Name end)
	if ok and string.find(string.lower(name), pattern) then
		n += 1
		if n <= LIMIT then
			local pos = ""
			if d:IsA("BasePart") then pos = tostring(d.Position)
			elseif d:IsA("Model") then
				local okp, pv = pcall(function() return d:GetPivot().Position end)
				if okp then pos = tostring(pv) end
			end
			table.insert(out, string.format("%-16s %s %s", d.ClassName, d:GetFullName(), pos))
		end
	end
end
table.insert(out, 1, string.format("%d match(es) for %q", n, pattern))
return table.concat(out, "\n")
