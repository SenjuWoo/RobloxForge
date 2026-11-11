-- probe: goto
-- datamodel: Server
-- params: x=0 y=10 z=0 anchor=true name=""
-- purpose: Move a player's character to a spot so that area streams in and can be inspected or captured. With
--   StreamingEnabled a camera pinned far from the character shows an empty world: content streams around the
--   character, not the camera, and RequestStreamAroundAsync from the client is not enough. `anchor=true` holds the
--   character in place and makes it unkillable while you look; run again with anchor=false to release it.
local Players = game:GetService("Players")
local want = {{name}}
local plr
for _, p in Players:GetPlayers() do
	if want == "" or p.Name == want or p.DisplayName == want then
		plr = p
		break
	end
end
if not plr or not plr.Character then
	return "no player character to move"
end
local char = plr.Character
local root = char:FindFirstChild("HumanoidRootPart")
local hum = char:FindFirstChildOfClass("Humanoid")
if not root or not hum then
	return "character has no HumanoidRootPart/Humanoid yet"
end
local target = Vector3.new({{x}}, {{y}}, {{z}})
pcall(function()
	plr:RequestStreamAroundAsync(target, 5)
end)
local hold = {{anchor}}
if hold then
	if char:GetAttribute("ForgeGotoHealth") == nil then
		char:SetAttribute("ForgeGotoHealth", hum.MaxHealth)
	end
	hum.MaxHealth, hum.Health = 1e6, 1e6
else
	local old = char:GetAttribute("ForgeGotoHealth")
	if old then
		hum.MaxHealth, hum.Health = old, old
		char:SetAttribute("ForgeGotoHealth", nil)
	end
end
char:PivotTo(CFrame.new(target))
root.AssemblyLinearVelocity = Vector3.zero
root.Anchored = hold
task.wait(2)
local at = char:GetPivot().Position
return string.format("%s at (%.0f, %.0f, %.0f) anchored=%s - now camera-pin on the Client and capture", plr.Name, at.X, at.Y, at.Z, tostring(hold))
