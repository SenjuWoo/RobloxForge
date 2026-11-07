"""Install, verify and remove RobloxForge's skill catalog without destroying user work.

Design rules, each one earned by a defect this file used to have:

* A version stamp alone never proves an install. Every skill carries a manifest of the files we
  wrote and their hashes, so `status` can tell `current` from `partial` (payload missing) and
  `modified` (the payload changed, or extra files appeared).
* Manifests are untrusted input. They live on disk, in a directory the user can edit, so every path
  in one is validated and proven to stay inside the skill directory before anything is deleted.
* `current` means current in EVERY root the agent uses. Hermes runs one skill tree per profile, so
  one healthy profile and one untouched profile is not "current".
* Nothing is deleted to make room. Preflight runs over every root before a single byte is written; a
  foreign skill aborts the whole install, and a directory we do not fully own is moved to a
  timestamped backup instead of being removed.
* Installation is a transaction: every skill is staged and validated first, then activated by rename,
  and a failure anywhere restores what was already activated.
* Uninstall removes only files whose bytes still match the manifest. A modified file, an extra file,
  or a directory without a valid manifest is preserved and reported.
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
ESSENTIAL = "SKILL.md"

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


def safe_rel(rel, skill_dir):
    """Absolute path for a manifest entry, or None when the entry is not provably inside.

    A manifest is user-editable data, so it can name `../victim.txt`, a drive-qualified path, or a
    link out of the tree. Anything that does not resolve inside the skill directory is refused, and
    the refusal is what stops `remove` from becoming an arbitrary file deleter.
    """
    if not isinstance(rel, str) or not rel.strip():
        return None
    if rel.startswith(("/", "\\")) or ":" in rel or "\x00" in rel:
        return None
    parts = rel.replace("\\", "/").split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None
    candidate = os.path.join(skill_dir, *parts)
    root = os.path.realpath(skill_dir)
    real = os.path.realpath(candidate)
    if os.path.commonpath([root, real]) != root:
        return None  # a symlink or a crafted name escaped the tree
    return candidate


def _read_manifest(skill_dir, version=None):
    """A validated manifest, or None.

    Requires the documented shape, a version that matches the stamp, at least one entry, the
    essential file, and every path provably inside the directory. A manifest that fails any of these
    is treated as absent: the install then reads as `partial`, never `current`.
    """
    try:
        with open(os.path.join(skill_dir, MANIFEST), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or set(data) - {"version", "files", "dirs"}:
        return None
    dirs = data.get("dirs")
    if dirs is not None and (not isinstance(dirs, list)
                             or any(safe_rel(d, skill_dir) is None for d in dirs)):
        return None
    files = data.get("files")
    if not isinstance(files, dict) or not files:
        return None
    if version is not None and data.get("version") != version:
        return None
    if ESSENTIAL not in files:
        return None
    for rel, want in files.items():
        if not isinstance(want, str) or len(want) != 64:
            return None
        if safe_rel(rel, skill_dir) is None:
            return None
    return data


def _is_link(path):
    """A symlink or a Windows junction. Junctions are directories, not symlinks, to the OS."""
    if os.path.islink(path):
        return True
    checker = getattr(os.path, "isjunction", None)
    try:
        return bool(checker and checker(path))
    except OSError:
        return False


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


def _manifest_dirs(skill_dir):
    """Every directory inside the skill, links included and never followed.

    Files alone are not an inventory: a user can add an empty folder or a junction into a skill, and
    a file-only walk cannot see either - so `remove` would delete them and `_matches_source` would call
    the tree ours. Links are reported as themselves, never as their target.
    """
    out = []
    for base, dirs, _names in os.walk(skill_dir, followlinks=False):
        prune = []
        for name in list(dirs):  # a stable copy: removing while iterating skips the next entry
            path = os.path.join(base, name)
            rel = os.path.relpath(path, skill_dir).replace("\\", "/")
            out.append(rel)
            if _is_link(path):
                prune.append(name)  # never descend: the target is not ours
        for name in prune:
            dirs.remove(name)
    return sorted(out)


def _extra_files(skill_dir, manifest):
    """Anything on disk this install never wrote - files, empty folders, symlinks, junctions."""
    if manifest is None:
        return []
    known = set(manifest.get("files") or {})
    known.update({STAMP, MANIFEST})
    extras = [p for p in _manifest_files(skill_dir) if p not in known]
    owned_dirs = manifest.get("dirs")
    if owned_dirs is not None:  # manifests before 0.13.11 did not record directories
        extras += [d for d in _manifest_dirs(skill_dir) if d not in set(owned_dirs)]
    return sorted(extras)


def _matches_source(skill_dir, src_dir):
    """True when every file and directory matches the shipped copy: provably ours, safe to replace."""
    ours = [rel for rel in _manifest_files(skill_dir) if rel != "KNOWLEDGE-PATH.txt"]
    theirs = [rel for rel in _manifest_files(src_dir) if rel != "KNOWLEDGE-PATH.txt"]
    if sorted(ours) != sorted(theirs):
        return False
    # An empty folder or a junction the user added is not in the source tree, so the copy is not
    # provably ours and must be backed up rather than replaced in place.
    if _manifest_dirs(skill_dir) != _manifest_dirs(src_dir):
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
    manifest = _read_manifest(skill_dir, version)
    if manifest is None:
        if not os.path.isfile(os.path.join(skill_dir, ESSENTIAL)):
            # Pre-manifest installs can only be judged by their entry point.
            return "partial (no SKILL.md)"
        if os.path.isfile(os.path.join(skill_dir, MANIFEST)):
            return "partial (manifest rejected)"
        # Version stamp alone proves nothing: without a manifest there is no record of which files we
        # wrote or whether they survived. Reinstall migrates it; until then it is not `current`.
        return "legacy (no manifest)"
    else:
        for rel, want in manifest["files"].items():
            path = safe_rel(rel, skill_dir)
            if path is None or not os.path.isfile(path):
                return "partial (missing %s)" % rel
            if _sha(path) != want:
                return "modified (%s)" % rel
    if _extra_files(skill_dir, manifest):
        return "modified (extra files kept)"
    if version != __version__:
        return "stale (%s -> %s)" % (version, __version__)
    return "current"


# Worst-first: one bad root must not be hidden by a healthy one.
_WORST = ("foreign", "partial", "legacy", "stale", "modified", "absent")


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
    payload = {"version": version, "files": files, "dirs": _manifest_dirs(dst)}
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


def backup_root():
    """Where replaced copies go. Never inside a skill root: every directory there is a loadable skill,
    and a backup named `roblox-audio.rbforge-backup-*` shows up as a duplicate skill in the agent UI."""
    return os.path.join(paths.home(), "backups")


def migrate_backups(agents=None):
    """Move backups that older versions left inside skill roots into the private backup folder.

    Only directories named after one of our own skills are touched - `<skill>.rbforge-backup-*` - so an
    unrelated folder whose name merely contains that marker is left alone. Failures are reported, not
    swallowed, and every agent name is validated before anything is read or moved.
    """
    targets = list(agents or _ROOTS)
    for agent in targets:
        if agent not in _ROOTS:
            raise ForgeError("RBF-ARG-001", "unknown agent %r" % agent,
                             hint="one of: %s" % ", ".join(_ROOTS))
    moved, failed = [], []
    by_agent = {agent: {"moved": [], "failed": []} for agent in targets}
    for agent in targets:
        for root in roots_for(agent):
            try:
                names = os.listdir(root)
            except OSError as exc:
                message = "%s: %s" % (root, exc)
                failed.append(message)
                by_agent[agent]["failed"].append(message)
                continue
            for name in names:
                if not any(name.startswith(skill + ".rbforge-backup-") for skill in OUR_SKILLS):
                    continue  # not ours, even if the marker appears somewhere in the name
                source = os.path.join(root, name)
                if not os.path.isdir(source):
                    continue
                try:
                    os.makedirs(backup_root(), exist_ok=True)
                    target = _unique(os.path.join(backup_root(), name))
                    os.replace(source, target)  # a rename: every byte inside moves with it
                    moved.append(target)
                    by_agent[agent]["moved"].append(target)
                except OSError as exc:
                    message = "%s: %s" % (source, exc)
                    failed.append(message)
                    by_agent[agent]["failed"].append(message)
    return {"moved": moved, "failed": failed, "by_agent": by_agent}


def _unique(path):
    """A path that does not exist yet - backups must never overwrite each other."""
    candidate, n = path, 1
    while os.path.exists(candidate):
        candidate = "%s-%d" % (path, n)
        n += 1
    return candidate


def _plan(agent):
    """Preflight every root before touching anything.

    Returns (roots, plan) where plan maps root -> {skill: decision}. Decision is one of
    `current` (skip), `install`, `replace`, `backup-and-replace` or `blocked:<reason>`.
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
                per_skill[name] = "current"
            elif state.startswith(("modified", "partial")):
                # Something on disk differs from what we recorded - an edited file, an added folder,
                # a touched generated pointer. Never replace in place: keep a copy, always.
                per_skill[name] = "backup-and-replace"
            else:
                # Replace in place only when the whole tree - files AND directories - is provably
                # the shipped copy. A manifest written before 0.13.11 has no `dirs`, so its word
                # alone cannot prove that a folder or a link the user added is ours.
                src_dir = os.path.join(src_root, name)
                per_skill[name] = ("replace" if _matches_source(dst, src_dir)
                                   else "backup-and-replace")
        plan[root] = per_skill
    return roots, plan


def _migration_note(migration, agent):
    """What migration did for this agent, or "" - failures must reach the caller, not vanish."""
    report = (migration.get("by_agent") or {}).get(agent) or {}
    parts = []
    if report.get("moved"):
        parts.append("migrated %d backup(s) out of a skill root" % len(report["moved"]))
    if report.get("failed"):
        parts.append("MIGRATION FAILED: " + "; ".join(report["failed"]))
    return ("; " + "; ".join(parts)) if parts else ""


def install(agents=None):
    """Copy our skills into every skill root each agent has, as one transaction per root."""
    from . import __version__

    targets = agents or list(_ROOTS)
    for agent in targets:
        if agent not in _ROOTS:
            raise ForgeError("RBF-ARG-001", "unknown agent %r" % agent,
                             hint="one of: %s" % ", ".join(_ROOTS))
    results = {}
    migration = migrate_backups(targets)
    for agent in targets:
        roots, plan = _plan(agent)
        if not roots:
            results[agent] = "skipped: no skill directory found" + _migration_note(migration, agent)
            continue
        blocked = [msg for per in plan.values() for msg in per.values()
                   if isinstance(msg, str) and msg.startswith("blocked")]
        if blocked:
            # Nothing was written: a foreign skill anywhere cancels the whole batch.
            results[agent] = ("blocked before any change: " + "; ".join(sorted(set(blocked)))
                              + _migration_note(migration, agent))
            continue

        src_root = paths.skills_source_dir()
        notes = []
        for root in roots:
            pending = [name for name in OUR_SKILLS if plan[root][name] != "current"]
            skipped = [name for name in OUR_SKILLS if plan[root][name] == "current"]

            # Phase 1: stage and validate every replacement before activating any of them.
            staged = {}
            attempted = []
            try:
                for name in pending:
                    stage = _unique(os.path.join(root, ".rbforge-stage-%s-%s-%d"
                                                 % (name, os.urandom(3).hex(), os.getpid())))
                    # Recorded before the copy: copytree can create the directory and then fail,
                    # which would leave debris that no cleanup list knows about.
                    attempted.append(stage)
                    shutil.copytree(os.path.join(src_root, name), stage)
                    _write_knowledge_pointer(stage, src_root)
                    _write_manifest(stage, __version__)
                    manifest = _read_manifest(stage, __version__)
                    if manifest is None or not os.path.isfile(os.path.join(stage, ESSENTIAL)):
                        raise ForgeError("RBF-SKILL-004",
                                         "staged copy of %s failed validation" % name,
                                         hint="nothing was activated")
                    staged[name] = stage
            except (OSError, ForgeError) as exc:
                for stage in attempted:
                    shutil.rmtree(stage, ignore_errors=True)
                raise ForgeError("RBF-SKILL-002", "could not stage %s: %s" % (agent, exc),
                                 hint="nothing was replaced")

            # Phase 2: activate by rename, recording what to undo.
            done, kept = [], []
            try:
                for name in pending:
                    stage = staged[name]
                    dst = os.path.join(root, name)
                    backup = None
                    if os.path.isdir(dst):
                        os.makedirs(backup_root(), exist_ok=True)
                        base = os.path.join(backup_root(), "%s.%s-%s" % (
                            name, time.strftime("%Y%m%d-%H%M%S"), os.urandom(2).hex()))
                        backup = _unique(base)
                        os.replace(dst, backup)
                    # The operation is in flight from this point: the original is already in the
                    # backup, so a failure below must put it back, not just report.
                    done.append((dst, backup, plan[root][name]))
                    os.replace(stage, dst)
            except OSError as exc:
                restored, failed = [], []
                for dst, backup, decision in reversed(done):
                    try:
                        if os.path.isdir(dst):
                            shutil.rmtree(dst, ignore_errors=True)
                        if backup and os.path.isdir(backup):
                            os.replace(backup, dst)
                        elif not backup:
                            pass  # nothing owned before: the empty destination is the restoration
                        restored.append(os.path.basename(dst))
                    except OSError:
                        failed.append(os.path.basename(dst))
                for stage in staged.values():
                    shutil.rmtree(stage, ignore_errors=True)
                detail = "restored %s" % ", ".join(restored) if restored else "nothing to restore"
                code = "RBF-SKILL-003"
                if failed:
                    detail += ("; ROLLBACK_FAILED for %s - the previous copy is under %s"
                               % (", ".join(failed), backup_root()))
                    code = "RBF-SKILL-005"
                raise ForgeError(code, "activation failed at %s: %s" % (agent, exc), hint=detail)

            for _dst, backup, decision in done:
                if backup and decision != "backup-and-replace":
                    shutil.rmtree(backup, ignore_errors=True)
                elif backup:
                    kept.append(os.path.basename(backup))
            parts = []
            if done:
                parts.append("installed %d" % len(done))
            if kept:
                parts.append("kept user copies: %s" % ", ".join(kept))
            if skipped:
                parts.append("already current %d" % len(skipped))
            notes.append("%s: %s" % (root, "; ".join(parts) or "nothing to do"))
        results[agent] = " | ".join(notes) + _migration_note(migration, agent)
    return results


def remove(agents=None):
    """Uninstall ONLY files whose bytes still match our manifest.

    Refuses a directory without a version stamp (not ours), skips a legacy install with no manifest
    (we cannot tell our files from the user's without one), preserves modified and extra files, and
    validates every manifest path before deleting anything.
    """
    targets = agents or list(_ROOTS)
    results = {}
    for agent in targets:
        roots = roots_for(agent)
        if not roots:
            results[agent] = "no skill directory"
            continue
        removed, kept, refused = [], [], []
        for root in roots:
            for name in OUR_SKILLS:
                d = os.path.join(root, name)
                if not os.path.isdir(d):
                    continue
                stamp = _installed_version(d)
                if stamp is None:
                    refused.append("%s (no RobloxForge stamp)" % name)
                    continue
                manifest = _read_manifest(d, stamp)
                if manifest is None:
                    refused.append("%s (legacy or invalid manifest - reinstall first)" % name)
                    continue

                # Preflight the whole skill before deleting one byte of it.
                targets_ok, modified = [], []
                for rel, want in manifest["files"].items():
                    path = safe_rel(rel, d)
                    if path is None:
                        refused.append("%s (manifest names a path outside the skill)" % name)
                        targets_ok = None
                        break
                    if os.path.isfile(path):
                        targets_ok.append(path) if _sha(path) == want else modified.append(rel)
                if targets_ok is None:
                    continue
                for path in targets_ok:
                    try:
                        os.remove(path)
                    except OSError:
                        modified.append(os.path.basename(path))
                for rel in (STAMP, MANIFEST):
                    try:
                        os.remove(os.path.join(d, rel))
                    except OSError:
                        pass
                # The knowledge pointer is generated, but the user may have edited it: it goes through
                # the same manifest-hash rule as every other managed file.
                pointer = os.path.join(d, "KNOWLEDGE-PATH.txt")
                if os.path.isfile(pointer):
                    want = (manifest.get("files") or {}).get("KNOWLEDGE-PATH.txt")
                    if want is None or _sha(pointer) == want:
                        try:
                            os.remove(pointer)
                        except OSError:
                            pass
                    else:
                        modified.append("KNOWLEDGE-PATH.txt")
                # Remove only directories the manifest recorded, deepest first, and only when empty.
                owned_dirs = manifest.get("dirs") or []
                for rel in sorted(owned_dirs, key=len, reverse=True):
                    path = safe_rel(rel, d)
                    if path:
                        try:
                            os.rmdir(path)
                        except OSError:
                            pass
                leftovers = _extra_files(d, manifest) if os.path.isdir(d) else []
                stray = _manifest_files(d) if os.path.isdir(d) else []
                if leftovers or stray:
                    kept.append("%s (kept %s)" % (name, ", ".join((leftovers + stray)[:3])))
                else:
                    try:
                        os.rmdir(d)  # never rmtree: an unknown entry must stop the delete
                    except OSError:
                        kept.append("%s (directory not empty)" % name)
                    else:
                        removed.append(name)
        parts = []
        if removed:
            parts.append("removed %d" % len(removed))
        if kept:
            parts.append("kept: %s" % "; ".join(kept))
        if refused:
            parts.append("refused: %s" % "; ".join(refused))
        results[agent] = " | ".join(parts) or "nothing of ours present"
    return results
