-- probe: restore
-- datamodel: Edit
-- params:
-- purpose: Put back everything the hide probe moved, to the exact parent it came from.
local bin = game:GetService("ServerStorage"):FindFirstChild("ProbeHidden")
if not bin then return "nothing hidden" end
local n = 0
for _, holder in bin:GetChildren() do
	local origin = holder:FindFirstChild("Origin")
	for _, c in holder:GetChildren() do
		if c ~= origin and origin and origin.Value then
			c.Parent = origin.Value
			n += 1
		end
	end
end
bin:Destroy()
return "restored " .. n .. " instance(s)"
