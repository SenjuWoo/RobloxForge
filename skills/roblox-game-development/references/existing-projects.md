# Taking over an existing project

A codebase you did not write - a human's, another agent's, or your own from a weaker session - is
evidence of what was built, not of what works. The fastest way to make it worse is to copy its
patterns forward because they are already there. The second fastest is to rewrite it.

## First hour: read, measure, change nothing

```
rbforge audit .            ranked reading list: data loss, exploitable remotes, runtime faults, ...
rbforge check .            does it even pass format / lint / types / unit specs today
rbforge project .          layout, script counts, remotes, data store usage
git log --oneline | head   what changed last, and how big the changes are
```

Then in Studio, before any edit: play it, read the console from a cold start, capture the main
screens. Write down what works. That list is what you must not break.

`rbforge audit` output is ordered by what it costs a live game. Work in that order:

1. **Data loss** - a failed read treated as a new player, name-keyed stores, saves without
   `BindToClose`, purchases granted outside `ProcessReceipt`. Fix these before any feature.
2. **Exploitable** - remotes that trust client values, test/debug remotes, client-side authority,
   unfiltered player text.
3. **Runtime faults** - server/client API mix-ups, missed existing players and characters, input that
   fires through chat, per-player tables never cleared.
4. **No safety net** - no tests. Write them before refactoring (below).
5. **Structure** - monoliths, global state, untyped files.
6. **Cost** - per-frame remotes, per-frame connections, a world or UI built entirely in code.
7. **Deprecations** - fix when you touch the file.

## Before changing a system, pin what it does now

A characterization test asserts the current behaviour, right or wrong, so you can tell when you
changed it. One per system you are about to touch:

- pure logic (prices, damage, XP curves, save-data clean-up): extract it into a module with no
  engine calls and write a `tests/*.spec.luau` - it runs in milliseconds in `rbforge check`;
- live behaviour (a remote path, a spawn, an enemy kill): a `rbforge servertest` file that drives
  the real modules in Play and reports PASS/FAIL through an attribute;
- visuals: a capture from a fixed camera pose, kept for comparison.

If the system cannot be tested without changing it, that is the first change: make it callable
(export the function the remote handler calls) and nothing else.

## Refactor by strangling, never by rewriting

- **One system per change.** Change, `rbforge check`, play the scenario, commit. A commit that
  touches eight systems cannot be bisected.
- **Split along seams that already exist.** A 3,000-line HUD builder already contains a health bar,
  an inventory and a compass: move one out behind the same call, verify, then the next. Do not
  design a new architecture and port everything to it.
- **New code follows the target pattern; old code is migrated when it is touched.** Two patterns
  side by side for a while is fine; a half-finished migration of everything is not.
- **Delete, do not disable.** A second mechanism left "just in case" becomes the bug: two systems
  that both think they own a door, a save, a spawn. Pick the one that survives a fresh Play, remove
  the other, and say which in the commit.
- **Keep save data readable.** Any change to what is saved needs a schema version bump and a
  migration that is tested against a copy of real old data before it ships.
- **Never fix a symptom by adding a wait.** `task.wait(2)` before reading something is a race you
  have hidden, not removed. Wait for the signal or attribute that says it is ready.

## Patterns to question, not copy

These are common in weak-model output. Finding one is not an emergency; extending it is a choice
you should make on purpose.

| Found in the project | Ask |
|---|---|
| The whole map is built by a server script at start-up | Is it the same every session? Then build it once in Edit and save it (`architecture.md`, "Authored or generated"). Measure the build time first. |
| Thousands of lines of `Instance.new` for the UI | Can the next screen be a small component instead of more lines in the same builder? |
| Every creature has its own per-frame procedural animator | Would a clip do? If not, is there distance LOD and one shared update loop (`animation.md`)? |
| `task.wait(n)` before things "to let them load" | What signal says it is ready? |
| `pcall` around everything, result ignored | Which failure is it hiding? Log it. |
| `GameConfig` with hundreds of unrelated fields | Fine as data; split only when two systems fight over it. |
| Remote handlers that forward straight to a 200-line function | Where is the type check, the rate limit, the ownership check? `rbforge audit` lists each handler with the guards it can see. |
| A debug remote or `Debug*` attribute | Is it gated to Studio or to the creator? |
| Managers that call each other in a circle | Which one owns the state? The other asks, it does not write. |
| Recovery copies and old versions inside the repo | Leave them; `rbforge` skips `artifacts/`, `backups/`, `recovery/` and git-ignored paths. Never edit a snapshot. |

## What to tell the owner

After the first hour, report three things: what works today (with evidence), what will lose player
data or can be exploited (the tier 1-2 list, file and line), and what you propose to change first.
Do not present structural taste (tier 5) as urgent, and do not start it before tiers 1-3 are closed.
