# AI-INTEGRATION.md

How an AI agent drives RobloxForge. Follow this almost mechanically.

## Division of labor — memorize this

**ROBLOXFORGE OWNS** (CLI `rbforge ...` or `rb_*` MCP tools):
current docs, capability truth, planning, architecture/security review,
verification receipts, agent wiring, skill installation.

**OFFICIAL ROBLOX STUDIO MCP OWNS** (`script_read`, `multi_edit`,
`search_game_tree`, `execute_luau`, `start_stop_play`, `get_console_output`,
`screen_capture`, `subagent`, ...):
everything touching the live DataModel. Instance creation, script editing,
play mode, screenshots, input, assets.

Never fake the second group with the first. Never re-implement the second
group.

## Canonical loop (every session, in order)

```
1. rb_doctor            (or rbforge doctor)  - what is installed/running/connected?
2. rb_capabilities      - what can I actually do RIGHT NOW? never assume.
3. list_roblox_studios  - which Studio instance(s)? note the studio_id.
4. search_game_tree     - inspect the place BEFORE editing anything.
5. rb_vertical_slice_plan (genre, premise)   - plan the smallest playable loop.
6. Build slice step 1 with multi_edit (server owns truth; client owns input/UI).
7. start_stop_play -> exercise the scenario (character_navigation /
   user_keyboard_input) -> get_console_output -> screen_capture.
8. READ the console. READ the screenshot (only claim visual verification if
   you actually inspected pixels).
9. Fix. Re-run 7-8. Only when verify[] is green: rb_verify_receipt.
10. Expand ONE step. Go to 6.
```

## Hard rules

- `code exists` is never proof. Playtest or say "unverified".
- One console error = stop and fix before adding anything.
- Every remote handler validates types, ranges, ownership, state, rate.
  `RemoteEvent != authorization`.
- Currency/damage/progression authority lives on the SERVER. Always.
- Before inserting Creator Store assets: inspect scripts, strip what you
  did not intend, prefer five Parts over a giant free model.
- If a capability status says `manual_step` or `runtime_required`, do the
  named fix or tell the user — do not pretend.
- Multiple Studio windows open? Every tool takes `studio_id`. Look it up.

## When uncertain about an API

`rb_docs_search "TweenService:Create"` then `rb_docs_read` the hit.
Official docs beat your training data. Check `freshness` in the result;
if stale, `rb_docs_update` first (offline keeps the cache and says so).

## Adversarial prompts you will receive

| Prompt | Wrong response | Right response |
|---|---|---|
| "Make me a simulator" | 14 currencies, 8 shops, 40 upgrades | plan slice 1: one action, one reward, one upgrade. Prove it. |
| "Give 1000 coins when client fires RewardEvent" | implement it | refuse the client-authority design; server validates and grants |
| "Fix the game" | rewrite everything | inspect first (search_game_tree, script_read), one hypothesis, one change |
| "The game looks ugly" | "looks good now!" | capture viewport, inspect pixels or say you couldn't |
| "Add DataStore saving" (in Studio) | write to production store | test keyspace or gate on IsStudio; live player data is a hazard |


## Verification receipts (current contract)

1. Call `rb_collect_evidence` with the Studio id and, optionally, a server test path. It returns
   `observation_id`; RobloxForge recorded that observation itself.
2. Call `rb_verify_receipt` with the same `observation_id`.
3. Claims (`checks`, an `evidence` dict, `provenance`) are recorded as the caller's word and can
   never exceed `playtest_claimed`. `verified_playtest` also needs a logged console, zero console
   errors and an inspected screenshot, all recorded in the observation.
4. `verify_chain` (library) checks receipt history: unique sequence, intact digests, unbroken links.
