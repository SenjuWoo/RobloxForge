# Horror vertical-slice recipe

Core loop: enter -> find the key item -> a door unlocks -> one scripted scare -> reach the exit while the threat hunts.

Who owns what:
- item and door state: server
- the threat's position and kills: server
- flashlight, camera effects, sound: client

First playable proof (build in this order, on top of the starter kit `rbforge new` wrote):
1. A small authored map with one dark lighting preset and one light the player carries
2. ONE pickup through a ProximityPrompt: the server records that this player has it
3. A locked door that opens only when the server sees the item
4. ONE trigger volume that fires a scare once per player
5. ONE chaser: pathfinding to the player, line of sight, a kill on contact
6. Death -> respawn at a checkpoint with item state as designed

Prove it:
- the door stays shut without the item, including when the prompt is fired from far away
- the scare fires once per player, not once per touch
- the chaser reaches a player who is standing around a corner
- the map is readable at the lowest graphics quality (not pitch black)
- console clean

Only after this works: more rooms and keys, a second threat with different rules, stamina and hiding, chapters, co-op. Scares are scripted once each; the chaser's rules must be learnable.
