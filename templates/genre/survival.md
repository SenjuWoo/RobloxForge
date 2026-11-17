# Survival / extraction vertical-slice recipe

Core loop: leave the safe zone -> gather one resource -> carry it back at risk -> bank it -> craft one upgrade -> go out again better equipped.

Who owns what:
- carried and banked inventory: server
- resource nodes and loot: server
- crafting and damage: server
- prompts and inventory display: client

First playable proof (build in this order, on top of the starter kit `rbforge new` wrote):
1. Two inventories per player: carried (lost on death) and banked (saved)
2. ONE resource node: the server checks range, grants once, then starts a respawn timer
3. ONE hostile between the safe zone and the resource
4. Banking at home: the server checks the player is alive and inside the zone
5. ONE recipe that spends banked resources and changes a stat the player can feel
6. Death drops or clears what was carried; the bank is untouched

Prove it:
- a node cannot be harvested from out of range or twice before it respawns
- death loses the carried resources and keeps the banked ones
- banking from outside the safe zone is refused
- crafting deducts exactly once and the stat change is visible
- banked resources survive a rejoin (if persistence is in the slice)
- console clean

Only after this works: more resources and recipes, base building, storage, more enemy types, day/night pressure, PvP rules. Trading and shared storage need session-locked saves first.
