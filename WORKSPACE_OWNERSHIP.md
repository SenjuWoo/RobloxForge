# Workspace ownership

- Project root: `.` (this file's directory; one owner shared by every agent).
- Active source: `.` - `src/` (CLI + `rbforge` package), `mcp_server/`, `skills/`, `templates/`, `scripts/`, `tests/`.
- Versioning: semantic version in `src/rbforge/__init__.py`, `CHANGELOG.md`, and a `vX.Y.Z` Git tag; `release.yml` refuses a tag that disagrees with the package version.
- Repository: existing public GitHub repository (MIT); preserve its remote and visibility. CI must be green on the exact SHA before a tag.
- Third-party reference clones evaluated in `docs/INTEGRATIONS.md` (SyphoDev, Roblox Blender plugin, Roqer) are read-only inputs and are never vendored.
- Publication intent: local/private by default. A build or release candidate is not permission to publish.
- Explicit GitHub publication: public and MIT for original work by default, subject to rights/platform terms; preserve existing licences. Generic publication uses the appropriate destination (Nexus for Skyrim); do not create duplicate source hosting for mods needing no compilation.
- Existing-repository maintenance: preserve its remote/visibility and follow the requested update, documentation, push and release scope.
- Read-only inputs: installed products, game Data/staging/saves and supplied references.
- Release staging: `release.yml` builds the zip with `git archive` from an allowlist (runtime files, installers, README, CHANGELOG, licences); tests, STATE.md, CI config and this file stay out.
- Machine state: `%LOCALAPPDATA%\RobloxForge` (`RBFORGE_HOME`) holds the docs cache, receipts and the push ledger - never the checkout.
- Recovery: read STATE.md and version/build/run metadata before continuing; keep the last known-good artifact.


Read the existing evidence and update the active-source/version fields before substantive edits. Do not create another owner or move files merely to match a template.
