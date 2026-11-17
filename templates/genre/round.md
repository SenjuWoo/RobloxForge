# Round game vertical-slice recipe

Core loop: lobby -> enough players -> intermission countdown -> teleport to the map -> round timer -> win condition -> results -> cleanup -> lobby.

Who owns what:
- round state machine and timer: server
- who is in the round: server
- countdown and results display: client (reads replicated state)

First playable proof (build in this order, on top of the starter kit `rbforge new` wrote):
1. One server module that owns the state (Lobby, Intermission, Playing, Results), published as attributes on workspace: state name and end time
2. Minimum player count, with a solo override that only works in Studio
3. Start: teleport participants to map spawns; late joiners stay in the lobby
4. ONE win condition (last alive, or highest score when the timer ends)
5. Cleanup: return everyone, destroy everything the round created, reset per-round state
6. Client: countdown and state label driven by the attributes

Prove it:
- two full cycles run back to back without restarting the server
- a player who dies is not put back into the running round
- a participant leaving mid-round does not hang the round
- nothing created by the round is left after cleanup (count the instances)
- the solo override is refused outside Studio
- console clean

Only after this works: more maps, map voting, teams, game modes, spectating, round rewards and persistence.
