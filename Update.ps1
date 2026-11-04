# RobloxForge -- updater.
#
# Because the forge runs from this checkout, updating the code IS `git pull`.
# What that does not do -- and what people forget -- is refresh the copies of
# the skills that `skills install` wrote into each agent home. A pulled repo
# with stale skills in five agent homes looks updated and is not.
[CmdletBinding()]
param(
  # hermes | claude | codex | grok | kimi -- or 'all' (default).
  [string]$Agent = 'all',
  # Skip `git pull` and only refresh what was written into the agents.
  [switch]$SkipPull,
  # Also refresh the creator-docs cache (~27 MB via git).
  [switch]$Docs
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

Write-Host '== RobloxForge update =='
Write-Host "checkout: $root"
Write-Host ''

if (-not $SkipPull) {
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Warning 'git not found on PATH -- skipping the code pull, refreshing agents only.'
  } elseif (-not (Test-Path -LiteralPath (Join-Path $root '.git'))) {
    Write-Warning "$root is not a git checkout -- skipping the code pull, refreshing agents only."
  } else {
    # A pull that silently discards local edits is worse than one that stops.
    $dirty = & git -C $root status --porcelain
    if ($dirty) {
      Write-Warning 'The checkout has uncommitted changes; not pulling over them.'
      Write-Host ($dirty | Select-Object -First 10)
      Write-Host 'Commit or stash, then re-run -- or use -SkipPull to refresh the agents only.'
      exit 1
    }
    Write-Host '-> git pull --ff-only'
    & git -C $root pull --ff-only
    if ($LASTEXITCODE -ne 0) {
      Write-Error 'git pull failed (see above). Nothing was changed in your agents.'
      exit 1
    }
    Write-Host ''
  }
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

# `skills update` is the same code path as install (see rbforge_cli._dispatch),
# so this overwrites the copies in each agent home with the freshly pulled ones.
Invoke-Rbforge -Label "skills update $Agent" -CliArgs @('skills', 'update', $Agent)
if ($Docs) { Invoke-Rbforge -Label 'docs update' -CliArgs @('docs', 'update') }
Invoke-Rbforge -Label 'doctor --no-probe' -CliArgs @('doctor', '--no-probe')

if ($failed) {
  Write-Warning "$failed step(s) reported problems (see above)."
  exit 1
}

Write-Host 'Updated. Code and agent-side skills are back in sync.'
exit 0
