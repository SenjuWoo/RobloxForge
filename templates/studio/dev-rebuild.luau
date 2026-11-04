--!nonstrict
-- Edit-time rebuild from fresh module clones (Edit `require` caches per instance; editing .Source does not invalidate).
-- Paste into execute_luau with datamodel_type = "Edit". Fill in MODULES, the entry module and the build call.
local SS = game:GetService("ServerStorage")
local source = game:GetService("ServerScriptService"):WaitForChild("Systems")
local MODULES = { "Kit", "Builder" } -- every module the entry module requires via script.Parent

local old = SS:FindFirstChild("DevRebuild")
if old then
	old:Destroy()
end
local folder = Instance.new("Folder")
folder.Name = "DevRebuild"
folder.Parent = SS
for _, name in MODULES do
	source[name]:Clone().Parent = folder
end

local Builder = require(folder.Builder)
local existing = workspace:FindFirstChild("Slice_1", true)
if existing then
	existing:Destroy()
end
local t0 = os.clock()
local model = Builder.Build(workspace) -- the one slice you changed, not the world
folder:Destroy() -- never save probes into the place
-- The MCP restores CameraType after a command; a delayed write survives and keeps the editor camera usable.
local cam = workspace.CurrentCamera
task.delay(1, function()
	cam.CameraType = Enum.CameraType.Custom
end)
return string.format(
	"rebuilt %s in %.2fs, %d descendants",
	model and model.Name or "?",
	os.clock() - t0,
	model and #model:GetDescendants() or 0
)
