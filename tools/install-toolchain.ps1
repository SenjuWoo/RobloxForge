# RobloxForge -- toolchain installer.
#
# Installs the pinned Luau toolchain so `rbforge check` runs for real instead
# of reporting `incomplete`: rokit itself, then rojo / stylua / selene /
# luau-lsp / lune / wally / wally-package-types / run-in-roblox, all pinned in
# the checkout's `rokit.toml` (and copied to a global manifest so the tools
# resolve from any directory, including a temp fixture).
#
# Nothing here needs admin. Exit codes: 0 ok, 2 network/registry reachable
# but a tool failed to resolve, 4 a prerequisite (cargo) is missing.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'

$root = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$root = Split-Path -Parent $root
$manifest = Join-Path $root 'rokit.toml'
if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
  Write-Error "rokit.toml not found at $manifest -- run this from the RobloxForge checkout."
  exit 4
}

Write-Host '== RobloxForge toolchain =='
Write-Host "checkout: $root"

$rokit = (Get-Command rokit -ErrorAction SilentlyContinue)
if (-not $rokit) {
  Write-Host '-> rokit not on PATH; installing it with cargo'
  $cargo = (Get-Command cargo -ErrorAction SilentlyContinue)
  if (-not $cargo) {
    Write-Error 'cargo not found on PATH. Install Rust (rustup) to get cargo, or install rokit by hand from https://github.com/rojo-rbx/rokit, then re-run.'
    exit 4
  }
  & $cargo.Source install rokit --locked
  if ($LASTEXITCODE -ne 0) {
    Write-Error "cargo install rokit exited $LASTEXITCODE"
    exit 2
  }
  $rokit = (Get-Command rokit -ErrorAction SilentlyContinue)
  if (-not $rokit) {
    $cargoBin = Join-Path $HOME '.cargo\\bin'
    $env:PATH = "$cargoBin;$env:PATH"
    $rokit = (Get-Command rokit -ErrorAction SilentlyContinue)
  }
  if (-not $rokit) {
    Write-Error 'rokit was installed but is still not on PATH (restart your terminal).'
    exit 2
  }
}
Write-Host ("rokit   : " + (& $rokit.Source --version 2>&1))

Write-Host '-> rokit self-install (tool links in ~/.rokit/bin)'
& $rokit.Source self-install
if ($LASTEXITCODE -ne 0) { Write-Warning "self-install exited $LASTEXITCODE" }

# Global manifest: without it the rokit shims only resolve inside a project
# directory that pins the tool, which makes `rbforge check` fail (not skip)
# for fixture roots. Adding globally keeps the shims working everywhere.
$tools = @(
  'rojo-rbx/rojo@7.7.1',
  'JohnnyMorganz/StyLua@2.6.0',
  'Kampfkarren/selene@0.32.0',
  'JohnnyMorganz/luau-lsp@1.70.1',
  'lune-org/lune@0.11.1',
  'UpliftGames/wally@0.3.2',
  'JohnnyMorganz/wally-package-types@1.7.0',
  'rojo-rbx/run-in-roblox@0.3.0'
)
$failed = 0
foreach ($t in $tools) {
  Write-Host "-> rokit add --global $t"
  & $rokit.Source add --global $t
  if ($LASTEXITCODE -ne 0) { $failed++; Write-Warning "add $t exited $LASTEXITCODE" }
}

Write-Host '-> rokit install (project, pinned by rokit.toml)'
Push-Location $root
try {
  & $rokit.Source install
  if ($LASTEXITCODE -ne 0) { $failed++; Write-Warning "install exited $LASTEXITCODE" }
} finally {
  Pop-Location
}

$rokitBin = Join-Path $HOME '.rokit\\bin'
if ($env:PATH -notlike "*$rokitBin*") { $env:PATH = "$rokitBin;$env:PATH" }

Write-Host ''
Write-Host '== versions =='
foreach ($name in @('rojo','stylua','selene','luau-lsp','lune','wally','wally-package-types','run-in-roblox')) {
  $cmd = (Get-Command $name -ErrorAction SilentlyContinue)
  if ($cmd) { Write-Host ("  {0,-20} {1}" -f $name, (& $cmd.Source --version 2>&1) -join ' ') }
  else { Write-Host ("  {0,-20} NOT FOUND" -f $name); $failed++ }
}

Write-Host ''
if ($failed) {
  Write-Warning "$failed tool(s) did not resolve. New terminals need ~/.rokit/bin on PATH -- rokit self-install usually adds it."
  exit 2
}
Write-Host 'Toolchain ready. `rbforge check` will now run the static rung for real.'
exit 0
