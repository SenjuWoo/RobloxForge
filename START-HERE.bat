@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   RobloxForge - AI Roblox development workbench
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [X] Python not found on PATH.
    echo     Install Python 3.10+ from https://www.python.org/downloads/
    echo     Be sure to check "Add python.exe to PATH" during install.
    pause
    exit /b 4
)

python --version

echo.
echo [1/3] Doctor: checking Roblox Studio, official MCP, docs cache...
python src\rbforge_cli.py doctor --no-probe
echo.

echo [2/3] Installing skills into detected agents...
python src\rbforge_cli.py skills install all
echo.

echo [3/3] Optional next steps:
echo   - rbforge new mygame --genre obby  (scaffold a project + plan; start here)
echo   - rbforge agent connect hermes     (wire official Roblox MCP into Hermes)
echo   - rbforge docs update              (fetch current creator-docs; ~27 MB via git)
echo   - rbforge doctor                   (full report incl. live MCP handshake)
echo   - rbforge check .                  (offline gate, run before any playtest)
echo.
pause
