"""Optional Luau toolchain detection. Detection only - never auto-installs.

All of these are optional. Absence is reported as `optional`, not failure;
they only matter for the source-controlled (Rojo) workflow.

`rbforge check` runs whichever of these are installed. `tools/install-toolchain.ps1`
(or `Install.ps1 -Toolchain`) installs the pinned set from the checkout's
`rokit.toml`, including a global manifest so the tools resolve anywhere.
"""
import os
import re
import shutil
import subprocess

TOOLS = {
    "rojo":     {"purpose": "sync filesystem project into Studio"},
    "stylua":   {"purpose": "Luau formatter"},
    "selene":   {"purpose": "Luau linter"},
    "luau-lsp": {"purpose": "type checking / autocomplete data"},
    "rokit":    {"purpose": "installs the others, pinned per-project"},
    "lune":     {"purpose": "headless Luau; unit tests, place-file assertions"},
    "wally":    {"purpose": "package manager for shared Luau packages"},
    "run-in-roblox": {"purpose": "run place/scripts in Studio from the CLI"},
}

_VERSION = re.compile(r"([0-9]+\.[0-9]+[0-9a-zA-Z.\-]*)")


def _probe_version(path):
    """First version-looking token from `<exe> --version`. Never raises."""
    try:
        done = subprocess.run([path, "--version"], capture_output=True,
                              text=True, timeout=15)
        text = (done.stdout or "") + (done.stderr or "")
        match = _VERSION.search(text)
        return match.group(1) if match else None
    except (OSError, subprocess.SubprocessError):
        return None


def _rokit_bin():
    """~/.rokit/bin, if it exists. `rokit self-install` puts tool links there;
    a shell started before the install won't have it on PATH yet."""
    candidate = os.path.join(os.path.expanduser("~"), ".rokit", "bin")
    return candidate if os.path.isdir(candidate) else None


def _which(name):
    path = shutil.which(name)
    if path:
        return path
    extra = _rokit_bin()
    if extra:
        for ext in ("", ".exe"):
            candidate = os.path.join(extra, name + ext)
            if os.path.isfile(candidate):
                return candidate
    return None


def status():
    out = {}
    for name, meta in TOOLS.items():
        path = _which(name)
        entry = {"found": bool(path), "purpose": meta["purpose"]}
        if path:
            entry["path"] = path
            entry["version"] = _probe_version(path)
        out[name] = entry
    return out


def recommend(project_style="studio-native"):
    """What to install for a given workflow. Honest: studio-native needs none."""
    if project_style == "studio-native":
        return []
    have = status()
    wanted = ["rokit", "rojo", "stylua", "selene"]
    return [{"tool": t, "purpose": TOOLS[t]["purpose"],
             "already_installed": bool(have[t]["found"])}
            for t in wanted if not have[t]["found"]]
