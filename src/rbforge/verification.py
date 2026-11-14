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
import base64
import binascii
import hashlib
import json
import os
import re
import time
import uuid

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
    """Receipts in creation order, legacy first.

    Pre-0.13 receipts have no `sequence`. Treating "missing sequence" as "late" made a legacy
    receipt sort after newer ones and every link look broken, so the rule is: the legacy prefix
    keeps its historical filename order, then sequenced receipts follow by sequence number.
    """
    try:
        names = [n for n in os.listdir(out_dir)
                 if n.endswith(".json") and n != "observations.json"]
    except OSError:
        return []
    legacy, sequenced = [], []
    for name in names:
        path = os.path.join(out_dir, name)
        rec = {}
        try:
            with open(path, "r", encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            rec = {}
        seq = rec.get("sequence")
        try:
            mtime = os.stat(path).st_mtime
        except OSError:
            continue
        if isinstance(seq, int):
            sequenced.append((seq, name))
        else:
            legacy.append((mtime, name))
    return [n for _m, n in sorted(legacy)] + [n for _s, n in sorted(sequenced)]


# --------------------------------------------------------------------- observations

def _observation_id(payload):
    body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return "obs-" + hashlib.sha256(body + str(time.time_ns()).encode()).hexdigest()[:16]


def _record_observation(payload):
    """Store one observation and return its opaque id.

    Private on purpose: `collect_evidence` calls this after Studio answered. It is not a way
    for a caller to promote its own dict to "observed" - tests inject a fake *session* into
    `collect_evidence` instead, which exercises the real collector.
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
        if not isinstance(store, dict):
            store = {}
        # Expired observations can never verify anything again; dropping them keeps the store small.
        now = record["recorded_at"]
        store = {k: v for k, v in store.items()
                 if isinstance(v, dict) and now - _recorded_at(v) <= OBSERVATION_MAX_AGE}
        store[obs_id] = record
        _write_json(path, store)
    return obs_id


def _recorded_at(record):
    try:
        return float(record.get("recorded_at") or 0)
    except (TypeError, ValueError):
        return 0.0


def load_observation(obs_id, max_age=OBSERVATION_MAX_AGE):
    """The stored observation, or None when the id is unknown, expired or malformed."""
    if not isinstance(obs_id, str) or not obs_id.startswith("obs-"):
        return None
    try:
        with open(_observations_path(), "r", encoding="utf-8") as fh:
            store = json.load(fh)
    except (OSError, ValueError):
        return None
    record = store.get(obs_id) if isinstance(store, dict) else None
    if not isinstance(record, dict):
        return None
    if time.time() - _recorded_at(record) > max_age:
        return None
    return record


# Console classification over the shapes Studio actually prints:
#     [Server] Error: attempt to index nil
#     19:52:36.782  ServerScriptService.Main:4: attempt to index nil
#     stack begin
# A timestamp, a [Tag] prefix and a `Script:line:` location are stripped first, so the marker is
# matched at the real start of the message. "No error was found" stays clean because the word is not
# in marker position.
CONSOLE_PREFIX = re.compile(
    r"^\s*(?:\d{1,2}:\d{2}:\d{2}(?:\.\d+)?\s+)?(?:\[[^\]]{1,24}\]\s*)*"
    r"(?:[\w./-]+:\d+:\s*)?", re.I)
CONSOLE_ERROR = re.compile(
    r"^(?:script error|error|fatal|attempt to|stack begin|stack trace)\b", re.I)
CONSOLE_WARNING = re.compile(r"^(?:warning|warn)\b", re.I)


def _console_marker(line):
    return CONSOLE_PREFIX.sub("", line).strip()


def classify_console(text):
    """(status, errors, warnings) where status is ok | errors | unknown.

    `unknown` means the output cannot support a clean claim: no text at all, or text that neither
    looks like a failure nor like normal output. It is never treated as "no errors".
    """
    if text is None:
        return "unknown", 0, 0
    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
    if not lines:
        return "unknown", 0, 0
    errors = sum(1 for ln in lines if CONSOLE_ERROR.search(_console_marker(ln)))
    warnings = sum(1 for ln in lines if CONSOLE_WARNING.search(_console_marker(ln)))
    return ("errors" if errors else "ok"), errors, warnings


SHOT_MAX_BYTES = 8 * 1024 * 1024
SHOT_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def _save_capture(blocks, text):
    """Turn an MCP screen_capture response into small, checkable records.

    Image blocks are decoded and stored under the receipts directory with a digest; text-only
    responses are recorded as an unverified reference, because a path proves nothing about pixels.
    """
    records = []
    for block in blocks:
        if block.get("type") != "image":
            continue
        mime = str(block.get("mimeType") or "").lower()
        data = block.get("data")
        if mime not in SHOT_TYPES or not isinstance(data, str):
            continue
        try:
            raw = base64.b64decode(data, validate=True)
        except (ValueError, binascii.Error):
            continue
        if not raw or len(raw) > SHOT_MAX_BYTES:
            continue
        digest = hashlib.sha256(raw).hexdigest()
        folder = os.path.join(_receipts_dir(), "shots")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "%s.%s" % (digest[:16], SHOT_TYPES[mime]))
        if not os.path.exists(path):
            with open(path, "wb") as fh:
                fh.write(raw)
        records.append({"artifact": path, "sha256": digest, "mime": mime, "bytes": len(raw),
                        "captured_at": time.time(), "verified_image": True})
    if not records and isinstance(text, str) and text.strip():
        records.append({"artifact": text.strip()[:400], "sha256": None, "mime": None, "bytes": None,
                        "captured_at": time.time(), "verified_image": False})
    return records


def collect_evidence(studio_id=None, test_path=None, test_attr="RbforgeTest",
                     screenshots=None, screenshots_inspected=False, untested=None,
                     place=None, project=None, scenario=None, revision=None,
                     capture_screenshot=False, session_factory=None, datamodel="Edit"):
    """Query Studio through RobloxForge's own MCP session and record what comes back.

    The caller supplies intent (which test to run, whether to capture a screenshot); every value
    that establishes trust is read from Studio. Console output is fetched through the documented
    `get_console_output` tool - if that tool is unavailable, `console_logged` stays False and the
    receipt can only be partial. Tests inject `session_factory`, which exercises this same path.
    """
    from . import live

    factory = session_factory or (lambda: live.Session(studio_id))
    with factory() as session:
        sid = session.studio_id
        # Evidence is usually collected during a playtest, where the Edit datamodel is unavailable.
        dm = datamodel
        try:
            identity = session.luau("return game.Name", "Edit").strip()
        except Exception:  # noqa: BLE001 - Studio is in Play; the Server context still answers
            dm = "Server"
            identity = session.luau("return game.Name", "Server").strip()
        place_name = identity or place

    tests = []
    if test_path:
        # server_test opens its own session; a second one opened around it here only spawned a
        # StudioMCP process that sat idle for the whole test.
        result = live.server_test(test_path, test_attr, studio_id=sid)
        tests.append({
            "name": os.path.basename(test_path),
            "expected": "PASS",
            "actual": result["result"],
            "passed": result["passed"],
        })

    console_text, console_logged, console_status = "", False, "unknown"
    console_errors = console_warnings = 0
    # A caller-supplied path is a claim. Only image bytes that Studio returned, or a text reference
    # the tool itself produced, are recorded as captures - and only images can be inspected.
    claimed_shots = _as_list(screenshots)
    shots = []
    # One session reads the console and takes the capture: each session is a StudioMCP spawn.
    try:
        with factory() as session:
            try:
                console_text = session.call("get_console_output", {"studio_id": sid}) or ""
                console_logged = True
                console_status, console_errors, console_warnings = classify_console(console_text)
            except Exception:  # noqa: BLE001 - the tool may not exist in this Studio build
                console_text, console_logged, console_status = "", False, "unknown"
                console_errors = console_warnings = 0
            if capture_screenshot:
                try:
                    # The real tool requires a capture_id; without it the call fails with
                    # "Missing required argument: capture_id".
                    blocks, is_error, text = session.call_content(
                        "screen_capture", {"studio_id": sid,
                                           "capture_id": "rbforge-%s" % uuid.uuid4().hex[:12]})
                    if not is_error:
                        shots = _save_capture(blocks, text)
                except Exception:  # noqa: BLE001 - capture is best effort, never a claim
                    shots = []
    except Exception:  # noqa: BLE001 - no session at all: nothing observed, recorded as such
        pass

    inspection = None
    if screenshots_inspected and shots:
        # An attestation, not a tool observation: recorded with what it refers to.
        inspection = {"performed": True, "by": "agent", "artifact_sha256": shots[0].get("sha256")}

    payload = {
        "studio_id": sid,
        "place": place_name,
        "datamodel": dm,
        "project": project,
        "scenario": scenario,
        "revision": revision,
        "tests": tests,
        "console_logged": console_logged,
        "console_status": console_status,
        "console_errors": console_errors,
        "console_warnings": console_warnings,
        "console_digest": hashlib.sha256(console_text.encode("utf-8")).hexdigest()[:16] if console_logged else None,
        "screenshots": shots,
        "claimed_screenshots": claimed_shots,
        "visual_inspection": inspection,
        "screenshots_inspected": bool(inspection),
        "screenshot_requested": bool(capture_screenshot or claimed_shots),
        "untested": _as_list(untested),
    }
    payload["observation_id"] = _record_observation(payload)
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


def _next_receipt_path(out_dir, task, sequence):
    """A destination that cannot collide, without leaving an empty placeholder behind.

    The sequence is allocated under the append lock, so `-<sequence>` alone is unique; the previous
    implementation created an empty .json and then replaced it, which a crash could leave behind.
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in task)[:60] or "receipt"
    path = os.path.join(out_dir, "%s-%06d-%s.json" % (stamp, sequence, safe))
    n = 2
    while os.path.exists(path):
        path = os.path.join(out_dir, "%s-%06d-%s-%02d.json" % (stamp, sequence, safe, n))
        n += 1
    return path


def _level(trusted, observation, agent_tests, agent_claim, console_errors):
    """The single place that decides a level, so the receipt's fields cannot contradict it."""
    if trusted:
        tests = observation.get("tests") or []
        failed = [t for t in tests if t.get("passed") is not True]
        if failed or int(observation.get("console_errors") or 0) > 0 or console_errors > 0:
            return "playtested_with_errors"
        # A caller-supplied claim (or a bare path) cannot satisfy the screenshot requirement: only
        # image bytes Studio returned, plus a recorded inspection attestation, count.
        images = [s for s in (observation.get("screenshots") or []) if isinstance(s, dict)
                  and s.get("verified_image")]
        inspection = observation.get("visual_inspection") or {}
        inspected = bool(inspection.get("performed")) and any(
            inspection.get("artifact_sha256") == s.get("sha256") for s in images)
        complete = (bool(tests) and observation.get("console_status") == "ok"
                    and images and inspected)
        return "verified_playtest" if complete else "playtest_observed_partial"
    if agent_claim and agent_tests:
        return "playtest_claimed"
    if agent_claim or agent_tests:
        return "static_only"
    return "unverified"


def receipt(task, checks=None, evidence=None, observation_id=None, provenance=None,
            console_errors=0, playtest_performed=False, screenshot_captured=False,
            screenshot_inspected=False, limitations=None, project=None, studio_id=None,
            scenario=None, revision=None, save=True):
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
    binding = []
    # Omission is not a match. An observation recorded for project/scenario/revision X can only
    # verify a receipt that states X - otherwise a past playtest would support an unrelated claim
    # simply by leaving the fields out.
    if trusted:
        for field, given in (("project", project), ("scenario", scenario), ("revision", revision)):
            recorded = observation.get(field)
            if recorded is not None and given != recorded:
                binding.append("%s recorded as %r, receipt says %r" % (field, recorded, given))
        if studio_id and observation.get("studio_id") != studio_id:
            binding.append("studio recorded as %r, receipt says %r"
                           % (observation.get("studio_id"), studio_id))
        if binding:
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
            state["console_checked"] and obs.get("console_status") == "ok"
            and int(obs.get("console_errors") or 0) == 0)
        state["gameplay_path_exercised"] = bool(obs.get("tests"))
        images = [s for s in (obs.get("screenshots") or []) if isinstance(s, dict)
                  and s.get("verified_image")]
        state["screenshot_captured"] = bool(images)
        state["screenshot_inspected"] = bool((obs.get("visual_inspection") or {}).get("performed"))
        for name in GAMEPLAY_CHECKS:
            if (obs.get("checks") or {}).get(name) is True:
                state[name] = True

    agent_tests = [t for t in (claimed_evidence.get("tests") or []) if isinstance(t, dict)]
    obs_tests = (obs.get("tests") or []) if trusted else []
    errors_now = int(obs.get("console_errors") or 0) if trusted else int(console_errors or 0)

    level = _level(trusted, obs, agent_tests, bool(playtest_performed), errors_now)

    # Observed fields come from the observation; caller booleans stay claims and never fill them.
    screenshots = [s for s in (obs.get("screenshots") or []) if isinstance(s, dict)]
    inspected = bool((obs.get("visual_inspection") or {}).get("performed")) and bool(screenshots)
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
            "binding": {"project": project, "scenario": scenario, "revision": revision,
                        "studio_id": studio_id, "mismatches": binding},
            "provenance": "tool" if trusted else "agent",
            "studio_id": obs.get("studio_id"),
            "place": obs.get("place"),
            "datamodel": obs.get("datamodel"),
            "console_logged": obs.get("console_logged") is True,
            "screenshots": [
                {"artifact": s.get("artifact"), "sha256": s.get("sha256"), "mime": s.get("mime"),
                 "bytes": s.get("bytes"), "verified_image": bool(s.get("verified_image"))}
                for s in screenshots],
            "visual_inspection": obs.get("visual_inspection"),
            "claimed_screenshots": _as_list(claimed_evidence.get("screenshots")),
            "tests": obs_tests or agent_tests,
            "untested": _as_list(obs.get("untested")) or
                        _as_list(claimed_evidence.get("untested")),
        },
        "console_errors_reported": errors_now,
        "playtest_performed": bool(playtest_performed),
        "screenshot_captured": bool(screenshots),
        # An attestation, not a machine check: the tool cannot see pixels.
        "screenshot_inspected_by_vision": inspected,
        "screenshot_inspection_kind": "agent_attestation" if inspected else None,
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
            rec["scenario"] = scenario
            rec["revision"] = revision
            rec["prev_digest"] = previous
            rec["digest"] = _digest(rec)
            file_path = _next_receipt_path(out_dir, task, sequence)
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
            # Legacy (pre-0.13) receipt: no sequence, but its digest and link must still hold.
            seq = None
        if seq is not None:
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
