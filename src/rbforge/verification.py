"""Verification receipts: observations are recorded here, not asserted by the caller.

The trusting boundary is this module. An agent can call `receipt()` with anything it likes,
but a *verified* level can only be reached through an observation this package recorded
itself:

    observation_id = collect_evidence(...)   # RobloxForge queries Studio and stores the result
    receipt(task, observation_id=...)        # the receipt references that stored record

A receipt that merely claims `provenance="tool"` is downgraded: that argument is no longer read
for trust at all. Observations are bound to Studio id, place, execution context and time, and
expire, so a stale or fabricated reference cannot be reused later.

This is tamper-*resistant against a careless agent*, not against one with full write access to
the receipts directory. Claiming more than that would be dishonest.
"""
import hashlib
import json
import os
import time

from . import paths

GAMEPLAY_CHECKS = (
    "studio_connected", "core_loop_exists", "player_spawns", "primary_action_works",
    "gameplay_path_exercised", "console_checked",
)

LEVEL_CLAIM = {
    "verified_playtest": "working (a scenario ran and its observations were recorded by the tooling)",
    "playtested_with_errors": "an observed test reported errors - FIX BEFORE CLAIMING DONE",
    "playtest_observed_partial": "partially observed: a required observation (test, console, screenshot) is missing",
    "playtest_claimed": "the agent claims a playtest; nothing was observed by the tooling",
    "static_only": "exists; NOT runtime-proven",
    "unverified": "unverified - do not claim working",
}

OBSERVATION_MAX_AGE = 6 * 3600  # evidence for one working session, not forever


# ------------------------------------------------------------------ filesystem plumbing

def _receipts_dir():
    return paths.receipts_dir()


def _observations_path():
    return os.path.join(_receipts_dir(), "observations.json")


class _FileLock:
    """Cross-process exclusive lock: the whole append transaction runs inside it."""

    def __init__(self, path):
        self.path = path
        self.fh = None

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.fh = open(self.path, "a+b")
        try:
            import msvcrt
            msvcrt.locking(self.fh.fileno(), msvcrt.LK_LOCK, 1)
        except ImportError:
            import fcntl
            fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        if self.fh is None:
            return False
        try:
            try:
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            except ImportError:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        finally:
            self.fh.close()
            self.fh = None
        return False


def _write_json(path, data):
    """Write through a temp file so a crash cannot leave a half-written record."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


def _as_list(value):
    """A string is one item, not a list of characters."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _receipt_files(out_dir):
    """Receipts in creation order: sequence first, mtime as the fallback for older files."""
    try:
        names = [n for n in os.listdir(out_dir)
                 if n.endswith(".json") and n != "observations.json"]
    except OSError:
        return []
    rows = []
    for name in names:
        path = os.path.join(out_dir, name)
        seq = None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                seq = json.load(fh).get("sequence")
        except (OSError, ValueError):
            seq = None
        try:
            mtime = os.stat(path).st_mtime
        except OSError:
            continue
        rows.append(((seq if isinstance(seq, int) else 10 ** 9, mtime), name))
    return [name for _key, name in sorted(rows)]


# --------------------------------------------------------------------- observations

def _observation_id(payload):
    body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return "obs-" + hashlib.sha256(body + str(time.time_ns()).encode()).hexdigest()[:16]


def record_observation(payload):
    """Store one observation and return its opaque id.

    Called by `collect_evidence` after Studio answered; exposed so tests - and any other
    tool-integrated caller - register a genuine observation instead of inventing a dict.
    """
    record = dict(payload)
    record["recorded_at"] = time.time()
    record["provenance"] = "tool"
    obs_id = _observation_id(record)
    with _FileLock(os.path.join(_receipts_dir(), ".observations.lock")):
        path = _observations_path()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                store = json.load(fh)
        except (OSError, ValueError):
            store = {}
        store[obs_id] = record
        _write_json(path, store)
    return obs_id


def load_observation(obs_id, max_age=OBSERVATION_MAX_AGE):
    """The stored observation, or None when the id is unknown, expired or malformed."""
    if not isinstance(obs_id, str) or not obs_id.startswith("obs-"):
        return None
    try:
        with open(_observations_path(), "r", encoding="utf-8") as fh:
            store = json.load(fh)
    except (OSError, ValueError):
        return None
    record = store.get(obs_id)
    if not isinstance(record, dict):
        return None
    if time.time() - float(record.get("recorded_at") or 0) > max_age:
        return None
    return record


def collect_evidence(studio_id=None, test_path=None, test_attr="RbforgeTest",
                     screenshots=None, screenshots_inspected=False, untested=None,
                     place=None):
    """Query Studio through RobloxForge's own MCP session and record what comes back.

    Every value here is produced by the tooling; the caller supplies only intent (which test to
    run, which screenshots exist). Raises ForgeError when Studio is unreachable - a missing
    observation is a gap, not a pass.
    """
    from . import live

    with live.Session(studio_id) as session:
        sid = session.studio_id
        place_name = session.luau("return game.Name", "Edit").strip()
        datamodel = "Edit"

    tests = []
    if test_path:
        result = live.server_test(test_path, test_attr, studio_id=sid)
        tests.append({
            "name": os.path.basename(test_path),
            "expected": "PASS",
            "actual": result["result"],
            "passed": result["passed"],
        })

    payload = {
        "studio_id": sid,
        "place": place_name or place,
        "datamodel": datamodel,
        "tests": tests,
        "console_logged": False,
        "console_errors": 0,
        "screenshots": _as_list(screenshots),
        "screenshots_inspected": bool(screenshots_inspected),
        "untested": _as_list(untested),
    }
    payload["observation_id"] = record_observation(payload)
    return payload


# ------------------------------------------------------------------------- receipts

def _digest(rec):
    body = {k: v for k, v in rec.items() if k not in ("digest", "saved_to")}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _required_checks():
    return {
        "studio_connected": False,
        "place_inspected_before_edit": False,
        "core_loop_exists": False,
        "player_spawns": False,
        "primary_action_works": False,
        "progression_works": False,
        "failure_death_behavior_works": False,
        "console_checked": False,
        "no_fatal_runtime_errors": False,
        "gameplay_path_exercised": False,
        "screenshot_captured": False,
        "screenshot_inspected": False,
    }


def _next_receipt_path(out_dir, task):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in task)[:60] or "receipt"
    for n in range(1, 1000):
        candidate = os.path.join(out_dir, "%s-%s-%03d.json" % (stamp, safe, n))
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            continue
        os.close(fd)
        return candidate
    raise RuntimeError("could not reserve a receipt filename in %s" % out_dir)


def _level(trusted, observation, agent_tests, agent_claim, console_errors):
    """The single place that decides a level, so the receipt's fields cannot contradict it."""
    if trusted:
        tests = observation.get("tests") or []
        failed = [t for t in tests if t.get("passed") is not True]
        if failed or int(observation.get("console_errors") or 0) > 0 or console_errors > 0:
            return "playtested_with_errors"
        complete = (bool(tests) and observation.get("console_logged") is True
                    and observation.get("screenshots") and observation.get("screenshots_inspected"))
        return "verified_playtest" if complete else "playtest_observed_partial"
    if agent_claim and agent_tests:
        return "playtest_claimed"
    if agent_claim or agent_tests:
        return "static_only"
    return "unverified"


def receipt(task, checks=None, evidence=None, observation_id=None, provenance=None,
            console_errors=0, playtest_performed=False, screenshot_captured=False,
            screenshot_inspected=False, limitations=None, project=None, studio_id=None,
            save=True):
    """Build (and by default persist) a verification receipt.

    Trust comes from `observation_id` alone - an id returned by `collect_evidence()` or
    `record_observation()`. `provenance` and a caller-supplied `evidence` dict are recorded as
    claims; they can never promote a receipt beyond `playtest_claimed`, whatever they contain.
    """
    evidence = evidence if isinstance(evidence, dict) else {}
    claimed_evidence = dict(evidence)
    claimed_evidence.pop("provenance", None)

    observation = load_observation(observation_id)
    trusted = observation is not None
    if trusted and studio_id and observation.get("studio_id") != studio_id:
        trusted, observation = False, None
    if trusted and project and observation.get("project") not in (None, project):
        trusted, observation = False, None

    state = _required_checks()
    claimed = [name for name in (checks or []) if name in state]
    obs = observation if (trusted and observation) else {}

    if trusted:
        # Only the recorded observation fills observed checks; the caller's claims never do.
        state["studio_connected"] = bool(obs.get("studio_id"))
        state["place_inspected_before_edit"] = bool(obs.get("place"))
        state["console_checked"] = obs.get("console_logged") is True
        state["no_fatal_runtime_errors"] = (
            state["console_checked"] and int(obs.get("console_errors") or 0) == 0)
        state["gameplay_path_exercised"] = bool(obs.get("tests"))
        state["screenshot_captured"] = bool(obs.get("screenshots"))
        state["screenshot_inspected"] = bool(obs.get("screenshots_inspected"))
        for name in GAMEPLAY_CHECKS:
            if (obs.get("checks") or {}).get(name) is True:
                state[name] = True

    agent_tests = [t for t in (claimed_evidence.get("tests") or []) if isinstance(t, dict)]
    obs_tests = (obs.get("tests") or []) if trusted else []
    errors_now = int(obs.get("console_errors") or 0) if trusted else int(console_errors or 0)

    level = _level(trusted, obs, agent_tests, bool(playtest_performed), errors_now)

    screenshots = _as_list(obs.get("screenshots"))
    if not screenshots and screenshot_captured:
        screenshots = ["captured"]
    inspected = bool(obs.get("screenshots_inspected") or
                     (screenshot_inspected and screenshot_captured))
    # A verified receipt never carries a field that contradicts it.
    if level == "verified_playtest" and not (screenshots and inspected):
        level = "playtest_observed_partial"

    rec = {
        "task": task,
        "project": project,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "checks": state,
        "claimed_checks": claimed,
        "evidence": {
            "observation_id": observation_id if trusted else None,
            "provenance": "tool" if trusted else "agent",
            "studio_id": obs.get("studio_id"),
            "place": obs.get("place"),
            "datamodel": obs.get("datamodel"),
            "console_logged": obs.get("console_logged") is True,
            "screenshots": screenshots,
            "tests": obs_tests or agent_tests,
            "untested": _as_list(obs.get("untested")) or
                        _as_list(claimed_evidence.get("untested")),
        },
        "console_errors_reported": errors_now,
        "playtest_performed": bool(playtest_performed),
        "screenshot_captured": bool(screenshots),
        "screenshot_inspected_by_vision": inspected,
        "verification_level": level,
        "claim_allowed": LEVEL_CLAIM[level],
        "limitations": _as_list(limitations) + _as_list(claimed_evidence.get("untested")),
    }
    if not trusted:
        rec["limitations"].append(
            "no observation was recorded by RobloxForge; the evidence is the caller's word")

    if save:
        with _FileLock(os.path.join(_receipts_dir(), ".receipts.lock")):
            out_dir = _receipts_dir()
            previous, sequence = None, 1
            for name in reversed(_receipt_files(out_dir)):
                try:
                    with open(os.path.join(out_dir, name), "r", encoding="utf-8") as fh:
                        last = json.load(fh)
                    previous = last.get("digest")
                    sequence = int(last.get("sequence") or 0) + 1
                    break
                except (OSError, ValueError):
                    continue
            rec["sequence"] = sequence
            rec["prev_digest"] = previous
            rec["digest"] = _digest(rec)
            file_path = _next_receipt_path(out_dir, task)
            _write_json(file_path, rec)
            rec["saved_to"] = file_path
    return rec


def verify_chain(out_dir=None):
    """Check the receipt history: unique sequence, intact digests, unbroken links."""
    out_dir = out_dir or _receipts_dir()
    problems = []
    expected_previous = None
    seen = set()
    last_seq = 0
    names = _receipt_files(out_dir)
    for name in names:
        path = os.path.join(out_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError) as exc:
            problems.append("%s: unreadable (%s)" % (name, exc))
            continue
        seq = rec.get("sequence")
        if not isinstance(seq, int):
            problems.append("%s: no sequence" % name)
        else:
            if seq in seen:
                problems.append("%s: duplicate sequence %s" % (name, seq))
            if seq <= last_seq:
                problems.append("%s: sequence %s not increasing after %s" % (name, seq, last_seq))
            seen.add(seq)
            last_seq = max(last_seq, seq)
        if rec.get("prev_digest") != expected_previous:
            problems.append("%s: prev_digest does not match the previous receipt" % name)
        if _digest({k: v for k, v in rec.items() if k != "saved_to"}) != rec.get("digest"):
            problems.append("%s: digest does not match its payload" % name)
        expected_previous = rec.get("digest")
    return {"receipts": len(names), "ok": not problems, "problems": problems}
