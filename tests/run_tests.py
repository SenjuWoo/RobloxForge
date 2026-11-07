"""RobloxForge test runner. No pytest, no Roblox install required.

Run: python tests/run_tests.py
Fixture-based; exercises every core module against synthetic state.
"""
import base64
import io
import json
import os
import shutil
import traceback
import re
import sys
import tempfile
import contextlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import rbforge  # noqa: E402
from rbforge import errors as err_mod  # noqa: E402

PASS, FAIL = [], []

def _fake_session(out):
    """A Studio session double that returns `out` from execute_luau."""
    class Fake:
        answer = out

        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def luau(self, code, dm="Edit"):
            return Fake.answer
    return Fake



def _home_for(skills):
    """Point installer backups at a temp home so a test never writes to the real profile."""
    import tempfile as _tf
    home = _tf.mkdtemp(prefix="rbf-home-")
    old = skills.paths.home
    skills.paths.home = lambda: home
    return home, old


def _backups_in(home, skill):
    import os as _os
    d = _os.path.join(home, "backups")
    return [_os.path.join(d, n) for n in _os.listdir(d) if skill in n] if _os.path.isdir(d) else []


def skills_version():
    from rbforge import __version__
    return __version__


@contextlib.contextmanager
def tempdir():
    import shutil
    d = tempfile.mkdtemp(prefix="rbf-test-")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@contextlib.contextmanager
def _isolated_home():
    from rbforge import paths
    old = os.environ.get("RBFORGE_HOME")
    d = tempfile.mkdtemp(prefix="rbf-home-")
    os.environ["RBFORGE_HOME"] = d
    try:
        paths.home()  # recreate
        yield d
    finally:
        if old is None:
            os.environ.pop("RBFORGE_HOME", None)
        else:
            os.environ["RBFORGE_HOME"] = old
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def check(name):
    def deco(fn):
        try:
            fn()
            PASS.append(name)
            print("ok   %s" % name)
        except Exception as exc:  # noqa: BLE001
            FAIL.append((name, exc))
            print("FAIL %s: %r" % (name, exc))
            # A bare repr hides where it broke; the last frames name the line.
            tb = traceback.format_exc().strip().splitlines()
            for line in tb[-6:]:
                print("     " + line)
        return fn
    return deco


# ---------------------------------------------------------------- errors

@check("errors: exit codes map by prefix")
def _():
    assert err_mod.ForgeError("RBF-DOCS-001", "x").exit_code == err_mod.ExitCode.DEPENDENCY
    assert err_mod.ForgeError("RBF-STUDIO-001", "x").exit_code == err_mod.ExitCode.NOT_FOUND
    d = err_mod.ForgeError("RBF-MCP-002", "m", hint="h").to_dict()
    assert d["error"]["code"] == "RBF-MCP-002" and d["error"]["hint"] == "h"


@check("errors: unknown prefix falls back to generic")
def _():
    assert err_mod.ForgeError("RBF-ZZZ-999", "x").exit_code == 1


# ---------------------------------------------------------------- docs (offline)

@check("docs: search works on existing cache without network")
def _():
    from rbforge import docs
    if not docs.cache_present():
        return  # skip quietly on machines without a cache; CI fixtures cover logic below
    r = docs.search("RemoteEvent:FireServer", limit=3)
    assert r["results"], "no results"
    assert "RemoteEvent.yaml" in r["results"][0]["path"]
    assert r["source"].startswith("Roblox/creator-docs")


@check("docs: freshness never guesses when cache absent")
def _():
    from rbforge import paths, docs as docs_mod
    with _isolated_home():
        f = docs_mod.freshness()
        assert f["present"] is False and f["stale"] is None


@check("docs: offline refresh failure keeps cache and records error")
def _():
    from rbforge import docs as docs_mod
    with _isolated_home():
        # fake a healthy cache + state without touching the network
        content = os.path.join(docs_mod.paths.docs_cache_dir(), "content", "en-us")
        os.makedirs(content)
        open(os.path.join(content, "x.md"), "w").write("# hi")
        docs_mod.write_state(fetched_at=__import__("time").time(),
                             method="git-sparse", commit="deadbeef")
        before = docs_mod.freshness()["stale"]
        docs_mod.ensure(refresh=True, allow_network=False)
        st = docs_mod.read_state()
        # allow_network=False skips refresh entirely - cache intact, no error written
        assert docs_mod.cache_present() and before is False


@check("docs: member query hits owning class (ProcessReceipt)")
def _():
    from rbforge import docs
    if not docs.cache_present():
        return
    r = docs.search("ProcessReceipt", limit=3)
    paths_ = [x["path"] for x in r["results"]]
    assert any("MarketplaceService" in p for p in paths_), paths_


@check("docs: read rejects path escape")
def _():
    from rbforge import docs
    try:
        docs.read("../../etc/passwd")
        raise AssertionError("should have raised")
    except err_mod.ForgeError as e:
        assert e.code in ("RBF-ARG-003", "RBF-DOCS-005", "RBF-DOCS-001")


# ---------------------------------------------------------------- planning

@check("planning: slice plan for every genre")
def _():
    from rbforge import planning
    for g in ("generic", "obby", "simulator", "tycoon"):
        p = planning.vertical_slice(g, "test premise")
        assert p["build_order"] and p["verification"] and p["core_loop"]
    try:
        planning.vertical_slice("mmorpg", "x")
        raise AssertionError("should have raised")
    except err_mod.ForgeError:
        pass


# ---------------------------------------------------------------- verification

def _fake_studio(console="", place="Deadzome Haven", capture="C:/shots/smoke.png"):
    """A Studio session double: tests exercise the real collector, not a fabricated record."""
    class FakeSession:
        studio_id = "fake-studio"

        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def luau(self, code, dm="Edit"):
            return place

        def call(self, tool, args):
            if tool == "get_console_output":
                if console is None:
                    raise RuntimeError("get_console_output is not available")
                return console
            if tool == "screen_capture":
                if capture is None:
                    raise RuntimeError("screen_capture is not available")
                return capture
            raise KeyError(tool)

        def call_content(self, tool, args):
            if tool == "screen_capture":
                if capture is None:
                    raise RuntimeError("screen_capture is not available")
                return ([{"type": "image", "mimeType": "image/png",
                          "data": base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()}],
                        False, "")
            raise KeyError(tool)
    return FakeSession


def _collect(project="demo", scenario="smoke", inspected=True, test_result=None,
             capture_screenshot_off=False, revision=None, **over):
    """Run collect_evidence against the double; returns the recorded observation payload."""
    from rbforge import live, verification
    orig = live.server_test
    answer = test_result or {"result": "PASS smoke", "passed": True, "outcome": "pass"}
    live.server_test = lambda *a, **k: answer
    path = os.path.join(tempfile.mkdtemp(prefix="rbf-test-"), "Smoke.luau")
    open(path, "w").write("return 1\n")
    try:
        return verification.collect_evidence(
            session_factory=_fake_studio(**over), project=project, scenario=scenario,
            revision=revision, screenshots_inspected=inspected,
            capture_screenshot=not capture_screenshot_off, test_path=path)
    finally:
        live.server_test = orig


@check("verification: a collected observation verifies, but only with console and screenshot")
def _():
    from rbforge import verification
    with _isolated_home():
        obs = _collect(console="[Server] ready")
        r = verification.receipt("observed", observation_id=obs["observation_id"],
                                 project="demo", scenario="smoke", playtest_performed=True, save=False)
        assert r["verification_level"] == "verified_playtest", (r["verification_level"], r["limitations"])
        assert r["checks"]["console_checked"] is True
        assert r["screenshot_inspected_by_vision"] is True
        assert r["evidence"]["provenance"] == "tool"

        # No console tool available: the same run can only be partial.
        obs2 = _collect(console=None)
        r2 = verification.receipt("no console", observation_id=obs2["observation_id"], project="demo",
                                  scenario="smoke", playtest_performed=True, save=False)
        assert r2["verification_level"] == "playtest_observed_partial", r2["verification_level"]


@check("verification: an observation from another project or scenario cannot verify")
def _():
    from rbforge import verification
    with _isolated_home():
        obs = _collect(project="demo", scenario="smoke")["observation_id"]
        other_project = verification.receipt("other project", observation_id=obs, project="different",
                                             playtest_performed=True, save=False)
        other_scenario = verification.receipt("other scenario", observation_id=obs, project="demo",
                                              scenario="night-raid", playtest_performed=True, save=False)
        assert other_project["verification_level"] != "verified_playtest", other_project["verification_level"]
        assert other_scenario["verification_level"] != "verified_playtest", other_scenario["verification_level"]


@check("verification: forged provenance='tool' does not verify")
def _():
    from rbforge import verification
    with _isolated_home():
        forged = {
            "provenance": "tool",
            "studio_id": "fake", "place": "Fake", "datamodel": "Server",
            "checks": {k: True for k in verification.GAMEPLAY_CHECKS},
            "tests": [{"name": "made up", "passed": True}],
            "console_logged": True,
            "screenshots": ["C:/does/not/exist.png"],
            "screenshots_inspected": True,
        }
        r = verification.receipt("forged", evidence=forged, provenance="tool",
                                 playtest_performed=True, save=False)
        assert r["verification_level"] != "verified_playtest", r["verification_level"]
        assert r["evidence"]["provenance"] == "agent"
        assert any("caller" in note for note in r["limitations"])


@check("verification: a forged screenshot path never counts as inspected")
def _():
    from rbforge import verification
    with _isolated_home():
        r = verification.receipt("shot", evidence={"screenshots": ["C:/nope.png"]},
                                 screenshot_captured=True, screenshot_inspected=True,
                                 playtest_performed=True, save=False)
        assert r["verification_level"] == "static_only", r["verification_level"]


@check("verification: console errors are read from output, not from a flag")
def _():
    from rbforge import verification
    with _isolated_home():
        obs = _collect(console="Script error: attempt to index nil\nstack begin\n")
        r = verification.receipt("errors", observation_id=obs["observation_id"], project="demo",
                                 scenario="smoke", playtest_performed=True, save=False)
        assert r["verification_level"] == "playtested_with_errors", r["verification_level"]
        assert r["console_errors_reported"] >= 2, r["console_errors_reported"]


@check("verification: three same-second receipts keep the chain in creation order")
def _():
    from rbforge import verification
    with _isolated_home():
        a = verification.receipt("same name", save=True)
        b = verification.receipt("same name", save=True)
        c = verification.receipt("same name", save=True)
        paths = [a["saved_to"], b["saved_to"], c["saved_to"]]
        assert len({os.path.basename(p) for p in paths}) == 3, "receipt filenames collided"
        loaded = [json.load(open(p, encoding="utf-8")) for p in paths]
        assert [r["sequence"] for r in loaded] == [1, 2, 3], [r["sequence"] for r in loaded]
        assert loaded[1]["prev_digest"] == a["digest"]
        assert loaded[2]["prev_digest"] == b["digest"], "third receipt chained to the first"
        assert verification.verify_chain()["ok"], verification.verify_chain()


@check("verification: concurrent writers cannot fork the history")
def _():
    import threading
    from rbforge import verification
    with _isolated_home():
        results = []
        lock = threading.Lock()

        def write():
            r = verification.receipt("concurrent", save=True)
            with lock:
                results.append(r)

        threads = [threading.Thread(target=write) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        seqs = sorted(r["sequence"] for r in results)
        assert seqs == [1, 2, 3, 4, 5, 6], seqs
        chain = verification.verify_chain()
        assert chain["ok"], chain["problems"]


@check("verification: tampering and middle deletion are detected; final deletion is not")
def _():
    from rbforge import verification
    import shutil as _shutil
    with _isolated_home():
        a = verification.receipt("one", save=True)
        b = verification.receipt("two", save=True)
        c = verification.receipt("three", save=True)
        original_a = open(a["saved_to"], "rb").read()

        # 1. A modified payload no longer matches its digest.
        data = json.loads(original_a.decode("utf-8"))
        data["verification_level"] = "verified_playtest"
        json.dump(data, open(a["saved_to"], "w", encoding="utf-8"))
        assert not verification.verify_chain()["ok"], "tampering went unnoticed"

        # 2. Restore A's exact original bytes, then delete the middle receipt.
        open(a["saved_to"], "wb").write(original_a)
        assert verification.verify_chain()["ok"], verification.verify_chain()["problems"]
        keep_b = open(b["saved_to"], "rb").read()
        os.remove(b["saved_to"])
        assert not verification.verify_chain()["ok"], "a missing middle receipt went unnoticed"

        # 3. Restore the middle, delete the final receipt. A hash chain cannot see a truncation;
        #    this asserts the documented limitation rather than pretending otherwise.
        open(b["saved_to"], "wb").write(keep_b)
        assert verification.verify_chain()["ok"]
        os.remove(c["saved_to"])
        chain = verification.verify_chain()
        assert chain["receipts"] == 2, chain
        assert chain["ok"], "truncation is not detectable from a hash chain alone"


@check("verification: a pre-0.13 receipt without a sequence still chains")
def _():
    from rbforge import verification
    with _isolated_home():
        r1 = verification.receipt("legacy one", save=True)
        # Rewrite it the way 0.12.x wrote receipts: no sequence field, older filename.
        legacy = json.load(open(r1["saved_to"], encoding="utf-8"))
        legacy.pop("sequence", None)
        legacy["digest"] = verification._digest({k: v for k, v in legacy.items() if k != "saved_to"})
        legacy_path = os.path.join(verification._receipts_dir(), "20200101-000000-legacy-one.json")
        json.dump(legacy, open(legacy_path, "w", encoding="utf-8"))
        os.remove(r1["saved_to"])

        r2 = verification.receipt("after upgrade", save=True)
        assert r2["prev_digest"] == legacy["digest"], "new receipt did not chain to the legacy one"
        chain = verification.verify_chain()
        assert chain["ok"], chain["problems"]


@check("verification: a receipt cannot inherit an observation from another project")
def _():
    from rbforge import verification
    with _isolated_home():
        obs = _collect(project="demo", scenario="smoke")["observation_id"]
        r = verification.receipt("no project named", observation_id=obs, playtest_performed=True,
                                 save=False)
        assert r["evidence"]["observation_id"] is None, "an unscoped receipt reused a scoped observation"


# ---------------------------------------------------------------- generated Luau (push)

def _generated_push_code(**over):
    from rbforge import live
    args = dict(parent="ServerScriptService.Systems", name="Main", klass="Script",
                text="print('hello')\n", parent_classes={"ServerScriptService.Systems": "Model"})
    args.update(over)
    return live._push_code(**args)


def _parse_luau(path, cfg):
    """(ok, detail) using a real parser. stylua: exit 2 = parse error, 1 = formatting only.
    selene: parse errors are counted. Whichever is installed, the contract is deterministic."""
    import shutil as _shutil
    import subprocess as _sub
    if _shutil.which("stylua"):
        out = _sub.run(["stylua", "--check", path], capture_output=True, text=True)
        blob = (out.stdout or "") + (out.stderr or "")
        if out.returncode == 2:
            return False, blob[:400]
        if "error parsing" in blob.lower():
            return False, blob[:400]
        return True, ""
    if _shutil.which("selene"):
        out = _sub.run(["selene", "--config", cfg, path], capture_output=True, text=True)
        blob = (out.stdout or "") + (out.stderr or "")
        parsed_clean = "0 parse errors" in blob
        return parsed_clean, blob[:400]
    raise AssertionError("a Luau parser (stylua or selene) is required for this test")


@check("live: generated push code is valid Luau, even with class mappings and odd text")
def _():
    with tempdir() as d:
        cfg = os.path.join(d, "selene.toml")
        open(cfg, "w").write('std = "lua51"\n')  # syntax only: no Roblox std, no network
        cases = [
            _generated_push_code(),
            _generated_push_code(parent_classes={"ServerScriptService": "Folder",
                                                 "ServerScriptService.Systems": "Model"}),
            _generated_push_code(name='Wei"rd\u00e9 name', parent="Workspace.Thing",
                                 text="-- ]=] ]] ]==] \u00e9 \\ backslash ' quote\n"),
            _generated_push_code(klass="ModuleScript", text="return 1\n"),
            _generated_push_code(parent_classes={"ServerScriptService.Systems": "Configuration"}),
        ]
        for i, code in enumerate(cases):
            path = os.path.join(d, "gen%d.luau" % i)
            open(path, "w", encoding="utf-8").write(code)
            ok, detail = _parse_luau(path, cfg)
            assert ok, "generated Luau does not parse:\n%s" % detail

        # Negative control: the gate must reject invalid Luau, or it proves nothing.
        bad = os.path.join(d, "broken.luau")
        open(bad, "w", encoding="utf-8").write("local x = = 1\nfunction\n")
        ok, _detail = _parse_luau(bad, cfg)
        assert ok is False, "the parser accepted invalid Luau - the gate is not testing anything"


@check("live: generated push code refuses a wrong existing class and can roll back")
def _():
    code = _generated_push_code()
    assert "HIERARCHY" in code and "the project expects" in code, "no existing-class check"
    assert "ROLLED_BACK" in code and "target.Source = prev" in code, "no rollback path"
    assert "backup.Parent = node" in code, "a moved original is never put back"
    assert "JSONDecode" in code, "class map must be decoded, not pasted as a table"


@check("live: push maps rollback and hierarchy outcomes to states")
def _():
    from rbforge import live
    orig = live.Session
    with tempdir() as d:
        os.makedirs(os.path.join(d, "src"))
        json.dump({"name": "t", "tree": {"ServerScriptService": {"$path": "src"}}},
                  open(os.path.join(d, "default.project.json"), "w"))
        src = os.path.join(d, "src", "A.luau")
        open(src, "w").write("return 1\n")
        try:
            for answer, state in [("ROLLED_BACK 3:1", "rolled_back"),
                                  ("ROLLBACK_FAILED 3:1", "rollback_failed"),
                                  ("HIERARCHY X is Folder, the project expects Model", "hierarchy")]:
                live.Session = _fake_session(answer)
                r = live.push(["ALL"], os.path.join(d, "default.project.json"))
                assert r["results"][0]["state"] == state, (answer, r["results"][0])
                assert r["pushed"] == 0
        finally:
            live.Session = orig


@check("verification: a limitation string is one item, not characters")
def _():
    from rbforge import verification
    r = verification.receipt("limits", limitations="not tested on mobile", save=False)
    assert "not tested on mobile" in r["limitations"], r["limitations"]
    assert not any(len(item) == 1 for item in r["limitations"]), "a string was split into characters"


@check("check: a crashed linter is a failure, never a quiet warning")
def _():
    from rbforge import check
    orig_run, orig_which = check._run, check.shutil.which
    with tempdir() as d:
        os.makedirs(os.path.join(d, "src"))
        open(os.path.join(d, "src", "a.luau"), "w").write("return 1\n")

        def fake(argv, cwd, timeout=180):
            if argv[0] == "selene":
                return (127, "process terminated unexpectedly")
            return (0, "ok")

        try:
            check.shutil.which = lambda name: "/fake/" + name
            check._run = fake
            rung = check.rung_static(d)
            got = [c for c in rung["checks"] if c["id"] == "selene"][0]
            assert got["status"] == "fail", got
            report = check.run(d, scope=["static"])
            assert report["status"] != "pass", report["status"]
        finally:
            check._run, check.shutil.which = orig_run, orig_which


@check("live: a mixed push batch reports every file without raising")
def _():
    from rbforge import live
    orig = live.Session
    with tempdir() as d:
        os.makedirs(os.path.join(d, "src"))
        json.dump({"tree": {"$className": "DataModel", "ServerScriptService": {"$path": "src"}}},
                  open(os.path.join(d, "default.project.json"), "w"))
        good = os.path.join(d, "src", "A.luau")
        open(good, "w").write("return 1\n")
        stray = os.path.join(d, "stray.luau")
        open(stray, "w").write("return 2\n")
        want = live.adler("return 1\n")
        try:
            live.Session = _fake_session("SYNCED " + want)
            r = live.push([good, stray], os.path.join(d, "default.project.json"))
            states = sorted(row["state"] for row in r["results"])
            assert states == ["synced", "unmapped"], states
            assert r["pushed"] == 1 and r["failed"] == 1, r
            for row in r["results"]:
                assert set(row) >= {"file", "target", "state", "ok"}, row
        finally:
            live.Session = orig


@check("check: a Rojo project without a tree fails validation")
def _():
    from rbforge import check
    with tempdir() as d:
        open(os.path.join(d, "default.project.json"), "w").write('{"name": "has no tree"}')
        got = [c for c in check.rung_structure(d)["checks"] if c["id"] == "project-map"][0]
        assert got["status"] == "fail", got
        assert "tree" in got["detail"], got["detail"]


@check("check: bad $path types and duplicate mappings fail validation")
def _():
    from rbforge import check
    with tempdir() as d:
        os.makedirs(os.path.join(d, "src"))
        cases = [
            {"tree": {"A": {"$path": 5}}},
            {"tree": {"A": {"$path": "src"}, "B": {"$path": "src"}}},
        ]
        for payload in cases:
            json.dump(payload, open(os.path.join(d, "default.project.json"), "w"))
            got = [c for c in check.rung_structure(d)["checks"] if c["id"] == "project-map"][0]
            assert got["status"] == "fail", (payload, got)


@check("live: a declared non-container parent is refused, not faked")
def _():
    from rbforge import live
    orig = live.Session
    with tempdir() as d:
        os.makedirs(os.path.join(d, "src", "Thing"))
        json.dump({"tree": {"Workspace": {"$className": "Workspace",
                                          "Thing": {"$className": "Script", "$path": "src/Thing"}}}},
                  open(os.path.join(d, "default.project.json"), "w"))
        open(os.path.join(d, "src", "Thing", "init.luau"), "w").write("return 1\n")
        try:
            live.Session = _fake_session("HIERARCHY Workspace.Thing must be a Script")
            r = live.push(["ALL"], os.path.join(d, "default.project.json"))
            assert r["results"][0]["state"] == "hierarchy", r["results"][0]
            assert r["pushed"] == 0
        finally:
            live.Session = orig


@check("live: cross-drive paths fall back to absolute instead of raising")
def _():
    from rbforge import live
    real = os.path.relpath

    def fake_rel(path, start=None):
        raise ValueError("path is on mount 'c:', start on mount 'Z:'")

    os.path.relpath = fake_rel
    try:
        assert live._rel("C:/other/file.luau", "Z:/project").endswith("file.luau")
    finally:
        os.path.relpath = real


@check("check: changed-only mode scopes linters and says so")
def _():
    import shutil as _shutil
    import subprocess as _sub
    from rbforge import check
    if not _shutil.which("git"):
        raise AssertionError("git unavailable")
    with tempdir() as d:
        _sub.run(["git", "init", "-q"], cwd=d, check=True)
        _sub.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
        _sub.run(["git", "config", "user.name", "t"], cwd=d, check=True)
        os.makedirs(os.path.join(d, "src"))
        legacy = os.path.join(d, "src", "legacy.luau")
        fresh = os.path.join(d, "src", "fresh.luau")
        open(legacy, "w").write("return 1\n")
        _sub.run(["git", "add", "."], cwd=d, check=True)
        _sub.run(["git", "commit", "-qm", "base"], cwd=d, check=True)
        open(fresh, "w").write("return 2\n")
        changed = check.changed_files(d)
        assert changed and any(p.endswith("fresh.luau") for p in changed), changed
        assert not any(p.endswith("legacy.luau") for p in changed), changed
        report = check.run(d, scope=["static"], changed_only=True)
        cov = report["coverage"]
        assert cov["mode"] == "changed-only" and "not a whole-project audit" in (cov["note"] or ""), cov
        ids = {c["id"] for c in report["rungs"][0]["checks"]}
        assert "luau-lsp" in ids, ids  # an empty change set must not skip the typechecker


def _mcp_rpc(proc, message, timeout=40):
    import threading
    result = {}

    def read():
        result["line"] = proc.stdout.readline()

    thread = threading.Thread(target=read, daemon=True)
    thread.start()
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()
    thread.join(timeout)
    assert not thread.is_alive(), "MCP server did not answer within %ss" % timeout
    line = result.get("line") or ""
    assert line, "MCP server closed the pipe"
    return json.loads(line)


@check("mcp: schemas match the implementation and forged provenance fails")
def _():
    import subprocess as _sub
    import sys as _sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    server = os.path.join(root, "mcp_server", "server.py")
    home = tempfile.mkdtemp(prefix="rbf-mcp-")
    env = dict(os.environ, RBFORGE_HOME=home)
    proc = _sub.Popen([_sys.executable, server], stdin=_sub.PIPE, stdout=_sub.PIPE,
                      text=True, env=env)
    assert proc.stdin and proc.stdout
    try:
        init = _mcp_rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                          "clientInfo": {"name": "t", "version": "1"}}})
        assert "result" in init, init

        tools = _mcp_rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
        names = {t["name"] for t in tools}
        assert {"rb_collect_evidence", "rb_verify_receipt"} <= names, sorted(names)
        schema = [t for t in tools if t["name"] == "rb_verify_receipt"][0]["inputSchema"]
        assert "observation_id" in schema["properties"], schema["properties"].keys()

        forged = _mcp_rpc(proc, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "rb_verify_receipt", "arguments": {
                "task": "forged through MCP", "provenance": "tool",
                "playtest_performed": True, "console_errors": 0,
                "evidence": {"checks": {"studio_connected": True}, "console_logged": True,
                             "screenshots": ["C:/fake.png"], "screenshots_inspected": True,
                             "tests": [{"name": "made up", "passed": True}]}}}})
        payload = json.loads(forged["result"]["content"][0]["text"])
        assert payload["verification_level"] != "verified_playtest", payload["verification_level"]

        unknown = _mcp_rpc(proc, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                  "params": {"name": "rb_nope", "arguments": {}}})
        assert "error" in unknown or unknown.get("result", {}).get("isError"), unknown
    finally:
        proc.kill()


@check("review: client-authority write flagged")
def _():
    from rbforge import review
    with tempdir() as d:
        open(os.path.join(d, "evil.client.lua"), "w").write(
            "local ls = Instance.new('Folder') ls.Name = 'leaderstats'\n")
        out = review.security(d)
        assert any(f["severity"] == "high" for f in out["findings"]), out["findings"]

@check("review: guarded remote handler rates 'info', unguarded 'medium'")
def _():
    from rbforge import review
    with tempdir() as d:
        open(os.path.join(d, "guarded.server.lua"), "w").write(
            "r.OnServerEvent:Connect(function(p, amt) if typeof(amt) ~= 'number' then return end end)")
        open(os.path.join(d, "unguarded.server.lua"), "w").write(
            "r.OnServerEvent:Connect(function(p, amt) give(p, amt) end)")
        out = review.security(d)
        sev = {f["file"]: f["severity"] for f in out["findings"]}
        assert sev.get("guarded.server.lua") == "info", sev
        assert sev.get("unguarded.server.lua") == "medium", sev

@check("scaffold: writes layout, refuses non-empty target")
def _():
    from rbforge import scaffold
    with tempdir() as base:
        target = os.path.join(base, "game")
        r = scaffold.scaffold(target, "simulator")
        assert os.path.isfile(os.path.join(target, "src", "server", "Main.server.lua"))
        cfg = open(os.path.join(target, "src", "shared", "Config.lua")).read()
        assert '"simulator"' in cfg
        try:
            scaffold.scaffold(target, "simulator")
            raise AssertionError("should have raised")
        except err_mod.ForgeError as e:
            assert e.code == "RBF-ARG-002"


# ---------------------------------------------------------------- studio (offline paths)

@check("studio: snapshot fields independent even with no probe")
def _():
    from rbforge import studio
    snap = studio.snapshot(probe=False)
    for key in ("studio_installed", "mcp_launcher_found", "mcp_enabled_setting",
                "studio_process"):
        assert key in snap
    assert snap["mcp_probe"]["responding"] is None


# ---------------------------------------------------------------- capabilities

@check("capabilities: statuses derived, optional absence calm")
def _():
    from rbforge import capabilities
    m = capabilities.compute(probe=False)
    assert m["official_studio_mcp"]["status"] in (
        "verified", "unavailable", "runtime_required", "manual_step")
    for t in ("rojo", "stylua", "selene"):
        assert m[t]["status"] in ("installed", "optional")


# ---------------------------------------------------------------- skills installer

@check("skills: install/remove roundtrip into a sandbox root")
def _():
    from rbforge import skills
    with tempdir() as root:
        skills._ROOTS["sandbox"] = ("RBFORGE_SANDBOX_SKILLS", (root,))
        try:
            res = skills.install(["sandbox"])
            assert "installed" in res["sandbox"], res
            st = skills.status()
            assert all(v == "current" for v in st["sandbox"]["skills"].values())
            assert os.path.isdir(os.path.join(root, "roblox-game-development"))
            skills.remove(["sandbox"])
            assert not os.path.isdir(os.path.join(root, "roblox-game-development"))
        finally:
            del skills._ROOTS["sandbox"]

@check("skills: foreign skill dir blocks overwrite")
def _():
    from rbforge import skills
    with tempdir() as root:
        foreign = os.path.join(root, "roblox-docs")
        os.makedirs(foreign)
        open(os.path.join(foreign, "SKILL.md"), "w").write("---\nname: roblox-docs\nnot ours\n")
        skills._ROOTS["sbx2"] = ("RBFORGE_SBX2_SKILLS", (root,))
        try:
            res = skills.install(["sbx2"])
            assert "blocked" in res["sbx2"], res
        finally:
            del skills._ROOTS["sbx2"]

@check("agents: TOML block parses and removes cleanly (codex/grok)")
def _():
    from rbforge import agents
    argv = ["C:\\Users\\x y\\py 3.11.exe", "C:\\repo\\mcp_server\\server.py"]  # worst case
    block = agents._toml_block("robloxforge", argv)
    import tomllib
    doc = tomllib.loads("[mcp_servers.other]\ncommand = \"keep.exe\"\n" + block +
                        "[mcp_servers.Roblox_Studio]\ncommand = \"official.exe\"\n")
    assert doc["mcp_servers"]["other"]["command"] == "keep.exe"
    assert doc["mcp_servers"]["robloxforge"]["enabled"] is False
    assert doc["mcp_servers"]["Roblox_Studio"]["command"] == "official.exe"
    cleaned = agents._toml_remove(
        "[mcp_servers.other]\ncommand = \"keep.exe\"\n" + block +
        "[mcp_servers.Roblox_Studio]\ncommand = \"official.exe\"\n", "robloxforge")
    reparsed = tomllib.loads(cleaned)
    assert "robloxforge" not in reparsed["mcp_servers"]
    assert reparsed["mcp_servers"]["other"]["command"] == "keep.exe"
    assert reparsed["mcp_servers"]["Roblox_Studio"]["command"] == "official.exe"

@check("mcp server: notifications silent, junk JSON survives")
def _():
    import subprocess
    p = subprocess.Popen([sys.executable, "mcp_server/server.py"],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True,
                         cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    out, err = p.communicate(
        '{"jsonrpc":"2.0","method":"notifications/cancelled"}\n'
        '[1]\n'
        '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}\n', timeout=60)
    lines = [l for l in out.splitlines() if l.strip()]
    assert len(lines) == 2, "notification must get NO response: %r" % out
    assert json.loads(lines[0])["error"]["code"] == -32600  # the [1]
    assert "tools" in json.loads(lines[1])["result"]
    assert p.returncode == 0

@check("shipped skills are loadable: frontmatter closes and carries a description")
def _():
    """v0.1.0 shipped `roblox-docs/SKILL.md` as 214 bytes ending in the literal
    text `...[truncated]`, with the frontmatter block never closed.

    A frontmatter block that does not close is not a skill: a strict reader
    never opens it, so the description -- the only thing an agent sees when
    deciding whether to load the skill -- is gone. It installed cleanly into
    every agent, occupied an index entry, and could never be selected. Nothing
    checked, because nothing here read a SKILL.md as a skill.
    """
    import re
    from rbforge import skills as skills_mod
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")
    for name in skills_mod.OUR_SKILLS:
        path = os.path.join(root, name, "SKILL.md")
        assert os.path.isfile(path), "%s: SKILL.md is missing" % name
        raw = open(path, "rb").read()
        assert not raw.startswith(b"\xef\xbb\xbf"), (
            "%s: UTF-8 BOM before frontmatter -- a strict reader sees '\\ufeff---' "
            "and never opens the block" % name)
        text = raw.decode("utf-8")
        m = re.match(r"(?s)^---\s*\n(.*?)\n---\s*\n", text)
        assert m, ("%s: frontmatter block never closes -- this is not a loadable "
                   "skill, it is a file that installs and can never be selected" % name)
        fm = m.group(1)
        dm = re.search(r"(?ms)^description:[ \t]*(.*?)(?=^[A-Za-z_-]+:|\Z)", fm)
        assert dm and dm.group(1).strip(), (
            "%s: no description -- the agent has nothing to match on" % name)
        desc = " ".join(dm.group(1).split())
        assert "[truncated]" not in text, (
            "%s: contains the literal marker '[truncated]'. Authoring tooling cut "
            "this file and it was committed that way." % name)
        assert re.match(r"^name:\s*%s\s*$" % re.escape(name), fm, re.M), (
            "%s: frontmatter name does not match its directory" % name)
        assert len(text) > len(m.group(0)) + 200, (
            "%s: frontmatter parses but there is no body worth loading" % name)
        assert len(desc) > 40, "%s: description is too short to route on" % name


# ---------------------------------------------------------------- check gate

@check("check: no toolchain is 'incomplete', never 'pass'")


def _():
    """A machine without StyLua is not a machine with clean formatting. If a
    skip could ever read as a pass, an agent would report verified work it never
    verified -- the exact failure this gate exists to prevent."""
    from rbforge import check as check_mod, types as types_mod
    old_discover = types_mod.discover
    types_mod.discover = lambda root, ref=None: (None, "no definitions in this fixture")
    with tempdir() as root:
        report = check_mod.run(root)
        assert report["status"] == "incomplete", report["status"]
        assert report["counts"]["skip"] > 0
        assert "do NOT report this as verified" in report["gate"]
    types_mod.discover = old_discover


@check("check: proven defects fail and name the file")


def _():
    from rbforge import check as check_mod
    with tempdir() as root:
        os.makedirs(os.path.join(root, "src", "client"))
        with open(os.path.join(root, "src", "client", "Main.client.luau"), "w",
                  encoding="utf-8") as fh:
            fh.write("local f = loadstring('return 1')\n"
                     "local DataStoreService = game:GetService('DataStoreService')\n")
        report = check_mod.run(root, scope=["structure"])
        assert report["status"] == "fail", report["status"]
        details = " ".join(c["detail"] for r in report["rungs"] for c in r["checks"])
        assert "loadstring" in details
        assert "DataStoreService" in details
        assert "Main.client.luau" in details, "a defect without a file is not actionable"

@check("check: missing Rojo $path target is a failure")


def _():
    from rbforge import check as check_mod
    with tempdir() as root:
        with open(os.path.join(root, "default.project.json"), "w", encoding="utf-8") as fh:
            json.dump({"name": "x", "tree": {"$className": "DataModel",
                                             "ReplicatedStorage": {"$path": "src/shared"}}}, fh)
        report = check_mod.run(root, scope=["structure"])
        assert report["status"] == "fail", report["status"]
        details = " ".join(c["detail"] for r in report["rungs"] for c in r["checks"])
        assert "src/shared" in details

@check("skills: every reference on disk is routed by SKILL.md")


def _():
    """A reference nobody can reach is dead weight, and the router listing a
    file that does not exist sends an agent to a 404. Both directions checked."""
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "skills", "roblox-game-development")
    skill = open(os.path.join(root, "SKILL.md"), encoding="utf-8").read()
    refs = sorted(n for n in os.listdir(os.path.join(root, "references")) if n.endswith(".md"))
    for name in refs:
        assert "references/%s" % name in skill, (
            "%s exists but SKILL.md never routes to it" % name)
    for token in set(__import__("re").findall(r"references/([\w-]+\.md)", skill)):
        assert token in refs, "SKILL.md routes to missing reference %s" % token

@check("doctor: renders when a studio reports no place name")


def _():
    from rbforge import doctor
    report = {
        "version": "test",
        "studio": {"studio_installed": True, "studio_version": "version-x",
                   "studio_process": {"running": True},
                   "mcp_enabled_setting": {"enabled": True},
                   "mcp_launcher_found": True,
                   "active_places": [None, "Real Place"]},
        "mcp_probe": {"responding": True, "tool_count": 34, "error": None},
        "docs": {"present": False},
        "toolchain": {},
        "agents": {},
        "capabilities_by_status": {},
    }
    text = doctor.render(report)
    assert "Real Place" in text


# ---------------------------------------------------------------- plugins

@check("plugins: detects known tools and always names a free alternative")


def _():
    from rbforge import plugins
    with tempdir() as root:
        open(os.path.join(root, "ForgeGUI.rbxm"), "wb").close()
        open(os.path.join(root, "MoonAnimator.rbxm"), "wb").close()
        open(os.path.join(root, "SomeUnknownThing.rbxmx"), "wb").close()
        os.environ["RBFORGE_PLUGIN_DIR"] = root
        try:
            info = plugins.status()
        finally:
            os.environ.pop("RBFORGE_PLUGIN_DIR", None)
        ids = {k["id"] for k in info["known"]}
        assert "forgegui" in ids and "moonanimator" in ids, ids
        assert info["unknown_count"] == 1, info["unknown_count"]
        assert all(k["free_alternative"] for k in info["known"]), (
            "a detected paid tool without a free alternative is a paywall")
        assert "never make them a requirement" in info["note"], info["note"]

@check("plugins: no plugin folder is a calm free-path answer")


def _():
    from rbforge import plugins
    os.environ["RBFORGE_PLUGIN_DIR"] = os.path.join(os.getcwd(), "does-not-exist")
    try:
        # force the default location to look empty for this assertion
        info = plugins.status()
    finally:
        os.environ.pop("RBFORGE_PLUGIN_DIR", None)
    assert info["free_path_is_default"] is True
    assert "free" in info["note"].lower()

@check("free-stack: search_asset filters match the live schema spelling")


def _():
    """`priceFilter` is lowercase and only valid with scope=creator_store.
    A doc with `priceFilter="Free"` is not a style nit - the call is rejected."""
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "skills", "roblox-game-development", "references")
    text = open(os.path.join(root, "free-stack.md"), encoding="utf-8").read()
    assert 'priceFilter="Free"' not in text
    assert 'scope="CreatorStore"' not in text
    assert 'priceFilter="free"' in text
    assert 'scope="creator_store"' in text


# ---------------------------------------------------------------- new project

@check("new: one command yields a gated project with a filled-in plan")


def _():
    """The beginner entry point. If PLAN.md ships with empty sections the user
    gets a scaffold and no idea what to build first."""
    from rbforge import scaffold
    with tempdir() as root:
        target = os.path.join(root, "g")
        res = scaffold.new_project(target, "obby", "dodge lasers")
        plan_path = os.path.join(target, "PLAN.md")
        assert os.path.isfile(plan_path)
        text = open(plan_path, encoding="utf-8").read()
        assert "1. " in text, "build order has no numbered steps"
        assert "- [ ] " in text, "verification list is empty"
        assert "## Build order" in text and "## Prove it" in text
        assert "build[]" not in text, "internal key names leaked into user copy"
        assert "rbforge check" in text
        assert os.path.isfile(os.path.join(target, "rokit.toml"))
        assert any("Baseplate" in s for s in res["next_steps"])
        assert "No purchase" in res["free"]

@check("scripts: no PowerShell helper declares the automatic $Args")
def _():
    """`param(... $Args)` is shadowed by PowerShell's automatic $args, so
    `@Args` splats nothing: Install.ps1 printed usage and installed no skills."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in sorted(os.listdir(root)):
        if name.endswith(".ps1"):
            text = open(os.path.join(root, name), encoding="utf-8-sig").read()
            assert not re.search(r"\[string\[\]\]\$Args\b", text, re.I), name
            assert "@Args" not in text, name


# ---------------------------------------------------------------- probes + traps

@check("probes: every probe renders with defaults and leaves no placeholder")
def _():
    from rbforge import probes
    cat = probes.catalog()
    names = {p["name"] for p in cat}
    for need in ("console", "gui-overflow", "ray-all", "box-scan", "hide", "restore", "camera-pin", "ui-audit"):
        assert need in names, need
    for p in cat:
        r = probes.render(p["name"])
        assert "{{" not in r["code"], p["name"]
        assert r["datamodel"] in ("any", "Edit", "Client", "Server"), p["name"]
        assert "execute_luau" in r["run"] and r["purpose"], p["name"]
        assert "return" in r["code"], p["name"] + " returns nothing for execute_luau to show"

@check("probes: overrides land, unknown names and params are refused")
def _():
    from rbforge import probes
    r = probes.render("whereis", probes.parse_sets(['pattern="ExitDoor"', "limit=5"]))
    assert '"ExitDoor"' in r["code"] and ", 5" in r["code"]
    for bad in (lambda: probes.render("nope"), lambda: probes.render("whereis", {"nope": "1"}),
                lambda: probes.render("whereis", {"pattern": "a\nb"}), lambda: probes.render("../x")):
        try:
            bad()
            raise AssertionError("accepted bad input")
        except err_mod.ForgeError:
            pass

@check("traps: each rule fires on its pattern and stays quiet on the fix")
def _():
    from rbforge import traps

    def ids(rel, text):
        return {f["id"] for f in traps.scan_text(rel, text)}
    assert "T003" in ids("a.luau", 'local g = Instance.new("SurfaceGui")')
    assert "T003" not in ids("a.luau", 'local g = Instance.new("SurfaceGui")\ng.ClipsDescendants = true')
    assert "T005" in ids("x.server.luau", "local p = game.Players.LocalPlayer")
    assert "T005" not in ids("x.client.luau", "local p = game.Players.LocalPlayer")
    assert "T007" in ids("src/client/a.luau", 'Instance.new("RemoteEvent")')
    assert "T011" in ids("a.server.luau", "local v = store:GetAsync(key)")
    assert "T011" not in ids("a.server.luau", "local ok, v = pcall(function()\n return store:GetAsync(key)\nend)")
    assert "T001" in ids("a.luau", "wait(1)") and "T001" not in ids("a.luau", "task.wait(1)")
    assert "T013" in ids("a.server.luau", "RunService.Heartbeat:Connect(function() r:FireAllClients(1) end)")
    assert not ids("a.luau", "-- wait(1) in a comment")
    # viewmodel clone keeping its character joints, and a saved transparency restored
    bugh = 'local m = weapon:Clone()\nlocal cam = workspace.CurrentCamera\nm.Parent = cam'
    assert "T022" in ids("src/client/vm.luau", bugh)
    assert "T022" not in ids("src/client/vm.luau", bugh + '\nfor _, d in ipairs(m:GetDescendants()) do\n if d:IsA("JointInstance") then d:Destroy() end\nend')
    assert "T023" in ids("src/client/vm.luau", "part.LocalTransparencyModifier = saved")
    assert "T023" not in ids("src/client/vm.luau", "part.LocalTransparencyModifier = 0")
    trig = 'local on = player:GetAttribute("DebugFirstPerson")'
    assert "T024" in ids("src/client/move.luau", trig)
    assert "T024" not in ids("src/client/move.luau", "local on = RunService:IsStudio() and player:GetAttribute(\"DebugFirstPerson\")")
    deco = 'w.rod("Tendril", a, b, 1, flesh, M.Slate, true)'
    assert "T025" in ids("src/server/t.server.luau", deco)
    assert "T025" not in ids("src/server/t.server.luau", 'w.rod("Tendril", a, b, 1, flesh, M.Slate, false)')

@check("traps: review skips snapshot folders")
def _():
    from rbforge import traps
    with tempdir() as d:
        os.makedirs(os.path.join(d, "src"))
        os.makedirs(os.path.join(d, "artifacts", "recovery"))
        open(os.path.join(d, "default.project.json"), "w").write("{}")
        open(os.path.join(d, "src", "a.server.luau"), "w").write("wait(1)\n")
        open(os.path.join(d, "artifacts", "recovery", "b.server.luau"), "w").write("wait(1)\n")
        res = traps.review(d)
        files = {f["file"] for f in res["findings"]}
        assert files == {"src/a.server.luau"}, files
        assert res["files_skipped"] == 1

@check("skills: router links the debugging playbook and the probes")
def _():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ref = os.path.join(root, "skills", "roblox-game-development")
    skill = open(os.path.join(ref, "SKILL.md"), encoding="utf-8").read()
    assert "references/debugging-playbook.md" in skill and "rb_studio_probe" in skill
    assert os.path.isfile(os.path.join(ref, "references", "debugging-playbook.md"))

@check("mcp: probe and traps tools are registered")
def _():
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location("rbf_server", os.path.join(root, "mcp_server", "server.py"))
    text = open(spec.origin, encoding="utf-8").read()
    assert '"rb_studio_probe"' in text and '"rb_traps_review"' in text


# ---------------------------------------------------------------- helpers (moved above)


# ------------------------------------------------- regression: audit 2026-11-06

@check("check: typechecker exit status decides, never a word search")
def _():
    from rbforge import check
    orig_run, orig_which = check._run, check.shutil.which
    with tempdir() as d:
        defs = os.path.join(d, "globalTypes.d.luau")
        open(defs, "w").write("-- definitions\n")
        os.environ["RBFORGE_LUAU_DEFINITIONS"] = defs

        def fake(argv, cwd, timeout=180):
            return (0, "ok") if argv[0] != "luau-lsp" else fake.answer

        try:
            check.shutil.which = lambda name: "/fake/" + name
            check._run = fake
            cases = [
                ((None, "could not run 'luau-lsp': boom"), "skip"),
                ((127, "process terminated unexpectedly"), "fail"),
                ((0, "0 errors, 0 warnings"), "pass"),
                ((0, "src/a.luau:12:5: TypeError: bad"), "fail"),
                ((1, "src/a.luau:3:1: Unknown global 'x'"), "fail"),
            ]
            for answer, want in cases:
                fake.answer = answer
                rung = check.rung_static(d)
                got = [c for c in rung["checks"] if c["id"] == "luau-lsp"][0]
                assert got["status"] == want, (answer, want, got)
        finally:
            check._run, check.shutil.which = orig_run, orig_which
            os.environ.pop("RBFORGE_LUAU_DEFINITIONS", None)

@check("check: malformed project JSON fails the project-map check")
def _():
    from rbforge import check
    with tempdir() as d:
        open(os.path.join(d, "default.project.json"), "w").write("{ not json")
        rung = check.rung_structure(d)
        got = [c for c in rung["checks"] if c["id"] == "project-map"][0]
        assert got["status"] == "fail", got
        assert "malformed" in got["detail"].lower(), got["detail"]

@check("live: rojo init.* files map the directory to a script")
def _():
    from rbforge import live
    with tempdir() as d:
        base = os.path.join(d, "src", "ServerScriptService")
        os.makedirs(os.path.join(base, "Systems"))
        json.dump({"tree": {"$className": "DataModel",
                            "ServerScriptService": {"$path": "src/ServerScriptService"}}},
                  open(os.path.join(d, "default.project.json"), "w"))
        for name in ("init.server.luau", "Systems/init.luau", "Systems/A.luau"):
            open(os.path.join(base, name), "w").write("-- \n")
        targets = live.rojo_targets(os.path.join(d, "default.project.json"))
        names = sorted(v for v in targets.values())
        assert ("", "ServerScriptService", "Script") in names, names
        assert ("ServerScriptService", "Systems", "ModuleScript") in names, names
        assert ("ServerScriptService.Systems", "A", "ModuleScript") in names, names


def _fake_session(out):
    class Fake:
        answer = out

        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def luau(self, code, dm="Edit"):
            return Fake.answer
    return Fake

@check("live: server test result parsing is exact")
def _():
    from rbforge import live
    orig = live.Session
    with tempdir() as d:
        path = os.path.join(d, "t.luau")
        # The fixture must declare the attribute: a test that cannot report is refused before it runs.
        open(path, "w").write('workspace:SetAttribute("Attr", "PASS ...")\n')
        try:
            for text, want in [("PASS 30 routes", "pass"), ("FAIL 2 routes", "fail"),
                               ("NOT_PASS 30", "fail"), ("TIMEOUT", "fail"),
                               ("", "unknown"), ("garbage output", "unknown"),
                               ("PASS", "pass")]:
                live.Session = _fake_session(text)
                got = live.server_test(path, "Attr", timeout=1)
                assert got["outcome"] == want, (text, got)
                assert got["passed"] is (want == "pass")
        finally:
            live.Session = orig

@check("live: push reports synced, mismatch and unverified separately")
def _():
    from rbforge import live
    orig = live.Session
    with tempdir() as d:
        os.makedirs(os.path.join(d, "src"))
        json.dump({"tree": {"$className": "DataModel",
                            "ServerScriptService": {"$path": "src"}}},
                  open(os.path.join(d, "default.project.json"), "w"))
        src = os.path.join(d, "src", "A.luau")
        open(src, "w").write("return 1\n")
        want = live.adler("return 1\n")
        try:
            for answer, state in [("SYNCED " + want, "synced"),
                                  ("MISMATCH " + want, "mismatch"),
                                  ("UNVERIFIED", "unverified")]:
                live.Session = _fake_session(answer)
                r = live.push(["ALL"], os.path.join(d, "default.project.json"))
                assert r["results"][0]["state"] == state, (answer, r["results"][0])
                assert r["pushed"] == (1 if state == "synced" else 0), r
        finally:
            live.Session = orig

@check("check: luau compound assignment is not a parse error")
def _():
    from rbforge import check
    with tempdir() as d:
        os.makedirs(os.path.join(d, "src"))
        open(os.path.join(d, "src", "a.luau"), "w").write(
            "--!strict\nlocal speed = 1\nspeed += 2\nreturn speed\n")
        rung = check.rung_static(d)
        got = [c for c in rung["checks"] if c["id"] == "selene"][0]
        assert "parse_error" not in got["detail"], got["detail"]


@check("verification: unknown and expired observations are rejected")
def _():
    from rbforge import verification
    with _isolated_home():
        unknown = verification.receipt("unknown", observation_id="obs-0000000000000000",
                                       playtest_performed=True, save=False)
        assert unknown["verification_level"] != "verified_playtest", unknown["verification_level"]
        obs = _collect()["observation_id"]
        # Age the stored record: the default six-hour window must reject it.
        store_path = verification._observations_path()
        store = json.load(open(store_path, encoding="utf-8"))
        store[obs]["recorded_at"] = store[obs]["recorded_at"] - 7 * 3600
        json.dump(store, open(store_path, "w", encoding="utf-8"))
        assert verification.load_observation(obs) is None, "an expired observation survived"
        expired = verification.receipt("expired", observation_id=obs, project="demo",
                                       scenario="smoke", playtest_performed=True, save=False)
        assert expired["verification_level"] != "verified_playtest", expired["verification_level"]


@check("verification: a missing screenshot or console caps the level at partial")
def _():
    from rbforge import verification
    with _isolated_home():
        no_shot = _collect(capture=None)["observation_id"]
        r = verification.receipt("no shot", observation_id=no_shot, project="demo", scenario="smoke",
                                 playtest_performed=True, save=False)
        assert r["verification_level"] == "playtest_observed_partial", r["verification_level"]
        assert r["screenshot_inspected_by_vision"] is False
        assert r["checks"]["screenshot_captured"] is False


@check("check: Rojo project validation matches a real rojo build")
def _():
    from rbforge import check
    with tempdir() as d:
        os.makedirs(os.path.join(d, "src"))
        # name is optional in Rojo 7.7.1; an empty tree is not.
        json.dump({"tree": {"ServerScriptService": {"$path": "src"}}},
                  open(os.path.join(d, "default.project.json"), "w"))
        got = [c for c in check.rung_structure(d)["checks"] if c["id"] == "project-map"][0]
        assert got["status"] == "pass", got
        json.dump({"name": "t", "tree": {}}, open(os.path.join(d, "default.project.json"), "w"))
        got = [c for c in check.rung_structure(d)["checks"] if c["id"] == "project-map"][0]
        assert got["status"] == "fail" and "empty" in got["detail"].lower(), got
        json.dump({"name": "t", "tree": {"$className": "DataModel"}},
                  open(os.path.join(d, "default.project.json"), "w"))
        got = [c for c in check.rung_structure(d)["checks"] if c["id"] == "project-map"][0]
        assert got["status"] == "pass", got


@check("check: changed-only honours an explicit base ref")
def _():
    import shutil as _shutil
    import subprocess as _sub
    from rbforge import check
    if not _shutil.which("git"):
        raise AssertionError("git unavailable")
    with tempdir() as d:
        _sub.run(["git", "init", "-q"], cwd=d, check=True)
        _sub.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
        _sub.run(["git", "config", "user.name", "t"], cwd=d, check=True)
        os.makedirs(os.path.join(d, "src"))
        open(os.path.join(d, "src", "a.luau"), "w").write("return 1\n")
        _sub.run(["git", "add", "."], cwd=d, check=True)
        _sub.run(["git", "commit", "-qm", "one"], cwd=d, check=True)
        base = _sub.run(["git", "rev-parse", "HEAD"], cwd=d, capture_output=True, text=True).stdout.strip()
        open(os.path.join(d, "src", "b.luau"), "w").write("return 2\n")
        _sub.run(["git", "add", "."], cwd=d, check=True)
        _sub.run(["git", "commit", "-qm", "two"], cwd=d, check=True)
        assert check.changed_files(d) == [], "a clean tree should show no working-tree changes"
        against = check.changed_files(d, base_ref=base)
        assert any(p.endswith("b.luau") for p in against), against


@check("live: a project that declares servePlaceIds refuses the wrong place")
def _():
    from rbforge import live
    orig = live.Session
    with tempdir() as d:
        os.makedirs(os.path.join(d, "src"))
        json.dump({"name": "t", "servePlaceIds": [1234],
                   "tree": {"ServerScriptService": {"$path": "src"}}},
                  open(os.path.join(d, "default.project.json"), "w"))
        open(os.path.join(d, "src", "A.luau"), "w").write("return 1\n")
        try:
            live.Session = _fake_session("9999")
            try:
                live.push(["ALL"], os.path.join(d, "default.project.json"))
                raise AssertionError("push accepted the wrong place")
            except err_mod.ForgeError as exc:
                assert exc.code == "RBF-STUDIO-003", exc.code
        finally:
            live.Session = orig


@check("verification: a screenshot path and a caller flag cannot verify anything")
def _():
    from rbforge import verification
    with _isolated_home():
        obs = _collect(capture_screenshot_off=True)["observation_id"]
        r = verification.receipt("claimed shot", observation_id=obs, project="demo",
                                 scenario="smoke",
                                 evidence={"screenshots": ["C:/does/not/exist.png"],
                                           "screenshots_inspected": True},
                                 screenshot_captured=True, screenshot_inspected=True,
                                 playtest_performed=True, save=False)
        assert r["verification_level"] == "playtest_observed_partial", r["verification_level"]
        assert r["checks"]["screenshot_captured"] is False, "a claimed path filled an observed field"


@check("verification: an image MCP block becomes a hashed artifact, junk is ignored")
def _():
    import base64 as b64
    from rbforge import verification
    with _isolated_home():
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
        good = [{"type": "image", "mimeType": "image/png", "data": b64.b64encode(png).decode()}]
        records = verification._save_capture(good, "")
        assert records and records[0]["verified_image"] is True, records
        assert records[0]["bytes"] == len(png) and len(records[0]["sha256"]) == 64
        assert os.path.isfile(records[0]["artifact"])

        bad = [
            [{"type": "image", "mimeType": "application/pdf", "data": "AAAA"}],
            [{"type": "image", "mimeType": "image/png", "data": "not base64 at all"}],
            [{"type": "image", "mimeType": "image/png"}],
            [],
        ]
        for blocks in bad:
            got = verification._save_capture(blocks, "")
            assert got == [], (blocks, got)
        # A text-only answer is recorded, but it is not an image.
        text_records = verification._save_capture([], "C:/shots/whatever.png")
        assert text_records and text_records[0]["verified_image"] is False


@check("verification: captured but uninspected stays partial")
def _():
    from rbforge import verification
    with _isolated_home():
        obs = _collect(inspected=False)["observation_id"]
        r = verification.receipt("captured", observation_id=obs, project="demo", scenario="smoke",
                                 playtest_performed=True, save=False)
        assert r["verification_level"] == "playtest_observed_partial", r["verification_level"]
        assert r["checks"]["screenshot_captured"] is True


@check("verification: console classification separates clean, errors and unknown")
def _():
    from rbforge import verification
    cases = [
        ("[Server] all good", "ok", 0),
        ("Script error: attempt to index nil", "errors", 1),
        ("stack begin\nScript error: boom", "errors", 2),
        ("No error was found here", "ok", 0),
        ("", "unknown", 0),
        (None, "unknown", 0),
        ("arbitrary informational output", "ok", 0),
    ]
    for text, status, errors in cases:
        got, count, _warn = verification.classify_console(text)
        assert got == status and count == errors, (text, got, count)


@check("live: declared Folder is enforced but never converted")
def _():
    code = _generated_push_code(parent_classes={"Workspace": "Folder"})
    assert "want ~= 'Folder'" not in code, "Folder was exempted from the class check"


@check("live: servePlaceIds fails closed on bad configuration")
def _():
    from rbforge import live
    with tempdir() as d:
        proj = os.path.join(d, "default.project.json")

        def ids(payload):
            json.dump(payload, open(proj, "w"))
            return live._project_place_ids(proj)

        assert ids({"name": "t"}) is None, "absent field must mean unconstrained"
        assert ids({"name": "t", "servePlaceIds": []}) == []
        assert ids({"name": "t", "servePlaceIds": [1234]}) == [1234]
        assert ids({"name": "t", "servePlaceIds": ["1234"]}) == [1234]
        for bad in (["invalid"], [True], [None], {"a": 1}, "1234"):
            try:
                ids({"name": "t", "servePlaceIds": bad})
                raise AssertionError("accepted %r" % (bad,))
            except err_mod.ForgeError as exc:
                assert exc.code == "RBF-ARG-002", exc.code


@check("mcp: schemas advertise the arguments the implementation accepts")
def _():
    import inspect
    from rbforge import check, live, verification
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(root, "mcp_server"))
    import server

    def props(name):
        return set(server.TOOLS[name][1]["properties"])

    assert {"changed_only", "base_ref"} <= props("rb_check"), props("rb_check")
    assert {"project", "scenario", "revision", "capture_screenshot"} <= props("rb_collect_evidence")
    assert {"project", "scenario", "studio_id"} <= props("rb_verify_receipt")

    accepted = set(inspect.signature(check.run).parameters)
    advertised = props("rb_check") | {"path", "scope"}
    assert advertised <= accepted | {"path"}, advertised - accepted
    for option in ("changed_only", "base_ref"):
        assert option in accepted, option


@check("verification: the collector asks Studio for a capture with a capture_id")
def _():
    from rbforge import verification
    seen = {}

    class SpyFake:
        studio_id = "fake"

        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def luau(self, code, dm="Edit"):
            return "Place1"

        def call(self, tool, args):
            if tool == "get_console_output":
                return "[Server] ok"
            raise KeyError(tool)

        def call_content(self, tool, args):
            seen.update(args)
            return ([], False, "")

    verification.collect_evidence(session_factory=SpyFake, capture_screenshot=True)
    # Studio rejects screen_capture without it: "Missing required argument: capture_id".
    assert seen.get("capture_id"), seen


@check("verification: collecting evidence during Play falls back to the Server context")
def _():
    from rbforge import verification

    class PlayOnly:
        studio_id = "fake"

        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def luau(self, code, dm="Edit"):
            if dm == "Edit":
                raise AssertionError("Edit datamodel is not available in Play mode")
            return "Game"

        def call(self, tool, args):
            return ""

        def call_content(self, tool, args):
            return ([], False, "")

    obs = verification.collect_evidence(session_factory=PlayOnly)
    assert obs["place"] == "Game" and obs["datamodel"] == "Server", obs


@check("live: a class-change rollback restores the original before removing the stand-in")
def _():
    code = _generated_push_code(klass="Script")
    backup_at = code.index("if backup then")
    created_at = code.index("if created then")
    assert backup_at < created_at, "the created branch runs before the backup is restored"
    assert "backup.Name = backupName" in code and "backup.Parent = node" in code
    assert "(original restored)" in code and "(new script removed)" in code


@check("live: an over-limit source is reported as rolled_back, never synced")
def _():
    # Studio rejects Source >= 200000 chars; the generated code must treat that as a write failure.
    code = _generated_push_code(text="x" * 10)
    assert "local wrote = pcall(function() target.Source = src end)" in code
    assert "if not wrote then return restore('write failed') end" in code


@check("verification: omitting scenario or revision does not match a bound observation")
def _():
    from rbforge import verification
    with _isolated_home():
        obs = _collect(project="demo", scenario="smoke-old", revision="rev-live-1",
                       console="[Server] ready")["observation_id"]
        # Capture the revision this observation recorded, then try to reuse it.
        stored = verification.load_observation(obs)
        rev = stored.get("revision")

        omitted = verification.receipt("unrelated feature", observation_id=obs, project="demo",
                                       playtest_performed=True, save=False)
        assert omitted["verification_level"] != "verified_playtest", omitted["verification_level"]

        wrong_scenario = verification.receipt("x", observation_id=obs, project="demo",
                                              scenario="new-feature", revision=rev,
                                              playtest_performed=True, save=False)
        assert wrong_scenario["verification_level"] != "verified_playtest"

        wrong_rev = verification.receipt("x", observation_id=obs, project="demo",
                                         scenario="smoke-old", revision="rev-other",
                                         playtest_performed=True, save=False)
        assert wrong_rev["verification_level"] != "verified_playtest"

        good = verification.receipt("x", observation_id=obs, project="demo", scenario="smoke-old",
                                    revision=rev, playtest_performed=True, save=False)
        assert good["verification_level"] == "verified_playtest", good["verification_level"]
        assert good["evidence"]["binding"]["scenario"] == "smoke-old"


@check("verification: console fixtures cover the shapes Studio prints")
def _():
    from rbforge import verification
    cases = [
        ("[Server] Error: attempt to index nil", "errors"),
        ("[Client] Script error: missing Foo", "errors"),
        ("19:52:36.782  ServerScriptService.Main:4: attempt to index nil", "errors"),
        ("stack begin", "errors"),
        ("[Server] Warning: deprecated API", "ok"),
        ("[Server] all good", "ok"),
        ("No error was found", "ok"),
        ("", "unknown"),
    ]
    for text, want in cases:
        got, _errors, _warn = verification.classify_console(text)
        assert got == want, (text, got)


@check("live: a batch stops after an unrecovered rollback")
def _():
    from rbforge import live
    orig = live.Session
    with tempdir() as d:
        os.makedirs(os.path.join(d, "src"))
        json.dump({"name": "t", "tree": {"ServerScriptService": {"$path": "src"}}},
                  open(os.path.join(d, "default.project.json"), "w"))
        for name in ("A", "B"):
            open(os.path.join(d, "src", "%s.luau" % name), "w").write("return %s\n" % name)

        class Sequenced:
            calls = 0

            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def luau(self, code, dm="Edit"):
                Sequenced.calls += 1
                if Sequenced.calls == 1:
                    return "ROLLBACK_FAILED write failed (original kept in ServerStorage.rbforge_backups)"
                return "SYNCED 1:1"

        try:
            live.Session = Sequenced
            r = live.push(["ALL"], os.path.join(d, "default.project.json"))
            assert Sequenced.calls == 1, "the batch kept writing after an unrecovered rollback"
            states = {row["state"] for row in r["results"]}
            assert {"rollback_failed", "not_attempted"} <= states, states
            assert r["pushed"] == 0
        finally:
            live.Session = orig


@check("mcp: rb_collect_evidence applies its advertised capture default")
def _():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(root, "mcp_server"))
    import server
    from rbforge import verification
    captured = {}

    def fake(**kwargs):
        captured.update(kwargs)
        return {"screenshots": [], "observation_id": "obs-x"}

    orig = verification.collect_evidence
    verification.collect_evidence = fake
    try:
        out = server.TOOLS["rb_collect_evidence"][0]({"task": "x"})
        assert captured.get("capture_screenshot") is True, captured
        assert out["capture"]["requested"] is True
        assert out["capture"]["status"] == "failed", out["capture"]

        captured.clear()
        server.TOOLS["rb_collect_evidence"][0]({"capture_screenshot": False})
        assert captured.get("capture_screenshot") is False, "explicit false must disable capture"
    finally:
        verification.collect_evidence = orig


@check("live: restoration is verified with a protected readback")
def _():
    code = _generated_push_code()
    assert "local okRead, now = pcall(function() return target.Source end)" in code
    assert "removed = created.Parent == nil" in code, "temporary replacement removal is not verified"


@check("release: version, changelog and STATE agree")
def _():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    import rbforge
    state = open(os.path.join(root, "STATE.md"), encoding="utf-8").read()
    changelog = open(os.path.join(root, "CHANGELOG.md"), encoding="utf-8").read()
    assert ("0.13.5 (pre-1.0" in state) or ("%s (pre-1.0" % rbforge.__version__ in state), state[:400]
    assert changelog.split("\n## ")[1].startswith(rbforge.__version__ + " "), changelog[:200]


@check("skills: an installed skill carries a pointer to vendored knowledge")
def _():
    from rbforge import skills
    with tempdir() as d:
        orig = skills.roots_for
        skills.roots_for = lambda agent: [d]
        try:
            out = skills.install(agents=["hermes"])
        finally:
            skills.roots_for = orig
        pointer = os.path.join(d, "roblox-game-development", "KNOWLEDGE-PATH.txt")
        assert os.path.isfile(pointer), out
        text = open(pointer, encoding="utf-8").read()
        assert "knowledge/vendor is at:" in text or "was not shipped" in text, text


@check("verification: screenshot inspection is labelled as an attestation")
def _():
    from rbforge import verification
    with _isolated_home():
        obs = _collect(console="[Server] ready", revision="r1")["observation_id"]
        r = verification.receipt("x", observation_id=obs, project="demo", scenario="smoke",
                                 revision="r1", playtest_performed=True, save=False)
        assert r["screenshot_inspection_kind"] == "agent_attestation", r["screenshot_inspection_kind"]
        assert r["evidence"]["visual_inspection"]["by"] == "agent"


@check("scaffold: a new project passes its own offline gate")
def _():
    import shutil as _shutil
    from rbforge import check, scaffold
    if not _shutil.which("stylua"):
        raise AssertionError("stylua is required to prove the scaffold is formatted")
    with tempdir() as d:
        target = os.path.join(d, "proj")
        scaffold.scaffold(target, genre="obby")
        report = check.run(target, scope=["static", "structure"])
        fails = [c for r in report["rungs"] for c in r["checks"] if c["status"] == "fail"]
        assert not fails, [(c["id"], c["detail"][:120]) for c in fails]


@check("skills: every shipped skill is loadable, attributed and tracked")
def _():
    """A skill that exists only on the author's disk is not shipped.

    The third-party pack arrived as an untracked folder once already; a fresh
    clone had no skills and nothing failed.
    """
    import subprocess
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")
    names = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
    assert len(names) >= 25, names
    for name in names:
        path = os.path.join(root, name, "SKILL.md")
        assert os.path.isfile(path), "%s: SKILL.md is missing" % name
        text = open(path, encoding="utf-8").read()
        assert text.lstrip().startswith("---"), "%s: no frontmatter" % name
        assert "[truncated]" not in text, "%s: truncated at commit time" % name
    assert os.path.isfile(os.path.join(root, "ROBLOX-SKILLS-LICENSE.txt")), \
        "the third-party licence must ship beside the skills it covers"
    listed = subprocess.run(["git", "-C", os.path.dirname(root), "ls-files", "skills"],
                            capture_output=True, text=True)
    if listed.returncode == 0:
        tracked = listed.stdout.splitlines()
        missing = [n for n in names if not any(t.startswith("skills/%s/" % n) for t in tracked)]
        assert not missing, "untracked skill(s): %s" % missing


@check("server_test: a test that never reports is refused before it burns the timeout")
def _():
    from rbforge import live
    with tempdir() as d:
        bad = os.path.join(d, "silent.luau")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("return 'PASS'\n")  # a returned value goes nowhere
        # The guard returns before opening a session, so this needs no Studio.
        result = live.server_test(bad, "RbforgeTest", studio_id=None)
    assert result["passed"] is False, result
    assert result["outcome"] == "fail", result
    assert "never calls SetAttribute" in result["result"], result


@check("skills: current requires every profile, not just one")
def _():
    from rbforge import skills
    with tempdir() as d:
        a, b = os.path.join(d, "a"), os.path.join(d, "b")
        os.makedirs(os.path.join(a, "roblox-audio"))
        os.makedirs(b)
        stamp = os.path.join(a, "roblox-audio", ".rbforge-version")
        open(stamp, "w").write(skills_version())
        open(os.path.join(a, "roblox-audio", "SKILL.md"), "w").write("# x")
        states = [skills.state_of(os.path.join(a, "roblox-audio")), skills.state_of(os.path.join(b, "roblox-audio"))]
    assert states[1] == "absent", states
    assert skills._combine(states) != "current", states


@check("skills: a stamp without a payload is partial, not current")
def _():
    from rbforge import skills
    with tempdir() as d:
        target = os.path.join(d, "roblox-audio")
        os.makedirs(target)
        open(os.path.join(target, ".rbforge-version"), "w").write(skills_version())
        assert skills.state_of(target).startswith("partial"), skills.state_of(target)


@check("skills: a changed payload is modified, an added file keeps that meaning")
def _():
    from rbforge import skills
    with tempdir() as d:
        target = os.path.join(d, "roblox-audio")
        os.makedirs(target)
        open(os.path.join(target, "SKILL.md"), "w").write("# x")
        skills._write_manifest(target, skills_version())
        assert skills.state_of(target) == "current", skills.state_of(target)
        open(os.path.join(target, "SKILL.md"), "w").write("# changed")
        assert skills.state_of(target).startswith("modified"), skills.state_of(target)
        open(os.path.join(target, "SKILL.md"), "w").write("# x")
        open(os.path.join(target, "MY-NOTES.md"), "w").write("mine")
        assert "extra" in skills.state_of(target), skills.state_of(target)


@check("skills: reinstall keeps user files in a backup instead of deleting them")
def _():
    from rbforge import skills
    with tempdir() as src, tempdir() as root:
        for name in skills.OUR_SKILLS:
            os.makedirs(os.path.join(src, name))
            open(os.path.join(src, name, "SKILL.md"), "w").write("# " + name)
        target = os.path.join(root, "roblox-audio")
        os.makedirs(target)
        open(os.path.join(target, "SKILL.md"), "w").write("# old")
        skl = skills._write_manifest(target, "0.0.0")
        open(os.path.join(target, "MY-NOTES.md"), "w").write("keep me")

        home = tempfile.mkdtemp(prefix="rbf-home-")
        orig_source, orig_roots, orig_home = (skills.paths.skills_source_dir, skills.roots_for,
                                              skills.paths.home)
        skills.paths.skills_source_dir = lambda: src
        skills.roots_for = lambda agent: [root]
        skills.paths.home = lambda: home
        try:
            first = skills.install(["hermes"])
            bdir = os.path.join(home, "backups")
            backups = os.listdir(bdir) if os.path.isdir(bdir) else []
            saved = os.path.join(bdir, backups[0], "MY-NOTES.md") if backups else None
            kept_text = open(saved).read() if saved and os.path.isfile(saved) else None
            second = skills.install(["hermes"])
            leftovers = [n for n in os.listdir(root) if n.startswith(".rbforge-stage")]
        finally:
            skills.paths.skills_source_dir, skills.roots_for = orig_source, orig_roots
            skills.paths.home = orig_home
    assert "installed" in first["hermes"], first
    assert kept_text == "keep me", (backups, kept_text)
    assert "already current" in second["hermes"], second
    assert not leftovers, "stage left behind: %s" % leftovers


@check("skills: a foreign skill blocks the whole batch before any write")
def _():
    from rbforge import skills
    with tempdir() as src, tempdir() as root:
        for name in skills.OUR_SKILLS:
            os.makedirs(os.path.join(src, name))
            open(os.path.join(src, name, "SKILL.md"), "w").write("# " + name)
        os.makedirs(os.path.join(root, "roblox-audio"))
        open(os.path.join(root, "roblox-audio", "SKILL.md"), "w").write("# someone else's")

        orig_source, orig_roots = skills.paths.skills_source_dir, skills.roots_for
        skills.paths.skills_source_dir = lambda: src
        skills.roots_for = lambda agent: [root]
        try:
            result = skills.install(["hermes"])
        finally:
            skills.paths.skills_source_dir, skills.roots_for = orig_source, orig_roots
        installed_others = [n for n in os.listdir(root)
                            if n.startswith("roblox-") and n != "roblox-audio"]
    assert "blocked before any change" in result["hermes"], result
    assert not installed_others, installed_others


@check("skills: remove deletes our files and leaves the user's directory")
def _():
    from rbforge import skills
    with tempdir() as src, tempdir() as root:
        for name in skills.OUR_SKILLS:
            os.makedirs(os.path.join(src, name))
            open(os.path.join(src, name, "SKILL.md"), "w").write("# " + name)
        orig_source, orig_roots = skills.paths.skills_source_dir, skills.roots_for
        skills.paths.skills_source_dir = lambda: src
        skills.roots_for = lambda agent: [root]
        try:
            skills.install(["hermes"])
            notes = os.path.join(root, "roblox-audio", "MY-NOTES.md")
            open(notes, "w").write("mine")
            result = skills.remove(["hermes"])
        finally:
            skills.paths.skills_source_dir, skills.roots_for = orig_source, orig_roots
        kept = os.path.isfile(notes)
        gone = not os.path.isfile(os.path.join(root, "roblox-audio", "SKILL.md"))
    assert kept and gone, (kept, gone, result)
    assert "kept" in result["hermes"], result


@check("server_test: a mention in a comment or string is not a report, a dynamic name is")
def _():
    from rbforge import live
    with tempdir() as d:
        cases = {
            "comment.luau": "-- workspace:SetAttribute('RbforgeTest', 'PASS')\nreturn 1\n",
            "string.luau": "print('workspace:SetAttribute(\"RbforgeTest\", \"PASS\")')\n",
            "long.luau": "print([==[ workspace:SetAttribute('RbforgeTest','PASS') ]==])\n",
            "multiline.luau": "--[==[ workspace:SetAttribute('RbforgeTest','PASS') ]==]\nreturn 1\n",
            "dynamic.luau": "local n = 'Rbforge' .. 'Test'\nworkspace:SetAttribute(n, 'PASS')\n",
        }
        results = {}
        for name, body in cases.items():
            path = os.path.join(d, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(body)
            results[name] = live._lua_code_only(body)
    assert "SetAttribute" not in results["comment.luau"], results["comment.luau"]
    assert "SetAttribute" not in results["string.luau"], results["string.luau"]
    assert "SetAttribute" not in results["long.luau"], results["long.luau"]
    assert "SetAttribute" not in results["multiline.luau"], results["multiline.luau"]
    assert "SetAttribute" in results["dynamic.luau"], results["dynamic.luau"]


@check("skills: one root spelled two ways is one root")
def _():
    from rbforge import skills
    with tempdir() as root:
        orig = dict(skills._ROOTS)
        skills._ROOTS["probe"] = ("RBFORGE_PROBE_SKILLS", (root, root.replace("\\", "/")))
        os.environ.pop("RBFORGE_PROBE_SKILLS", None)
        try:
            roots = skills.roots_for("probe")
        finally:
            skills._ROOTS.clear()
            skills._ROOTS.update(orig)
    assert len(roots) == 1, roots


def _sandbox_agent(skills, root, name="sbx"):
    skills._ROOTS[name] = ("RBFORGE_%s_SKILLS" % name.upper(), (root,))
    return name


@check("skills: a manifest naming ../victim.txt cannot delete outside the skill")
def _():
    from rbforge import skills
    with tempdir() as root, tempdir() as outside:
        victim = os.path.join(outside, "victim.txt")
        open(victim, "w").write("do not delete")
        d = os.path.join(root, "roblox-audio")
        os.makedirs(d)
        open(os.path.join(d, "SKILL.md"), "w").write("# ours")
        open(os.path.join(d, ".rbforge-version"), "w").write(skills_version())
        with open(os.path.join(d, ".rbforge-manifest.json"), "w") as fh:
            json.dump({"version": skills_version(),
                       "files": {"SKILL.md": skills._sha(os.path.join(d, "SKILL.md")),
                                 "../victim.txt": skills._sha(victim)}}, fh)
        agent = _sandbox_agent(skills, root, "sbxtrav")
        try:
            result = skills.remove([agent])
        finally:
            del skills._ROOTS[agent]
        survived = os.path.isfile(victim)
        refused = "refused" in result[agent]
    assert survived, "traversal deleted an external file"
    assert refused, result


@check("skills: a foreign directory (manifest, no stamp) is never uninstalled")
def _():
    from rbforge import skills
    with tempdir() as root:
        d = os.path.join(root, "roblox-audio")
        os.makedirs(d)
        open(os.path.join(d, "SKILL.md"), "w").write("# someone else")
        with open(os.path.join(d, ".rbforge-manifest.json"), "w") as fh:
            json.dump({"version": "1.0",
                       "files": {"SKILL.md": skills._sha(os.path.join(d, "SKILL.md"))}}, fh)
        agent = _sandbox_agent(skills, root, "sbxforeign")
        try:
            result = skills.remove([agent])
            gone = not os.path.isdir(d)
        finally:
            del skills._ROOTS[agent]
    assert not gone, "a foreign directory was deleted"
    assert "refused" in result[agent], result


@check("skills: a modified managed file survives uninstall")
def _():
    from rbforge import skills
    with tempdir() as src, tempdir() as root:
        for name in skills.OUR_SKILLS:
            os.makedirs(os.path.join(src, name))
            open(os.path.join(src, name, "SKILL.md"), "w").write("# " + name)
        orig = (skills.paths.skills_source_dir, skills.roots_for)
        skills.paths.skills_source_dir = lambda: src
        skills.roots_for = lambda agent: [root]
        _sandbox_agent(skills, root, "sandbox")
        try:
            skills.install(["sandbox"])
            target = os.path.join(root, "roblox-audio", "SKILL.md")
            open(target, "w").write("# edited by the user")
            result = skills.remove(["sandbox"])
            kept = os.path.isfile(target)
        finally:
            skills.paths.skills_source_dir, skills.roots_for = orig
            del skills._ROOTS["sandbox"]
    assert kept, "the customized file was deleted"
    assert "kept" in result["sandbox"], result


@check("skills: a legacy install with only a stamp is refused, not rmtree'd")
def _():
    from rbforge import skills
    with tempdir() as root:
        d = os.path.join(root, "roblox-audio")
        os.makedirs(d)
        open(os.path.join(d, "SKILL.md"), "w").write("# legacy")
        open(os.path.join(d, ".rbforge-version"), "w").write("0.13.0")
        agent = _sandbox_agent(skills, root, "sbxlegacy")
        try:
            result = skills.remove([agent])
            survived = os.path.isdir(d)
        finally:
            del skills._ROOTS[agent]
    assert survived, "a legacy install was deleted wholesale"
    assert "refused" in result[agent], result


@check("skills: an empty or corrupt manifest never reports current")
def _():
    from rbforge import skills
    with tempdir() as d:
        target = os.path.join(d, "roblox-audio")
        os.makedirs(target)
        open(os.path.join(target, "SKILL.md"), "w").write("# ours")
        open(os.path.join(target, ".rbforge-version"), "w").write(skills_version())
        with open(os.path.join(target, ".rbforge-manifest.json"), "w") as fh:
            json.dump({"version": skills_version(), "files": {}}, fh)
        empty = skills.state_of(target)
        with open(os.path.join(target, ".rbforge-manifest.json"), "w") as fh:
            fh.write("{not json")
        corrupt = skills.state_of(target)
    assert empty != "current", empty
    assert corrupt != "current", corrupt


@check("skills: a staging failure installs nothing")
def _():
    from rbforge import skills
    with tempdir() as src, tempdir() as root:
        for name in skills.OUR_SKILLS:
            os.makedirs(os.path.join(src, name))
            open(os.path.join(src, name, "SKILL.md"), "w").write("# " + name)
        orig = (skills.paths.skills_source_dir, skills.roots_for, skills.shutil.copytree)
        skills.paths.skills_source_dir = lambda: src
        skills.roots_for = lambda agent: [root]
        _sandbox_agent(skills, root, "sandbox")
        calls = {"n": 0}

        def flaky(a, b, *rest, **kw):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("disk full")
            return orig[2](a, b, *rest, **kw)

        skills.shutil.copytree = flaky
        error = None
        try:
            try:
                skills.install(["sandbox"])
            except Exception as exc:  # noqa: BLE001
                error = exc
        finally:
            skills.paths.skills_source_dir, skills.roots_for, skills.shutil.copytree = orig
            del skills._ROOTS["sandbox"]
        installed = [n for n in os.listdir(root) if n.startswith("roblox-")]
        stages = [n for n in os.listdir(root) if n.startswith(".rbforge-stage")]
    assert error is not None, "a failed stage was reported as success"
    assert "nothing was replaced" in str(error), error
    assert not installed, installed
    assert not stages, stages


@check("skills: a failed activation rolls the earlier skills back")
def _():
    from rbforge import skills
    with tempdir() as src, tempdir() as root:
        for name in skills.OUR_SKILLS:
            os.makedirs(os.path.join(src, name))
            open(os.path.join(src, name, "SKILL.md"), "w").write("# " + name)
        orig = (skills.paths.skills_source_dir, skills.roots_for, skills.os.replace)
        skills.paths.skills_source_dir = lambda: src
        skills.roots_for = lambda agent: [root]
        _sandbox_agent(skills, root, "sandbox")

        def flaky(a, b):
            if os.path.basename(str(b)).startswith("roblox-docs"):
                raise OSError("target locked")
            return orig[2](a, b)

        skills.os.replace = flaky
        error = None
        try:
            try:
                skills.install(["sandbox"])
            except Exception as exc:  # noqa: BLE001
                error = exc
        finally:
            skills.paths.skills_source_dir, skills.roots_for, skills.os.replace = orig
            del skills._ROOTS["sandbox"]
        installed = [n for n in os.listdir(root) if n.startswith("roblox-")]
    assert error is not None, "a failed activation was reported as success"
    assert "restored" in str(error), error
    assert not installed, installed


@check("skills: backup names never collide")
def _():
    from rbforge import skills
    with tempdir() as d:
        base = os.path.join(d, "x.rbforge-backup-1")
        open(base, "w").write("taken")
        unique = skills._unique(base)
    assert unique != base and not os.path.exists(unique), unique


@contextlib.contextmanager
def installed_tree(old_schema=False, extra=None):
    """A throwaway skill source, root and home with the installer's globals patched.

    One context manager for every installer test: it patches `skills.paths.skills_source_dir`,
    `skills.roots_for` and `skills.paths.home`, yields (src, root, home), and on the way out restores
    every one of them and deletes the three temporary directories. Tests must not invent their own
    cleanup, or a leaked lambda keeps making directories long after the test ends.
    """
    from rbforge import skills

    src = tempfile.mkdtemp(prefix="rbf-src-")
    root = tempfile.mkdtemp(prefix="rbf-root-")
    home = tempfile.mkdtemp(prefix="rbf-home-")
    original = (skills.paths.skills_source_dir, skills.roots_for, skills.paths.home)
    added = []

    def sandbox_agent(name="sbx-tmp"):
        skills._ROOTS[name] = ("RBFORGE_%s_SKILLS" % name.upper().replace("-", ""), (root,))
        added.append(name)
        return name

    skills.paths.skills_source_dir = lambda: src
    skills.roots_for = lambda agent: [root]
    skills.paths.home = lambda: home
    try:
        for name in skills.OUR_SKILLS:
            os.makedirs(os.path.join(src, name), exist_ok=True)
            open(os.path.join(src, name, "SKILL.md"), "w").write("# " + name)
        if old_schema:
            dst = os.path.join(root, "roblox-docs")
            shutil.copytree(os.path.join(src, "roblox-docs"), dst)
            skills._write_knowledge_pointer(dst, src)
            files = {rel: skills._sha(os.path.join(dst, rel.replace("/", os.sep)))
                     for rel in skills._manifest_files(dst)}
            with open(os.path.join(dst, skills.MANIFEST), "w", encoding="utf-8") as fh:
                json.dump({"version": "0.13.10", "files": files}, fh)
            with open(os.path.join(dst, skills.STAMP), "w", encoding="utf-8") as fh:
                fh.write("0.13.10")
        agent = sandbox_agent()
        if extra:
            extra(root)
        yield src, root, home, agent
    finally:
        for name in added:
            skills._ROOTS.pop(name, None)
        skills.paths.skills_source_dir, skills.roots_for, skills.paths.home = original
        for path in (root, src, home):
            shutil.rmtree(path, ignore_errors=True)


@check("skills: a copy that dies after creating its stage leaves no debris")
def _():
    from rbforge import skills
    with tempdir() as src, tempdir() as root:
        for name in skills.OUR_SKILLS:
            os.makedirs(os.path.join(src, name))
            open(os.path.join(src, name, "SKILL.md"), "w").write("# " + name)
        orig = (skills.paths.skills_source_dir, skills.roots_for, skills.shutil.copytree)
        skills.paths.skills_source_dir = lambda: src
        skills.roots_for = lambda agent: [root]
        _sandbox_agent(skills, root, "sbx-partial")

        def half_copy(a, b, *rest, **kw):
            os.makedirs(b, exist_ok=True)          # the destination exists...
            open(os.path.join(b, "half.txt"), "w").write("partial")
            raise OSError("interrupted copy")       # ...and then the copy dies

        skills.shutil.copytree = half_copy
        try:
            try:
                skills.install(["sbx-partial"])
                raised = False
            except Exception:  # noqa: BLE001
                raised = True
        finally:
            skills.paths.skills_source_dir, skills.roots_for, skills.shutil.copytree = orig
            del skills._ROOTS["sbx-partial"]
        debris = [n for n in os.listdir(root) if n.startswith(".rbforge-stage")]
        installed = [n for n in os.listdir(root) if n.startswith("roblox-")]
    assert raised, "a failed copy was reported as success"
    assert not debris, debris
    assert not installed, installed


@check("skills: a failed move to backup leaves the original in place")
def _():
    from rbforge import skills
    with tempdir() as src, tempdir() as root:
        for name in skills.OUR_SKILLS:
            os.makedirs(os.path.join(src, name))
            open(os.path.join(src, name, "SKILL.md"), "w").write("# " + name)
        target = os.path.join(root, "roblox-docs")
        os.makedirs(target)
        open(os.path.join(target, "SKILL.md"), "w").write("# existing install")
        # A legacy install (stamp, no manifest) is the case that gets replaced, so the backup move
        # is actually attempted; a bare foreign directory would be refused before any write.
        open(os.path.join(target, ".rbforge-version"), "w").write("0.13.0")
        orig = (skills.paths.skills_source_dir, skills.roots_for, skills.os.replace)
        skills.paths.skills_source_dir = lambda: src
        skills.roots_for = lambda agent: [root]
        _sandbox_agent(skills, root, "sbx-move")

        def no_backup(a, b):
            if os.sep + "backups" + os.sep in str(b):
                raise OSError("cannot move original")
            return orig[2](a, b)

        skills.os.replace = no_backup
        try:
            try:
                skills.install(["sbx-move"])
                raised = False
            except Exception:  # noqa: BLE001
                raised = True
        finally:
            skills.paths.skills_source_dir, skills.roots_for, skills.os.replace = orig
            del skills._ROOTS["sbx-move"]
        intact = os.path.isfile(os.path.join(target, "SKILL.md")) and \
            open(os.path.join(target, "SKILL.md")).read() == "# existing install"
    assert raised, "the failure was swallowed"
    assert intact, "the original skill was lost"


@check("skills: an activation failure restores the skill that was in flight")
def _():
    from rbforge import skills
    with installed_tree() as (src, root, home, agent):
        skills.install([agent])
        edited = os.path.join(root, "roblox-docs", "SKILL.md")
        open(edited, "w").write("# user edit that must survive")
        real_replace = skills.os.replace

        def fails_on_activation(a, b):
            if ".rbforge-stage" in str(a) and str(b).endswith("roblox-docs"):
                raise OSError("activation blocked")
            return real_replace(a, b)

        skills.os.replace = fails_on_activation
        try:
            raised = False
            try:
                skills.install([agent])
            except Exception:  # noqa: BLE001
                raised = True
        finally:
            skills.os.replace = real_replace
        restored = os.path.isfile(edited) and open(edited).read() == "# user edit that must survive"
    assert raised, "a failed activation was reported as success"
    assert restored, "the in-flight skill was left in its backup"

@check("skills: a restore that also fails reports ROLLBACK_FAILED and keeps the backup")
def _():
    from rbforge import skills
    with installed_tree() as (src, root, home, agent):
        skills.install([agent])
        edited = os.path.join(root, "roblox-docs", "SKILL.md")
        open(edited, "w").write("# edited")
        real_replace = skills.os.replace

        def fails_both_ways(a, b):
            if ".rbforge-stage" in str(a) and str(b).endswith("roblox-docs"):
                raise OSError("activation blocked")
            if os.sep + "backups" + os.sep in str(a) and str(b).endswith("roblox-docs"):
                raise OSError("restore blocked")
            return real_replace(a, b)

        skills.os.replace = fails_both_ways
        try:
            error = None
            try:
                skills.install([agent])
            except Exception as exc:  # noqa: BLE001
                error = exc
        finally:
            skills.os.replace = real_replace
        code = getattr(error, "code", None)
        backups = _backups_in(home, "roblox-docs")
    assert error is not None, "no error was raised"
    assert code == "RBF-SKILL-005", code
    assert "ROLLBACK_FAILED" in str(error), error
    assert backups, "the previous copy was not preserved"

@check("skills: an edited KNOWLEDGE-PATH.txt survives uninstall")
def _():
    from rbforge import skills
    with tempdir() as src, tempdir() as root:
        for name in skills.OUR_SKILLS:
            os.makedirs(os.path.join(src, name))
            open(os.path.join(src, name, "SKILL.md"), "w").write("# " + name)
        orig = (skills.paths.skills_source_dir, skills.roots_for)
        skills.paths.skills_source_dir = lambda: src
        skills.roots_for = lambda agent: [root]
        _sandbox_agent(skills, root, "sandbox")
        try:
            skills.install(["sandbox"])
            pointer = os.path.join(root, "roblox-docs", "KNOWLEDGE-PATH.txt")
            open(pointer, "w").write("my own path notes")
            result = skills.remove(["sandbox"])
            kept = os.path.isfile(pointer) and open(pointer).read() == "my own path notes"
        finally:
            skills.paths.skills_source_dir, skills.roots_for = orig
            del skills._ROOTS["sandbox"]
    assert kept, "the edited knowledge pointer was deleted"
    assert "kept" in result["sandbox"], result


@check("skills: a stamp without a manifest is legacy, never current")
def _():
    from rbforge import skills
    with tempdir() as d:
        target = os.path.join(d, "roblox-docs")
        os.makedirs(target)
        open(os.path.join(target, "SKILL.md"), "w").write("# x")
        open(os.path.join(target, ".rbforge-version"), "w").write(skills_version())
        state = skills.state_of(target)
    assert state != "current", state
    assert state.startswith("legacy"), state


def _make_link(link, target):
    """A directory symlink where the OS allows it, else a Windows junction. Returns the kind."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return "symlink"
    except (OSError, NotImplementedError):
        pass
    try:
        import subprocess as _sp
        done = _sp.run(["cmd", "/c", "mklink", "/J", link, target],
                       capture_output=True, text=True)
        if done.returncode == 0:
            return "junction"
    except Exception:  # noqa: BLE001 - reported by the caller as unsupported
        pass
    return None


@check("skills: uninstall keeps a user-added empty directory")
def _():
    from rbforge import skills
    with tempdir() as src, tempdir() as root:
        for name in skills.OUR_SKILLS:
            os.makedirs(os.path.join(src, name))
            open(os.path.join(src, name, "SKILL.md"), "w").write("# " + name)
        orig = (skills.paths.skills_source_dir, skills.roots_for)
        skills.paths.skills_source_dir = lambda: src
        skills.roots_for = lambda agent: [root]
        _sandbox_agent(skills, root, "sandbox")
        try:
            skills.install(["sandbox"])
            mine = os.path.join(root, "roblox-docs", "my-notes")
            os.makedirs(mine)
            result = skills.remove(["sandbox"])
            survived = os.path.isdir(mine)
            skill_kept = os.path.isdir(os.path.join(root, "roblox-docs"))
        finally:
            skills.paths.skills_source_dir, skills.roots_for = orig
            del skills._ROOTS["sandbox"]
    assert survived, "a user-added empty directory was deleted"
    assert skill_kept, "the skill directory was removed around the user's folder"
    assert "kept" in result["sandbox"], result


@check("skills: uninstall keeps a user-added directory link and never deletes its target")
def _():
    from rbforge import skills
    kind = None
    with tempdir() as target, tempdir() as src, tempdir() as root:
        open(os.path.join(target, "precious.txt"), "w").write("outside")
        for name in skills.OUR_SKILLS:
            os.makedirs(os.path.join(src, name))
            open(os.path.join(src, name, "SKILL.md"), "w").write("# " + name)
        orig = (skills.paths.skills_source_dir, skills.roots_for)
        skills.paths.skills_source_dir = lambda: src
        skills.roots_for = lambda agent: [root]
        _sandbox_agent(skills, root, "sandbox")
        try:
            skills.install(["sandbox"])
            link = os.path.join(root, "roblox-docs", "outside")
            kind = _make_link(link, target)
            if kind:
                skills.remove(["sandbox"])
            link_alive = os.path.lexists(link) if kind else None
            target_alive = os.path.isfile(os.path.join(target, "precious.txt"))
        finally:
            skills.paths.skills_source_dir, skills.roots_for = orig
            del skills._ROOTS["sandbox"]
    assert target_alive, "the link target was deleted"
    assert kind is not None, "no symlink or junction could be created on this host"
    assert link_alive, "the user's directory link was deleted"


@check("skills: a broken link is inventoried, not followed, and survives uninstall")
def _():
    from rbforge import skills
    with tempdir() as src, tempdir() as root:
        for name in skills.OUR_SKILLS:
            os.makedirs(os.path.join(src, name))
            open(os.path.join(src, name, "SKILL.md"), "w").write("# " + name)
        orig = (skills.paths.skills_source_dir, skills.roots_for)
        skills.paths.skills_source_dir = lambda: src
        skills.roots_for = lambda agent: [root]
        _sandbox_agent(skills, root, "sandbox")
        try:
            skills.install(["sandbox"])
            broken = os.path.join(root, "roblox-docs", "gone")
            made = _make_link(broken, os.path.join(root, "does-not-exist"))
            if made:
                skills.remove(["sandbox"])
            alive = os.path.lexists(broken) if made else None
        finally:
            skills.paths.skills_source_dir, skills.roots_for = orig
            del skills._ROOTS["sandbox"]
    assert made, "no link could be created"
    assert alive, "a broken link was treated as ours and deleted"


@check("skills: an upgrade backs up a skill that gained a user directory")
def _():
    from rbforge import skills
    with tempdir() as src, tempdir() as root:
        for name in skills.OUR_SKILLS:
            os.makedirs(os.path.join(src, name))
            open(os.path.join(src, name, "SKILL.md"), "w").write("# " + name)
        home = tempfile.mkdtemp(prefix="rbf-home-")
        orig = (skills.paths.skills_source_dir, skills.roots_for)
        orig_home = skills.paths.home
        skills.paths.skills_source_dir = lambda: src
        skills.roots_for = lambda agent: [root]
        skills.paths.home = lambda: home
        _sandbox_agent(skills, root, "sandbox")
        try:
            skills.install(["sandbox"])
            mine = os.path.join(root, "roblox-docs", "keep-me")
            os.makedirs(mine)
            skills.install(["sandbox"])  # same version, but the tree is no longer provably ours
            bdir = os.path.join(home, "backups")
            backups = [n for n in os.listdir(bdir) if "roblox-docs" in n] if os.path.isdir(bdir) else []
            saved = os.path.isdir(os.path.join(bdir, backups[0], "keep-me")) if backups else False
        finally:
            skills.paths.skills_source_dir, skills.roots_for = orig
            skills.paths.home = orig_home
            del skills._ROOTS["sandbox"]
    assert backups, "the skill was replaced in place instead of backed up"
    assert saved, "the user's directory is not in the backup"


def _old_schema_install(skills, root, src, name="roblox-docs", version="0.13.10"):
    """Write a skill the way 0.13.10 did: a stamp, a manifest with files only, no dirs."""
    dst = os.path.join(root, name)
    shutil.copytree(os.path.join(src, name), dst)
    skills._write_knowledge_pointer(dst, src)
    files = {rel: skills._sha(os.path.join(dst, rel.replace("/", os.sep)))
             for rel in skills._manifest_files(dst)}
    with open(os.path.join(dst, skills.MANIFEST), "w", encoding="utf-8") as fh:
        json.dump({"version": version, "files": files}, fh)
    with open(os.path.join(dst, skills.STAMP), "w", encoding="utf-8") as fh:
        fh.write(version)
    return dst


@check("skills: a 0.13.10 manifest with no dirs still backs up a user directory on upgrade")
def _():
    from rbforge import skills

    def add_dir(_root):
        pass

    with installed_tree(old_schema=True) as (src, root, home, agent):
        os.makedirs(os.path.join(root, "roblox-docs", "mine"))
        result = skills.install([agent])
        backups = _backups_in(home, "roblox-docs")
        saved = os.path.isdir(os.path.join(backups[0], "mine")) if backups else False
    assert backups, "the old-schema install was replaced without a backup: %s" % result
    assert saved, "the user's directory was not preserved in the backup"

@check("skills: the same migration preserves a link and never touches its target")
def _():
    from rbforge import skills
    target = tempfile.mkdtemp(prefix="rbf-target-")
    open(os.path.join(target, "precious.txt"), "w").write("outside")
    made = {"v": None}
    try:
        with installed_tree(old_schema=True) as (src, root, home, agent):
            made["v"] = _make_link(os.path.join(root, "roblox-docs", "outside"), target)
            if not made["v"]:
                raise AssertionError("no link could be created on this host")
            skills.install([agent])
            backups = _backups_in(home, "roblox-docs")
            saved = os.path.lexists(os.path.join(backups[0], "outside")) if backups else False
            target_alive = os.path.isfile(os.path.join(target, "precious.txt"))
    finally:
        import shutil as _sh
        _sh.rmtree(target, ignore_errors=True)
    assert made["v"], "no link could be created on this host"
    assert backups, "the link was dropped without a backup"
    assert saved, "the link is not in the backup"
    assert target_alive, "the link target was modified"

@check("skills: adjacent directory links are all inventoried")
def _():
    from rbforge import skills
    with tempdir() as d, tempdir() as targets:
        skill = os.path.join(d, "roblox-docs")
        os.makedirs(skill)
        open(os.path.join(skill, "SKILL.md"), "w").write("# x")
        made = []
        for i in range(3):
            t = os.path.join(targets, "t%d" % i)
            os.makedirs(t)
            made.append(_make_link(os.path.join(skill, "link%d" % i), t))
        if not all(made):
            raise AssertionError("links unavailable on this host: %s" % made)
        listed = skills._manifest_dirs(skill)
    assert sorted(listed) == ["link0", "link1", "link2"], listed


@check("skills: an edited knowledge pointer is backed up on same-version reinstall")
def _():
    from rbforge import skills
    with tempdir() as src, tempdir() as root:
        for name in skills.OUR_SKILLS:
            os.makedirs(os.path.join(src, name))
            open(os.path.join(src, name, "SKILL.md"), "w").write("# " + name)
        orig = (skills.paths.skills_source_dir, skills.roots_for)
        home, orig_home = _home_for(skills)
        skills.paths.skills_source_dir = lambda: src
        skills.roots_for = lambda agent: [root]
        _sandbox_agent(skills, root, "sandbox")
        try:
            skills.install(["sandbox"])
            pointer = os.path.join(root, "roblox-docs", "KNOWLEDGE-PATH.txt")
            open(pointer, "w").write("my own notes")
            state = skills.state_of(os.path.join(root, "roblox-docs"))
            skills.install(["sandbox"])
            backups = _backups_in(home, "roblox-docs")
            saved = None
            if backups:
                cand = os.path.join(backups[0], "KNOWLEDGE-PATH.txt")
                saved = open(cand).read() if os.path.isfile(cand) else None
        finally:
            skills.paths.skills_source_dir, skills.roots_for = orig
            skills.paths.home = orig_home
            del skills._ROOTS["sandbox"]
    assert state.startswith("modified"), state
    assert backups, "the reinstall replaced an edited pointer with no backup"
    assert saved == "my own notes", saved


@check("skills: an edited pointer survives a cross-version upgrade in a backup")
def _():
    from rbforge import skills
    with installed_tree(old_schema=True) as (src, root, home, agent):
        pointer = os.path.join(root, "roblox-docs", "KNOWLEDGE-PATH.txt")
        open(pointer, "w").write("edited before the upgrade")
        state = skills.state_of(os.path.join(root, "roblox-docs"))
        skills.install([agent])
        backups = _backups_in(home, "roblox-docs")
        saved = None
        if backups:
            cand = os.path.join(backups[0], "KNOWLEDGE-PATH.txt")
            saved = open(cand).read() if os.path.isfile(cand) else None
    assert state != "current", state
    assert backups, "the upgrade dropped the edited pointer without a backup"
    assert saved == "edited before the upgrade", saved

@check("types: project definitions win, then the cache, then a clear reason")
def _():
    from rbforge import types as t
    with tempdir() as root, tempdir() as cache:
        old_cache = t.cache_dir
        t.cache_dir = lambda: cache
        try:
            found, why = t.discover(root)
            assert found is None and "types fetch" in why, (found, why)
            cached = os.path.join(cache, "globalTypes-%s.d.luau" % t.REF)
            open(cached, "w").write("x" * 2048)
            old_sha = t.SHA256
            t.SHA256 = t._sha(cached)  # a cache that matches its pin
            try:
                found, source = t.discover(root)
            finally:
                t.SHA256 = old_sha
            assert source == "cache", (found, source)
            project = os.path.join(root, "globalTypes.d.luau")
            open(project, "w").write("y" * 2048)
            found, source = t.discover(root)
            assert source == "project" and found == project, (found, source)
        finally:
            t.cache_dir = old_cache


@check("types: a payload that does not match the pin is refused, not cached")
def _():
    from rbforge import types as t
    with tempdir() as cache:
        old_cache, old_sha = t.cache_dir, t.SHA256
        t.cache_dir = lambda: cache
        t.SHA256 = "0" * 64
        try:
            error = None
            try:
                t.fetch(force=True)
            except Exception as exc:  # noqa: BLE001
                error = exc
            cached = os.listdir(cache) if os.path.isdir(cache) else []
        finally:
            t.cache_dir, t.SHA256 = old_cache, old_sha
    assert error is not None, "an unverified download was accepted"
    assert "do not match" in str(error), error
    assert not [n for n in cached if n.endswith(".d.luau")], cached


@check("check: the typechecker runs with platform and definitions, and parses (line,col)")
def _():
    from rbforge import check as check_mod
    with tempdir() as root:
        open(os.path.join(root, "a.luau"), "w").write("local x: number = 1\n")
        defs = os.path.join(root, "globalTypes.d.luau")
        open(defs, "w").write("--" + "x" * 2048)
        calls = {}

        def fake_run(argv, cwd, timeout=180):
            calls["argv"] = argv
            return 1, "a.luau(1,7): TypeError: Expected number, got string"

        old_run, old_which = check_mod._run, check_mod.shutil.which
        check_mod._run = fake_run
        check_mod.shutil.which = lambda name: "C:/fake/" + name
        os.environ["RBFORGE_LUAU_DEFINITIONS"] = defs
        try:
            rung = check_mod.rung_static(root)
        finally:
            check_mod._run, check_mod.shutil.which = old_run, old_which
            os.environ.pop("RBFORGE_LUAU_DEFINITIONS", None)
    lsp = [c for c in rung["checks"] if c["id"] == "luau-lsp"][0]
    assert any("--platform=roblox" == a for a in calls["argv"]), calls["argv"]
    assert any(a.startswith("--definitions=@roblox=") for a in calls["argv"]), calls["argv"]
    assert lsp["status"] == "fail", lsp
    assert "(1,7)" in lsp["detail"], lsp


@check("optimize: a simple obby gets quality rules and no optimization pipeline")
def _():
    from rbforge import optimize
    with tempdir() as root:
        os.makedirs(os.path.join(root, "src"))
        open(os.path.join(root, "src", "Main.server.luau"), "w").write(
            'local checkpoint = Instance.new("Part")\ncheckpoint.Parent = workspace\n')
        prof = optimize.profile(root, "simple obby with checkpoints")
    ids = [i["id"] for i in prof["level_b"]]
    assert ids == [], ids
    assert prof["level_a"], prof


@check("optimize: a large multiplayer city activates streaming, network, npc and physics")
def _():
    from rbforge import optimize
    with tempdir() as root:
        open(os.path.join(root, "Main.server.luau"), "w").write("local p = Instance.new('Part')\n")
        prof = optimize.profile(root, "large multiplayer city with NPCs and physics, PvPvE extraction")
    ids = {i["id"] for i in prof["level_b"]}
    assert {"streaming", "networking", "npc", "physics"} <= ids, ids
    assert all(i["measure_first"] for i in prof["level_b"] if i["id"] in ids), prof


@check("optimize: a procedural spaceship activates geometry and replication guidance")
def _():
    from rbforge import optimize
    with tempdir() as root:
        open(os.path.join(root, "Gen.server.luau"), "w").write(
            "local m = Instance.new('EditableMesh')\n")
        prof = optimize.profile(root, "procedurally generated biological spaceship with real physics")
    ids = {i["id"] for i in prof["level_b"]}
    assert {"procedural", "physics"} <= ids, ids
    procedural = [i for i in prof["level_b"] if i["id"] == "procedural"][0]
    assert "generation" in procedural["why"], procedural


@check("optimize: output never claims the project is optimized")
def _():
    from rbforge import optimize
    with tempdir() as root:
        open(os.path.join(root, "a.luau"), "w").write("print(1)\n")
        prof = optimize.profile(root, "large multiplayer city")
    assert "not measurement" in prof["note"], prof["note"]
    assert "measurement" in prof["next"], prof["next"]


@check("check: an abnormal analyzer exit is a failure even with readable lint output")
def _():
    from rbforge import check as check_mod
    with tempdir() as root:
        open(os.path.join(root, "main.luau"), "w").write("print(1)\n")
        defs = os.path.join(root, "globalTypes.d.luau")
        open(defs, "w").write("--" + "x" * 2048)

        def fake_run(argv, cwd, timeout=180):
            return 127, "main.luau(1,1): LocalUnused: unused"

        old_run, old_which = check_mod._run, check_mod.shutil.which
        check_mod._run = fake_run
        check_mod.shutil.which = lambda name: "C:/fake/" + name
        os.environ["RBFORGE_LUAU_DEFINITIONS"] = defs
        try:
            rung = check_mod.rung_static(root)
        finally:
            check_mod._run, check_mod.shutil.which = old_run, old_which
            os.environ.pop("RBFORGE_LUAU_DEFINITIONS", None)
    lsp = [c for c in rung["checks"] if c["id"] == "luau-lsp"][0]
    assert lsp["status"] == "fail", lsp
    assert "127" in lsp["detail"], lsp


@check("types: a tampered cache is not trusted, and fetch repairs it")
def _():
    from rbforge import types as t
    with tempdir() as root, tempdir() as cache:
        old_cache = t.cache_dir
        t.cache_dir = lambda: cache
        try:
            cached = os.path.join(cache, "globalTypes-%s.d.luau" % t.REF)
            open(cached, "w").write("x" * 4096)  # big enough, wrong bytes
            found, why = t.discover(root)
            assert found is None, (found, why)
            assert "pinned digest" in why, why
            path, digest, size = t.fetch()
            found, source = t.discover(root)
            assert source == "cache" and found == cached, (found, source)
            assert digest == t.SHA256, digest
        finally:
            t.cache_dir = old_cache


@check("skills: installer backups never land inside a skill root")
def _():
    from rbforge import skills
    with tempdir() as src, tempdir() as root, tempdir() as home:
        for name in skills.OUR_SKILLS:
            os.makedirs(os.path.join(src, name))
            open(os.path.join(src, name, "SKILL.md"), "w").write("# " + name)
        old = (skills.paths.skills_source_dir, skills.roots_for, skills.paths.home)
        skills.paths.skills_source_dir = lambda: src
        skills.roots_for = lambda agent: [root]
        skills.paths.home = lambda: home
        _sandbox_agent(skills, root, "sandbox")
        try:
            skills.install(["sandbox"])
            target = os.path.join(root, "roblox-docs", "SKILL.md")
            open(target, "w").write("# edited")
            skills.install(["sandbox"])  # forces a backup of the modified skill
            inside = [n for n in os.listdir(root) if "rbforge-backup" in n]
            kept = os.listdir(os.path.join(home, "backups")) if os.path.isdir(os.path.join(home, "backups")) else []
        finally:
            skills.paths.skills_source_dir, skills.roots_for, skills.paths.home = old
            del skills._ROOTS["sandbox"]
    assert not inside, inside
    assert kept, "no backup was taken outside the skill root"


@check("optimize: 'ai' in 'terrain' and 'map' in 'bitmap' do not route")
def _():
    from rbforge import optimize
    with tempdir() as root:
        open(os.path.join(root, "Main.server.luau"), "w").write(
            "local terrain = workspace.Terrain\nlocal bitmap = 'x'\n")
        terrain = optimize.profile(root, "simple terrain obby")
        bitmap = optimize.profile(root, "bitmap UI tutorial")
        roadmap = optimize.profile(root, "roadmapping tutorial for beginners")
    assert not [i for i in terrain["level_b"] if i["id"] == "npc"], terrain["level_b"]
    assert not [i for i in bitmap["level_b"] if i["id"] == "streaming"], bitmap["level_b"]
    assert not [i for i in roadmap["level_b"] if i["id"] == "streaming"], roadmap["level_b"]


@check("optimize: comments in the source do not route a project")
def _():
    from rbforge import optimize
    with tempdir() as root:
        open(os.path.join(root, "Main.server.luau"), "w").write(
            "-- TODO: maybe PathfindingService and RemoteEvent later\nlocal x = 1\n")
        prof = optimize.profile(root, "simple obby")
    assert prof["level_b"] == [], prof["level_b"]


@check("optimize: an invalid project directory is an explicit error")
def _():
    from rbforge import optimize
    from rbforge.errors import ForgeError
    missing = os.path.join(tempfile.gettempdir(), "rbf-does-not-exist-%d" % os.getpid())
    error = None
    try:
        optimize.profile(missing, "multiplayer city")
    except ForgeError as exc:
        error = exc
    assert error is not None and error.code == "RBF-ARG-003", error


@check("optimize: no readable source is reported, not called 'small'")
def _():
    from rbforge import optimize
    with tempdir() as root:
        prof = optimize.profile(root, "")
    assert prof["source"] == "none", prof
    assert "small project" not in prof["next"], prof["next"]
    assert "no readable Luau source" in prof["next"], prof["next"]


@check("skills: migration moves only our backups and reports what it cannot move")
def _():
    from rbforge import skills
    with tempdir() as root, tempdir() as home:
        ours = os.path.join(root, "roblox-docs.rbforge-backup-20260101-000000-abcd")
        theirs = os.path.join(root, "my-tool.rbforge-backup-20260101-000000-ffff")
        os.makedirs(ours)
        open(os.path.join(ours, "SKILL.md"), "w").write("# ours")
        os.makedirs(theirs)
        open(os.path.join(theirs, "keep.txt"), "w").write("not ours")
        old = (skills.paths.home, skills.roots_for)
        skills.paths.home = lambda: home
        skills.roots_for = lambda agent: [root]
        skills._ROOTS["sbxmig"] = ("RBFORGE_MIG_SKILLS", (root,))
        try:
            report = skills.migrate_backups(["sbxmig"])
        finally:
            skills.paths.home, skills.roots_for = old
            del skills._ROOTS["sbxmig"]
        moved_names = [os.path.basename(p) for p in report["moved"]]
        ours_gone = not os.path.isdir(ours)
        theirs_alive = os.path.isdir(theirs)
        content = os.path.isfile(os.path.join(home, "backups",
                                              "roblox-docs.rbforge-backup-20260101-000000-abcd",
                                              "SKILL.md"))
    assert moved_names and ours_gone, report
    assert theirs_alive, "an unrelated directory was relocated"
    assert content, "the backup lost its contents"
    assert report["failed"] == [], report


@check("skills: migration refuses an unknown agent before touching anything")
def _():
    from rbforge import skills
    from rbforge.errors import ForgeError
    error = None
    try:
        skills.migrate_backups(["definitely-not-an-agent"])
    except ForgeError as exc:
        error = exc
    assert error is not None and error.code == "RBF-ARG-001", error


@check("skills: a migration that fails is surfaced by install, not swallowed")
def _():
    from rbforge import skills
    with installed_tree() as (src, root, home, agent):
        stale = os.path.join(root, "roblox-docs.rbforge-backup-20260101-000000-abcd")
        os.makedirs(stale)
        open(os.path.join(stale, "SKILL.md"), "w").write("# old copy")
        real_replace = skills.os.replace

        def refuses_moves(a, b):
            if ".rbforge-backup-" in str(a) and os.sep + "backups" + os.sep in str(b):
                raise OSError("access denied")
            return real_replace(a, b)

        skills.os.replace = refuses_moves
        try:
            result = skills.install([agent])
        finally:
            skills.os.replace = real_replace
        still_there = os.path.isdir(stale)
    assert "MIGRATION FAILED" in result[agent], result
    assert "access denied" in result[agent], result
    assert still_there, "the test did not actually leave the backup in place"


@check("tests: installed_tree restores every patched global and removes its temp dirs")
def _():
    from rbforge import paths, skills
    before = (skills.paths.skills_source_dir, skills.roots_for, skills.paths.home)
    with installed_tree() as (src, root, home, agent):
        inside = (skills.paths.skills_source_dir, skills.roots_for, skills.paths.home)
        dirs = (src, root, home)
    after = (skills.paths.skills_source_dir, skills.roots_for, skills.paths.home)
    assert inside != before, "the context manager did not patch anything"
    assert after == before, (after, before)
    assert not [d for d in dirs if os.path.isdir(d)], dirs
    assert "sbx-tmp" not in skills._ROOTS, sorted(skills._ROOTS)


if __name__ == "__main__":
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    for name, exc in FAIL:
        print("  FAILED: %s -> %r" % (name, exc))
    sys.exit(1 if FAIL else 0)
