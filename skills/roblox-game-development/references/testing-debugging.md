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

`live.server_test` (and anything built on it) runs your file as a temporary `Script` in a live Play
session and waits for an attribute. The file has to write the verdict:

```lua
workspace:SetAttribute("RbforgeTest", ok and ("PASS " .. detail) or ("FAIL " .. detail))
```

A file that merely `return`s a value reports nothing: it was silently a 120 s `TIMEOUT`, which reads
as "the test hung" instead of "the test never reported". Newer builds return
`INVALID: the test never sets workspace:<attr>` immediately - if you see `TIMEOUT`, check that the
attribute name in the test matches the one the runner passes (`test_attr`, default `RbforgeTest`).


## The MCP sandbox has its own `require` cache

Code executed through the MCP's Luau sandbox gets a **separate module cache** from the running server.
`require(ServerScriptService.Systems.DataManager)` there returns a fresh copy: it answers an empty
`Profiles` table even while the game's HUD shows a loaded profile, and mutations you make in the
sandbox are invisible to the game. Two consequences:

- A test that needs live server state (a profile, an assigned plot, a spawned enemy) must run as a
  real `Script` in `ServerScriptService`, not through the sandbox.
- Do not diagnose "the game is broken" from a sandbox read of module state. Cross-check with
  something the game writes: a `leaderstats` value, a workspace attribute, or the HUD text.

Setting `Script.Source` from the sandbox is refused in Play mode
(`cannot read 'Source' (lacking capability PluginOrOpenCloud)`), so a live test has to be pushed to
the place from disk (Rojo mapping + `rb_studio_push`) before Play starts.

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
