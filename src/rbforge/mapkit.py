"""Optional adapter for the external SyphoDev `roblox-map` prover.

RobloxForge does not vendor that package: its licence allows free use and modification but not resale,
and asks for attribution. Instead this module **runs it where it already lives**, so the map proving keeps
its own JSON spec format, its own checks and its own report - the forge only adds discovery, a dependency
probe, and a stable way for an agent to call it.

Nothing here touches a Studio place. `prove()` is a subprocess that prints a report; placing a map stays a
separate, deliberate step.

Configure the install once:

    set RBFORGE_SYPHODEV=Z:\\path\\to\\roblox-ai-skills        (repo root)
    set RBFORGE_SYPHODEV=Z:\\path\\to\\roblox-map             (skill folder itself)

With no configuration, or with numpy/scipy/Pillow missing for the current interpreter, `status()` reports
unavailable and `prove()` refuses - it never silently degrades into a guess.
"""
import json
import os
import subprocess
import sys

SKILL_RELATIVE = os.path.join("skills", "roblox-map")
MODULES = ("numpy", "scipy", "PIL")
ATTRIBUTION = ("External skill: SyphoDev-yt/roblox-ai-skills (roblox-map). Not redistributed by RobloxForge; "
               "its licence asks for attribution and forbids resale.")


def _looks_like_skill(path):
    return bool(path) and os.path.isfile(os.path.join(path, "scripts", "prove.py")) \
        and os.path.isdir(os.path.join(path, "specs"))


def find_install(configured=None):
    """The roblox-map skill directory, from an explicit path or RBFORGE_SYPHODEV, or None."""
    candidate = configured or os.environ.get("RBFORGE_SYPHODEV")
    if not candidate:
        return None
    candidate = candidate.rstrip("\\/")
    for path in (candidate, os.path.join(candidate, SKILL_RELATIVE)):
        if _looks_like_skill(path):
            return path.replace("\\", "/")
    return None


def _probe_once(python):
    """True when every module imports in this interpreter."""
    try:
        done = subprocess.run([python, "-c", "import %s" % ", ".join(MODULES)],
                              capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def missing_dependencies(python=None, probe=None):
    """Which of the prover's imports this interpreter cannot satisfy. Empty list means runnable.

    `probe` is injectable so tests never spawn an interpreter; production passes nothing.
    """
    if probe is not None:
        return list(probe(python or sys.executable))
    python = python or sys.executable
    if _probe_once(python) or _probe_once(python):
        return []  # one retry: a spawn can fail under memory pressure, and that is not a missing module
    missing = []
    for name in MODULES:
        try:
            done = subprocess.run([python, "-c", "import %s" % name], capture_output=True,
                                  text=True, timeout=120)
        except (OSError, subprocess.SubprocessError):
            missing.append(name)
            continue
        if done.returncode != 0:
            missing.append(name)
    return missing or ["<unknown import failure>"]


def status(configured=None, python=None, probe=None):
    """Whether the external prover can be used here, and exactly why not when it cannot."""
    path = find_install(configured)
    out = {"available": False, "path": path, "attribution": ATTRIBUTION,
           "env": "RBFORGE_SYPHODEV", "touches_studio": False}
    if not path:
        out["reason"] = ("not configured: set RBFORGE_SYPHODEV to the roblox-ai-skills clone "
                         "(or to its skills/roblox-map folder)")
        return out
    missing = missing_dependencies(python, probe=probe)
    out["missing_dependencies"] = missing
    if missing:
        out["reason"] = "dependencies missing for %s: %s" % (python or sys.executable, ", ".join(missing))
        return out
    out["available"] = True
    specs = []
    specs_dir = os.path.join(path, "specs")
    if os.path.isdir(specs_dir):
        specs = sorted(f[:-5] for f in os.listdir(specs_dir) if f.endswith(".json"))
    out["specs"] = specs
    out["entry_point"] = os.path.join(path, "scripts", "prove.py").replace("\\", "/")
    return out


def prove(spec, out_path=None, res=None, configured=None, python=None, timeout=600, probe=None):
    """Run the external prover on one spec and return its report.

    Its spec and report formats are untouched: the JSON this returns under `report` is the file the
    upstream script wrote. `checks_failed` is a convenience summary, not a reinterpretation.
    """
    path = find_install(configured)
    if not path:
        return {"available": False, "ok": False,
                "reason": "no roblox-map install configured (set RBFORGE_SYPHODEV)"}
    missing = missing_dependencies(python, probe=probe)
    if missing:
        return {"available": False, "ok": False, "missing_dependencies": missing,
                "reason": "the prover's dependencies are not installed for this interpreter"}

    spec_path = spec if os.path.isabs(spec) else os.path.join(path, "specs", spec if spec.endswith(".json") else spec + ".json")
    if not os.path.isfile(spec_path):
        return {"available": True, "ok": False, "reason": "no such spec: %s" % spec_path}

    report_path = out_path or os.path.join(os.path.dirname(os.path.abspath(spec_path)),
                                           "prove-report.json")
    cmd = [python or sys.executable, os.path.join(path, "scripts", "prove.py"), spec_path,
           "--json", report_path]
    if res:
        cmd += ["--res", str(res)]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"available": True, "ok": False, "reason": "prover timed out after %ss" % timeout}

    report, problem = None, None
    if os.path.isfile(report_path):
        try:
            report = json.load(open(report_path, encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problem = "report unreadable: %s" % exc
    else:
        problem = "the prover wrote no report file"

    out = {"available": True, "ok": done.returncode == 0, "exit_code": done.returncode,
           "report_path": report_path.replace("\\", "/"),
           "stdout_tail": "\n".join(done.stdout.strip().splitlines()[-14:]),
           "attribution": ATTRIBUTION, "touches_studio": False}
    if problem:
        out["reason"] = problem
        return out
    out["report"] = report
    if isinstance(report, dict):
        out["result"] = report.get("result")
        out["map"] = report.get("map")
        out["checks_failed"] = [{"id": c.get("id"), "title": c.get("title"), "detail": c.get("detail")}
                                for c in report.get("checks", []) if c.get("status") == "FAIL"]
    return out
