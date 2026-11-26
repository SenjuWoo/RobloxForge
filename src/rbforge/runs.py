"""Run ledger: every live test the CLI ran, per project, and what it says about flakiness.

A milestone that needs "three passes in a row" also needs the honest denominator ("cleared in 8 of 12
runs"); agents kept that count in their heads and lost it at the usage limit. Each CLI servertest run
appends one JSON line per test to RBFORGE_HOME/runs/<project>.jsonl, and the console of a failed run
to RBFORGE_HOME/runs/logs/. `rbforge runs` reads it back.

The ledger is state, not proof: an agent can edit it. A receipt (rb_collect_evidence) is the proof;
the ledger is the memory that tells the next session what has been tried.
"""
import hashlib
import json
import os
import re
import subprocess
import time

from . import paths as paths_mod
from .errors import ForgeError

_MARKERS = (".git", "default.project.json")


def project_root(start=None):
    """The nearest folder at or above `start` holding .git or default.project.json, else `start`."""
    here = os.path.abspath(start or os.getcwd())
    if os.path.isfile(here):
        here = os.path.dirname(here)
    probe = here
    while True:
        if any(os.path.exists(os.path.join(probe, m)) for m in _MARKERS):
            return probe
        parent = os.path.dirname(probe)
        if parent == probe:
            return here
        probe = parent


def git_state(root):
    """(short sha, dirty) of the project's checkout, or (None, None) outside Git or without git."""
    def git(*args):
        return subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=15)
    try:
        head = git("rev-parse", "--short=12", "HEAD")
        if head.returncode != 0:
            return None, None
        status = git("status", "--porcelain", "--untracked-files=no")
        dirty = bool(status.stdout.strip()) if status.returncode == 0 else None
        return head.stdout.strip() or None, dirty
    except (OSError, subprocess.SubprocessError):
        return None, None


def _slug(root):
    name = re.sub(r"[^A-Za-z0-9_-]+", "-", os.path.basename(root.rstrip("\\/")) or "project").strip("-")
    digest = hashlib.sha1(os.path.normcase(os.path.abspath(root)).encode("utf-8")).hexdigest()[:10]
    return "%s-%s" % (name[:40] or "project", digest)


def runs_dir():
    d = os.path.join(paths_mod.home(), "runs")
    os.makedirs(d, exist_ok=True)
    return d


def ledger_path(root):
    return os.path.join(runs_dir(), _slug(root) + ".jsonl")


def save_log(run_id, name, text):
    d = os.path.join(runs_dir(), "logs")
    os.makedirs(d, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", os.path.basename(name or "test"))[:60]
    path = os.path.join(d, "%s_%s.log" % (run_id, safe))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def _entry(root, sha, dirty, batch, run, restarted, r):
    console = r.get("console") or {}
    log = None
    if console.get("text") and not r.get("passed"):
        log = save_log(r.get("run_id") or batch, r.get("name") or r.get("test"), console["text"])
    test = r.get("name") or r.get("test") or "?"
    if os.path.isabs(test):
        try:
            test = os.path.relpath(test, root)
        except ValueError:
            pass
    return {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "project": root, "sha": sha, "dirty": dirty, "batch": batch, "run": run, "restarted": restarted,
        "test": test.replace("\\", "/"), "datamodel": r.get("datamodel"), "outcome": r.get("outcome"),
        "result": (r.get("result") or "")[:400], "seconds": r.get("seconds"), "log": log,
        "console_errors": (console.get("errors") or [])[:5],
    }


def record(root, results, batch=None, run=1, restarted=False, tested=None):
    """Append one line per test result; returns the entries written. Never raises for a bad home:
    losing the ledger must not turn a test result into a crash, so the error is returned instead."""
    from .verification import _FileLock
    if not results:
        return {"ledger": None, "entries": []}
    # `tested` is (sha, dirty) read before the run started: a commit made during a long run is not
    # what was tested.
    sha, dirty = tested if tested else git_state(root)
    batch = batch or time.strftime("%Y%m%d-%H%M%S")
    try:
        entries = [_entry(root, sha, dirty, batch, run, restarted, r) for r in results]
        path = ledger_path(root)
        with _FileLock(path + ".lock"):
            with open(path, "a", encoding="utf-8") as fh:
                for e in entries:
                    fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        return {"ledger": path, "entries": entries}
    except (OSError, ForgeError) as exc:
        return {"ledger": None, "entries": [], "error": str(exc)}


def record_streak(root, streak, tested=None):
    out = {"ledger": None, "written": 0}
    for run in streak.get("runs", []):
        res = record(root, run.get("tests") or [], batch=streak.get("batch"), run=run.get("run", 1),
                     restarted=bool(run.get("restarted")), tested=tested)
        out["ledger"] = res.get("ledger") or out["ledger"]
        out["written"] += len(res.get("entries", []))
        if res.get("error"):
            out["error"] = res["error"]
        # A log path makes the failure findable from the JSON report, not only from the ledger.
        for t, e in zip(run.get("tests") or [], res.get("entries", [])):
            if e.get("log"):
                t["console_log"] = e["log"]
    compact(streak)
    return out


def compact(streak):
    """Drop the full console text from a report once it is on disk (or unwanted): the JSON goes into
    an agent's context, and the tail and error lines are what it reads first."""
    for run in streak.get("runs", []):
        for t in run.get("tests") or []:
            console = t.get("console")
            if isinstance(console, dict):
                console.pop("text", None)
    return streak


def load(root):
    path = ledger_path(root)
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue  # a torn line from a killed process is skipped, never fatal
                if isinstance(e, dict) and isinstance(e.get("test"), str):
                    out.append(e)
    except OSError:
        pass
    return out


def summarize(root, test=None, last=None):
    """Per test: runs, passes, pass rate, current streak (passes since the last failure), best
    streak, last outcome/result/sha/log. `test` filters by substring; `last` keeps each test's N
    newest runs."""
    entries = load(root)
    if test:
        entries = [e for e in entries if test.lower() in e["test"].lower()]
    by = {}
    for e in entries:
        by.setdefault(e["test"], []).append(e)
    tests = []
    for name, rows in sorted(by.items()):
        if last:
            rows = rows[-int(last):]
        passes = sum(1 for r in rows if r.get("outcome") == "pass")
        best = cur = 0
        for r in rows:
            cur = cur + 1 if r.get("outcome") == "pass" else 0
            best = max(best, cur)
        tail = rows[-1]
        last_fail = next((r for r in reversed(rows) if r.get("outcome") != "pass"), None)
        tests.append({
            "test": name, "runs": len(rows), "passes": passes, "failures": len(rows) - passes,
            "pass_rate": round(passes / len(rows), 3), "current_streak": cur, "best_streak": best,
            "last": {k: tail.get(k) for k in ("at", "outcome", "result", "sha", "dirty", "log")},
            "last_failure": None if last_fail is None else
            {k: last_fail.get(k) for k in ("at", "result", "sha", "log", "console_errors")},
        })
    return {"project": root, "ledger": ledger_path(root), "tests": tests,
            "note": None if tests else "no recorded runs: `rbforge servertest` records every live run"}


def render(summary):
    lines = ["Runs for %s" % summary["project"], ""]
    if not summary["tests"]:
        lines.append(summary.get("note") or "no runs")
        return "\n".join(lines)
    lines.append("%-44s %5s %5s %6s %6s %5s  %s" % ("test", "runs", "pass", "rate", "streak", "best", "last"))
    for t in summary["tests"]:
        last = t["last"]
        lines.append("%-44s %5d %5d %5.0f%% %6d %5d  %s %s" % (
            t["test"][-44:], t["runs"], t["passes"], t["pass_rate"] * 100, t["current_streak"],
            t["best_streak"], last.get("outcome"), (last.get("sha") or "")[:8]))
        if t["last_failure"]:
            f = t["last_failure"]
            lines.append("    last failure %s: %s" % (f.get("at"), (f.get("result") or "")[:110]))
            if f.get("log"):
                lines.append("    console: %s" % f["log"])
    lines += ["", "ledger: %s" % summary["ledger"]]
    return "\n".join(lines)
