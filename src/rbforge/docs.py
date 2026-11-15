"""Current-knowledge system: a local cache of Roblox's official creator-docs.

Why this exists: model memory about Roblox is stale, and the official Studio
MCP's own `http_get` only reaches allow-listed doc URLs one page at a time.
A local corpus can be *searched and ranked* offline, so an agent reads three
relevant sections instead of guessing or dumping a whole page into context.

Upstream:  https://github.com/Roblox/creator-docs  (branch main)
License:   CC-BY-4.0 for prose, MIT-style LICENSE-CODE for code samples.
           The cache is downloaded to the user's machine at runtime; this
           repository never vendors Roblox documentation.

Freshness is always reported honestly. Offline refresh failure degrades to the
cached copy and says so - it never silently claims to be current.
"""
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time

from . import paths
from .errors import ForgeError

REPO_URL = "https://github.com/Roblox/creator-docs.git"
BRANCH = "main"
CONTENT_SUBDIR = os.path.join("content", "en-us")
STALE_AFTER_HOURS = 24.0

_MD_EXT = (".md", ".yaml", ".yml")
_SKIP_DIRS = {".git", "includes", "assets", "img", "images"}


# ------------------------------------------------------------------ state

def _state_path():
    return paths.docs_state_file()


def read_state():
    try:
        with open(_state_path(), "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def write_state(**kw):
    state = read_state()
    state.update(kw)
    with open(_state_path(), "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
    return state


def cache_present():
    return os.path.isdir(os.path.join(paths.docs_cache_dir(), CONTENT_SUBDIR))


def freshness():
    """Honest freshness report. Never guesses."""
    state = read_state()
    present = cache_present()
    fetched = state.get("fetched_at")
    age_hours = None
    if fetched:
        age_hours = max(0.0, (time.time() - float(fetched)) / 3600.0)
    return {
        "present": present,
        "path": paths.docs_cache_dir() if present else None,
        "method": state.get("method"),
        "commit": state.get("commit"),
        "fetched_at": fetched,
        "age_hours": round(age_hours, 2) if age_hours is not None else None,
        "stale": (age_hours is None or age_hours > STALE_AFTER_HOURS) if present else None,
        "indexed_documents": state.get("indexed_documents"),
        "last_refresh_error": state.get("last_refresh_error"),
    }


# ------------------------------------------------------------- acquisition

def _git():
    return paths.which("git")


def _run_git(args, cwd=None, timeout=600):
    # stdin is closed so git can never prompt (or read the MCP server's JSON-RPC stream), and
    # localized git messages cannot raise UnicodeDecodeError past the callers' error handling.
    return subprocess.run([_git()] + args, cwd=cwd, capture_output=True, stdin=subprocess.DEVNULL,
                          text=True, encoding="utf-8", errors="replace", timeout=timeout)


def _git_commit(cache):
    try:
        done = _run_git(["rev-parse", "HEAD"], cwd=cache, timeout=60)
        if done.returncode == 0:
            return done.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


# A plain `git clone --depth 1` of creator-docs costs ~20 GB, because
# content/en-us/assets carries 4k PNGs, 1.3k JPGs and 800 MP4s, and the
# blobs come down with it. Blobless + sparse checkout of just the prose
# and the engine reference costs ~27 MB - the same 1007 .md and 1232 .yaml
# files an agent can actually read. Measured, not assumed.
SPARSE_PATTERNS = [
    "/content/en-us/**/*.md",
    "/content/en-us/**/*.yaml",
    "/LICENSE*",
    "/README.md",
]


def _write_sparse(cache):
    info_dir = os.path.join(cache, ".git", "info")
    os.makedirs(info_dir, exist_ok=True)
    with open(os.path.join(info_dir, "sparse-checkout"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(SPARSE_PATTERNS) + "\n")


def _cache_is_lean(cache):
    """True when the checkout was made with our sparse rules.

    A cache cloned by an older/naive path would be enormous; we re-clone it
    rather than let it sit on the user's disk.
    """
    marker = os.path.join(cache, ".git", "info", "sparse-checkout")
    if not os.path.isfile(marker):
        return False
    return not os.path.isdir(os.path.join(cache, CONTENT_SUBDIR, "assets"))


def _rmtree(path):
    """Remove a tree that may hold git's read-only object files (Windows refuses to delete those)."""
    def retry(func, target, _exc):
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError:
            pass
    if os.path.isdir(path):
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=retry)
        else:  # 3.11: onexc does not exist yet
            shutil.rmtree(path, onerror=retry)


def _clone_git(cache):
    """Clone into a staging folder and swap it in only once the checkout succeeded.

    The old cache is moved aside, never deleted first: an offline or failed clone leaves the
    working cache exactly as it was.
    """
    parent = os.path.dirname(cache)
    os.makedirs(parent, exist_ok=True)
    stage = tempfile.mkdtemp(prefix=".creator-docs-stage-", dir=parent)
    try:
        done = _run_git(["clone", "--filter=blob:none", "--no-checkout", "--depth", "1",
                         "--single-branch", "--branch", BRANCH, REPO_URL, stage])
        if done.returncode != 0:
            raise ForgeError("RBF-DOCS-002", "git clone of creator-docs failed",
                             hint="check network access to github.com; the existing cache was kept",
                             stderr=done.stderr.strip()[-800:])
        _run_git(["sparse-checkout", "init", "--no-cone"], cwd=stage, timeout=120)
        _write_sparse(stage)
        done = _run_git(["checkout", BRANCH], cwd=stage)
        if done.returncode != 0:
            raise ForgeError("RBF-DOCS-002", "sparse checkout of creator-docs failed",
                             hint="check disk space and that the cache path is writable",
                             stderr=done.stderr.strip()[-800:])
        commit = _git_commit(stage)
        old = None
        if os.path.isdir(cache):
            old = "%s.old-%d" % (cache, os.getpid())
            try:
                os.replace(cache, old)
            except OSError as exc:
                raise ForgeError("RBF-DOCS-004", "cannot replace the creator-docs cache: %s" % exc,
                                 hint="close anything holding files in %s and retry" % cache)
        os.replace(stage, cache)
        stage = None
        if old:
            _rmtree(old)
    finally:
        if stage:
            _rmtree(stage)
    return {"method": "git-sparse", "commit": commit}


def _pull_git(cache):
    _write_sparse(cache)  # keep the checkout lean even if upstream adds trees
    done = _run_git(["fetch", "--depth", "1", "origin", BRANCH], cwd=cache)
    if done.returncode != 0:
        raise ForgeError("RBF-DOCS-003", "git fetch of creator-docs failed",
                         hint="the cached copy is still usable; retry when online",
                         stderr=done.stderr.strip()[-800:])
    done = _run_git(["reset", "--hard", "FETCH_HEAD"], cwd=cache)
    if done.returncode != 0:
        raise ForgeError("RBF-DOCS-003", "git reset to fetched creator-docs failed",
                         stderr=done.stderr.strip()[-800:])
    return {"method": "git-sparse", "commit": _git_commit(cache)}


def _require_git():
    """git is a hard requirement for the docs cache, and that is deliberate.

    The obvious alternative - GitHub's zipball - is the full working tree,
    which for creator-docs means ~10 GB of images and videos with no way to
    ask for a subset. Sparse blobless git fetches the same 2.2k text files in
    ~27 MB. Rather than ship a fallback that quietly eats a user's disk, we
    report the missing dependency and say how to fix it.
    """
    if _git():
        return
    raise ForgeError(
        "RBF-DOCS-006", "git is required to fetch the Roblox creator-docs cache",
        hint="install Git for Windows (https://git-scm.com/download/win), reopen "
             "your terminal, then run: rbforge docs update. Everything else in "
             "RobloxForge works without git.")


def ensure(refresh=False, allow_network=True):
    """Make the cache usable. Returns a freshness dict.

    First use with no cache clones. A fresh cache is left alone. `refresh=True`
    attempts an update; if that fails while a cache exists, the cached copy is
    kept and the failure is recorded rather than raised - being offline must
    never destroy working knowledge.
    """
    cache = paths.docs_cache_dir()

    if cache_present() and not _cache_is_lean(cache):
        # A checkout made without our sparse rules; replace it rather than
        # leave gigabytes of assets on disk.
        if allow_network and _git():
            try:
                write_state(fetched_at=time.time(), last_refresh_error=None, **_clone_git(cache))
                build_index(force=True)
                return freshness()
            except ForgeError as exc:
                # The clone failed, and _clone_git kept the old cache: use it and say so.
                write_state(last_refresh_error={"code": exc.code, "message": exc.message,
                                                "at": time.time()})

    if not cache_present():
        if not allow_network:
            raise ForgeError("RBF-DOCS-001",
                             "no creator-docs cache and network use is disabled",
                             hint="run: rbforge docs update")
        _require_git()
        info = _clone_git(cache)
        write_state(fetched_at=time.time(), last_refresh_error=None, **info)
        build_index(force=True)
        return freshness()

    if refresh and allow_network:
        try:
            _require_git()
            info = (_pull_git(cache) if os.path.isdir(os.path.join(cache, ".git"))
                    else _clone_git(cache))
            write_state(fetched_at=time.time(), last_refresh_error=None, **info)
            build_index(force=True)
        except ForgeError as exc:
            # Offline or upstream trouble: keep the cache, tell the truth.
            write_state(last_refresh_error={"code": exc.code, "message": exc.message,
                                            "at": time.time()})
    build_index(force=False)
    return freshness()


# ------------------------------------------------------------------- index

def _index_path():
    return os.path.join(paths.home(), "docs-index.json")


_FRONT_TITLE = re.compile(r"^title:\s*(.+?)\s*$", re.M)
_H_LINE = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.M)
_YAML_NAME = re.compile(r"^name:\s*(\S+)\s*$", re.M)
_MEMBER_SECTION = re.compile(r"^(properties|methods|events|callbacks|functions|items):\s*$")
_MEMBER_NAME = re.compile(r"^\s+-\s+name:\s*(\S+)\s*$")


def _content_root():
    return os.path.join(paths.docs_cache_dir(), CONTENT_SUBDIR)


def _iter_doc_files():
    root = _content_root()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            if name.lower().endswith(_MD_EXT):
                yield os.path.join(dirpath, name)


def _parse_yaml_reference(text):
    """Extract API identity from an engine reference YAML without a YAML lib.

    These files are machine-generated with a stable shape, so a line scan is
    both sufficient and dependency-free.
    """
    name_match = _YAML_NAME.search(text)
    api_name = name_match.group(1) if name_match else None
    members, section = [], None
    for line in text.splitlines():
        top = _MEMBER_SECTION.match(line)
        if top:
            section = top.group(1)
            continue
        if line and not line[0].isspace():
            section = None
            continue
        if section:
            member = _MEMBER_NAME.match(line)
            if member:
                # Reference YAML qualifies members as `Owner:Method` or
                # `Owner.Property`; queries use the bare name, so store that.
                members.append(_SPLIT.split(member.group(1))[-1])
    return api_name, sorted(set(members))


def build_index(force=False):
    """Build (or reuse) the search index. Cheap enough to run on every ensure."""
    if not cache_present():
        raise ForgeError("RBF-DOCS-001", "creator-docs cache is not present",
                         hint="run: rbforge docs update")
    state = read_state()
    index_file = _index_path()
    if not force and os.path.isfile(index_file):
        try:
            with open(index_file, "r", encoding="utf-8") as handle:
                cached = json.load(handle)
            if cached.get("commit") == state.get("commit") and cached.get("documents"):
                return cached
        except (OSError, ValueError):
            pass

    root = paths.docs_cache_dir()
    documents = []
    for full in _iter_doc_files():
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            continue
        rel = os.path.relpath(full, root).replace("\\", "/")
        is_reference = "/reference/engine/" in "/" + rel
        entry = {"path": rel, "size": len(text)}
        if is_reference and rel.lower().endswith((".yaml", ".yml")):
            api_name, members = _parse_yaml_reference(text)
            entry["kind"] = "engine-reference"
            entry["title"] = api_name or os.path.splitext(os.path.basename(rel))[0]
            entry["api"] = api_name
            entry["members"] = members
            entry["headings"] = []
        else:
            title = _FRONT_TITLE.search(text[:2000])
            headings = [h[1] for h in _H_LINE.findall(text)][:40]
            entry["kind"] = "guide"
            entry["title"] = (title.group(1).strip('"\'') if title
                              else (headings[0] if headings else
                                    os.path.splitext(os.path.basename(rel))[0]))
            entry["api"] = None
            entry["members"] = []
            entry["headings"] = headings
        documents.append(entry)

    index = {"commit": state.get("commit"), "built_at": time.time(),
             "documents": documents}
    with open(index_file, "w", encoding="utf-8") as handle:
        json.dump(index, handle)
    write_state(indexed_documents=len(documents))
    return index


def load_index():
    try:
        with open(_index_path(), "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return build_index(force=True)


# ------------------------------------------------------------------ search

# split API paths *and* prose: "TweenService:Create", "RunService.Heartbeat",
# and "checkpoint respawn" all decompose the same way.
_SPLIT = re.compile(r"[.:\s]+")


def _query_parts(query):
    """`TweenService:Create` -> ("TweenService", "Create").

    A bare single token is treated as *both* an owner and a member candidate,
    because `ProcessReceipt` and `StreamingEnabled` are members whose owning
    class the caller usually does not know - that is why they are asking.
    """
    query = query.strip()
    parts = [p for p in _SPLIT.split(query) if p]
    if len(parts) >= 2:
        return parts[0], parts[-1], parts
    if len(parts) == 1 and " " not in query:
        return query, query, parts
    return query, None, parts


MIN_SCORE = 10


def _scan_bodies(terms, limit):
    """Full-text pass over the cached corpus for prose queries.

    The sparse cache is ~27 MB of text, so scanning it costs well under a
    second and is always current - cheaper to maintain than an inverted index
    that has to be invalidated. Only runs when identity ranking came up short.
    """
    if not terms:
        return {}
    root = paths.docs_cache_dir()
    hits = {}
    for full in _iter_doc_files():
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as handle:
                body = handle.read().lower()
        except OSError:
            continue
        score = 0
        for term in terms:
            found = body.count(term)
            if not found:
                score = 0
                break  # require every term to appear
            score += min(found, 10)
        if score:
            rel = os.path.relpath(full, root).replace("\\", "/")
            hits[rel] = score
    return dict(sorted(hits.items(), key=lambda kv: (-kv[1], kv[0]))[:limit * 3])


def search(query, limit=8, kind=None):
    """Rank documents for a query. Exact API identity always outranks prose."""
    if not query or not query.strip():
        raise ForgeError("RBF-ARG-001", "search query is empty")
    index = load_index()
    owner, member, parts = _query_parts(query)
    owner_l = owner.lower()
    member_l = member.lower() if member else None
    terms = [p.lower() for p in parts if len(p) > 2]
    scored = []

    for doc in index["documents"]:
        if kind and doc["kind"] != kind:
            continue
        score, why = 0, []
        api = (doc.get("api") or "")
        api_l = api.lower()
        title_l = (doc.get("title") or "").lower()
        base = os.path.basename(doc["path"]).lower()
        members_l = [m.lower() for m in doc.get("members") or []]

        if api_l and api_l == owner_l:
            score += 100
            why.append("exact API name")
        elif base.split(".")[0] == owner_l:
            score += 70
            why.append("exact file name")
        elif api_l and owner_l in api_l:
            score += 30
            why.append("API name contains query")

        if member_l and member_l in members_l:
            score += 60
            why.append("declares member %s" % member)
        elif member_l and any(member_l in m for m in members_l):
            score += 20
            why.append("member name match")

        if title_l == owner_l:
            score += 40
            why.append("exact title")
        elif owner_l in title_l:
            score += 12
            why.append("title match")

        for heading in doc.get("headings") or []:
            if owner_l in heading.lower():
                score += 6
                why.append("heading match")
                break

        for term in terms:
            if term in doc["path"].lower():
                score += 4
        if doc["kind"] == "engine-reference" and member_l:
            score += 3  # API-shaped query: prefer the API reference

        if score >= MIN_SCORE:
            scored.append((score, doc, why))

    if len(scored) < limit:
        by_path = {d["path"]: d for d in index["documents"]}
        prose_terms = terms or [owner_l]
        for rel, body_score in _scan_bodies(prose_terms, limit).items():
            doc = by_path.get(rel)
            if not doc or any(s[1]["path"] == rel for s in scored):
                continue
            if kind and doc["kind"] != kind:
                continue
            scored.append((min(body_score, 40), doc, ["body text match"]))

    scored.sort(key=lambda item: (-item[0], item[1]["path"]))
    results = []
    for score, doc, why in scored[:limit]:
        results.append({
            "path": doc["path"], "title": doc["title"], "kind": doc["kind"],
            "score": score, "why": sorted(set(why)),
            "url": _doc_url(doc["path"]),
        })
    fresh = freshness()
    return {"query": query, "results": results, "total_matches": len(scored),
            "freshness": {"stale": fresh["stale"], "age_hours": fresh["age_hours"],
                          "commit": fresh["commit"], "method": fresh["method"],
                          "last_refresh_error": fresh["last_refresh_error"]},
            "source": "Roblox/creator-docs (official)"}


def _doc_url(rel):
    """Best-effort creator-hub URL for a cached file. Reference pages differ."""
    if not rel.startswith("content/en-us/"):
        return None
    tail = rel[len("content/en-us/"):]
    if tail.startswith("reference/engine/classes/"):
        return "https://create.roblox.com/docs/reference/engine/classes/" + \
               os.path.splitext(os.path.basename(tail))[0]
    if tail.lower().endswith(".md"):
        return "https://create.roblox.com/docs/" + tail[:-3]
    return None


def read(rel_path, max_chars=8000, around=None):
    """Read one cached document. Bounded, so nobody dumps the corpus into context."""
    root = paths.docs_cache_dir()
    full = os.path.normpath(os.path.join(root, rel_path))
    if not full.startswith(os.path.normpath(root) + os.sep):
        raise ForgeError("RBF-ARG-003", "path escapes the docs cache: %r" % rel_path)
    if not os.path.isfile(full):
        raise ForgeError("RBF-DOCS-005", "no such cached document: %r" % rel_path,
                         hint="run rbforge docs search first and use a returned path")
    with open(full, "r", encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    truncated = False
    if around:
        low = text.lower()
        at = low.find(around.lower())
        if at >= 0:
            start = max(0, at - max_chars // 3)
            text = text[start:start + max_chars]
            truncated = True
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True
    return {"path": rel_path, "url": _doc_url(rel_path), "truncated": truncated,
            "content": text, "source": "Roblox/creator-docs (official)"}
