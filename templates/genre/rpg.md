# RPG vertical-slice recipe

Core loop: accept one quest -> defeat N of one enemy -> gain XP and loot -> level up -> a stat grows -> turn the quest in.

Who owns what:
- quest progress, XP, level, inventory: server
- damage and kill credit: server
- dialogue and quest tracker: client

First playable proof (build in this order, on top of the starter kit `rbforge new` wrote):
1. A pure stats module (XP needed per level, damage formula) with an offline spec
2. One enemy type with a spawner that respawns it
3. One melee attack: the server checks range and cooldown, then applies damage
4. Quest state per player from a data table; a ProximityPrompt on the quest giver
5. Level up applies the stat change once and publishes it
6. Save level, XP and quest state - or decide in writing that slice 1 does not persist

Prove it:
- XP comes only from kills the server confirmed, and goes to the player who dealt the damage
- the quest counter cannot pass its target or count another player's kills
- a level up applies its stat change exactly once
- attacking from out of range or faster than the cooldown is refused
- rejoin restores level and quest state (if persistence is in the slice)
- console clean

Only after this works: more quests, a quest chain, equipment slots, skills, zones, bosses, parties, trading (trading needs session-locked saves first).
