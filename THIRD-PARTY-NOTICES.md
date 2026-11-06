# Third-Party Notices

RobloxForge's own code is MIT-licensed (see LICENSE). It redistributes
nothing; everything below is fetched or executed at runtime under its own
terms.

## Runtime dependencies

| Upstream | Use | License | How used |
|---|---|---|---|
| [Roblox/creator-docs](https://github.com/Roblox/creator-docs) | searchable knowledge corpus | CC-BY-4.0 (prose), permissive LICENSE-CODE (samples) | cloned sparsely (~27 MB of text) into `%LOCALAPPDATA%\RobloxForge\creator-docs` at the user's request via `rbforge docs update`; never vendored into this repo |
| Roblox Studio built-in MCP (`StudioMCP.exe` / `mcp.bat`) | live engine control | proprietary, ships with Roblox Studio | launched only when probing/connecting; RobloxForge is not affiliated with Roblox Corporation |
| Python `tomllib` / stdlib | TOML parsing, JSON-RPC, subprocess | PSF | stdlib |

## Studied during development (no code copied)

Community projects reviewed as references, clean-room synthesized:
brockmartin/roblox-game-skill, zilibobi/roblox-skills,
gogolumo/rbsmithy-roblox-claude-skill, CodePhobiia/claude-roblox-game-studio.
Several target the archived standalone Studio MCP server
(`Roblox/studio-rust-mcp-server`, archived 2026-04); their assumptions were
treated as outdated and not relied upon.

## Third-party skills: EL4CTEO/roblox-skills

- Source: https://github.com/EL4CTEO/roblox-skills (October 2026 snapshot)
- Licence: MIT -- full text in `skills/ROBLOX-SKILLS-LICENSE.txt`
- Contents: 23 Roblox Agent Skills under `skills/roblox-*`, copied unmodified
- Added: 2026-11-06, so this repository owns and versions them independently

## Trademarks

"Roblox" and "Roblox Studio" are trademarks of Roblox Corporation. This
project is not affiliated with, endorsed by, or sponsored by Roblox
Corporation.
