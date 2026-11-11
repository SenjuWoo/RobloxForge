-- probe: sound-audit
-- datamodel: Client
-- params: seconds=4 extra=""
-- purpose: Which sounds will actually play? Collects every SoundId the place refers to (Sound instances, plus ids
--   written in script sources and any comma-separated `extra` ids), loads each one muted and reports the ones that
--   never load. A missing sound raises no error - it is just silent - so "the gun sounds are gone" needs this.
--   It also flags rbxasset:// files that are not stock Roblox content: those live in the versioned Studio install
--   folder, vanish on every Studio update and never exist for real players.
local SoundService = game:GetService("SoundService")
local ids, order = {}, {}
local function add(id)
	if type(id) == "string" and id ~= "" and not ids[id] then
		ids[id] = true
		order[#order + 1] = id
	end
end
local roots = { workspace, SoundService, game:GetService("ReplicatedStorage"), game:GetService("ReplicatedFirst"),
	game:GetService("StarterGui"), game:GetService("StarterPack"), game:GetService("StarterPlayer") }
for _, root in roots do
	for _, d in root:GetDescendants() do
		if d:IsA("Sound") then
			add(d.SoundId)
		elseif d:IsA("LuaSourceContainer") then
			local ok, src = pcall(function()
				return d.Source
			end)
			if ok and type(src) == "string" then
				for _, ext in { "wav", "mp3", "ogg" } do
					for id in src:gmatch("rbxasset://[%w_/%.%- ]+%." .. ext) do
						add(id)
					end
				end
			end
		end
	end
end
for id in string.gmatch({{extra}}, "[^,]+") do
	add((id:gsub("^%s+", ""):gsub("%s+$", "")))
end
local probes = {}
for _, id in order do
	local s = Instance.new("Sound")
	s.Name, s.SoundId, s.Volume = "ForgeSoundAudit", id, 0
	s.Parent = SoundService
	probes[id] = s
end
task.wait({{seconds}})
local missing, localOnly, loaded = {}, {}, 0
for _, id in order do
	local s = probes[id]
	if s.IsLoaded and s.TimeLength > 0 then
		loaded += 1
	else
		missing[#missing + 1] = id
	end
	-- Stock content sits directly in sounds/; a subfolder is something a tool copied into this install.
	if id:match("^rbxasset://sounds/[^/]+/") then
		localOnly[#localOnly + 1] = id
	end
	s:Destroy()
end
local out = { string.format("%d sound ids, %d load, %d do NOT load", #order, loaded, #missing) }
for _, id in missing do
	out[#out + 1] = "NOT LOADED  " .. id
end
if #localOnly > 0 then
	out[#out + 1] = string.format(
		"%d id(s) are local Studio content (rbxasset://sounds/<folder>/...): wiped by a Studio update and absent for players; upload them as audio assets before shipping. First: %s",
		#localOnly, localOnly[1])
end
return table.concat(out, "\n")
