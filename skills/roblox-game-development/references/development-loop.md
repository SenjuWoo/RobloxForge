# Roblox development loop — weak-model-safe vertical slices

The fastest path to a good Roblox game is **not** implementing the whole design.
It is proving one complete loop and expanding from evidence.

## Universal loop

1. **Inspect** the current place. Never assume blank Baseplate.
2. **State the player loop** in one sentence.
3. **Choose the smallest playable slice** that proves it.
4. **Assign authority**: server truth, client input/presentation, shared contracts.
5. **Build only that slice.**
6. **Playtest the actual scenario.**
7. **Read Output / runtime state.**
8. **Capture the viewport and inspect it if vision exists.**
9. **Fix the first real failure.**
10. Repeat until the slice is proven; only then expand.

## Obby slice

Spawn -> 2-3 obstacles -> checkpoint -> die -> respawn at checkpoint -> finish.

Do not build 50 stages before checkpoint/respawn is proven.

## Simulator slice

Perform action -> server validates -> server grants reward -> UI reflects truth ->
buy one upgrade -> upgrade changes action/reward -> repeat.

Do not add pets/rebirths/shops before this loop works.

## Tycoon slice

Claim plot -> obtain currency -> buy one button -> one machine appears ->
machine changes income -> UI updates -> reset/rejoin behavior understood.

## Combat/RPG slice

Spawn -> acquire/equip one ability -> attack one NPC -> server validates hit ->
damage applies -> NPC dies -> reward granted -> respawn/reset works.

## Round game slice

Lobby -> minimum players/solo test override -> intermission -> map/round start ->
win condition -> round cleanup -> results -> return to lobby.

## UI-heavy game slice

Open screen -> perform one meaningful action -> server accepts/rejects ->
UI shows authoritative result -> resize/device check -> close/reopen retains expected state.

## Expansion gate

Before adding a major system, answer:

- What already works?
- What evidence proves it?
- What new player loop does this feature add?
- Can the new loop be tested in under a few minutes?

If the previous loop is still broken, do not expand.

## Delegating build work (second production project, 2026-11)

A long project goes faster when cheaper agents take the work they can finish from a complete brief,
and slower when they collide. What held up:

| Work | Hand it to | The brief carries |
|---|---|---|
| "Where is X used?", call sites before a refactor | a search agent | the names, the folders, "paths and line numbers only" |
| an API, limit or release note to look up | a research agent | the exact question, the primary sources allowed; the answer is recorded with its source |
| a pure-rules module and its Lune spec from a written spec section | a build agent | the spec section, the file paths, an existing rules module as the shape, the spec command to pass; "do not touch Studio" |
| content tables, Blender pack scripts, receipts and changelog text | a cheaper agent | the source section, the type or schema it must satisfy, the command that checks it |
| anything that calls Studio: push, Play, suites, captures, builders, `save_place` | the main session, one call at a time | - |
| a service, its remote handler and its live suite; tuning; a red suite | the main session | - |

- Workers get disjoint paths and never the integrator's files (the loader's service list, the remote
  registry, the profile schema, the suite manifest, the asset id table).
- A worker returns a diff plus the command that proves it; the main session runs that command itself
  before accepting.
- There is one Studio and one operator: nothing that touches Studio is delegated or run in parallel.
- If delegation fails (a provider out of credits did, once), do the work inline and move on.
