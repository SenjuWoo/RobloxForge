# Current Roblox toolchain snapshot — verified 2026-11-01 against upstream releases

This is a **recommendation snapshot**, not an auto-install list. Pinned form:
`templates/source-controlled/rokit.toml`.

| Tool | Snapshot | Why |
|---|---:|---|
| Rojo | 7.7.1 | source-controlled Roblox projects |
| Rokit | 1.2.0 | maintained toolchain manager |
| StyLua | 2.6.0 | formatter |
| Selene | 0.32.0 | linter |
| luau-lsp | 1.70.1 | Roblox-aware LSP/sourcemaps |
| Wally | 0.3.2 | packages |
| Lune | 0.11.1 | headless Luau, unit tests, place-file assertions |
| run-in-roblox | 0.3.0 | run place/scripts in Studio from CLI |
| wally-package-types | 1.7.0 | types for Wally packages |

## Important

- Prefer Rokit over Aftman for new projects; Aftman is archived.
- Do not use Rojo just because the game is Roblox. Studio-native workflows are valid.
- Do not install every tool for a blank-place prototype.
- Recheck releases before creating a new lockfile/pin.
- `rbforge check` runs whichever of these are installed and reports the rest as
  skipped; a missing tool makes the run `incomplete`, never `pass`.

