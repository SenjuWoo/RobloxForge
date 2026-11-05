-- probe: remotes
-- datamodel: any
-- params:
-- purpose: Every RemoteEvent / UnreliableRemoteEvent / RemoteFunction / BindableEvent with its path. Remotes the
--   client creates never reach the server, and a typo in a name fails silently: compare this list to the names
--   your scripts use. Each server handler still needs type, range, ownership and rate checks.
local out = {}
for _, svc in { game:GetService("ReplicatedStorage"), workspace, game:GetService("ServerStorage") } do
	for _, d in svc:GetDescendants() do
		if d:IsA("RemoteEvent") or d:IsA("UnreliableRemoteEvent") or d:IsA("RemoteFunction") or d:IsA("BindableEvent") then
			table.insert(out, string.format("%-22s %s", d.ClassName, d:GetFullName()))
		end
	end
end
table.sort(out)
table.insert(out, 1, #out .. " remote/bindable object(s)")
return table.concat(out, "\n")
