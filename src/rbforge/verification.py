"""Verification receipts: evidence records, not claims.

Three things are kept apart, because mixing them is how an agent ends up
"verifying" its own work:

  claimed     what the agent says it did
  evidence    observations, carrying a provenance: "tool" when RobloxForge
              produced them by talking to Studio, "agent" when the caller
              supplied them
  level       the strongest claim the receipt may make

Agent-supplied evidence can never exceed `playtest_claimed`. `verified_playtest`
requires observations this package collected itself (`collect_evidence`).
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
    "verified_playtest": "working (observed by tooling in Studio)",
    "playtested_with_errors": "works with known errors - FIX BEFORE CLAIMING DONE",
    "playtest_claimed": "agent claims a playtest; the evidence was supplied by the agent, not observed",
    "static_only": "exists; NOT runtime-proven",
    "unverified": "unverified - do not claim working",
}


def _as_list(value):
    """A string is one item, not a list of characters."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _receipt_files(out_dir):
    """Receipts in creation order.

    Filename sorting is not creation order: `-2` sorts before `.`, so a numbered suffix used to
    make the third receipt chain to the first one instead of the second.
    """
    try:
        names = [n for n in os.listdir(out_dir) if n.endswith(".json")]
    except OSError:
        return []
    rows = []
    for name in names:
        try:
            rows.append((os.stat(os.path.join(out_dir, name)).st_mtime, name))
        except OSError:
            continue
    return [name for _mtime, name in sorted(rows)]


def _previous_digest(out_dir):
    """Hash of the most recent receipt already on disk, or None.

    Chaining is what turns a folder of receipts into an audit trail: a receipt
    that claims a state can be checked against the one it follows, so a later
    edit cannot quietly rewrite history.
    """
    for name in reversed(_receipt_files(out_dir)):
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
    """Reserve a fresh receipt path atomically; never reuse another receipt's name."""
    base = "%s-%s" % (stamp, safe or "receipt")
    for n in range(1, 1000):
        candidate = os.path.join(out_dir, "%s-%03d.json" % (base, n))
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            continue
        os.close(fd)
        return candidate
    raise RuntimeError("could not reserve a receipt filename in %s" % out_dir)


def collect_evidence(studio_id=None, test_path=None, test_attr="RbforgeTest",
                     screenshots=None, screenshots_inspected=False, untested=None):
    """Observe a place through RobloxForge's own Studio session.

    This is the only path that marks evidence `provenance: "tool"`, because every value comes back
    from Studio instead of from the caller. Raises ForgeError when Studio is unreachable - a missing
    observation is a gap, not a pass.
    """
    from . import live

    with live.Session(studio_id) as session:
        sid = session.studio_id
        place = session.luau("return game.Name", "Edit").strip()

    tests = []
    if test_path:
        result = live.server_test(test_path, test_attr, studio_id=sid)
        tests.append({
            "name": os.path.basename(test_path),
            "expected": "PASS",
            "actual": result["result"],
            "passed": result["passed"],
        })

    return {
        "provenance": "tool",
        "studio_id": sid,
        "place": place,
        "datamodel": "Edit",
        "checks": {"studio_connected": True, "place_inspected_before_edit": bool(place)},
        "tests": tests,
        "console_logged": False,
        "screenshots": _as_list(screenshots),
        "screenshots_inspected": bool(screenshots_inspected),
        "untested": _as_list(untested),
    }


def receipt(task, checks=None, evidence=None, provenance=None, console_errors=0,
            playtest_performed=False, screenshot_captured=False, screenshot_inspected=False,
            limitations=None, project=None, save=True):
    """Build (and by default persist) a verification receipt.

    `checks` are the agent's claims. `evidence` is an observation dict; its `provenance` decides how
    much it can prove - "tool" (from `collect_evidence`) or "agent" (supplied by the caller, and
    therefore untrusted). An explicit `provenance` argument overrides the dict.
    """
    evidence = evidence if isinstance(evidence, dict) else {}
    state = _required_checks()

    claimed = [name for name in (checks or []) if name in state]
    raw_checks = evidence.get("checks")
    observed_in = raw_checks if isinstance(raw_checks, dict) else {}
    for name in state:
        if observed_in.get(name) is True:
            state[name] = True

    source = provenance or evidence.get("provenance") or "agent"
    trusted = source == "tool"

    tests = [t for t in (evidence.get("tests") or []) if isinstance(t, dict)]
    tests_ok = bool(tests) and all(t.get("passed") is True for t in tests)
    console_logged = evidence.get("console_logged") is True
    errors_now = int(console_errors or 0)
    shots = _as_list(evidence.get("screenshots"))
    visual = bool((shots and evidence.get("screenshots_inspected")) or
                  (screenshot_captured and screenshot_inspected))

    gameplay_evidence = all(state[k] for k in GAMEPLAY_CHECKS)
    playtested = bool(gameplay_evidence and tests_ok and playtest_performed)

    if playtested and trusted and console_logged and errors_now == 0 and visual:
        level = "verified_playtest"
    elif playtested and trusted:
        level = "playtested_with_errors"
    elif playtested:
        level = "playtest_claimed"
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
            "provenance": source,
            "studio_id": evidence.get("studio_id"),
            "place": evidence.get("place"),
            "datamodel": evidence.get("datamodel"),
            "console_logged": console_logged,
            "screenshots": shots,
            "tests": tests,
            "untested": _as_list(evidence.get("untested")),
        },
        "console_errors_reported": errors_now,
        "playtest_performed": bool(playtest_performed),
        "screenshot_captured": bool(screenshot_captured),
        "screenshot_inspected_by_vision": bool(screenshot_inspected),
        "verification_level": level,
        "claim_allowed": LEVEL_CLAIM[level],
        "limitations": _as_list(limitations) + _as_list(evidence.get("untested")),
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
