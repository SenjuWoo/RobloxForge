"""Install the pinned selene binary in CI so generated Luau is really parsed.

The push path emits Luau; Python's compileall cannot check it. This fetches the same selene
version the project pins in rokit.toml from its official GitHub release and puts it on PATH.
Fails loudly: a CI job that silently loses its Luau parser is exactly how invalid code ships.
"""
import io
import os
import platform
import stat
import sys
import urllib.request
import zipfile

VERSION = "0.32.0"
BASE = "https://github.com/Kampfkarren/selene/releases/download"


def target():
    system = platform.system().lower()
    arch = platform.machine().lower()
    if system == "windows":
        return "selene-%s-windows.zip" % VERSION
    if system == "linux":
        return ("selene-%s-linux-aarch64.zip" if arch in ("aarch64", "arm64")
                else "selene-%s-linux.zip") % VERSION
    if system == "darwin":
        return "selene-%s-macos.zip" % VERSION
    raise SystemExit("unsupported platform for selene: %s" % system)


def main():
    name = target()
    url = "%s/%s/%s" % (BASE, VERSION, name)
    print("downloading", url)
    with urllib.request.urlopen(url, timeout=60) as response:
        blob = io.BytesIO(response.read())
    out_dir = os.path.join(os.getcwd(), ".ci-tools")
    os.makedirs(out_dir, exist_ok=True)
    with zipfile.ZipFile(blob) as archive:
        archive.extractall(out_dir)
    binary = os.path.join(out_dir, "selene.exe" if os.name == "nt" else "selene")
    if not os.path.exists(binary):
        raise SystemExit("selene was not in %s" % name)
    os.chmod(binary, os.stat(binary).st_mode | stat.S_IEXEC)
    print("selene at", binary)
    github_path = os.environ.get("GITHUB_PATH")
    if github_path:
        with open(github_path, "a", encoding="utf-8") as fh:
            fh.write(out_dir + "\n")


if __name__ == "__main__":
    sys.exit(main())
