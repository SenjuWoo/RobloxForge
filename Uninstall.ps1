# RobloxForge -- uninstaller.
#
# This is the script that was actually missing. RobloxForge runs from its
# checkout, so deleting the folder was always "uninstalling" it -- except that
# it is NOT, because `skills install` and `agent connect` write into agent
# homes that the folder does not own. Delete the checkout and those entries
# stay behind: skills for a tool that is gone, and an MCP server entry pointing
# at a path that no longer exists.
#
# So the order here matters. Un-wire the agents FIRST, while the CLI that knows
# what it wrote still exists.
#
# The checkout itself is never deleted by this script -- it is your working
# copy, and removing a directory the user is standing in is not an
# uninstaller's job. It tells you the path and lets you decide.
[CmdletBinding()]
param(
  # hermes | claude | codex | grok | kimi -- or 'all' (default).
  [string]$Agent = 'all',
  # Report what would be removed and change nothing.
  [switch]$WhatIfOnly,
  # Also delete RobloxForge's machine state (docs cache, receipts, push ledger, type
  # definitions, config backups). Off by default: receipts and backups are evidence.
  [switch]$RemoveState
)
$ErrorActionPreference = 'Stop'

$root = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$cli  = Join-Path $root 'src\rbforge_cli.py'
if (-not (Test-Path -LiteralPath $cli -PathType Leaf)) {
  Write-Error "rbforge_cli.py not found at $cli -- run this from the RobloxForge checkout."
  exit 1
}

$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) {
  Write-Error 'Python not found on PATH; the CLI that recorded the wiring cannot be asked to undo it.'
  exit 4
}

# Machine state lives outside the checkout (RBFORGE_HOME, default %LOCALAPPDATA%\RobloxForge).
# Ask the package for the path instead of guessing it.
$stateDir = (& $py.Source -c "import sys; sys.path.insert(0, sys.argv[1]); from rbforge import paths; print(paths.home())" (Join-Path $root 'src')).Trim()

Write-Host '== RobloxForge uninstall =='
Write-Host "checkout: $root"
Write-Host "state   : $stateDir"
Write-Host ''

Write-Host 'Currently wired:'
& $py.Source $cli skills status
& $py.Source $cli agent status
Write-Host ''

if ($WhatIfOnly) {
  Write-Host "-WhatIfOnly: nothing was changed. Re-run without it to remove the wiring above."
  exit 0
}

$failed = 0
function Invoke-Rbforge {
  param([string]$Label, [string[]]$CliArgs)
  Write-Host "-> $Label"
  & $py.Source $cli @CliArgs
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "$Label exited $LASTEXITCODE"
    $script:failed++
  }
  Write-Host ''
}

# agent BEFORE skills is deliberate: disconnect removes the MCP server entry,
# which is the one that breaks an agent's startup if it is left pointing at a
# deleted path. Skills that linger are noise; a dead MCP entry is a failure.
Invoke-Rbforge -Label "agent disconnect $Agent" -CliArgs @('agent', 'disconnect', $Agent)
Invoke-Rbforge -Label "skills remove $Agent"    -CliArgs @('skills', 'remove', $Agent)

Write-Host 'Remaining:'
& $py.Source $cli skills status
& $py.Source $cli agent status
Write-Host ''

if ($failed) {
  Write-Warning "$failed step(s) reported problems -- check the status output above before deleting the checkout."
  exit 1
}

Write-Host 'Agent wiring removed.'
Write-Host ''
if ($RemoveState) {
  # Only the directory the package itself reports, and only when it is not the checkout.
  if ($stateDir -and (Test-Path -LiteralPath $stateDir -PathType Container) -and
      ((Resolve-Path -LiteralPath $stateDir).Path -ne (Resolve-Path -LiteralPath $root).Path)) {
    Remove-Item -LiteralPath $stateDir -Recurse -Force
    Write-Host "State removed: $stateDir"
  }
} else {
  Write-Host 'Machine state was kept (docs cache, receipts, push ledger, config backups):'
  Write-Host "    $stateDir"
  Write-Host 'Delete it with -RemoveState, or by hand.'
}
Write-Host ''
Write-Host 'The checkout itself was NOT deleted. Remove it yourself when you are ready:'
Write-Host "    $root"
exit 0
