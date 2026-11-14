"""Install the pinned Lune binary in CI so generated Luau is executed, not only parsed.

The push guard (conflict refusal, backup-before-overwrite, stamp parity with Python) is proven by
running the exact code `rbforge push` sends, against a mock DataModel, under Lune. Fetches the
version rokit.toml pins from the official GitHub release.
"""
import io
import os
import platform
import stat
import sys
import urllib.request
import zipfile

VERSION = "0.11.1"
BASE = "https://github.com/lune-org/lune/releases/download/v%s" % VERSION


def asset():
    system = platform.system().lower()
    arch = "aarch64" if platform.machine().lower() in ("aarch64", "arm64") else "x86_64"
    if system == "windows":
        return "lune-%s-windows-%s.zip" % (VERSION, arch), "lune.exe"
    if system in ("linux", "darwin"):
        return "lune-%s-%s-%s.zip" % (VERSION, "macos" if system == "darwin" else "linux", arch), "lune"
    raise SystemExit("unsupported platform for lune: %s" % system)


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
        raise SystemExit("lune was not in %s" % name)
    os.chmod(binary, os.stat(binary).st_mode | stat.S_IEXEC)
    print("lune at", binary)
    github_path = os.environ.get("GITHUB_PATH")
    if github_path:
        with open(github_path, "a", encoding="utf-8") as fh:
            fh.write(out_dir + "\n")


if __name__ == "__main__":
    sys.exit(main())
