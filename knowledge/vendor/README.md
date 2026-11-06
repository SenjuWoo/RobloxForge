# Vendored: roblox-skills and Roblox Assistant references

Third-party material kept here so an agent can load deep engine detail without shipping it into
every session's context. Nothing in this folder is installed automatically.

## roblox-skills — https://github.com/EL4CTEO/roblox-skills

23 Agent Skills (MIT, `LICENSE` alongside), checked against the Roblox API reference for Studio
0.743 (October 2026) and CI-typechecked in strict mode. Use when a task needs current specifics
that the main `roblox-game-development` skill only summarises:

| Skill | Reach for it when |
|---|---|
| `roblox-networking` | remotes, serialization limits, rate limiting, bandwidth |
| `roblox-data-stores` | persistence, sessions, `UpdateAsync`, retry budgets |
| `roblox-security` | client authority, exploit surface, validation boundaries |
| `roblox-performance` | frame budget, instance counts, streaming |
| `roblox-ui` | ScreenGui layouts, scaling, input on touch |
| `roblox-characters-animation`, `roblox-physics` | rigs, motors, constraints, moving parts |
| `roblox-npc-ai` | pathfinding, perception, state machines |
| `roblox-studio-mcp` | what the official MCP can and cannot do |
| `roblox-testing` | test shape and CI for Roblox code |
| others | audio, monetization, Open Cloud, teleport/matchmaking, text chat, world building, Luau, architecture, analytics, input, game systems, tooling, code review |

Read one file directly, e.g. `knowledge/vendor/roblox-skills/roblox-networking/SKILL.md`. Do not copy
whole trees into a session: each is ~2-4k tokens.

## roblox-assistant — `roblox-analytics-liveops.md` … `roblox-world-building.md`

23 single-file briefs in the same spirit, written for Roblox Studio's own Assistant. Useful as a
second opinion when the skill above is silent; they carry no licence header beyond the source pack.

## Policy

- Vendored, not installed: `rbforge skills install` still ships only the two first-party skills.
- Keep the upstream `LICENSE` with any copied file.
- If a future revision contradicts `roblox-game-development` (for example a deprecated API), the
  vendored file wins on API facts and the first-party skill should be corrected.
- Re-check upstream before relying on version-specific claims; this snapshot is October 2026.
