"""Verification receipts: evidence records, not claims.

A receipt separates two things that used to be mixed together:

  claimed   what the agent says it did
  observed  what the tooling actually saw (Studio id, place, execution context,
            test results, console output, screenshots)

Only `observed` promotes a receipt to a verified level. Claims are recorded on the
receipt so a reader can see the gap, but a claim alone never becomes evidence.
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


def _previous_digest(out_dir):
    """Hash of the most recent receipt already on disk, or None.

    Chaining is what turns a folder of receipts into an audit trail: a receipt
    that claims a state can be checked against the one it follows, so a later
    edit cannot quietly rewrite history.
    """
    try:
        names = sorted(n for n in os.listdir(out_dir) if n.endswith(".json"))
    except OSError:
        return None
    for name in reversed(names):
        try:
            with open(os.path.join(out_dir, name), "r", encoding="utf-8") as fh:
                return json.load(fh).get("digest")
        except (OSError, ValueError):
            continue
    return None


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


def _unique_path(out_dir, stamp, safe):
    """A receipt never overwrites another, even inside the same second."""
    base = os.path.join(out_dir, "%s-%s" % (stamp, safe or "receipt"))
    path = base + ".json"
    n = 2
    while os.path.exists(path):
        path = "%s-%d.json" % (base, n)
        n += 1
    return path


def receipt(task, checks=None, evidence=None, console_errors=0, playtest_performed=False,
            screenshot_captured=False, screenshot_inspected=False,
            limitations=None, project=None, save=True):
    """Build (and by default persist) a verification receipt.

    `checks` are the agent's claims and are recorded as such. `evidence` is what the
    tooling observed:

        studio_id, place, datamodel      identity of the session the work happened in
        checks {name: bool}              checks observed by tooling, not asserted
        tests [{name, expected, actual, passed}]
        console_logged                   console was actually read
        screenshots [paths], screenshots_inspected
        untested [str]                   scenarios deliberately not covered
    """
    evidence = evidence if isinstance(evidence, dict) else {}
    state = _required_checks()

    claimed = [name for name in (checks or []) if name in state]
    raw_checks = evidence.get("checks")
    observed_in = raw_checks if isinstance(raw_checks, dict) else {}
    for name in state:
        if observed_in.get(name) is True:
            state[name] = True

    tests = [t for t in (evidence.get("tests") or []) if isinstance(t, dict)]
    tests_ok = bool(tests) and all(t.get("passed") is True for t in tests)
    console_logged = evidence.get("console_logged") is True
    errors_now = int(console_errors or 0)
    shots = evidence.get("screenshots") or []
    visual = bool((shots and evidence.get("screenshots_inspected")) or
                  (screenshot_captured and screenshot_inspected))

    gameplay_evidence = all(state[k] for k in GAMEPLAY_CHECKS)

    if gameplay_evidence and tests_ok and playtest_performed:
        if console_logged and errors_now == 0 and visual:
            level = "verified_playtest"
        else:
            level = "playtested_with_errors"
    elif gameplay_evidence or tests:
        level = "static_only"
    else:
        level = "unverified"

    rec = {
        "task": task,
        "project": project,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "checks": state,
        "claimed_checks": claimed,
        "evidence": {
            "studio_id": evidence.get("studio_id"),
            "place": evidence.get("place"),
            "datamodel": evidence.get("datamodel"),
            "console_logged": console_logged,
            "screenshots": shots,
            "tests": tests,
            "untested": evidence.get("untested") or [],
        },
        "console_errors_reported": errors_now,
        "playtest_performed": bool(playtest_performed),
        "screenshot_captured": bool(screenshot_captured),
        "screenshot_inspected_by_vision": bool(screenshot_inspected),
        "verification_level": level,
        "claim_allowed": {
            "verified_playtest": "working (as tested)",
            "playtested_with_errors": "works with known errors - FIX BEFORE CLAIMING DONE",
            "static_only": "exists; NOT runtime-proven",
            "unverified": "unverified - do not claim working",
        }[level],
        "limitations": list(limitations or []) + list(evidence.get("untested") or []),
    }
    if save:
        out_dir = paths.receipts_dir()
        rec["prev_digest"] = _previous_digest(out_dir)
        rec["digest"] = _digest(rec)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in task)[:60]
        file_path = _unique_path(out_dir, stamp, safe)
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, indent=2)
        rec["saved_to"] = file_path
    return rec
