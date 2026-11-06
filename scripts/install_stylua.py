"""Install the pinned stylua binary in CI so scaffolded projects can be checked.

The suite requires a formatter to prove `rbforge new` produces a project that passes its own gate.
Fetches the same version the project pins in rokit.toml from the official GitHub release.
"""
import io
import os
import platform
import stat
import sys
import urllib.request
import zipfile

VERSION = "2.6.0"
BASE = "https://github.com/JohnnyMorganz/StyLua/releases/download/v%s" % VERSION


def asset():
    system = platform.system().lower()
    arch = platform.machine().lower()
    if system == "windows":
        return "stylua-windows-x86_64.zip", "stylua.exe"
    if system == "linux":
        name = "stylua-linux-aarch64.zip" if arch in ("aarch64", "arm64") else "stylua-linux-x86_64.zip"
        return name, "stylua"
    if system == "darwin":
        name = "stylua-macos-aarch64.zip" if arch in ("aarch64", "arm64") else "stylua-macos.zip"
        return name, "stylua"
    raise SystemExit("unsupported platform for stylua: %s" % system)


def main():
    name, binary_name = asset()
    url = "%s/%s" % (BASE, name)
    print("downloading", url)
    with urllib.request.urlopen(url, timeout=60) as response:
        blob = io.BytesIO(response.read())
    out_dir = os.path.join(os.getcwd(), ".ci-tools")
    os.makedirs(out_dir, exist_ok=True)
    with zipfile.ZipFile(blob) as archive:
        archive.extractall(out_dir)
    binary = os.path.join(out_dir, binary_name)
    if not os.path.exists(binary):
        raise SystemExit("stylua was not in %s" % name)
    os.chmod(binary, os.stat(binary).st_mode | stat.S_IEXEC)
    print("stylua at", binary)
    github_path = os.environ.get("GITHUB_PATH")
    if github_path:
        with open(github_path, "a", encoding="utf-8") as fh:
            fh.write(out_dir + "\n")


if __name__ == "__main__":
    sys.exit(main())
