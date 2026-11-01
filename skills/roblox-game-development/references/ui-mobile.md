# Roblox UI, mobile, controller, and device verification

A Roblox UI is not complete because it looks good at one desktop resolution.

## Layout rules

Prefer:
- anchors/scale where appropriate,
- constraints/aspect ratios intentionally,
- padding/list/grid layout objects,
- readable contrast,
- safe-area aware placement,
- touch targets large enough to use,
- content hierarchy over decorative clutter.

Avoid:
- hardcoded pixel positions everywhere,
- tiny desktop-only buttons,
- text clipped at localization/scale changes,
- important HUD under platform chrome/notches,
- UI that requires hover.

## Input

Design actions around abstractions rather than only `MouseButton1Click`:
- touch,
- mouse/keyboard,
- gamepad where the game targets console/controller.

Use `ContextActionService` or other appropriate current APIs when input mapping matters.

## Roblox built-in skill accelerator

If the official Studio MCP exposes the `skill` capability, prefer Roblox's own
`rbx-device-simulator-lua` skill for form-factor checks.

Use it to test:
- phone portrait/landscape,
- tablet,
- PC,
- console/controller focus where applicable.

If that skill is not available externally, state the limitation and use the actual
device emulator/manual Studio tools that are available. Do not pretend a device test happened.

## Visual evidence

For a UI change:
1. open the UI in its real state,
2. capture screenshot,
3. inspect pixels if host vision exists,
4. test at least one small-screen form factor for meaningful UI,
5. fix clipping/overlap,
6. recapture final state.

Screenshot captured != screenshot inspected.

## Fusion 0.3: scopes or nothing

Fusion 0.3 rewrote lifetime management around **scopes**. Almost every Fusion
failure an AI writes is a 0.2 habit: `:get()`, a `[Cleanup]` key, or a
`cleanup()` call. Those do not exist in 0.3 and throw at runtime.

```lua
--!strict
-- StarterPlayerScripts/UI/StaminaBar.luau
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Fusion = require(ReplicatedStorage.Packages.Fusion)

local scoped = Fusion.scoped
local Children = Fusion.Children
local OnEvent = Fusion.OnEvent
local peek = Fusion.peek

export type Props = {
    ParentScope: any,
    Stamina: any,            -- Fusion state, 0..1
    OnSprint: () -> (),
}

return function(props: Props): (Instance, () -> ())
    local scope = props.ParentScope:innerScope()

    -- Created before its dependents: Fusion 0.3 cleans up newest-first, so a
    -- dependency must never be destroyed before the thing watching it.
    local fillSize = scope:Spring(
        scope:Computed(function(use)
            return UDim2.fromScale(math.clamp(use(props.Stamina), 0, 1), 1)
        end),
        25,
        0.85
    )

    local frame = scope:New "Frame" {
        Name = "StaminaBar",
        AnchorPoint = Vector2.new(0.5, 1),
        Position = UDim2.new(0.5, 0, 1, -32),
        Size = UDim2.fromOffset(280, 24),
        BackgroundColor3 = Color3.fromRGB(24, 26, 32),
        [Children] = {
            scope:New "UICorner" { CornerRadius = UDim.new(0, 6) },
            scope:New "Frame" {
                Name = "Fill",
                Size = fillSize,
                BackgroundColor3 = Color3.fromRGB(26, 115, 232),
                [Children] = { scope:New "UICorner" { CornerRadius = UDim.new(0, 6) } },
            },
            scope:New "TextButton" {
                Name = "Sprint",
                Size = UDim2.fromScale(1, 1),
                BackgroundTransparency = 1,
                Text = "",
                [OnEvent "Activated"] = function()
                    -- Reading state outside a reactive graph is peek(), never :get()
                    if peek(props.Stamina) > 0.1 then props.OnSprint() end
                end,
            },
        },
    }

    return frame, function()
        Fusion.doCleanup(scope)
    end
end
```

Rules:
- **Every constructor takes a scope first.** `scope:Value`, `scope:Computed`,
  `scope:Spring`, `scope:New` — not the global `Fusion.Value(...)` form.
- **`scope:Computed(function(use) ... end)`** — `use` is the dependency tracker.
  Reading a state inside without `use` silently does not subscribe.
- **`Fusion.peek(state)`** for one-off reads; `:get()` was removed.
- **`Fusion.doCleanup(scope)`** or `table.insert(scope, fn)` to tear down. Call
  it when the screen is destroyed, or the connections live forever.
- **Child components get `ParentScope:innerScope()`** and clean their own scope.
  Never share one scope across a hierarchy you might tear down independently.
- **`Fusion.innerScope` / `Fusion.deriveScope`** exist for wrapping existing
  scopes — use them instead of passing scopes through five layers.
- **No `[Cleanup]` key, no `cleanup()` function.** If you write them, stop and
  re-read this section.

`OnyxUI` (0.4+) provides prebuilt Fusion 0.3 components if you want a head start
on styling; it is optional, not a requirement.

## Layout that survives phones and localization

- `AnchorPoint = Vector2.new(0.5, 0.5)` with `UDim2.fromScale(0.5, 0.5)` to
  center responsively; `UDim2.fromOffset` for things that must not stretch.
- `AutomaticSize` set on the axis that should grow, and a zero scale on that axis
  — a list with `Size = UDim2.fromScale(1, 1)` will never fit its content.
- `ScreenGui.IgnoreGuiInset = true` plus `GuiService:GetGuiInset()` to keep HUD
  out of the topbar and the mobile notch. Test on a phone profile, not by eye.
- `UserInputService.InputBegan` handlers must check
  `gameProcessedEvent` before reacting, or typing in chat fires your ability.
- Text: `TextScaled = true` + `UITextSizeConstraint` with sane bounds, or localized
  strings will overflow their frame.
