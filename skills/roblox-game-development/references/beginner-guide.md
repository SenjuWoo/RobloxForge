# Beginner mode: the user has never made a Roblox game

Assume zero Roblox experience unless they show otherwise. That does not mean
asking them to learn the engine — it means **you operate Studio for them** and
narrate in plain language. They describe the game they want; you build, test and
report.

## What you do vs what they do

| You (the agent) | The user |
|---|---|
| open/inspect the place, build everything, playtest, fix, screenshot | describe the game in their own words |
| choose the architecture and file layout | say whether it feels right when asked |
| run every command and tool call | click "Enable MCP" once in Studio (it is an editor-side setting no tool can flip) |
| explain what changed in one plain sentence | approve anything that costs money (you should never need to) |

Never hand them code to paste. Never say "add a RemoteEvent and wire it" — that
is your job. If they must do something, it is one click and you say exactly
where that click is.

## Session one, start to finish

1. **Confirm Studio is open with a place.** "A place" = the 3D world file; a
   blank Baseplate is fine. You check with `rb_doctor`; if no place is open, say
   "open Studio, New → Baseplate, then tell me" — one instruction, nothing else.
2. **Confirm the MCP toggle.** Studio → Assistant → `...` → Manage MCP Servers →
   *Enable Studio as MCP server*. If `rb_doctor` says the handshake fails, that
   is the step to mention, with those exact words.
3. **Get one sentence of intent.** If they say "a game where you collect
   coins", do not ask what engine or framework. Translate it yourself:
   obby/simulator/tycoon, one loop, one reward.
4. **Probe the place.** `search_game_tree` before writing anything.
5. **Gate.** `rbforge check .` — cheap, catches typos before a 20-second boot.
6. **Build the smallest playable slice** (see `development-loop.md`):
   spawn → first action → reward → feedback on screen.
7. **Playtest** with `start_stop_play`, read `get_console_output`, fix errors.
8. **Screenshot** with explicit camera framing, look at it, fix what reads badly.
9. **Report in three lines:** what works (tested), what you did not verify, what
   is next. No jargon unless they asked.

## Translate their words into work

| They say | You build |
|---|---|
| "collect coins" | a part with a touch handler, server-side counter, HUD number |
| "it should feel fast" | walk speed, camera FOV kick, movement accel |
| "make it look nice" | one lighting preset + a consistent 4-colour palette |
| "a shop" | one `ProximityPrompt`, one server-validated purchase, one UI list |
| "multiplayer" | server authority first; remotes only after single-player works |
| "it keeps crashing" | `get_console_output`, first error, smallest fix, re-test |

## Vocabulary, if they ask

Only when asked. One line each, no lecture.

- **Place** — the world file you edit and publish.
- **Part** — a 3D block; everything solid is some kind of part.
- **Script** — code that runs inside the place.
- **Server / client** — the shared truth vs each player's own screen. You keep
  money and damage on the server; this is not negotiable.
- **Playtest** — running the game inside Studio to see if it actually works.
- **RemoteEvent** — the one safe way for a client to ask the server for something.

## Beginner traps you must absorb for them

- **Trying to build everything at once** → they get a half-finished game. Slice
  first, always.
- **Trusting the client** → any counter on the client can be edited; currency,
  damage and inventory live on the server.
- **`WaitForChild` on something that never loads** → infinite yield; the item
  does not exist, a longer wait does not fix it.
- **Unanchored parts** → the map falls apart on play. `rbforge check` flags this
  before you ever press play.
- **Selling/buying assets early** → nothing in this workflow needs a purchase;
  see `free-stack.md`.
- **Publishing before testing** → publish only after a clean playtest and a
  screenshot you actually looked at.

## When they ask "is it done?"

Three lines, in this order:

1. **Tested:** what you personally exercised in a playtest, and the result.
2. **Not verified:** anything you could not run (no vision, no playtest
   capability, feature not yet built).
3. **Next:** the single next slice.

If the honest answer is "it exists but I have not played it", say exactly that.
A beginner cannot tell the difference between "built" and "works" — so never let
that gap be yours to hide.
