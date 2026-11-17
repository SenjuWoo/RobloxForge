"""Vertical-slice planning: turn a premise into the smallest provable loop.

Weak-model-first: this is a deterministic template filler, not a creative
act. It reduces decision entropy so a cheap model starts building the right
thing.
"""
from .errors import ForgeError

_SLICES = {
    "obby": {
        "core_loop": "spawn -> clear obstacles -> reach checkpoint -> die -> respawn at checkpoint",
        "authority": {"progression (stage number)": "server",
                      "death handling": "server",
                      "HUD display": "client"},
        "build": [
            "SpawnLocation + flat baseplate area",
            "2-3 distinct obstacle parts (gap jump, moving/lava block, narrow beam)",
            "Checkpoint part with Tag 'Checkpoint' + order attribute",
            "Server Script: Touched on checkpoint -> set player stage attr; "
            "CharacterAdded -> teleport to current checkpoint",
            "Kill parts (Tag 'Hazard') with debounced Touched -> Humanoid.Health = 0",
            "Minimal HUD: Stage label updated via RemoteEvent or attribute watcher",
        ],
        "verify": [
            "walk to checkpoint 1 - stage becomes 1",
            "die on hazard - respawn AT checkpoint 1, not spawn",
            "reach finish - completion fires",
            "console clean through all of the above",
        ],
    },
    "simulator": {
        "core_loop": "perform action -> server grants reward -> HUD updates -> buy 1 upgrade -> action yields more",
        "authority": {"currency balance": "server", "upgrade effects": "server",
                      "click feedback": "client"},
        "build": [
            "Server Currency module (authoritative balance)",
            "One action input -> remote with rate limiting -> server grants amount",
            "HUD counter listening for balance updates",
            "ONE upgrade: server catalog, purchase validation, multiplier applied",
        ],
        "verify": [
            "action increments currency (server-checked)",
            "rapid-fire requests get rate-limited (no double income)",
            "buy upgrade -> balance decreases once -> per-action yield increases",
            "console clean",
        ],
    },
    "tycoon": {
        "core_loop": "claim plot -> earn currency -> buy dropper button -> machine spawns -> income changes",
        "authority": {"ownership/claims": "server", "purchases": "server",
                      "button prompts": "client presentation"},
        "build": [
            "One plot with claim pad (server validates free plot)",
            "Currency accrual while claimed",
            "ONE purchase button -> validated purchase -> server clones dropper model from ServerStorage",
            "Dropper emits collectible -> collector adds currency",
        ],
        "verify": [
            "second player cannot steal claimed plot",
            "buy button deducts once and spawns exactly one dropper",
            "dropper income visible in balance",
            "console clean",
        ],
    },
    "shooter": {
        "core_loop": "spawn with one weapon -> aim and fire -> server validates the shot -> target takes damage "
                     "-> target dies -> reward -> respawn",
        "authority": {"hit validation and damage": "server", "ammo and fire rate": "server",
                      "aim, recoil, tracers, muzzle flash, viewmodel": "client"},
        "build": [
            "One weapon as data in a shared config module: damage, range, fire interval, magazine size",
            "Client: input -> ray from the camera -> immediate local tracer and sound -> "
            "FireServer(aim direction) - a direction, never a damage number or a hit target to trust",
            "Server: weapon equipped, fire interval elapsed, ammo left -> re-cast the ray from the "
            "character's own position, range clamped -> Humanoid:TakeDamage on what the server hit",
            "One static target with a Humanoid, then one moving target",
            "Reload: ammo is a server value published as an attribute",
            "Death -> reward once -> respawn",
        ],
        "verify": [
            "firing faster than the fire interval is refused (count the shots the server accepted)",
            "a shot through a wall does no damage",
            "a request with an origin far from the character is refused or ignored",
            "ammo never goes below zero; reload restores it",
            "a kill grants the reward exactly once",
            "console clean",
        ],
    },
    "round": {
        "core_loop": "lobby -> enough players -> intermission countdown -> teleport to the map -> round timer "
                     "-> win condition -> results -> cleanup -> lobby",
        "authority": {"round state machine and timer": "server", "who is in the round": "server",
                      "countdown and results display": "client (reads replicated state)"},
        "build": [
            "One server module that owns the state (Lobby, Intermission, Playing, Results), published as "
            "attributes on workspace: state name and end time",
            "Minimum player count, with a solo override that only works in Studio",
            "Start: teleport participants to map spawns; late joiners stay in the lobby",
            "ONE win condition (last alive, or highest score when the timer ends)",
            "Cleanup: return everyone, destroy everything the round created, reset per-round state",
            "Client: countdown and state label driven by the attributes",
        ],
        "verify": [
            "two full cycles run back to back without restarting the server",
            "a player who dies is not put back into the running round",
            "a participant leaving mid-round does not hang the round",
            "nothing created by the round is left after cleanup (count the instances)",
            "the solo override is refused outside Studio",
            "console clean",
        ],
    },
    "towerdefense": {
        "core_loop": "place one tower with currency -> a wave spawns -> enemies follow the path -> the tower "
                     "attacks -> enemy dies -> currency -> a leak costs base health -> next wave",
        "authority": {"placement (cost, bounds, overlap)": "server", "enemy position and health": "server",
                      "base health and wave state": "server", "placement preview": "client"},
        "build": [
            "The path as ordered waypoint parts authored in the place",
            "Enemies as data on the server (distance along the path, health) moved every step; one "
            "anchored model each, no Humanoid and no PathfindingService",
            "ONE tower type: range check and attack interval run on the server",
            "Placement remote: the server checks cost, that the cell is free and off the path",
            "Waves from a config table; the next wave starts when the current one is cleared",
            "Base health; reaching the last waypoint removes the enemy and costs health once",
        ],
        "verify": [
            "a tower cannot be placed on the path, on another tower, or without the currency",
            "an enemy reaching the end reduces base health exactly once",
            "wave 2 starts after wave 1 is cleared and not before",
            "50 enemies alive: measure the server step time and record it",
            "console clean",
        ],
    },
    "rpg": {
        "core_loop": "accept one quest -> defeat N of one enemy -> gain XP and loot -> level up -> a stat grows "
                     "-> turn the quest in",
        "authority": {"quest progress, XP, level, inventory": "server", "damage and kill credit": "server",
                      "dialogue and quest tracker": "client"},
        "build": [
            "A pure stats module (XP needed per level, damage formula) with an offline spec",
            "One enemy type with a spawner that respawns it",
            "One melee attack: the server checks range and cooldown, then applies damage",
            "Quest state per player from a data table; a ProximityPrompt on the quest giver",
            "Level up applies the stat change once and publishes it",
            "Save level, XP and quest state - or decide in writing that slice 1 does not persist",
        ],
        "verify": [
            "XP comes only from kills the server confirmed, and goes to the player who dealt the damage",
            "the quest counter cannot pass its target or count another player's kills",
            "a level up applies its stat change exactly once",
            "attacking from out of range or faster than the cooldown is refused",
            "rejoin restores level and quest state (if persistence is in the slice)",
            "console clean",
        ],
    },
    "horror": {
        "core_loop": "enter -> find the key item -> a door unlocks -> one scripted scare -> reach the exit "
                     "while the threat hunts",
        "authority": {"item and door state": "server", "the threat's position and kills": "server",
                      "flashlight, camera effects, sound": "client"},
        "build": [
            "A small authored map with one dark lighting preset and one light the player carries",
            "ONE pickup through a ProximityPrompt: the server records that this player has it",
            "A locked door that opens only when the server sees the item",
            "ONE trigger volume that fires a scare once per player",
            "ONE chaser: pathfinding to the player, line of sight, a kill on contact",
            "Death -> respawn at a checkpoint with item state as designed",
        ],
        "verify": [
            "the door stays shut without the item, including when the prompt is fired from far away",
            "the scare fires once per player, not once per touch",
            "the chaser reaches a player who is standing around a corner",
            "the map is readable at the lowest graphics quality (not pitch black)",
            "console clean",
        ],
    },
    "survival": {
        "core_loop": "leave the safe zone -> gather one resource -> carry it back at risk -> bank it -> craft "
                     "one upgrade -> go out again better equipped",
        "authority": {"carried and banked inventory": "server", "resource nodes and loot": "server",
                      "crafting and damage": "server", "prompts and inventory display": "client"},
        "build": [
            "Two inventories per player: carried (lost on death) and banked (saved)",
            "ONE resource node: the server checks range, grants once, then starts a respawn timer",
            "ONE hostile between the safe zone and the resource",
            "Banking at home: the server checks the player is alive and inside the zone",
            "ONE recipe that spends banked resources and changes a stat the player can feel",
            "Death drops or clears what was carried; the bank is untouched",
        ],
        "verify": [
            "a node cannot be harvested from out of range or twice before it respawns",
            "death loses the carried resources and keeps the banked ones",
            "banking from outside the safe zone is refused",
            "crafting deducts exactly once and the stat change is visible",
            "banked resources survive a rejoin (if persistence is in the slice)",
            "console clean",
        ],
    },
    "generic": {
        "core_loop": "player spawns -> performs the core action -> server responds -> visible feedback",
        "authority": {"any persistent state": "server", "input/effects": "client"},
        "build": [
            "Define the single CORE ACTION first (one sentence)",
            "Server module owning the state it changes",
            "One remote carrying intent only",
            "Client presentation reacting to server events",
        ],
        "verify": ["action works end-to-end", "state survives rejoin if persisted",
                   "console clean"],
    },
}

# What people call these genres. An unknown word is an error, not a silent "generic".
_ALIASES = {
    "fps": "shooter", "tps": "shooter", "combat": "shooter", "pvp": "shooter",
    "rounds": "round", "minigame": "round", "minigames": "round",
    "td": "towerdefense", "tower-defense": "towerdefense", "tower_defense": "towerdefense",
    "wave": "towerdefense", "waves": "towerdefense",
    "adventure": "rpg", "story": "horror",
    "extraction": "survival", "crafting": "survival", "base": "survival",
    "clicker": "simulator", "incremental": "simulator",
    "parkour": "obby",
}

GENRES = ["generic"] + sorted(g for g in _SLICES if g != "generic")
GENRE_CHOICES = GENRES + sorted(_ALIASES)


def resolve(genre):
    """Canonical genre name for a genre or one of its aliases; raises RBF-ARG-001 otherwise."""
    g = (genre or "generic").strip().lower()
    g = _ALIASES.get(g, g)
    if g not in _SLICES:
        raise ForgeError("RBF-ARG-001", "unknown genre %r" % genre,
                         hint="one of: %s" % ", ".join(GENRES))
    return g


def vertical_slice(genre, premise):
    name = resolve(genre)
    g = _SLICES[name]
    return {
        "genre": name,
        "premise": premise,
        "rule": "Build ONLY step 1 of the build order. Prove every item in the "
                "verification list. Then expand one item at a time.",
        "design_gate": {
            "CORE_ACTION": premise,
            "FEEDBACK": "what does the player see/hear within 0.1s of acting?",
            "REWARD": "what grows?",
            "PROGRESSION": "what unlocks next? (for slice 1: nothing)",
            "FAILURE_FRICTION": "what stops mindless repetition? (slice 1 may defer)",
            "REASON_TO_REPEAT": "why act again? (slice 1 may defer)",
            "note": "deferred gates are fine for slice 1; they are NOT fine for release",
        },
        "core_loop": g["core_loop"],
        "authority": g["authority"],
        "build_order": g["build"],
        "verification": g["verify"],
        "anti_pattern": ("Do not create map+economy+UI+inventory in one pass. "
                         "Slice 1 is small enough to playtest within minutes."),
    }
