# Optimization levels: apply the one the project has earned

Performance advice fails in two directions: a beginner's obby gets an Actors pipeline it never needed,
or a 60-player city gets "keep it simple". Pick the level from evidence about *this* project, not from
the ambition of the prompt.

## Level A — always

Every project, including a 40-line obby:

- server owns truth; client owns input and presentation
- module boundaries that match the ownership split
- `--!strict` where the file is non-trivial
- connections, instances and threads cleaned up on death/respawn
- no work per frame that only needs to happen on change
- client requests validated (type, range, distance, ownership, cooldown)
- the feature actually works: played, console read, screenshot inspected

Level A is not optional and it is not "optimization" - it is the difference between a project that
survives its first feature request and one that does not.

## Level B — only when the feature asks for it

Activate on evidence from the request, the DataModel or the source:

| Evidence | Then apply |
|---|---|
| Large map, distant content, long draw distance | streaming, streaming-safe code, model streaming modes |
| Hundreds of parts moving or colliding | assembly simplification, collision groups, network ownership |
| Remote traffic every frame or per player per tick | batching, event-driven updates, payload size |
| Dozens of NPCs with pathfinding | scheduling, staggered updates, population caps |
| Geometry generated at runtime | budgets, chunking, reuse, deterministic seeds |
| UI-heavy game | layout cost, tween vs rebuild, device scaling |
| Saved progression | `UpdateAsync` correctness, session locking, migration path |
| Big asset inventory | preload selectively, reuse meshes and materials |

Say why a level-B technique is on: "streaming is on because the map is 4k studs across" beats a
generic checklist.

## Level C — profiling first, always

Require a measurement before any of these:

- parallel Luau / Actors
- native compilation
- custom binary protocols over buffers
- aggressive pooling or custom schedulers
- hand-rolled caches
- major geometry restructuring
- framework migration

Each of them adds synchronization, memory and debugging cost. Without a before/after number you cannot
tell whether it helped, and the added complexity is real either way.

## No universal budgets

There is no texture size, mesh count, part count or FPS number that is correct for every game. Record
what was measured and against what target: device tier, graphics level, player count, duration. A
1024×1024 texture is right for one asset and wrong for another; 60 FPS is a useful target, not proof.

When a user asks "is this optimized", the honest answer is a measurement or "not measured yet".

## Choosing the level in one pass

1. Read the request and the project description.
2. Look at the DataModel (services, part counts, streaming settings) and the source (remotes, loops,
   parallel patterns).
3. Name the two or three systems that dominate this project's cost.
4. Apply level A everywhere, level B on those systems only.
5. Write down what level C would need measured before anyone touches it.

If evidence is missing, use the conservative general profile and revise it as soon as the project
shows what it is.
