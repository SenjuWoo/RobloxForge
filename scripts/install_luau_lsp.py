#!/usr/bin/env python3
"""Install the pinned luau-lsp release into .ci-tools/ (CI + local integration tests).

Pinned on purpose: the typecheck rung's behaviour (exit codes, diagnostic shape, flag names) is
verified against this version. Bump the pin and re-run the suite, never track "latest".

    python scripts/install_luau_lsp.py            # download if missing
    python scripts/install_luau_lsp.py --force    # re-download
"""
import io
import os
import platform
import stat
import sys
import urllib.request
import zipfile

VERSION = "1.70.1"
BASE = f"https://github.com/JohnnyMorganz/luau-lsp/releases/download/{VERSION}"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, ".ci-tools")


def asset_name():
    system, machine = platform.system().lower(), platform.machine().lower()
    if system == "windows":
        return "luau-lsp-win64.zip", "luau-lsp.exe"
    if system == "darwin":
        return "luau-lsp-macos.zip", "luau-lsp"
    if machine in ("aarch64", "arm64"):
        return "luau-lsp-linux-arm64.zip", "luau-lsp"
    return "luau-lsp-linux-x86_64.zip", "luau-lsp"


def main():
    force = "--force" in sys.argv
    asset, binary = asset_name()
    os.makedirs(DEST, exist_ok=True)
    target = os.path.join(DEST, binary)
    if os.path.isfile(target) and not force:
        print(f"luau-lsp already at {target}")
        return 0
    url = f"{BASE}/{asset}"
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=180) as resp:
        blob = resp.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        member = next((n for n in zf.namelist() if n.endswith(binary)), None)
        if member is None:
            print(f"{asset} does not contain {binary}", file=sys.stderr)
            return 4
        with zf.open(member) as src, open(target, "wb") as out:
            out.write(src.read())
    if binary != "luau-lsp.exe":
        os.chmod(target, os.stat(target).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"installed {target} (luau-lsp {VERSION})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
