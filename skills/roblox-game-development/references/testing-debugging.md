# Roblox testing and debugging

## Evidence-first bug loop

1. Reproduce the exact behavior.
2. Read Output / error text.
3. Identify script, line, state, or event path.
4. Inspect the actual source/state.
5. Form one concrete hypothesis.
6. Apply the smallest useful fix.
7. Re-run the same scenario.
8. Remove temporary debug spam.
9. Verify nearby regression risks.

Do not replace three scripts because one nil error appeared.

## Roblox built-in Assistant skills

The current Studio Assistant documents Roblox-maintained skills. If the official
Studio MCP exposes the `skill` tool, use these specialized capabilities when they
fit instead of manually reinventing them:

- `rbx-debug` — breakpoints, call stacks, locals/thread state.
- `rbx-unit-test` — framework detection and Luau unit-test workflow.
- `rbx-device-simulator-lua` — device presets/orientation/UI capture.
- `rbx-perf-profiling` — MicroProfiler interpretation.
- `rbx-scene-analysis` — scene/memory/rendering health.
- `rbx-docs-search` — authoritative Roblox docs.

Always discover current availability; names/capabilities can change.

## Unit testing policy

Use existing project framework first.

Current useful options include:
- Roblox/Jest Roblox (Roblox-maintained read-only mirror / internal lineage),
- jsdotlua/jest-lua community continuation,
- a tiny built-in harness for small pure modules.

TestEZ is historically common but archived; do not install it as the automatic modern default.

Unit-test:
- pure calculations,
- inventory/economy rules,
- state machines,
- validation,
- serialization/migrations.

Playtest:
- character motion,
- physics,
- UI interaction,
- remotes,
- spawn/respawn,
- NPC behavior,
- camera,
- networked gameplay.

## Source-controlled automation

For Rojo projects, `rojo-rbx/run-in-roblox` can run a place/model/script inside
Studio and pipe output to stdout/stderr. It is useful for deterministic CI-style
Studio tests when the project shape fits it.

Do not install it for a Studio-native prototype unless automation justifies it.

## Completion

A gameplay fix is complete only when the failing scenario is exercised in the
final state and the expected result is observed.

## The five-rung ladder (cheapest check that can catch the bug)

Booting Studio to discover a typo costs 10-30 seconds and thousands of tokens.
Escalate only as far as you must:

| Rung | Cost | Catches | How |
|---|---|---|---|
| 1 static | <1s | syntax, types, API typos, formatting | `rbforge check --scope static` |
| 2 unit | ms | economy/combat/inventory math, state machines | `rbforge check --scope unit` (Lune) |
| 3 structure | ms | missing project paths, unanchored geometry, client-side authority, `loadstring` | `rbforge check --scope structure` |
| 4 playtest | 10-30s | physics, remotes, spawn/respawn, UI interaction, camera | `start_stop_play` + subagent/playtest |
| 5 cloud regression | minutes | the whole suite on a real server build | Open Cloud Luau execution |

Run `rbforge check` (rungs 1-3) after every edit batch. It exits 0 only when
everything that could run, passed; `incomplete` means a tool was missing, and an
agent must not report that as verified.

Rung 4 is the only rung that proves a game *works*. Rungs 1-3 are how you stop
wasting it.

## Rung 5: keep it to one task per run

Open Cloud's Luau execution endpoint creates a *session task*. Creating one per
module is how pipelines stall: the endpoint is rate-limited per account owner,
and a naive suite spends several task creations per run. Treat it as a release
gate, not a dev loop:

1. Build a test place with Rojo from `test.project.json`.
2. Upload it as a saved version of a dedicated test place.
3. Run the entire Jest-Lua / test suite **inside one** task creation:
   `require(ReplicatedStorage.DevPackages.Jest).runCLI(root, { ci = true }, { root })`
   with a generous timeout (up to 300s).
4. Poll the task to a terminal state and read `/logs?view=STRUCTURED`.

If you get `429 RESOURCE_EXHAUSTED`, stop creating tasks, back off, and report
the quota rather than retrying in a loop. Verify current limits in the docs
before designing a pipeline around them - they are not the same as the
documented per-minute figure, and they change.

## Geometry proofs (procedural worlds)

Screenshots miss floating props and blocked doorways. Two cheap Luau checks
catch them; templates live in `templates/studio/`.

- **Connectivity (`connectivity.luau`)** - union-find over every queryable
  part in a model, joining parts whose boxes touch within a small margin
  (`GetPartBoundsInBox` with an include filter). Everything not in the largest
  component is "floating". Run it after every geometry change; target 0.
  Mark invisible text carriers `CanQuery = false` so they are ignored.
- **Route matrix (`route-matrix.luau`)** - `PathfindingService` from every
  entry point to every room/objective with the real agent size, from both
  approach directions. Report failures by label; target 0.
- **Census** - count the things the game depends on (prompts per
  `PromptKind`, gates, spawn pads) after a full server build. A builder that
  silently skips one plot shows up here, not in a screenshot.

## Console triage: read the first error, not the loudest

1. `get_console_output` immediately after `start_stop_play`.
2. The **first** error is usually the cause; later ones are cascade. Stack
   traces in Studio show the throw site, not the origin - follow the data.
3. `nil` index errors are almost always a load-order problem. Check whether the
   profile/character actually existed when the code ran (see the
   `SetupPlayer`-after-profile rule in `architecture.md`).
4. "Infinite yield possible on X" means a `WaitForChild` for something the
   server never creates. Do not add a longer timeout; find the missing instance.
5. Re-run the *same* scenario after the fix. A different path proves nothing
   about the one that broke.

## Geometry tests run against a world that does not exist yet

The world builder is asynchronous. A route or clearance test fired immediately
after `start_stop_play` reports hundreds of failures that all mean "nothing has
been built": 126 failures across five plots in one run, zero after the same test
waited for `workspace:GetAttribute("WorldReady")`. Start every geometry test
with a bounded wait for the ready flag, then assert it.

Make the assertion carry the detail. `assert(#failures == 0, "6 checks failed")`
costs another whole play cycle to diagnose; embedding the first six failure
strings in the message turned that round trip into a five-second read.

## Count the HUD, do not just photograph it

A screenshot proves the HUD looks right; instance counts prove it finished
building. A third-person HUD that stopped halfway still photographs as a HUD, and
a failed require leaves an empty PlayerGui that photographs as nothing at all.
Report both every time: `hud=true frames=467 labels=151`, `visor panes=6`,
`drone parts=12`. If a count is zero, the module threw or never ran, no matter
how good the picture looks.

Read the errors the same way: `LogService:GetLogHistory()` on the Client
datamodel, filtered to `MessageError`, is the only cheap way to prove a client
script is clean without dumping the whole Studio console into context.

## Server tests must report themselves

`rbforge servertest` (`live.server_test`, and anything built on it) runs your file as a temporary
`Script` in a live Play session and waits for an attribute. The file has to write the verdict, on
`workspace` or on its own Script:

```lua
workspace:SetAttribute("RbforgeTest", ok and ("PASS " .. detail) or ("FAIL " .. detail))
-- or
script:SetAttribute("RbforgeTest", ok and ("PASS " .. detail) or ("FAIL " .. detail))
```

A file that merely `return`s a value reports nothing: it was silently a 120 s `TIMEOUT`, which reads
as "the test hung" instead of "the test never reported". The runner returns
`INVALID: the test never calls SetAttribute` immediately - if you see `TIMEOUT`, check that the
attribute name in the test matches the one the runner passes (`test_attr`, default `RbforgeTest`).

What the runner does (all verified live, 2026-11-16):

- **Play first.** It asks `get_studio_state` before anything else; in Edit mode it refuses with
  `RBF-PLAY-001 start Play first` (exit 4) instead of a datamodel error.
- **Readiness.** `--ready "workspace.BootStage=players-wired"` waits until that attribute on that
  instance equals the value before the test starts, inside the same timeout. Not reached ->
  `NOT_READY ...`, a failure.
- **Client tests.** `--dm Client` runs the file as a `LocalScript` in the local player's
  `PlayerScripts`.
- **Cleanup kills deferred work.** The runner destroys the test Script once the result is set.
  Destroying a Script kills every thread it started - `task.delay`, `task.spawn`, and deferred work
  the test triggered inside game code, such as a delayed body removal after a kill. `Parent = nil`
  and `Disabled = true` kill them too (all checked live). Keep test cleanup synchronous, or pass
  `--grace <seconds>` to wait after the result before destroying, or `--keep` to leave the Script
  (stopping Play discards it).
- **Suites.** `rbforge servertest --suite suites.json` runs every suite in one Studio session, prints
  one line per suite on stderr, emits the JSON report on stdout, and exits with the number of failed
  suites (a refused run, such as Edit mode, still exits with its error code):

```json
{"suites": [
  {"file": "tests/Combat.server.luau", "attr": "CombatTest", "timeout": 60},
  {"file": "tests/Hud.client.luau", "attr": "HudTest", "datamodel": "Client"},
  {"file": "tests/Ragdoll.server.luau", "attr": "RagdollTest", "grace": 3,
   "ready": "workspace.BootStage=players-wired", "name": "ragdoll cleanup"}
]}
```

Paths are relative to the manifest. `datamodel` is `Server` (default) or `Client`; `timeout`
defaults to 120.

## Live-suite patterns from a second production project (live 2026-11)

- **Suites change the world; order the manifest.** A suite that clears enemies, resets a profile
  or leaves the hero in a guard state changes what the next one sees. Put the suite that asserts a
  fresh state (boot) first, and say in the manifest's names which suites leave the place changed
  (after a full run the valley was empty of enemies until Play restarted).
- **Client auto-behaviour fights server-side tests.** A guard the test raised on the server was
  dropped a frame later because the client controller releases the guard when the key is not
  held; the test timed out "waiting for the blocked hit". Give such controllers a Studio-only
  player attribute (`DebugHandsOff`) that the test sets and the controller honours only when
  `RunService:IsStudio()`, instead of weakening the test.
- **Walk the character the way the engine does.** Replacing an input module's `move` function did
  not move the hero: the engine's control script drives the `Humanoid`. A client test that needs
  walking calls `humanoid:Move(direction)` from a `BindToRenderStep` callback bound after the
  input priority, then asserts the distance walked.
- **Prove persistence across a real Play restart.** A save read back in the same session proves
  little (caches, the same server). The manifest lists the persistence suite twice: last ("run 1
  of 2": build a profile through the real services, save, record a checksum and a mark), and first
  ("run 2 of 2": the new session loads it and compares). Stop and start Play between two manifest
  runs. Anything that resets the profile between the runs destroys the mark, so the evidence needs
  two consecutive runs.
- **Stage scenes, then let a bot play them.** A fight driven by MCP keystrokes is lost to tool-call
  latency: a hero idling in an enemy camp's sight died in about ten seconds, and every later attempt
  depended on timing the agent does not control. Keep stage scripts in `tools/stage/` (or named
  stages in a dev service) that set the hour, the weather and the hero's spot, and say in their
  output when they change difficulty. Then drive the scene with a Pilot (next section), not with
  keystrokes. A stage is a fixture, never proof of the thing it shortcuts. Order matters inside a
  stage too: a reset that wipes the profile must run before the step that marks the tutorial skipped.

## Proving it in one Studio instance (second production project, live 2026-11)

The owner of that project works in one Studio window and forbade anything that opens more: no
`StudioTestService:ExecuteMultiplayerTestAsync`, no Test -> "Server & Clients", no second copy of the
place. Everything below makes multiplayer, input-driven and long-timer behaviour provable inside the one
Play session anyway. Ask the owner before opening windows; never assume.

**QA slots: a disposable save that cannot touch the owner's.** A Studio-only attribute set in Edit
before Play (`ServerStorage.QaSlot`) picks the save: `"mem"` reads and writes nothing (an in-memory
store), `"t-<task>"` gives a fresh save that still persists across Play restarts, unset is the owner's
own returning character. The refusal lives in the code every test goes through: with no slot set,
`DataService.wipe` returns false and the dev reset returns nil, so no suite can replace the owner's
save. Slot the shared-world documents the same way (a key suffix `@<slot>`), and refuse `save_place`
while a slot or a stage's Edit changes are in the place.

**Puppets: the second to eighth player.** Make services take a `Who`: a connected `Player` or an actor
table with the same four fields services read (`UserId`, `Parent`, `Character`, how to message it) and
an inbox in place of a client. A puppet then fights, trades, loots and dies through the same code path
as a player, and what a client would have been sent lands in `actor.inbox` for the suite to assert.
Drive a puppet by calling the function a remote handler calls after validation; prove the handler's
validation separately with hostile arguments (wrong types, out of range, stale request id, another
actor's id). Every multi-party feature gets: the happy path, each party cancelling at each step, one
party leaving at each step, the same request twice, and a conserved-totals check (items and currency
across every pack, mailbox and document before and after).

**The Pilot: real input without a person.** A Studio-only client module that reads only what a player
can see (positions, replicated state attributes, prompts) and acts only through the player's own
routes:

- buttons through the authored input actions: `InputBinding:Fire(state)` on a binding whose `Type` is
  `Enum.InputBindingType.Scriptable` (`InputAction:Fire` is marked deprecated in the reference);
- walking through `Player:Move(direction, relativeToCamera)` from a render step bound after the stock
  control script. Measured: firing the `Move` action alone set its state and moved nobody (0.00 studs
  in a second); `Player:Move` walked 19.0 studs;
- looking through the look-stick action the camera already reads.

It never calls a remote, a service or `Humanoid:MoveTo`. Give it policies: a careful one (guards what
is telegraphed, parries what it can see, heals when hurt) and a reckless one (never defends). A fight
only the careful policy wins is tuned right, one the reckless policy wins is too easy, one the careful
policy loses three times in five is too hard - a difficulty oracle you can rerun at every commit. Know
its limits (straight-line walking, weaker than a person against several enemies) and write them down.
A client suite requires the Pilot from `PlayerScripts` and asks the server for fixtures through a
Studio-only `RemoteFunction`.

**A game Clock for anything longer than a minute.** Weather fronts, respawns, cooldowns, crops, jail
terms: read `Clock.now()` (server time plus a skip held in a workspace attribute, so clients agree),
never `os.clock()`. A suite calls `Clock.advance(86400)` instead of waiting a day. Keep animation and
sky stamps on raw server time: they are measured in frames and must not jump. Without `game` (under
Lune) the Clock keeps the skip in a local, so pure rules can be specced with time moving.

**Fixtures that outlive the test.** Threads a `servertest` script starts die when it reports (see the
cleanup rule above). A fixture that must keep running (enemies thrown down a stair every nine seconds,
a staged event) lives in a dev service, driven from a connection the service owns, and the test only
asks for it by name.

**The proof ladder, cheapest first:** Lune spec (pure rules, shared state on an in-memory port, the
Clock advanced) -> server suite with puppets -> client suite with the Pilot -> capture inspected ->
the owner plays it. Use the cheapest rung that can actually fail for the thing claimed. A receipt
names the commit it proved; a small script can refuse a receipt whose `src`/`tests` files differ
between that commit and `HEAD`.

## Place test units at their own level

A ground ray cast from high above a spawn point lands on whatever is on top: roofs, crane beams,
canopies. A unit spawned there walks off the edge and falls out of the map, and the test fails in a
way that looks like an AI bug. Cast a short ray at the unit's own level (start a few studs above the
intended floor, not at the sky) and set `RespectCanCollide = true` so trigger volumes and decorative
non-collidable parts are ignored:

```lua
local params = RaycastParams.new()
params.FilterType = Enum.RaycastFilterType.Exclude
params.FilterDescendantsInstances = { unit }
params.RespectCanCollide = true
local hit = workspace:Raycast(spawnPos + Vector3.new(0, 4, 0), Vector3.new(0, -12, 0), params)
```


## The MCP sandbox has its own `require` cache

Code executed through the MCP's Luau sandbox gets a **separate module cache** from the running server.
`require(ServerScriptService.Systems.DataManager)` there returns a fresh copy: it answers an empty
`Profiles` table even while the game's HUD shows a loaded profile, and mutations you make in the
sandbox are invisible to the game. Two consequences:

- A test that needs live server state (a profile, an assigned plot, a spawned enemy) must run as a
  real `Script` in `ServerScriptService`, not through the sandbox.
- Do not diagnose "the game is broken" from a sandbox read of module state. Cross-check with
  something the game writes: a `leaderstats` value, a workspace attribute, or the HUD text.

An earlier Studio build refused `Script.Source` from the sandbox in Play mode
(`cannot read 'Source' (lacking capability PluginOrOpenCloud)`). Re-checked 2026-11-16: creating a
Script and reading or setting its `Source` in the Server datamodel works, which is how `servertest`
injects a test. If your build refuses it, push the test from disk (Rojo mapping + `rb_studio_push`)
before Play starts.

## A cold-start `NoPath` can be a navmesh bake - but it is still a failure if it persists

`PathfindingService` bakes asynchronously, so a route computed the instant the world signals ready can
answer `Enum.PathStatus.NoPath` even though the geometry is fine. Two rules keep this honest:

- **Wait for the world's own ready signal first** (an attribute the builder sets after the last part
  exists), then start the clock.
- **Retry a bounded, configurable number of times** - 12 attempts x 0.5 s was measured sufficient for
  six plots on one map; log the attempt that first succeeded so the budget stays evidence-based.
- **After the window, `NoPath` is a real defect**, reported with the start/end positions and the
  attempt count - never silently downgraded to a pass. A geometry regression and a slow bake look
  identical on the first frame and completely different after the window.

Do not assume "it becomes available after a couple of minutes" - that observation came from a warm
server where the route had been computed before. Measure on a cold Play, then set the budget.

## A clean static pass is not a working game

`rbforge check` passing means formatting, lint and types are clean. It says nothing about network
ownership, multiplayer authority, mobile layout, or frame time. Evidence for those comes from a played
session: a test that exercises the remotes, a capture at the target resolution, and a MicroProfiler
run when performance is claimed. Report them separately, and never let a green gate stand in for one.
