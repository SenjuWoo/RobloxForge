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


def vertical_slice(genre, premise):
    g = _SLICES.get((genre or "").lower())
    if not g:
        raise ForgeError("RBF-ARG-001", "unknown genre %r" % genre,
                         hint="one of: %s" % ", ".join(sorted(_SLICES)))
    return {
        "genre": genre.lower(),
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
