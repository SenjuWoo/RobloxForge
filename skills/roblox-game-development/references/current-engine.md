# Current engine: what model memory gets wrong

Training data is mostly older Roblox code. This is the short list of places where the engine moved
and remembered patterns are now wrong or second-best. Every class and property named here was
checked against the official creator-docs reference (2026-11-17); each line gives the query that
returns the real page. Read the page before writing code against it - this file is a pointer, not
the API.

`rb_docs_search "<query>"` then `rb_docs_read <path>`; `rbforge docs update` refreshes the cache.

## Replace on sight

| Old habit | Current | Why / where |
|---|---|---|
| `wait()`, `spawn()`, `delay()` | `task.wait`, `task.spawn`, `task.defer`, `task.delay` | the legacy scheduler is throttled; `rb_docs_read scripting/scheduler.md` |
| `tick()` | `os.clock()` for durations, `workspace:GetServerTimeNow()` for shared time, `os.time()` for dates | |
| `:connect()` / `:disconnect()` | `:Connect()` / `:Disconnect()` | |
| `Instance.new("Part", parent)` | set properties, then `.Parent` last | |
| `model:SetPrimaryPartCFrame(cf)` | `model:PivotTo(cf)` | |
| `BodyVelocity`, `BodyGyro`, `BodyPosition` | `LinearVelocity`, `AlignOrientation`, `AlignPosition`, `VectorForce` | constraint-based movers |
| `workspace:FindPartOnRay(...)` | `workspace:Raycast(origin, direction, RaycastParams)` | `direction` carries the length |
| `Humanoid:LoadAnimation` | `Animator:LoadAnimation` | `animation.md` |
| `Player:LoadCharacter()` | `Player:LoadCharacterAsync()` | the reference marks the old one superseded |
| `Mouse.KeyDown`, `GetMouse()` for keys | `UserInputService` with `gameProcessed`, or the Input Action System | |
| `InputAction:Fire(state)` to press an action from code | `InputBinding:Fire(state)` on a binding with `Type = Enum.InputBindingType.Scriptable` | the reference marks `InputAction:Fire` deprecated; firing an `Automatic` binding throws |
| `AnalyticsService:FireEvent`, `FireCustomEvent`, `FireInGameEconomyEvent`, `FirePlayerProgressionEvent`, `FireLogEvent` | `LogCustomEvent`, `LogEconomyEvent`, `LogProgressionEvent`, `LogFunnelStepEvent`, `LogOnboardingFunnelStepEvent` | all five `Fire*` are tagged deprecated |
| `Instance:Remove()` | `Instance:Destroy()` | |
| `game.Workspace`, `game.Players` | `workspace`, `game:GetService("Players")` | |
| `pairs()` / `ipairs()` everywhere | `for key, value in tbl do` | generalized iteration; the old forms still work |
| `"a" .. tostring(n)` chains | `` `a{n}` `` string interpolation | |
| legacy chat (`Chat` service scripts) | `TextChatService` | `roblox-text-chat` skill |
| `Sound` parented to a part for everything | still fine; the modular Audio API (`AudioPlayer`, `AudioEmitter`, `AudioListener`, `Wire`) is the route for effects chains and per-listener mixing | no oscillator or noise source exists in it |

`rbforge review --kind traps` flags most of the left column with the replacement.

## New since most training data

- **Input Action System** - `InputContext`, `InputAction`, `InputBinding` instances define an action
  once for keyboard, touch and gamepad. `ContextActionService:BindAction` is marked as planned for
  deprecation. `rb_docs_read input/input-action-system.md`; Studio skill `rbx-input-action-system`.
- **Server authority** - `Workspace.AuthorityMode = Server` turns on engine-level prediction,
  rollback and resimulation for competitive games; it requires `StreamingEnabled`, deferred signals,
  fixed simulation and the Input Action System, and code that runs in `RunService:BindToSimulation`.
  Do not hand-roll movement reconciliation before reading `projects/server-authority/index.md`.
- **Deferred signals** - `Workspace.SignalBehavior = Deferred` runs event handlers at defined resume
  points instead of immediately. Code that assumes "the handler already ran by the next line" breaks.
  `rb_docs_read scripting/events/deferred.md`.
- **AnimationConstraint avatars** - R15 characters may have no `Motor6D` at all (`animation.md`).
- **IKControl** - engine inverse kinematics on a rig; do not write a solver first.
  `rb_docs_read animation/inverse-kinematics.md`.
- **ScreenGui.ScreenInsets** - safe-area handling replaces `IgnoreGuiInset` arithmetic
  (`ui-mobile.md`).
- **UI building blocks** - `UIFlexItem` and flex layout on `UIListLayout`, `CanvasGroup` for group
  fades, `UIDragDetector` for draggable UI, `StyleSheet` / `StyleRule` for shared styling, `Path2D`
  for vector lines. Search each before building it by hand.
- **DragDetector** - 3D objects players can drag, with the physics handled.
- **ConfigService** - live, per-experience configuration values that can change without publishing.
  `rb_docs_read production/configs.md`.
- **EditableImage / EditableMesh** - runtime pixel and vertex editing; permission-gated and
  memory-heavy, so read the limits first. `AssetService:CreateEditableMeshAsync` loads only assets the
  owner or the player owns, and fails by default in a published game until it is enabled in
  Experience Settings: that switch is an owner step, so plan a fallback.
- **SLIM level of detail** - `Model.LevelOfDetail = Enum.ModelLevelOfDetail.SLIM` on a static model
  keeps an engine stand-in visible after the model streams out and merges draw calls up close. It
  needs streaming, a place saved to Roblox and Team Create; not for models that move, animate or hold
  a `Humanoid`. SLIM avatars (`Workspace.EnableSLIMAvatars`) cover player characters on a standard
  or advanced R15 rig, including a `StarterCharacter`; NPCs (even on an R15 rig) and R6 are excluded.
  `rb_docs_read workspace/streaming/slim.md`.
- **AnalyticsService `Log*` methods** - custom, economy, progression and funnel events. Limits from
  the docs: 100 custom event names an experience, three custom fields an event
  (`Enum.AnalyticsCustomFieldKeys.CustomField01..03`, string values), 8,000 distinct field
  combinations. Keep event names in one module; never put a player or item id in a field.
- **AudioPlayer regions** - `PlaybackRegion` and `LoopRegion` play or loop a slice of one asset, so
  several cues can live in one uploaded file (audio uploads are counted per month).
- **Players.MaxPlayers is read-only in scripts** - server size is set per place on the Creator
  Dashboard, not in code.
- **Parallel Luau** - `Actor`, `task.desynchronize`, `ConnectParallel`, `SharedTableRegistry`. Level C
  in `optimization-levels.md`: only with a profile that shows a script bottleneck.
- **Luau language** - `--!strict` typing, `buffer` and `vector` libraries, `if ... then ... else`
  expressions, compound assignment, `continue`, `table.freeze` / `table.clone`, `math.clamp`,
  native code generation (`--!native`). There are **no default parameter values**.
  `typing-luau.md` covers the type checker.
- **Text to speech and speech input** - `AudioTextToSpeech` exists; check policy and quota pages
  before designing around it.
- **Streaming is the normal case** - `Workspace.StreamingEnabled` is on by default in new places
  and cannot be set from a script.
  Client code must tolerate parts that are not there yet: `WaitForChild`, `CollectionService` added
  signals, `Model.ModelStreamingMode` for things that must arrive whole. `roblox-architecture`
  skill, `references/streaming.md`.
- **Studio MCP generators** - meshes, materials, textures, scenes, avatars and animations from text
  (`studio-mcp.md`). Model memory predates all of them.

## Still true, still forgotten

- The client can read everything that replicates and fire every remote with any arguments.
- A data store call can fail; a failed read is not a new player (`persistence.md`).
- `PlayerAdded` and `CharacterAdded` miss what already exists.
- Nothing done in Play survives Stop; nothing built by a script at runtime is saved.
- Teleport data set with `TeleportOptions:SetTeleportData` reaches the client and the client can change
  it: never carry currency, items or authority in it.

Members and deprecation tags added on 2026-11-24 were read from the cache at `a23352b`:
`InputAction:Fire` (deprecated), `InputBinding:Fire`, `Enum.InputBindingType`, the `Log*` and
deprecated `Fire*` methods, `AudioPlayer.PlaybackRegion` / `LoopRegion`, `Model.LevelOfDetail`,
`Enum.ModelLevelOfDetail.SLIM`, `CreateEditableMeshAsync`, `Players.MaxPlayers` (ReadOnly),
`SetTeleportData`, `Player:Move`.

Checked classes: InputContext, InputAction, InputBinding, AnimationConstraint, IKControl, UIFlexItem,
CanvasGroup, UIDragDetector, StyleSheet, StyleRule, Path2D, DragDetector, ConfigService,
EditableImage, EditableMesh, Actor, SharedTableRegistry, AudioTextToSpeech, AudioPlayer,
AudioEmitter, AudioListener, Wire, TextChatService, LinearVelocity, AlignOrientation, AlignPosition,
VectorForce, Animator, AnalyticsService, AssetService, TeleportOptions.
