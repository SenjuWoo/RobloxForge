# RobloxForge -- installer. No admin required.
#
# RobloxForge RUNS FROM THIS CHECKOUT. Nothing is copied to LOCALAPPDATA and
# there is no second copy to keep in sync -- so "install" here means the thing
# that actually leaves state on the machine: wiring the skills (and optionally
# the official Roblox Studio MCP) into your agents.
#
# This is START-HERE.bat's work in a form a script can call: no pause, no
# prompts, and a non-zero exit when a step genuinely failed.
[CmdletBinding()]
param(
  # hermes | claude | codex | grok | kimi -- or 'all' (default).
  [string]$Agent = 'all',
  # Also wire the official Roblox Studio MCP into the agent(s). Left off by
  # default because the forge installs it DISABLED for token discipline and
  # says so in the README; opting in is the user's call, not the installer's.
  [switch]$ConnectMcp,
  # Fetch the creator-docs cache (~27 MB via git). Off by default: it is a
  # large network fetch and `docs update` can be run any time.
  [switch]$Docs,
  # Install the pinned Luau toolchain (rokit + rojo/stylua/selene/...) so
  # `rbforge check` runs for real instead of reporting `incomplete`. This is
  # a network fetch of ~50 MB and can be re-run any time.
  [switch]$Toolchain
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
  Write-Error 'Python not found on PATH. Install Python 3.10+ and tick "Add python.exe to PATH".'
  exit 4
}

Write-Host '== RobloxForge install =='
Write-Host "checkout: $root"
Write-Host ("python  : " + (& $py.Source --version 2>&1))
Write-Host ''

$failed = 0
function Invoke-Rbforge {
  param([string]$Label, [string[]]$CliArgs)
  Write-Host "-> $Label"
  & $py.Source $cli @CliArgs
  # $LASTEXITCODE, not $? : a non-zero exit from a native/py process does not
  # trip $? reliably on PS 5.1, and this script must report a real failure.
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "$Label exited $LASTEXITCODE"
    $script:failed++
  }
  Write-Host ''
}

Invoke-Rbforge -Label "skills install $Agent" -CliArgs @('skills', 'install', $Agent)
if ($ConnectMcp) { Invoke-Rbforge -Label "agent connect $Agent" -CliArgs @('agent', 'connect', $Agent) }
if ($Docs)       { Invoke-Rbforge -Label 'docs update'          -CliArgs @('docs', 'update') }
if ($Toolchain) {
  Write-Host '-> install Luau toolchain'
  $toolchainScript = Join-Path $root 'tools\install-toolchain.ps1'
  if (Test-Path -LiteralPath $toolchainScript -PathType Leaf) {
    & $toolchainScript
    if ($LASTEXITCODE -ne 0) { $failed++; Write-Warning "toolchain exited $LASTEXITCODE" }
  } else {
    Write-Warning 'tools/install-toolchain.ps1 not found in this checkout.'
    $failed++
  }
  Write-Host ''
}

# --no-probe: the live MCP handshake needs Roblox Studio open, and an install
# must not fail merely because the user has not started Studio yet.
Invoke-Rbforge -Label 'doctor --no-probe' -CliArgs @('doctor', '--no-probe')

if ($failed) {
  Write-Warning "$failed step(s) reported problems (see above)."
  exit 1
}

Write-Host 'Done. Next:'
Write-Host '    rbforge new mygame --genre obby    scaffold a project + a plan, then build slice 1'
Write-Host '    rbforge agent connect all     wire the official Roblox Studio MCP (installed disabled)'
Write-Host '    rbforge docs update           fetch current creator-docs (~27 MB)'
Write-Host '    rbforge doctor                full report, including the live MCP handshake'
Write-Host ''
Write-Host 'To remove everything this put into your agents:  .\Uninstall.ps1'
exit 0
