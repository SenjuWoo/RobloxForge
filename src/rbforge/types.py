"""Roblox type definitions for luau-lsp: fetch the maintained file, verify it, cache it.

luau-lsp cannot invent Roblox globals. Without definitions it reports `Unknown global 'Instance'` for
every line, which is why the typecheck rung used to skip on every machine. The definitions are
published in the luau-lsp repository itself (`scripts/globalTypes.d.luau`); this module pins one
release, verifies the exact bytes before caching, and never executes what it downloads.
"""
import hashlib
import os
import shutil
import subprocess
import tempfile
import urllib.request

from . import paths
from .errors import ForgeError

# Pinned to a luau-lsp release. Definitions and analyzer are published together, so the pairing is
# the upstream one rather than something invented here.
REF = "1.70.1"
URL = "https://raw.githubusercontent.com/JohnnyMorganz/luau-lsp/%s/scripts/globalTypes.d.luau" % REF
SHA256 = "2857efa8245485f8c25c19c018ee1ef9b46afab4efd2ea70fc3257cd3faf7080"

# Project-local files win over the cache: a place may pin its own API surface.
PROJECT_CANDIDATES = (
    "globalTypes.d.luau",
    os.path.join("types", "globalTypes.d.luau"),
    os.path.join(".rbforge", "globalTypes.d.luau"),
)


def cache_dir():
    return os.path.join(paths.home(), "types")


def cached_path(ref=REF):
    return os.path.join(cache_dir(), "globalTypes-%s.d.luau" % ref)


def installed_version():
    """The luau-lsp version on PATH, or None. Used to say when the pin is older than the tool."""
    if not shutil.which("luau-lsp"):
        return None
    try:
        out = subprocess.run(["luau-lsp", "--version"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (out.stdout or out.stderr).strip().splitlines()
    return text[0].strip() if text else None


def discover(root, ref=REF):
    """(path, source) for the definitions to use, or (None, reason)."""
    env = os.environ.get("RBFORGE_LUAU_DEFINITIONS")
    if env and os.path.isfile(env):
        return env, "env"
    for rel in PROJECT_CANDIDATES:
        candidate = os.path.join(root, rel)
        if os.path.isfile(candidate) and os.path.getsize(candidate) > 1024:
            return candidate, "project"
    cached = cached_path(ref)
    if os.path.isfile(cached):
        if _verified(cached):
            return cached, "cache"
        return None, ("cached definitions do not match the pinned digest; run `rbforge types fetch "
                      "--force` (or set RBFORGE_LUAU_DEFINITIONS for your own file)")
    return None, ("no Roblox type definitions found; run `rbforge types fetch` "
                  "(or set RBFORGE_LUAU_DEFINITIONS)")


def fetch(ref=REF, force=False):
    """Download and verify the pinned definitions. Returns (path, sha256, bytes)."""
    target = cached_path(ref)
    if os.path.isfile(target) and not force:
        digest = _sha(target)
        if digest == SHA256:
            return target, digest, os.path.getsize(target)
    url = URL if ref == REF else URL.replace(REF, ref)
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            blob = response.read()
    except Exception as exc:  # noqa: BLE001 - surfaced as a ForgeError with the URL
        raise ForgeError("RBF-TYPES-001", "could not download %s: %s" % (url, exc),
                         hint="check the network, or set RBFORGE_LUAU_DEFINITIONS to a local file")
    digest = hashlib.sha256(blob).hexdigest()
    if ref == REF and digest != SHA256:
        raise ForgeError("RBF-TYPES-002",
                         "downloaded definitions do not match the pinned digest",
                         hint="expected %s, got %s - refusing to cache them" % (SHA256, digest))
    os.makedirs(cache_dir(), exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=cache_dir(), suffix=".part")
    try:
        with os.fdopen(handle, "wb") as fh:
            fh.write(blob)
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.remove(temp)
    return target, digest, len(blob)


def status(ref=REF):
    path = cached_path(ref)
    found, source = discover(os.getcwd(), ref)
    return {
        "ref": ref,
        "cached": path if os.path.isfile(path) else None,
        "cached_sha256": _sha(path) if os.path.isfile(path) else None,
        "pinned_sha256": SHA256,
        "using": found,
        "source": source,
        "luau_lsp": installed_version(),
    }


_DIGESTS = {}


def _verified(path, expected=None):
    """True when this file matches its pin. Memoised on (path, size, mtime) so one check does not
    rehash 850 KB several times; a touched file invalidates itself."""
    expected = expected or SHA256
    try:
        stat = os.stat(path)
    except OSError:
        return False
    key = (os.path.normcase(os.path.abspath(path)), stat.st_size, stat.st_mtime_ns)
    digest = _DIGESTS.get(key)
    if digest is None:
        digest = _sha(path)
        _DIGESTS[key] = digest
    return digest == expected


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
