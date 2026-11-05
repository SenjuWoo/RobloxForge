-- probe: scene-audit
-- datamodel: any
-- params: root=workspace
-- purpose: One-pass health check of a place for the traps that most often break agent-built games. Every line is a
--   lead to read, not a verdict.
local root = {{root}}
local Players = game:GetService("Players")
local counts, leads = {}, {}
local function bump(k) counts[k] = (counts[k] or 0) + 1 end
local function lead(k, inst, why)
	bump(k)
	if counts[k] <= 3 then table.insert(leads, string.format("[%s] %s - %s", k, inst:GetFullName(), why)) end
end
local function inCharacter(inst)
	local m = inst:FindFirstAncestorOfClass("Model")
	while m do
		if Players:GetPlayerFromCharacter(m) or m:FindFirstChildOfClass("Humanoid") then return true end
		m = m:FindFirstAncestorOfClass("Model")
	end
	return false
end
for _, d in root:GetDescendants() do
	if d:IsA("BasePart") then
		bump("parts")
		if not d.Anchored and not inCharacter(d) and #d:GetJoints() == 0 then lead("loose", d, "unanchored and unwelded: it will fall or drift") end
		if d.CanCollide and d.Transparency >= 0.99 and not inCharacter(d) then lead("invisible-wall", d, "invisible but collidable") end
		if d.Size.Magnitude > 2048 then lead("huge", d, "very large part: physics/streaming cost") end
	elseif d:IsA("LocalScript") and not inCharacter(d) then
		lead("localscript-in-world", d, "LocalScripts do not run in Workspace unless inside a player's character")
	elseif d:IsA("Sound") and d.SoundId == "" then
		lead("silent-sound", d, "Sound with no SoundId")
	elseif (d:IsA("ImageLabel") or d:IsA("ImageButton")) and d.Image == "" and d.BackgroundTransparency >= 1 then
		lead("blank-image", d, "image element with no Image and no background: draws nothing")
	elseif d:IsA("Decal") and d.Texture == "" then
		lead("blank-decal", d, "Decal with no Texture")
	elseif d:IsA("SurfaceGui") and not d.ClipsDescendants then
		bump("surfacegui-unclipped")
	elseif d:IsA("PointLight") or d:IsA("SpotLight") or d:IsA("SurfaceLight") then
		bump("lights")
		if d.Shadows then bump("shadow-lights") end
	elseif d:IsA("ParticleEmitter") and d.Enabled then
		bump("emitters")
	end
end
for _, s in game:GetService("ReplicatedStorage"):GetDescendants() do
	if s:IsA("Script") and s.RunContext == Enum.RunContext.Legacy then lead("script-in-replicated", s, "server Scripts do not run in ReplicatedStorage") end
end
for _, s in game:GetService("ServerScriptService"):GetDescendants() do
	if s:IsA("LocalScript") then lead("localscript-on-server", s, "LocalScripts never run in ServerScriptService") end
end
local summary = {}
for k, v in counts do table.insert(summary, k .. "=" .. v) end
table.sort(summary)
table.insert(leads, 1, "counts: " .. table.concat(summary, "  "))
table.insert(leads, 2, "StreamingEnabled=" .. tostring(workspace.StreamingEnabled) .. "  Gravity=" .. workspace.Gravity)
if (counts["shadow-lights"] or 0) > 40 then table.insert(leads, "PERF: more than 40 shadow-casting lights") end
if (counts["surfacegui-unclipped"] or 0) > 0 then table.insert(leads, "NOTE: unclipped SurfaceGuis - run gui-overflow if anything shows where it should not") end
return table.concat(leads, "\n")
