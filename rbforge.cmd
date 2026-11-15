@echo off
rem RobloxForge CLI launcher: `rbforge <command>` from this folder, or from anywhere once this
rem folder is on PATH. It runs the checkout's own CLI, so there is no second copy to update.
python "%~dp0src\rbforge_cli.py" %*
exit /b %ERRORLEVEL%
