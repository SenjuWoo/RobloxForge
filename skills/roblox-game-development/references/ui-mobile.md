# Roblox UI, mobile, controller, and device verification

A Roblox UI is not complete because it looks good at one desktop resolution. Most players are on
phones. Component and layout API detail is in the `roblox-ui` skill, input mapping in `roblox-input`;
`ui-craft.md` is about taste.

## Build it the plain way first

Instances plus a small controller is the default: it needs no package, the type checker understands
it, and a capture shows exactly what was built. Either author the ScreenGui under `StarterGui` (by
hand, or by a script run once in Edit) and have a LocalScript drive it, or build it in code as small
components - one module per panel, each returning its root instance and an `update` function.

```lua
--!strict
local gui = Instance.new("ScreenGui")
gui.Name = "Hud"
gui.ResetOnSpawn = false -- or the HUD is destroyed and rebuilt on every death
gui.Parent = player:WaitForChild("PlayerGui")

-- state -> screen: one render function, called when a replicated value changes
local function render()
	coinsLabel.Text = `Coins: {player:GetAttribute("Coins") or 0}`
end
player:GetAttributeChangedSignal("Coins"):Connect(render)
render()
```

A reactive UI library (Fusion, React-Lua) earns its place when the interface has many screens with
shared state. It is a dependency with its own failure modes; do not add one for a HUD.

## Layout rules that survive phones

- `ScreenGui.ResetOnSpawn = false` for anything persistent.
- **Safe areas:** `ScreenGui.ScreenInsets` decides how the gui sits against the notch and Roblox's
  top bar. The default (`CoreUISafeInsets`) keeps content clear of both; use `DeviceSafeInsets` for
  full-bleed backgrounds that must still avoid the notch, and `None` only for a true full-screen
  layer. Check with `rb_docs_search "ScreenInsets"` before overriding.
- Anchor to the edge the element belongs to (`AnchorPoint` + scale position + pixel offset), not to
  absolute pixel positions.
- Size with scale **and** a `UISizeConstraint` / `UIAspectRatioConstraint`, so a panel neither
  covers a phone nor shrinks to nothing on a 4K monitor.
- `AutomaticSize` on the axis that should grow, with zero scale on that axis.
- Touch targets at least ~44 px; keep the bottom-left (thumbstick) and bottom-right (jump) clear on
  touch devices.
- Text: a fixed `TextSize` that reads on a phone, inside a frame that can grow. If you use
  `TextScaled`, bound it with a `UITextSizeConstraint`.
- Nothing may depend on hover.
- `UIListLayout` / `UIGridLayout` / `UIPadding` instead of hand-computed positions.

## Input

- Buttons: `GuiButton.Activated` fires for mouse, touch and gamepad. `MouseButton1Click` does not.
- Keys: `UserInputService.InputBegan(input, gameProcessed)` - return when `gameProcessed` is true,
  or typing in chat fires the ability.
- Actions that need rebinding, touch buttons and gamepad from one definition: the **Input Action
  System** (`InputAction`, `InputBinding`, `InputContext` instances) is the current engine route;
  read `skill "rbx-input-action-system"` or `rb_docs_read input/input-action-system.md` before
  writing it. `ContextActionService:BindAction` still runs and is what most existing code uses, but
  the official reference marks it as planned for deprecation in favour of the Input Action System.
- Show the right glyph: check `UserInputService.PreferredInput` (or `GetLastInputType`) rather than
  assuming a keyboard.
- **Re-label when the device changes.** A player picks up a gamepad mid-session: listen to
  `LastInputTypeChanged` (or the `PreferredInput` change) and rebuild every visible prompt from the
  binding table, so "E climb" becomes the gamepad glyph without a respawn. Keep one function that
  names the key for an action on the current device; prompts, hints and tutorials all call it.
- **Every hint you show for touch needs a listener.** A prompt reading "TAP" with nothing bound to
  a tap is a dead end for a phone player (live 2026-11, a second production project). When you add
  a touch label, add the `TouchTap`/button route and a test that it fires the same action.

## Device verification

If the Studio MCP exposes `skill`, use `rbx-device-simulator-lua` for form-factor checks: phone
portrait and landscape, tablet, desktop, console focus. If it is not available, say so and use the
Studio device emulator by hand. Do not claim a device test that did not happen.

For a UI change:
1. open the UI in its real state,
2. capture,
3. look at the pixels,
4. repeat on at least one small-screen form factor,
5. fix clipping and overlap,
6. recapture the final state.

Screenshot captured != screenshot inspected.

## If the project already uses Fusion 0.3

Fusion 0.3 rewrote lifetime management around **scopes**. Almost every failure is a 0.2 habit:
`:get()`, a `[Cleanup]` key, or a `cleanup()` call. Those do not exist in 0.3.

```lua
--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Fusion = require(ReplicatedStorage.Packages.Fusion)

local Children = Fusion.Children
local OnEvent = Fusion.OnEvent
local peek = Fusion.peek

export type Props = {
	ParentScope: any,
	Stamina: any, -- Fusion state, 0..1
	OnSprint: () -> (),
}

return function(props: Props): Instance
	local scope = props.ParentScope:innerScope()

	local fillSize = scope:Spring(
		scope:Computed(function(use)
			return UDim2.fromScale(math.clamp(use(props.Stamina), 0, 1), 1)
		end),
		25,
		0.85
	)

	return scope:New("Frame")({
		Name = "StaminaBar",
		AnchorPoint = Vector2.new(0.5, 1),
		Position = UDim2.new(0.5, 0, 1, -32),
		Size = UDim2.fromOffset(280, 24),
		[Children] = {
			scope:New("Frame")({ Name = "Fill", Size = fillSize }),
			scope:New("TextButton")({
				Size = UDim2.fromScale(1, 1),
				BackgroundTransparency = 1,
				Text = "",
				[OnEvent("Activated")] = function()
					if peek(props.Stamina) > 0.1 then
						props.OnSprint()
					end
				end,
			}),
		},
	})
end
```

- Every constructor is a method of a scope: `scope:Value`, `scope:Computed`, `scope:Spring`,
  `scope:New`.
- Inside `Computed`, read state through `use(...)`; a read without it does not subscribe.
- `Fusion.peek(state)` for one-off reads.
- A child component takes `ParentScope:innerScope()`; `Fusion.doCleanup(scope)` tears a scope down.
- Check the version the project pins before relying on any of this: `rb_docs_search` does not cover
  third-party libraries, so read the package source.
