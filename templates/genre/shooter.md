# Shooter vertical-slice recipe

Core loop: spawn with one weapon -> aim and fire -> server validates the shot -> target takes damage -> target dies -> reward -> respawn.

Who owns what:
- hit validation and damage: server
- ammo and fire rate: server
- aim, recoil, tracers, muzzle flash, viewmodel: client

First playable proof (build in this order, on top of the starter kit `rbforge new` wrote):
1. One weapon as data in a shared config module: damage, range, fire interval, magazine size
2. Client: input -> ray from the camera -> immediate local tracer and sound -> FireServer(aim direction) - a direction, never a damage number or a hit target to trust
3. Server: weapon equipped, fire interval elapsed, ammo left -> re-cast the ray from the character's own position, range clamped -> Humanoid:TakeDamage on what the server hit
4. One static target with a Humanoid, then one moving target
5. Reload: ammo is a server value published as an attribute
6. Death -> reward once -> respawn

Prove it:
- firing faster than the fire interval is refused (count the shots the server accepted)
- a shot through a wall does no damage
- a request with an origin far from the character is refused or ignored
- ammo never goes below zero; reload restores it
- a kill grants the reward exactly once
- console clean

Only after this works: more weapons, attachments, classes, maps, killstreaks, matchmaking. For competitive movement and hit registration read the engine's server-authority mode before building your own (`rb_docs_read projects/server-authority/index.md`).
