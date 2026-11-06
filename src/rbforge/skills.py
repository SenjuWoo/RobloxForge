"""Install, verify and remove RobloxForge's skill catalog without destroying user work.

Design rules, each one earned by a defect this file used to have:

* A version stamp alone never proves an install. Every skill carries a manifest of the files we
  wrote and their hashes, so `status` can tell `current` from `partial` (payload missing) and
  `modified` (the payload changed, or extra files appeared).
* `current` means current in EVERY root the agent uses. Hermes runs one skill tree per profile, so
  one healthy profile and one untouched profile is not "current".
* Nothing is deleted to make room. Preflight runs over every root before a single byte is written; a
  foreign skill aborts the whole install, and a directory we do not fully own is moved to a
  timestamped backup instead of being removed.
* Activation is a rename, not a mirror: the new copy is staged, then swapped in, and the previous
  copy is restored if the swap fails.
"""
import hashlib
import json
import os
import shutil
import time

from . import paths
from .errors import ForgeError

OUR_SKILLS = (
    "roblox-game-development",
    "roblox-docs",
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
MANIFEST = ".rbforge-manifest.json"

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

    Hermes runs one skill tree PER PROFILE (`profiles/<name>/skills`), so a single hardcoded root
    updates the wrong agent the moment more than one profile exists - it reports a skill as blocked
    while the session in front of you still loads the old copy.
    """
    env_name, candidates = _ROOTS[agent]
    env = os.environ.get(env_name)
    if env and os.path.isdir(env):
        return [env]
    out, seen = [], set()

    def add(path):
        # The same root arrives spelled two ways (`\\` vs `/`, case), and installing it twice is
        # just work; compare normalized paths, keep the first spelling.
        key = os.path.normcase(os.path.abspath(path))
        if path and key not in seen and os.path.isdir(path):
            seen.add(key)
            out.append(path)

    for cand in candidates:
        add(_expand(cand))
    if agent == "hermes":
        profiles = os.path.join(_expand("%LOCALAPPDATA%"), "hermes", "profiles")
        if os.path.isdir(profiles):
            for name in sorted(os.listdir(profiles)):
                add(os.path.join(profiles, name, "skills"))
    return out


def _looks_like_ours(skill_dir):
    """Adopt an unstamped directory only if it is unmistakably a prior copy."""
    return os.path.isfile(os.path.join(skill_dir, "references", "development-loop.md"))


def _installed_version(skill_dir):
    try:
        with open(os.path.join(skill_dir, STAMP), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return None


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_manifest(skill_dir):
    try:
        with open(os.path.join(skill_dir, MANIFEST), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("files"), dict) else None


def _manifest_files(skill_dir):
    """Every file we would write for this skill, relative to its directory."""
    out = []
    for base, _dirs, names in os.walk(skill_dir):
        for name in names:
            rel = os.path.relpath(os.path.join(base, name), skill_dir).replace("\\", "/")
            if rel in (STAMP, MANIFEST):
                continue
            out.append(rel)
    return sorted(out)


def _extra_files(skill_dir, manifest):
    """Files present on disk that this install never wrote - i.e. the user's."""
    if manifest is None:
        return []
    known = set(manifest.get("files") or {})
    known.update({STAMP, MANIFEST})
    return sorted(p for p in _manifest_files(skill_dir) if p not in known)


def _matches_source(skill_dir, src_dir):
    """True when every file on disk matches the shipped copy: provably ours, safe to replace."""
    ours = [rel for rel in _manifest_files(skill_dir) if rel != "KNOWLEDGE-PATH.txt"]
    theirs = [rel for rel in _manifest_files(src_dir) if rel != "KNOWLEDGE-PATH.txt"]
    if sorted(ours) != sorted(theirs):
        return False
    for rel in ours:
        try:
            if _sha(os.path.join(skill_dir, rel.replace("/", os.sep))) != \
                    _sha(os.path.join(src_dir, rel.replace("/", os.sep))):
                return False
        except OSError:
            return False
    return True


def state_of(skill_dir):
    """One directory's state: absent | foreign | partial | stale | modified | current."""
    from . import __version__

    if not os.path.isdir(skill_dir):
        return "absent"
    version = _installed_version(skill_dir)
    if version is None:
        return "stale (unstamped)" if _looks_like_ours(skill_dir) else "foreign"
    manifest = _read_manifest(skill_dir)
    if manifest is not None:
        for rel, want in manifest["files"].items():
            path = os.path.join(skill_dir, rel.replace("/", os.sep))
            if not os.path.isfile(path):
                return "partial (missing %s)" % rel
            if _sha(path) != want:
                return "modified (%s)" % rel
    elif not os.path.isfile(os.path.join(skill_dir, "SKILL.md")):
        # Pre-manifest installs can only be judged by their entry point.
        return "partial (no SKILL.md)"
    if _extra_files(skill_dir, manifest):
        return "modified (extra files kept)"
    if version != __version__:
        return "stale (%s -> %s)" % (version, __version__)
    return "current"


# Worst-first: one bad root must not be hidden by a healthy one.
_WORST = ("foreign", "partial", "stale", "modified", "absent")


def _combine(values):
    for prefix in _WORST:
        for v in values:
            if v.startswith(prefix):
                return v
    return "current"


def status():
    out = {}
    for agent in _ROOTS:
        roots = roots_for(agent)
        entry = {"root": roots[0] if roots else None, "roots": roots}
        if not roots:
            entry["note"] = "skill directory not found"
            entry["skills"] = {name: "absent" for name in OUR_SKILLS}
            out[agent] = entry
            continue
        states = {}
        for name in OUR_SKILLS:
            per_root = {r: state_of(os.path.join(r, name)) for r in roots}
            states[name] = _combine(list(per_root.values()))
            if len(roots) > 1:
                entry.setdefault("by_root", {})[name] = per_root
        entry["skills"] = states
        entry["current"] = all(v == "current" for v in states.values())
        out[agent] = entry
    return out


def _write_manifest(dst, version):
    files = {rel: _sha(os.path.join(dst, rel.replace("/", os.sep))) for rel in _manifest_files(dst)}
    payload = {"version": version, "files": files}
    with open(os.path.join(dst, MANIFEST), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, sort_keys=True)
    with open(os.path.join(dst, STAMP), "w", encoding="utf-8") as fh:
        fh.write(version)
    return payload


def _write_knowledge_pointer(dst, src_root):
    vendor = os.path.join(os.path.dirname(os.path.abspath(src_root)), "knowledge", "vendor")
    with open(os.path.join(dst, "KNOWLEDGE-PATH.txt"), "w", encoding="utf-8") as fh:
        if os.path.isdir(vendor):
            fh.write("knowledge/vendor is at:\n%s\n" % vendor)
        else:
            fh.write("knowledge/vendor was not shipped with this install.\n"
                     "Fall back to the first-party references in this skill, or the official\n"
                     "Roblox Creator Hub documentation.\n")


def _plan(agent):
    """Preflight every root before touching anything.

    Returns (roots, plan) where plan maps root -> {skill: decision}. Decision is one of
    `current` (skip), `replace`, `backup-and-replace` or `blocked:<reason>`.
    """
    from . import __version__

    src_root = paths.skills_source_dir()
    roots = roots_for(agent)
    plan = {}
    for root in roots:
        per_skill = {}
        for name in OUR_SKILLS:
            if not os.path.isdir(os.path.join(src_root, name)):
                per_skill[name] = "blocked: source skill %s is missing from this install" % name
                continue
            dst = os.path.join(root, name)
            state = state_of(dst)
            if state == "absent":
                per_skill[name] = "install"
            elif state.startswith("foreign"):
                per_skill[name] = "blocked: %s exists and is not RobloxForge's (%s)" % (name, root)
            elif state == "current" and _installed_version(dst) == __version__:
                # A pre-manifest install can look current because the stamp matches. Re-install it
                # once so the directory gains a manifest - without a backup only when every byte is
                # provably ours.
                src_dir = os.path.join(src_root, name)
                per_skill[name] = ("replace" if _matches_source(dst, src_dir)
                                   else "backup-and-replace") if _read_manifest(dst) is None else "current"
            elif state.startswith(("modified", "partial")) or state == "stale (unstamped)":
                # Content we cannot prove is ours gets preserved, not deleted.
                per_skill[name] = "backup-and-replace"
            else:
                per_skill[name] = "replace"
        plan[root] = per_skill
    return roots, plan


def install(agents=None):
    """Copy our skills into every skill root each agent has. Repeatable and non-destructive."""
    from . import __version__

    targets = agents or list(_ROOTS)
    results = {}
    for agent in targets:
        if agent not in _ROOTS:
            raise ForgeError("RBF-ARG-001", "unknown agent %r" % agent,
                             hint="one of: %s" % ", ".join(_ROOTS))
        roots, plan = _plan(agent)
        if not roots:
            results[agent] = "skipped: no skill directory found"
            continue
        blocked = [msg for per in plan.values() for msg in per.values()
                   if isinstance(msg, str) and msg.startswith("blocked")]
        if blocked:
            # Nothing was written: a foreign skill anywhere cancels the whole batch.
            results[agent] = "blocked before any change: " + "; ".join(sorted(set(blocked)))
            continue

        src_root = paths.skills_source_dir()
        notes = []
        for root in roots:
            changed, kept, skipped = [], [], []
            for name in OUR_SKILLS:
                decision = plan[root][name]
                dst = os.path.join(root, name)
                if decision == "current":
                    skipped.append(name)
                    continue
                stage = os.path.join(root, ".rbforge-stage-%s-%d" % (name, os.getpid()))
                if os.path.isdir(stage):
                    shutil.rmtree(stage)
                try:
                    shutil.copytree(os.path.join(src_root, name), stage)
                    _write_knowledge_pointer(stage, src_root)
                    _write_manifest(stage, __version__)
                except OSError as exc:
                    shutil.rmtree(stage, ignore_errors=True)
                    raise ForgeError("RBF-SKILL-002",
                                     "could not stage %s: %s" % (name, exc),
                                     hint="nothing was replaced; fix the filesystem and rerun")
                backup = None
                try:
                    if os.path.isdir(dst):
                        if decision == "backup-and-replace":
                            backup = "%s.rbforge-backup-%s" % (dst, time.strftime("%Y%m%d-%H%M%S"))
                            os.replace(dst, backup)
                        else:
                            os.replace(dst, stage + ".old")
                            backup = stage + ".old"
                    os.replace(stage, dst)
                except OSError as exc:
                    # Put the previous copy back before reporting the failure.
                    shutil.rmtree(stage, ignore_errors=True)
                    if backup and os.path.isdir(backup) and not os.path.isdir(dst):
                        os.replace(backup, dst)
                    raise ForgeError("RBF-SKILL-003", "could not activate %s: %s" % (name, exc),
                                     hint="the previous copy was restored")
                if backup and os.path.isdir(backup) and not backup.endswith(".old"):
                    kept.append(os.path.basename(backup))
                elif backup:
                    shutil.rmtree(backup, ignore_errors=True)
                changed.append(name)
            parts = []
            if changed:
                parts.append("installed %d" % len(changed))
            if kept:
                parts.append("kept user copies: %s" % ", ".join(kept))
            if skipped:
                parts.append("already current %d" % len(skipped))
            notes.append("%s: %s" % (root, "; ".join(parts) or "nothing to do"))
        results[agent] = " | ".join(notes)
    return results


def remove(agents=None):
    """Uninstall ONLY the files we wrote. Anything the user added stays where it is."""
    targets = agents or list(_ROOTS)
    results = {}
    for agent in targets:
        roots = roots_for(agent)
        if not roots:
            results[agent] = "no skill directory"
            continue
        removed, kept = [], []
        for root in roots:
            for name in OUR_SKILLS:
                d = os.path.join(root, name)
                if not os.path.isdir(d):
                    continue
                manifest = _read_manifest(d)
                if manifest is None:
                    if _installed_version(d) is None:
                        continue  # not ours
                    shutil.rmtree(d)  # pre-manifest install: nothing to preserve selectively
                    removed.append(d)
                    continue
                extras = _extra_files(d, manifest)
                for rel in manifest["files"]:
                    path = os.path.join(d, rel.replace("/", os.sep))
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                for rel in (STAMP, MANIFEST, "KNOWLEDGE-PATH.txt"):
                    try:
                        os.remove(os.path.join(d, rel))
                    except OSError:
                        pass
                # Drop directories that are now empty, but never one still holding user files.
                for base, dirs, files in os.walk(d, topdown=False):
                    if not dirs and not files:
                        try:
                            os.rmdir(base)
                        except OSError:
                            pass
                if extras and os.path.isdir(d):
                    kept.append(d)
                elif os.path.isdir(d):
                    shutil.rmtree(d, ignore_errors=True)
                    removed.append(d)
                else:
                    removed.append(d)
        parts = []
        if removed:
            parts.append("removed %d" % len(removed))
        if kept:
            parts.append("kept (user files inside): %s" % ", ".join(kept))
        results[agent] = "; ".join(parts) or "nothing of ours present"
    return results
