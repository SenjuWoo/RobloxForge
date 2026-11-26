"""Detached live runs: a long `servertest` that outlives the agent's tool call.

A full suite can take tens of minutes; an agent's shell call is cut long before that. `servertest --detach`
starts the very same CLI command in a background process (one code path: run, ledger, forensics) and
returns a job id at once. Files under RBFORGE_HOME/runs/jobs/:

    <id>.json         the job: argv, cwd, pid, started
    <id>.out.json     the command's stdout (its JSON report)
    <id>.log          its stderr (one progress line per suite)
    <id>.result.json  written last, atomically: exit code and finish time
    studio.lock       held while a job runs: the one Studio connection belongs to it

`status(id)` says running, done or died (the process is gone and never wrote a result). `wait(id, s)`
polls until the job ends or the timeout passes. Run this module as `python -m rbforge.jobs <id>` only
through `start`.
"""
import json
import os
import re
import subprocess
import sys
import time
import uuid

from .errors import ForgeError
from . import paths as paths_mod

_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")
LOCK_NAME = "studio.lock"
ENV_JOB = "RBFORGE_JOB_ID"            # set in the child: its own lock does not refuse it
ENV_IGNORE = "RBFORGE_IGNORE_JOB_LOCK"  # set to 1 to talk to Studio anyway (you take the risk)


def jobs_dir():
    d = os.path.join(paths_mod.home(), "runs", "jobs")
    os.makedirs(d, exist_ok=True)
    return d


def _path(job_id, suffix):
    if not _ID.match(job_id or ""):
        raise ForgeError("RBF-ARG-002", "not a job id: %r" % (job_id,), hint="ids look like 20261126-142233-a1b2c3")
    return os.path.join(jobs_dir(), job_id + suffix)


def _write_json(path, data):
    """Atomic: a reader never sees half a file."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)
    os.replace(tmp, path)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def new_id():
    return "%s-%s" % (time.strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:6])


def start(argv, cwd=None):
    """Start `rbforge <argv>` in the background; returns the job record."""
    job_id = new_id()
    cwd = os.path.abspath(cwd or os.getcwd())
    job = {"job": job_id, "argv": list(argv), "cwd": cwd, "started": time.time(),
           "out": _path(job_id, ".out.json"), "log": _path(job_id, ".log")}
    _write_json(_path(job_id, ".json"), job)
    src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env[ENV_JOB] = job_id
    kwargs = {}
    if os.name == "nt":
        # No console, not killed with the agent's shell.
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    with open(job["out"], "wb") as out, open(job["log"], "wb") as log:
        proc = subprocess.Popen([sys.executable, "-m", "rbforge.jobs", job_id], cwd=cwd, env=env,
                                stdin=subprocess.DEVNULL, stdout=out, stderr=log, close_fds=True, **kwargs)
    job["pid"] = proc.pid
    _write_json(_path(job_id, ".json"), job)
    return job


def status(job_id):
    job = _read_json(_path(job_id, ".json"))
    if job is None:
        raise ForgeError("RBF-ARG-001", "no job %s" % job_id, hint="`rbforge runs --jobs` lists them")
    result = _read_json(_path(job_id, ".result.json"))
    out = {"job": job_id, "argv": job.get("argv"), "cwd": job.get("cwd"), "pid": job.get("pid"),
           "started": job.get("started"), "log": job.get("log"), "out": job.get("out")}
    if result is not None:
        out.update(state="done", exit=result.get("exit"), finished=result.get("finished"),
                   seconds=round((result.get("finished") or 0) - (job.get("started") or 0), 1))
        out["report"] = _read_json(job.get("out") or "")
        if result.get("error"):
            out["error"] = result["error"]
    elif pid_alive(job.get("pid")):
        out["state"] = "running"
        out["seconds"] = round(time.time() - (job.get("started") or time.time()), 1)
    else:
        out["state"] = "died"
        out["hint"] = "the process ended without writing a result; read the log"
    out["progress"] = _tail(job.get("log"), 12)
    return out


def wait(job_id, timeout, poll=2.0):
    deadline = time.time() + max(0.0, float(timeout))
    while True:
        st = status(job_id)
        if st["state"] != "running" or time.time() >= deadline:
            return st
        time.sleep(min(poll, max(0.05, deadline - time.time())))


def listing(limit=20):
    names = sorted((n[:-5] for n in os.listdir(jobs_dir()) if _ID.match(n[:-5] or "") and n.endswith(".json")),
                   reverse=True)
    out = []
    for job_id in names[:limit]:
        st = status(job_id)
        out.append({k: st.get(k) for k in ("job", "state", "exit", "seconds", "argv")})
    return out


def _tail(path, n):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return [line.rstrip("\n") for line in fh.readlines()[-n:]]
    except OSError:
        return []


# ------------------------------------------------------------------ the Studio connection lock


def lock_path():
    return os.path.join(jobs_dir(), LOCK_NAME)


def holder():
    """The running job that holds Studio, or None. A lock whose process is gone is stale and ignored."""
    lock = _read_json(lock_path())
    if not lock:
        return None
    if lock.get("job") == os.environ.get(ENV_JOB):
        return None
    if not pid_alive(lock.get("pid")):
        return None
    return lock


def refuse_if_held():
    """Raise when a detached job owns the Studio connection: a second StudioMCP would take it over."""
    if os.environ.get(ENV_IGNORE) == "1":
        return
    lock = holder()
    if lock:
        raise ForgeError("RBF-STUDIO-004",
                         "a detached run holds the Studio connection (job %s, pid %s)" % (lock.get("job"), lock.get("pid")),
                         hint="`rbforge runs --job %s --wait` to wait for it; set %s=1 to override "
                              "(it can break that run)" % (lock.get("job"), ENV_IGNORE))


def _child(job_id):
    job = _read_json(_path(job_id, ".json")) or {}
    _write_json(lock_path(), {"job": job_id, "pid": os.getpid(), "since": time.time()})
    code, error = 1, None
    try:
        import rbforge_cli
        code = rbforge_cli.main(list(job.get("argv") or []))
    except SystemExit as exc:  # argparse exits on a bad argument
        code = exc.code if isinstance(exc.code, int) else 2
    except BaseException as exc:  # noqa: BLE001 - the result file must say what happened
        error = "%s: %s" % (type(exc).__name__, exc)
    finally:
        sys.stdout.flush()
        lock = _read_json(lock_path())
        if lock and lock.get("job") == job_id:
            try:
                os.remove(lock_path())
            except OSError:
                pass
        _write_json(_path(job_id, ".result.json"), {"exit": code, "finished": time.time(), "error": error})
    return code


if __name__ == "__main__":
    sys.exit(_child(sys.argv[1]))
