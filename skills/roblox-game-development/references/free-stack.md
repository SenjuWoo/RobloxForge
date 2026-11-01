# The free stack: $0, no purchases, no subscriptions

RobloxForge must never require anything that costs money. Not a plugin, not a
marketplace asset, not an audio pack, not a subscription. Everything below is
free, built into Studio, or open source.

**Hard rule:** never spend Robux or money on the user's behalf, and never tell
them a purchase is needed to finish a slice. If a paid tool would genuinely
help, say so once, show the free alternative, and continue on the free path.

## Free forever

| Need | Free option | Notes |
|---|---|---|
| Engine + editor + playtest | **Roblox Studio** | free; publishing is free |
| Agent control of Studio | **official Studio MCP** (`mcp.bat`) | ships with Studio |
| 3D props, materials, textures, scenes | `generate_mesh`, `generate_procedural_model`, `generate_material`, `generate_texture`, `generate_scene` | Roblox-hosted. If a call returns an entitlement/quota error, fall back to primitives — never treat it as a reason to buy anything |
| Terrain, lighting, atmosphere | built-in `Terrain` API + `Lighting` presets | `worldbuilding-lighting.md` |
| Animation | **Roblox Animation Editor** | built into Studio, free |
| UI | Instance tree / **Fusion 0.3** (open source) | `ui-mobile.md` |
| UI preview | **UI Labs** (free), **GuiForge** (free) | optional, never required |
| Data/session locking | **ProfileStore** (open source) | `persistence.md` |
| Networking schemas | **ByteNet Max / Blink / Zap** (open source) | `security-networking.md` |
| Lifecycle cleanup | **Trove** / **Janitor** (open source) | or 20 lines of your own |
| Source control + tooling | **Rojo, Rokit, StyLua, Selene, luau-lsp, Lune, Wally** | all free; pinned in `rokit.toml` |
| Docs | the creator-docs cache (public, CC-BY-4.0) | `rbforge docs update` |
| 3D modeling outside Studio | **Blender** | free |

## Never pay for these

| Paid thing | Why not | Free replacement |
|---|---|---|
| Paid Creator Store models | unknown scripts, unknown licence, unanchored geoms — and avoidable | generate it, or build from parts |
| Paid UI plugins | the free stack covers layout and preview | Fusion + UI Labs / GuiForge |
| Moon Animator | nice, not required | built-in Animation Editor |
| Archimedes | CSG convenience | `generate_mesh` + unions |
| Atmos | weather effects | Atmosphere/Clouds + lighting presets |
| Paid audio packs | licence traps | see "Free audio" below |

## Buying assets safely, when the user insists

`search_asset` can filter before anything is inserted:

```
search_asset(assetType="Model", query="streetlamp", scope="creator_store",
             priceFilter="free", verifiedCreatorsOnly=true, maxResults=10)
```

- `priceFilter` is lowercase (`"free"` / `"paid"` / `"all"`) and **requires
  `scope="creator_store"`** — it is rejected on any other scope.
- `scope` is one of `auto`, `creator_store`, `user`, `group`, `universe`.
- `verifiedCreatorsOnly=true` drops anonymous reuploads — the main source of
  backdoored models.
- `maxPriceCents=0` is the same guarantee at the price level, also
  `creator_store`-only.
- Whatever comes back still goes through the **quarantine sanitizer** in
  `assets.md` before it touches `Workspace`. Free is not the same as safe.

## Free audio

Audio is the one asset class that is genuinely hard to make procedurally, and
the one most likely to carry a licence problem.

1. Search the free pool: `search_asset(assetType="Audio", query="impact",
   scope="creator_store", priceFilter="free", audioMaxDuration=2)`.
2. Prefer short SFX (under ~2s) — they are plentiful and free.
3. Roblox audio has a hard ownership rule: you can only use audio you own or
   have explicit permission for. A free-listed asset in the Creator Store is
   usable; a random ID from a forum is not.
4. If nothing suitable exists, ship with `SoundService` hooks wired and
   silent — silence is a known gap, a stolen audio ID is a takedown.

## Quality without money

Free does not mean ugly. The difference between "AI slop" and "reads like a
game" is, in order of impact per minute spent:

1. **Lighting** — one preset from `worldbuilding-lighting.md` changes everything.
2. **Consistent palette** — pick 4 colours and reuse them; do not let every
   part be a different random brick colour.
3. **Scale** — studs are ~0.28m; a doorway is ~7 studs tall, a player is ~5.
   Wrong scale reads as "wrong" before anyone can name why.
4. **Game feel** — the juice matrix in `game-design.md` (FOV spring, hit-stop,
   pooled particles).
5. **Generated props** — `generate_mesh` for the 3-5 hero objects, primitives
   for everything else.

## Optional paid tools the user may already own

Ask the forge what is installed rather than assuming:

```
rbforge plugins          # CLI
rb_plugins               # MCP
```

It reports each detected tool, what it changes, and its free alternative. Rules:

- **Detected != required.** A paid plugin being present never becomes a
  dependency of the build.
- **Design tools produce references, not instances.** ForgeGUI output is an
  image: save it, `store_image` it, then build the actual `ScreenGui`/Instances.
  Do not claim a design is "in the game" until the instances render.
- **Never install a plugin** for the user, and never ask them to buy one.

## The $0 checklist before saying "done"

- [ ] no asset ID was guessed
- [ ] no purchase was made or requested
- [ ] every inserted asset came from the free pool or was generated
- [ ] audio, if any, is owned/free-listed
- [ ] the build works with only Studio + the official MCP installed
