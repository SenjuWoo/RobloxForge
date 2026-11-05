-- probe: camera-pin
-- datamodel: Client
-- params: px=0 py=20 pz=30 lx=0 ly=5 lz=0
-- purpose: Hold the Play camera at a fixed pose so captures are comparable (before/after a fix, hide/restore
--   bisects). Game camera scripts and execute_luau both move the camera otherwise. Run camera-free afterwards.
local RunService = game:GetService("RunService")
local cam = workspace.CurrentCamera
local pose = CFrame.lookAt(Vector3.new({{px}}, {{py}}, {{pz}}), Vector3.new({{lx}}, {{ly}}, {{lz}}))
pcall(function() RunService:UnbindFromRenderStep("ForgeProbeCamera") end)
RunService:BindToRenderStep("ForgeProbeCamera", Enum.RenderPriority.Last.Value + 1, function()
	cam.CameraType = Enum.CameraType.Scriptable
	cam.CFrame = pose
end)
return "camera pinned; capture with screen_capture (no camera args), then run camera-free"
