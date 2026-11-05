-- probe: player-state
-- datamodel: any
-- params: name=""
-- purpose: Where a player is and what state they are in: position, velocity, humanoid state and health, floor
--   material, the player's and character's attributes. On the Client it reads the local player; on the Server pass
--   a name (empty = first player). Use it instead of guessing from a screenshot.
local Players = game:GetService("Players")
local plr = Players.LocalPlayer
if not plr then
	local want = {{name}}
	for _, p in Players:GetPlayers() do
		if want == "" or p.Name == want or p.DisplayName == want then plr = p break end
	end
end
if not plr then return "no player" end
local char = plr.Character
local hrp = char and char:FindFirstChild("HumanoidRootPart")
local hum = char and char:FindFirstChildOfClass("Humanoid")
local out = { "player " .. plr.Name }
if hrp then
	table.insert(out, string.format("pos %s  vel %.1f studs/s", tostring(hrp.Position), hrp.AssemblyLinearVelocity.Magnitude))
end
if hum then
	table.insert(out, string.format("state %s  health %.0f/%.0f  floor %s  walkspeed %.0f", hum:GetState().Name, hum.Health, hum.MaxHealth, hum.FloorMaterial.Name, hum.WalkSpeed))
end
local function attrs(inst, label)
	local parts = {}
	for k, v in inst:GetAttributes() do table.insert(parts, k .. "=" .. tostring(v)) end
	table.sort(parts)
	if #parts > 0 then table.insert(out, label .. ": " .. table.concat(parts, "  ")) end
end
attrs(plr, "player attrs")
if char then attrs(char, "character attrs") end
return table.concat(out, "\n")
