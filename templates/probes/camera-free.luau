-- probe: camera-free
-- datamodel: Client
-- params:
-- purpose: Release a camera-pin and give the camera back to the game.
local RunService = game:GetService("RunService")
pcall(function() RunService:UnbindFromRenderStep("ForgeProbeCamera") end)
local cam = workspace.CurrentCamera
cam.CameraType = Enum.CameraType.Custom
local hum = game:GetService("Players").LocalPlayer.Character and game:GetService("Players").LocalPlayer.Character:FindFirstChildOfClass("Humanoid")
if hum then cam.CameraSubject = hum end
return "camera released (if the game uses its own Scriptable camera it takes over next frame)"
