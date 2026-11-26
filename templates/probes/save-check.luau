-- probe: save-check
-- datamodel: Edit
-- params: attrs={"QaSlot"} prefixes={"Stage","Debug"} roots={game:GetService("ServerStorage"),workspace,game:GetService("ReplicatedStorage")}
-- purpose: Before save_place: is anything in the Edit place that a test or stage left behind? Lists the named
--   test attributes (attrs) and any attribute starting with one of prefixes on the roots, and says whether a
--   playtest is running. Ends with "safe to save_place: yes" or "no" and why. RobloxForge cannot block the MCP's
--   save_place itself: run this first, and clear what it lists. Set attrs to your project's own slot names.
local RunService = game:GetService("RunService")
local ATTRS, PREFIXES, ROOTS = {{attrs}}, {{prefixes}}, {{roots}}
local named = {}
for _, a in ATTRS do
	named[a] = true
end
local found = {}
for _, root in ROOTS do
	for name, value in root:GetAttributes() do
		local hit = named[name]
		if not hit then
			for _, prefix in PREFIXES do
				if string.sub(name, 1, #prefix) == prefix then
					hit = true
					break
				end
			end
		end
		if hit then
			table.insert(found, string.format("%s.%s = %s", root:GetFullName(), name, tostring(value)))
		end
	end
end
table.sort(found)
local playing = RunService:IsRunning()
local why = {}
if playing then
	table.insert(why, "a playtest is running (save from Edit after Stop)")
end
if #found > 0 then
	table.insert(why, #found .. " test attribute(s) set: clear them in Edit first")
end
local out = { "save-check:" }
for _, line in found do
	table.insert(out, "  " .. line)
end
table.insert(out, "safe to save_place: " .. (if #why == 0 then "yes" else "no - " .. table.concat(why, "; ")))
return table.concat(out, "\n")
