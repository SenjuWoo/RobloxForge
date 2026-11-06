"""Install/update/remove RobloxForge's two skills into supported agents.

Only ever touches directories WE own (`roblox-game-development`,
`roblox-docs`). A foreign skill with the same name is never overwritten -
that is reported as a manual decision instead. Versioned via a stamp file,
so `skills status` can say when an install is stale.
"""
import os
import shutil

from . import paths
from .errors import ForgeError

OUR_SKILLS = ("roblox-game-development", "roblox-docs") + (
    "roblox-analytics-liveops",
    "roblox-architecture",
    "roblox-audio",
    "roblox-characters-animation",
    "roblox-code-review",
    "roblox-data-stores",
    "roblox-game-systems",
    "roblox-input",
    "roblox-luau",
    "roblox-monetization",
    "roblox-networking",
    "roblox-npc-ai",
    "roblox-open-cloud",
    "roblox-performance",
    "roblox-physics",
    "roblox-security",
    "roblox-studio-mcp",
    "roblox-teleport-matchmaking",
    "roblox-testing",
    "roblox-text-chat",
    "roblox-tooling",
    "roblox-ui",
    "roblox-world-building",
)
STAMP = ".rbforge-version"

# Discovered skill roots on this machine class. Env override wins.
_ROOTS = {
    "hermes": ("RBFORGE_HERMES_SKILLS",
               ("%LOCALAPPDATA%\\hermes\\skills", "~/AppData/Local/hermes/skills")),
    "claude": ("RBFORGE_CLAUDE_SKILLS", ("~/.claude/skills",)),
    "codex": ("RBFORGE_CODEX_SKILLS", ("~/.codex/skills",)),
    "grok": ("RBFORGE_GROK_SKILLS", ("~/.grok/skills",)),
    "kimi": ("RBFORGE_KIMI_SKILLS", ("~/.kimi/skills",)),
}


def _expand(p):
    return paths.expand(p.replace("%LOCALAPPDATA%", "%LOCALAPPDATA%"))


def root_for(agent):
    """First skill root for this agent, if discoverable."""
    roots = roots_for(agent)
    return roots[0] if roots else None


def roots_for(agent):
    """Every skill root this agent keeps.

    Hermes runs one skill tree PER PROFILE (`profiles/<name>/skills`), so a
    single hardcoded root updates the wrong agent the moment more than one
    profile exists - it reports a skill as blocked while the session in front of
    you still loads the old copy.
    """
    env_name, candidates = _ROOTS[agent]
    env = os.environ.get(env_name)
    if env and os.path.isdir(env):
        return [env]
    out = []
    for cand in candidates:
        real = _expand(cand)
        if real and os.path.isdir(real) and real not in out:
            out.append(real)
    if agent == "hermes":
        profiles = os.path.join(_expand("%LOCALAPPDATA%"), "hermes", "profiles")
        if os.path.isdir(profiles):
            for name in sorted(os.listdir(profiles)):
                p = os.path.join(profiles, name, "skills")
                if os.path.isdir(p) and p not in out:
                    out.append(p)
    return out


def _looks_like_ours(skill_dir):
    """Adopt an unstamped directory only if it is unmistakably a prior copy.

    An older RobloxForge installed before the stamp file existed carries our
    reference layout; anything else is someone else's skill and must never be
    overwritten.
    """
    return os.path.isfile(os.path.join(skill_dir, "references", "development-loop.md"))


def _installed_version(skill_dir):
    try:
        with open(os.path.join(skill_dir, STAMP), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return None


def status():
    from . import __version__

    def state_of(skill_dir):
        if not os.path.isdir(skill_dir):
            return "absent"
        v = _installed_version(skill_dir)
        if v is None:
            # ours-but-unstamped is stale, not foreign: it needs an update
            return "stale (unstamped)" if _looks_like_ours(skill_dir) else "foreign"
        if v != __version__:
            return "stale (%s -> %s)" % (v, __version__)
        return "current"

    out = {}
    for agent in _ROOTS:
        roots = roots_for(agent)
        entry = {"root": roots[0] if roots else None, "roots": roots}
        if not roots:
            entry["note"] = "skill directory not found"
            out[agent] = entry
            continue
        states = {}
        for name in OUR_SKILLS:
            per_root = {r: state_of(os.path.join(r, name)) for r in roots}
            values = list(per_root.values())
            if all(v == "absent" for v in values):
                states[name] = "absent"
            elif "foreign" in values:
                states[name] = "foreign"
            else:
                stale = [v for v in values if v.startswith("stale")]
                states[name] = stale[0] if stale else "current"
            if len(roots) > 1:
                entry.setdefault("by_root", {})[name] = per_root
        entry["skills"] = states
        out[agent] = entry
    return out


def install(agents=None):
    """Copy our skills into every skill root each agent has. Repeatable."""
    from . import __version__
    src_root = paths.skills_source_dir()
    targets = agents or list(_ROOTS)
    results = {}
    for agent in targets:
        if agent not in _ROOTS:
            raise ForgeError("RBF-ARG-001", "unknown agent %r" % agent,
                             hint="one of: %s" % ", ".join(_ROOTS))
        roots = roots_for(agent)
        if not roots:
            results[agent] = "skipped: no skill directory found"
            continue
        notes = []
        for root in roots:
            copied = []
            blocked = None
            for name in OUR_SKILLS:
                src = os.path.join(src_root, name)
                dst = os.path.join(root, name)
                if os.path.isdir(dst) and _installed_version(dst) is None \
                        and not _looks_like_ours(dst):
                    blocked = "blocked: %s exists and is not RobloxForge's (%s)" % (name, root)
                    break
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                with open(os.path.join(dst, STAMP), "w", encoding="utf-8") as fh:
                    fh.write(__version__)
                # The installed skill points at vendored knowledge by relative path, which stops
                # working outside the checkout. Record where this install came from.
                vendor = os.path.join(os.path.dirname(os.path.abspath(src_root)), "knowledge", "vendor")
                with open(os.path.join(dst, "KNOWLEDGE-PATH.txt"), "w", encoding="utf-8") as fh:
                    if os.path.isdir(vendor):
                        fh.write("knowledge/vendor is at:\n%s\n" % vendor)
                    else:
                        fh.write("knowledge/vendor was not shipped with this install.\n"
                                 "Fall back to the first-party references in this skill, or the official\n"
                                 "Roblox Creator Hub documentation.\n")
                copied.append(name)
            notes.append(blocked or ("installed %s" % ", ".join(copied) if copied
                                     else "nothing to do"))
        results[agent] = "; ".join(notes)
    return results


def remove(agents=None):
    """Uninstall ONLY our skill dirs, from every root. Foreign content untouched."""
    targets = agents or list(_ROOTS)
    results = {}
    for agent in targets:
        roots = roots_for(agent)
        if not roots:
            results[agent] = "no skill directory"
            continue
        removed = []
        for root in roots:
            for name in OUR_SKILLS:
                d = os.path.join(root, name)
                if os.path.isdir(d) and _installed_version(d) is not None:
                    shutil.rmtree(d)
                    removed.append(os.path.join(root, name))
        results[agent] = "removed %s" % ", ".join(removed) if removed else "nothing of ours present"
    return results
