# Tower defense vertical-slice recipe

Core loop: place one tower with currency -> a wave spawns -> enemies follow the path -> the tower attacks -> enemy dies -> currency -> a leak costs base health -> next wave.

Who owns what:
- placement (cost, bounds, overlap): server
- enemy position and health: server
- base health and wave state: server
- placement preview: client

First playable proof (build in this order, on top of the starter kit `rbforge new` wrote):
1. The path as ordered waypoint parts authored in the place
2. Enemies as data on the server (distance along the path, health) moved every step; one anchored model each, no Humanoid and no PathfindingService
3. ONE tower type: range check and attack interval run on the server
4. Placement remote: the server checks cost, that the cell is free and off the path
5. Waves from a config table; the next wave starts when the current one is cleared
6. Base health; reaching the last waypoint removes the enemy and costs health once

Prove it:
- a tower cannot be placed on the path, on another tower, or without the currency
- an enemy reaching the end reduces base health exactly once
- wave 2 starts after wave 1 is cleared and not before
- 50 enemies alive: measure the server step time and record it
- console clean

Only after this works: more tower types, upgrades, enemy types with resistances, multiple paths, co-op placement, difficulty scaling. Enemies stay data on the server; clients draw them.
