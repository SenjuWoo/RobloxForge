--!strict
-- Client entry point: input and presentation only. It shows what the server published and sends
-- intents; it never decides a reward, a price or a result.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Config = require(Shared:WaitForChild("Config"))
local Net = require(Shared:WaitForChild("Net"))
local Rules = require(Shared:WaitForChild("Rules"))

local player = Players.LocalPlayer
local doAction = Net.event("DoAction")
local buyUpgrade = Net.event("BuyUpgrade")

-- ---- HUD --------------------------------------------------------------------------------------
-- Built once. ResetOnSpawn = false, or the HUD is destroyed and rebuilt on every death.
local gui = Instance.new("ScreenGui")
gui.Name = "Hud"
gui.ResetOnSpawn = false

local panel = Instance.new("Frame")
panel.Name = "Panel"
panel.AnchorPoint = Vector2.new(0.5, 1)
panel.Position = UDim2.new(0.5, 0, 1, -24) -- bottom centre: clear of the top bar and the thumbstick
panel.Size = UDim2.fromOffset(320, 132)
panel.BackgroundColor3 = Color3.fromRGB(22, 24, 30)
panel.BackgroundTransparency = 0.2
panel.BorderSizePixel = 0
panel.Parent = gui

local layout = Instance.new("UIListLayout")
layout.SortOrder = Enum.SortOrder.LayoutOrder -- a layout made in code sorts by Name unless told otherwise
layout.Padding = UDim.new(0, 8)
layout.HorizontalAlignment = Enum.HorizontalAlignment.Center
layout.VerticalAlignment = Enum.VerticalAlignment.Center
layout.Parent = panel

-- Keeps the panel usable on a phone in portrait instead of running off both edges.
local limit = Instance.new("UISizeConstraint")
limit.MaxSize = Vector2.new(360, 160)
limit.Parent = panel

local function label(name: string, order: number): TextLabel
	local text = Instance.new("TextLabel")
	text.Name = name
	text.LayoutOrder = order
	text.Size = UDim2.new(1, -24, 0, 24)
	text.BackgroundTransparency = 1
	text.Font = Enum.Font.GothamBold
	text.TextSize = 20
	text.TextColor3 = Color3.fromRGB(240, 240, 245)
	text.Parent = panel
	return text
end

local function button(name: string, order: number): TextButton
	local control = Instance.new("TextButton")
	control.Name = name
	control.LayoutOrder = order
	control.Size = UDim2.new(1, -24, 0, 44) -- 44 px: the smallest target a thumb hits reliably
	control.BackgroundColor3 = Color3.fromRGB(52, 120, 246)
	control.BorderSizePixel = 0
	control.AutoButtonColor = true
	control.Font = Enum.Font.GothamBold
	control.TextSize = 18
	control.TextColor3 = Color3.new(1, 1, 1)
	control.Parent = panel
	return control
end

local coinsLabel = label("Coins", 1)
local actionButton = button("Action", 2)
local upgradeButton = button("Upgrade", 3)
upgradeButton.BackgroundColor3 = Color3.fromRGB(40, 150, 90)

gui.Parent = player:WaitForChild("PlayerGui")

-- ---- state -> screen --------------------------------------------------------------------------
local power = Config.Upgrades.Power

local function render()
	local coins = (player:GetAttribute("Coins") :: number?) or 0
	local level = (player:GetAttribute("Power") :: number?) or 0
	coinsLabel.Text = `Coins: {coins}`
	actionButton.Text = `Collect +{Rules.rewardFor(Config.BaseReward, level)}  [E]`
	if level >= power.MaxLevel then
		upgradeButton.Text = "Power: MAX"
	else
		-- Shown for the player's benefit only; the server computes the real price again.
		upgradeButton.Text = `Power {level} -> {level + 1}: {Rules.upgradeCost(power.BaseCost, power.Growth, level)}`
	end
end

player:GetAttributeChangedSignal("Coins"):Connect(render)
player:GetAttributeChangedSignal("Power"):Connect(render)
render()

-- ---- input -> intent --------------------------------------------------------------------------
-- Activated fires for mouse, touch and gamepad alike; MouseButton1Click does not.
actionButton.Activated:Connect(function()
	doAction:FireServer()
end)
upgradeButton.Activated:Connect(function()
	buyUpgrade:FireServer("Power")
end)

UserInputService.InputBegan:Connect(function(input: InputObject, gameProcessed: boolean)
	if gameProcessed then
		return -- the player is typing in chat or pressing a button
	end
	if input.KeyCode == Enum.KeyCode.E then
		doAction:FireServer()
	end
end)
