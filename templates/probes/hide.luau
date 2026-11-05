-- probe: hide
-- datamodel: Edit
-- params: target=workspace.Model
-- purpose: Bisect a visual artefact. Moves one instance (and everything under it) out of the world into
--   ServerStorage.ProbeHidden and remembers where it came from. Capture again from the SAME camera pose: if the
--   artefact is gone it lives under that instance; restore and hide half its children next. Always run `restore`.
local target = {{target}}
assert(target and target.Parent, "target not found or already detached")
local SS = game:GetService("ServerStorage")
local bin = SS:FindFirstChild("ProbeHidden") or Instance.new("Folder")
bin.Name, bin.Parent = "ProbeHidden", SS
local link = Instance.new("ObjectValue")
link.Name, link.Value = "Origin", target.Parent
local holder = Instance.new("Folder")
holder.Name = target.Name
link.Parent = holder
holder.Parent = bin
local path = target:GetFullName()
target.Parent = holder
return "hidden " .. path .. " (run the restore probe when done)"
