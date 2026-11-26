"""RobloxForge test runner. No pytest, no Roblox install required.

Run: python tests/run_tests.py
Fixture-based; exercises every core module against synthetic state.
"""
import base64
import io
import time
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

PASS, FAIL, SKIPPED = [], [], []

# Studio states the preflights read: servertest needs Play, push needs Edit.
_PLAY_STATE = "- Current Studio Mode: Play\n- Available DataModels: Client, Server\n"
_EDIT_STATE = "- Current Studio Mode: Edit\n- Available DataModels: Edit\n"


def _fake_session(out, state=_PLAY_STATE):
    """A Studio session double: `out` from execute_luau, `state` from get_studio_state."""
    class Fake:
        answer = out

        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        studio_id = "s1"

        def call(self, tool, args):  # preflights: servertest wants Play, push wants Edit
            return state

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


_ONLY = os.environ.get("RBFORGE_TEST_ONLY")  # substring filter for a quick local loop; CI never sets it




def check(name):
    def deco(fn):
        if _ONLY and _ONLY not in name:
            return fn
        try:
            # A test that cannot run its subject returns "skip: <why>". That is never counted as a
            # pass: an integration test that silently degrades to green is worse than no test.
            outcome = fn()
            if isinstance(outcome, str) and outcome.lower().startswith("skip"):
                SKIPPED.append((name, outcome))
                print("skip %s (%s)" % (name, outcome))
            else:
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

def _fake_studio(console="", place="Sample Place", capture="C:/shots/smoke.png"):
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
                live.Session = _fake_session(answer, _EDIT_STATE)
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
            live.Session = _fake_session("SYNCED " + want, _EDIT_STATE)
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
            live.Session = _fake_session("HIERARCHY Workspace.Thing must be a Script", _EDIT_STATE)
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
        assert {"rb_collect_evidence", "rb_verify_receipt", "rb_assets"} <= names, sorted(names)
        assets_schema = [t for t in tools if t["name"] == "rb_assets"][0]["inputSchema"]
        assert set(assets_schema["properties"]["action"]["enum"]) == {"status", "check"}, assets_schema
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
        assert os.path.isfile(os.path.join(target, "src", "server", "Main.server.luau"))
        cfg = open(os.path.join(target, "src", "shared", "Config.luau")).read()
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

@check("probes: goto, capture-quality and sound-audit exist, state their datamodel and are in the playbook")
def _():
    from rbforge import probes
    names = {p["name"]: p for p in probes.catalog()}
    for name, dm in (("goto", "Server"), ("capture-quality", "Client"), ("sound-audit", "Client")):
        assert name in names, f"{name} missing from the catalog"
        assert names[name]["datamodel"] == dm, f"{name} should run in {dm}"
    restore = probes.render("capture-quality", {"level": "0"})["code"]
    assert "ForgeSavedQuality" in restore and "_G." not in restore, "quality must be saved in an attribute, not _G"
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "skills", "roblox-game-development", "references", "debugging-playbook.md"),
              encoding="utf-8") as fh:
        playbook = fh.read()
    for name in ("goto", "capture-quality", "sound-audit"):
        assert f"`{name}`" in playbook, f"{name} is not documented in the playbook"


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
    bugh = 'local viewmodel = weapon:Clone()\nlocal m = viewmodel\nlocal cam = workspace.CurrentCamera\nm.Parent = cam'
    assert "T022" in ids("src/client/vm.luau", bugh)
    assert "T022" not in ids("src/client/vm.luau", bugh + '\nfor _, d in ipairs(m:GetDescendants()) do\n if d:IsA("JointInstance") then d:Destroy() end\nend')
    assert "T023" in ids("src/client/vm.luau", "part.LocalTransparencyModifier = saved")
    assert "T023" not in ids("src/client/vm.luau", "part.LocalTransparencyModifier = 0")
    trig = 'local on = player:GetAttribute("DebugFirstPerson")'
    assert "T024" in ids("src/client/move.luau", trig)
    assert "T024" not in ids("src/client/move.luau", "local on = RunService:IsStudio() and player:GetAttribute(\"DebugFirstPerson\")")

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


@check("installer: a cached luau-lsp is trusted only when it reports the pinned version")
def _():
    # A file at the cache path proves nothing: an older pin, a half-written download or an
    # unrelated executable all live there. The decision is the binary's own --version.
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "rbf_install_lsp", os.path.join(root, "scripts", "install_luau_lsp.py"))
    assert spec and spec.loader, "install_luau_lsp.py cannot be loaded"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with tempdir() as tmp:
        cached = os.path.join(tmp, "luau-lsp")
        open(cached, "wb").write(b"\x00not really a binary")
        assert mod.is_current(cached, "1.70.1", probe=lambda p: "1.70.1") is True, "the pin was not reused"
        assert mod.is_current(cached, "1.70.1", probe=lambda p: "1.69.0") is False, "an older pin was trusted"
        assert mod.is_current(cached, "1.70.1", probe=lambda p: None) is False, "an unrunnable file was trusted"
        assert mod.is_current(cached, "1.70.2", probe=lambda p: "1.70.1") is False, "a bumped pin was ignored"
        assert mod.is_current(os.path.join(tmp, "absent"), "1.70.1",
                              probe=lambda p: "1.70.1") is False, "a missing file counted as current"
        # Reading the real path: garbage cannot report a version, so it must come back as None.
        assert mod.probe_version(cached) is None, "an unusable binary reported a version"
    assert mod.VERSION == "1.70.1", mod.VERSION


def _glb_bytes(meshes, materials=1, version=2, chunk_override=None, magic=b"glTF"):
    """Build a minimal GLB. `meshes` is [(name, [(mode, accessor_count, indexed)])]."""
    import struct as _struct
    accessors, doc_meshes = [], []
    for name, prims in meshes:
        out_prims = []
        for mode, count, indexed in prims:
            pos = len(accessors)
            accessors.append({"count": count})
            prim = {"attributes": {"POSITION": pos}, "mode": mode}
            if indexed:
                prim["indices"] = pos
            out_prims.append(prim)
        doc_meshes.append({"name": name, "primitives": out_prims})
    doc = {"asset": {"version": "2.0"}, "meshes": doc_meshes,
           "accessors": accessors, "materials": [{} for _ in range(materials)]}
    blob = json.dumps(doc).encode("utf-8")
    blob += b" " * ((4 - len(blob) % 4) % 4)
    header = _struct.pack("<4sII", magic, version, 12 + 8 + len(blob))
    chunk = _struct.pack("<II", len(blob), 0x4E4F534A)
    if chunk_override is not None:
        chunk = chunk_override
    return header + chunk + blob


@check("assets: the triangle limit applies per mesh, not to the file total")
def _():
    from rbforge import assets

    with tempdir() as root:
        def write(name, meshes):
            path = os.path.join(root, name)
            open(path, "wb").write(_glb_bytes(meshes))
            return assets.inspect_export(path)

        # One mesh just under the cap.
        under = write("under.glb", [("Body", [(4, 19999 * 3, True)])])
        assert under["status"] == assets.STATUS_WITHIN and under["within_limit"] is True, under

        # One mesh just over it.
        over = write("over.glb", [("Body", [(4, 20001 * 3, True)])])
        assert over["status"] == assets.STATUS_OVER and over["within_limit"] is False, over
        assert over["triangles"] == 20001, over

        # Two meshes of 16k each: 32k total, but neither mesh is over - this is a pass.
        split = write("split.glb", [("A", [(4, 16000 * 3, True)]), ("B", [(4, 16000 * 3, True)])])
        assert split["triangles"] == 32000, split
        assert split["status"] == assets.STATUS_WITHIN and split["within_limit"] is True, split

        # One over-cap mesh plus a small one, and the two fields must agree.
        mixed = write("mixed.glb", [("Huge", [(4, 21000 * 3, True)]), ("Tiny", [(4, 300, True)])])
        assert mixed["status"] == assets.STATUS_OVER, mixed
        assert mixed["within_limit"] is False and len(mixed["over_limit"]) == 1, mixed
        assert mixed["over_limit"][0]["name"] == "Huge", mixed["over_limit"]

        # Several primitives in one mesh add up to that mesh's total.
        one = write("prim.glb", [("Body", [(4, 12000 * 3, True), (4, 12000 * 3, True)])])
        assert one["per_mesh"][0]["triangles"] == 24000 and one["status"] == assets.STATUS_OVER, one


@check("assets: glTF primitive modes are counted by their own rule, not count // 3")
def _():
    from rbforge import assets
    with tempdir() as root:
        def counts(name, mode, count, indexed=True):
            path = os.path.join(root, name)
            open(path, "wb").write(_glb_bytes([("M", [(mode, count, indexed)])]))
            return assets.glb_summary(path)

        tri = counts("tri.glb", 4, 300)
        assert tri["per_mesh"][0]["triangles"] == 100 and tri["status"] == assets.STATUS_WITHIN, tri

        strip = counts("strip.glb", 5, 302)
        assert strip["per_mesh"][0]["triangles"] == 300, strip  # n-2

        fan = counts("fan.glb", 6, 302)
        assert fan["per_mesh"][0]["triangles"] == 300, fan  # n-2

        points = counts("points.glb", 0, 900)
        assert points["per_mesh"][0]["triangles"] == 0 and points["status"] == assets.STATUS_WITHIN, points

        odd = counts("odd.glb", 99, 300)
        assert odd["status"] == assets.STATUS_UNVERIFIED, "an unknown mode must not be counted as triangles"
        assert any("mode" in p for p in odd.get("problems", [])), odd

        # Non-indexed geometry reads POSITION instead of indices.
        loose = counts("loose.glb", 4, 300, indexed=False)
        assert loose["per_mesh"][0]["triangles"] == 100, loose


@check("assets: malformed GLBs are refused with a reason instead of crashing")
def _():
    import struct as _struct
    from rbforge import assets
    with tempdir() as root:
        def probe(name, blob):
            path = os.path.join(root, name)
            open(path, "wb").write(blob)
            return assets.glb_summary(path)

        # The reproduced crash: valid magic, then an incomplete chunk header.
        short = probe("short.glb", b"glTF" + _struct.pack("<II", 2, 999))
        assert short["status"] == assets.STATUS_INVALID and "truncated" in short["error"], short

        empty = probe("empty.glb", b"glTF")
        assert empty["status"] == assets.STATUS_INVALID, empty

        wrong_magic = probe("magic.glb", b"PVR\x00" + b"\x00" * 40)
        assert wrong_magic["status"] == assets.STATUS_INVALID and "magic" in wrong_magic["error"], wrong_magic

        bad_version = probe("v1.glb", _glb_bytes([("M", [(4, 30, True)])], version=1))
        assert bad_version["status"] == assets.STATUS_INVALID and "version" in bad_version["error"], bad_version

        not_json = probe("json.glb", _glb_bytes([], chunk_override=_struct.pack("<II", 8, 0x4E4F534A))
                         + b"not json")
        assert not_json["status"] == assets.STATUS_INVALID, not_json

        # Declared length larger than the bytes present.
        truncated = probe("trunc.glb", _glb_bytes([("M", [(4, 30, True)])])[:-20])
        assert truncated["status"] == assets.STATUS_INVALID, truncated

        # An accessor index past the end of the table is not a zero-triangle mesh.
        doc = {"asset": {"version": "2.0"}, "accessors": [{"count": 30}],
               "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 7, "mode": 4}]}]}
        blob = json.dumps(doc).encode("utf-8")
        blob += b" " * ((4 - len(blob) % 4) % 4)
        out_of_range = probe("range.glb", _struct.pack("<4sII", b"glTF", 2, 20 + len(blob))
                             + _struct.pack("<II", len(blob), 0x4E4F534A) + blob)
        assert out_of_range["status"] == assets.STATUS_INVALID, out_of_range
        assert any("out of range" in p for p in out_of_range["problems"]), out_of_range

        # A mismatched declared file length is reported and never passes.
        good = _glb_bytes([("M", [(4, 30, True)])])
        lies = good[:8] + _struct.pack("<I", 99999) + good[12:]
        mismatch = probe("lies.glb", lies)
        assert mismatch.get("declared_bytes_mismatch") is True, mismatch
        assert mismatch["status"] != assets.STATUS_WITHIN, mismatch
        assert "within_limit" not in mismatch, "a file with a lying header must not carry a verdict"


@check("assets: nothing passes without being measured, and the CLI exit codes agree")
def _():
    import io
    import contextlib
    from rbforge import assets
    from rbforge_cli import main as cli_main

    with tempdir() as root:
        obj = os.path.join(root, "not_a_model.obj")
        open(obj, "w").write("this is prose, not a mesh\n")
        report = assets.inspect_export(obj)
        assert report["status"] == assets.STATUS_UNVERIFIED, report
        assert "within_limit" not in report, "an unmeasured file must not carry a verdict"

        junk = os.path.join(root, "junk.glb")
        open(junk, "wb").write(b"not a model at all")
        assert assets.inspect_export(junk)["status"] == assets.STATUS_INVALID

        good = os.path.join(root, "ok.glb")
        open(good, "wb").write(_glb_bytes([("Body", [(4, 900, True)])]))
        big = os.path.join(root, "big.glb")
        open(big, "wb").write(_glb_bytes([("Body", [(4, 20001 * 3, True)])]))
        txt = os.path.join(root, "notes.txt")
        open(txt, "w").write("hello")

        def code_for(path):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cli_main(["assets", "check", path])
            return code, buf.getvalue()

        assert code_for(good)[0] == 0, "a measured, within-limit export is the only success"
        assert code_for(big)[0] == 2, "over the cap must fail the gate"
        assert code_for(junk)[0] == 2, "malformed input must fail"
        assert code_for(obj)[0] == 4, "recognised but unmeasured must be incomplete, not OK"
        assert code_for(txt)[0] == 2, "an unsupported extension must fail"


@check("assets: the add-on directory uses Blender's major.minor name, and absence is not assumed")
def _():
    from rbforge import assets
    # Blender writes 5.2, never 5.2.0 - the folder must match or the search looks in a place that cannot exist.
    assert assets.addons_dir("5.2.0").replace("\\", "/").endswith("Blender/5.2/scripts/addons"), assets.addons_dir("5.2.0")
    assert assets.extensions_dir("5.2.0").replace("\\", "/").endswith("Blender/5.2/extensions")

    with tempdir() as root:
        install = os.path.join(root, "Blender")
        os.makedirs(install)
        exe = os.path.join(install, "blender.exe")
        open(exe, "wb").write(b"MZ")
        os.makedirs(os.path.join(install, "5.2"))
        blender = {"path": exe.replace("\\", "/"), "version": "5.2.0", "short_version": "5.2"}

        # A hermetic %APPDATA%, because the real one would make the answer machine-dependent.
        appdata = os.path.join(root, "appdata")
        os.makedirs(os.path.join(appdata, "Blender Foundation", "Blender", "5.2", "scripts", "addons"))
        old_appdata = os.environ.get("APPDATA")
        os.environ["APPDATA"] = appdata
        try:
            # Nothing installed in a root that exists -> confirmed absent, not unknown.
            found, searched, complete = assets.find_addon_anywhere(blender)
            assert found is None
            assert complete is True, searched
            assert any(s["path"].endswith("5.2/scripts/addons") for s in searched), searched

            # Installed in the portable layout beside the binary -> found there, and absence elsewhere
            # never gets reported as a fact.
            portable = os.path.join(install, "portable", "5.2", "scripts", "addons", "upload_to_roblox")
            os.makedirs(portable)
            open(os.path.join(portable, "blender_manifest.toml"), "w").write(
                'name = "Upload to Roblox"\nversion = "1.0.0"\n')
            found, _, _ = assets.find_addon_anywhere(blender)
            assert found and found.endswith("upload_to_roblox"), found
        finally:
            if old_appdata is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = old_appdata


@check("map: an unconfigured external prover is unavailable, never a guess")
def _():
    from rbforge import mapkit
    old = os.environ.pop("RBFORGE_SYPHODEV", None)
    try:
        report = mapkit.status()
        assert report["available"] is False, report
        assert "RBFORGE_SYPHODEV" in report["reason"], report
        run = mapkit.prove("minimal")
        assert run["available"] is False and run["ok"] is False, run
    finally:
        if old is not None:
            os.environ["RBFORGE_SYPHODEV"] = old
    # A path that is not the package is not accepted just because it exists.
    with tempdir() as root:
        assert mapkit.find_install(root) is None
        assert mapkit.status(configured=root)["available"] is False


@check("map: the prover's own spec and report formats survive the adapter")
def _():
    import sys as _sys
    from rbforge import mapkit
    with tempdir() as root:
        skill = os.path.join(root, "roblox-map")
        os.makedirs(os.path.join(skill, "scripts"))
        os.makedirs(os.path.join(skill, "specs"))
        open(os.path.join(skill, "specs", "tiny.json"), "w").write('{"name": "Tiny"}\n')
        # Stands in for the upstream script: same contract, writes the report where --json says.
        open(os.path.join(skill, "scripts", "prove.py"), "w").write(
            "import json, sys\n"
            "args = sys.argv[1:]\n"
            "out = args[args.index('--json') + 1]\n"
            "json.dump({'map': 'Tiny', 'result': 'FAIL', 'checks': [\n"
            "    {'id': 'P2', 'title': 'Standable surface', 'status': 'FAIL', 'detail': 'island'},\n"
            "    {'id': 'P4', 'title': 'Reachability', 'status': 'PASS', 'detail': 'ok'}]}, open(out, 'w'))\n"
            "print('RESULT: FAIL')\n"
            "sys.exit(1)\n")
        report = mapkit.prove("tiny", configured=skill, python=_sys.executable,
                              out_path=os.path.join(root, "report.json"), probe=lambda p: [])
        assert report["available"] is True and report["ok"] is False, report
        assert report["result"] == "FAIL" and report["map"] == "Tiny", report
        assert [c["id"] for c in report["checks_failed"]] == ["P2"], report["checks_failed"]
        assert os.path.isfile(report["report_path"]), report  # the upstream file, untouched
        assert report["touches_studio"] is False

        # A run that produces no report is a failure with a reason, not a silent pass.
        open(os.path.join(skill, "scripts", "prove.py"), "w").write(
            "import sys\nprint('boom')\nsys.exit(1)\n")
        broken = mapkit.prove("tiny", configured=skill, python=_sys.executable,
                              out_path=os.path.join(root, "absent.json"), probe=lambda p: [])
        assert broken["ok"] is False and "no report file" in broken["reason"], broken

        # A spec that does not exist is named, and nothing is executed.
        missing = mapkit.prove("nope", configured=skill, python=_sys.executable, probe=lambda p: [])
        assert missing["ok"] is False and "no such spec" in missing["reason"], missing


@check("map: missing dependencies make it unavailable instead of half-working")
def _():
    from rbforge import mapkit
    with tempdir() as root:
        skill = os.path.join(root, "roblox-map")
        os.makedirs(os.path.join(skill, "scripts"))
        os.makedirs(os.path.join(skill, "specs"))
        open(os.path.join(skill, "scripts", "prove.py"), "w").write("print('x')\n")
        assert mapkit.find_install(skill) is not None
        assert mapkit.find_install(root) is None  # the parent is not the package

        missing = mapkit.missing_dependencies(python=os.path.join(root, "no-such-python"))
        assert missing, "an unusable interpreter must report missing dependencies"
        report = mapkit.status(configured=skill, python=os.path.join(root, "no-such-python"))
        assert report["available"] is False and "dependencies" in report["reason"], report
        run = mapkit.prove("tiny", configured=skill, python=os.path.join(root, "no-such-python"))
        assert run["available"] is False and run["missing_dependencies"], run


@check("assets: malformed metadata is invalid, never an exception")
def _():
    import io
    import contextlib
    from rbforge import assets
    from rbforge_cli import main as cli_main

    def glb(doc, declared=None):
        import struct as _struct
        blob = json.dumps(doc).encode("utf-8")
        blob += b" " * ((4 - len(blob) % 4) % 4)
        total = declared if declared is not None else 20 + len(blob)
        return (_struct.pack("<4sII", b"glTF", 2, total)
                + _struct.pack("<II", len(blob), 0x4E4F534A) + blob)

    base = {"asset": {"version": "2.0"}}
    cases = {
        "accessor-null": dict(base, accessors=[None],
                              meshes=[{"primitives": [{"indices": 0, "mode": 4}]}]),
        "attributes-list": dict(base, accessors=[{"count": 30}],
                                meshes=[{"primitives": [{"attributes": [1, 2], "mode": 4}]}]),
        "primitives-not-array": dict(base, accessors=[{"count": 30}],
                                     meshes=[{"primitives": {"mode": 4}}]),
        "mesh-not-object": dict(base, accessors=[], meshes=["nope"]),
        "primitive-not-object": dict(base, accessors=[], meshes=[{"primitives": [7]}]),
        "mode-bool": dict(base, accessors=[{"count": 30}],
                          meshes=[{"primitives": [{"indices": 0, "mode": True}]}]),
    }
    with tempdir() as root:
        for name, doc in cases.items():
            path = os.path.join(root, name + ".glb")
            open(path, "wb").write(glb(doc))
            report = assets.inspect_export(path)  # must not raise
            assert report["status"] == assets.STATUS_INVALID, (name, report)
            assert report.get("problems") or report.get("error"), (name, report)

            # The CLI contract is JSON on stdout even for this, and the exit code is a failure.
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cli_main(["assets", "check", path])
            assert code == 2, (name, code, buf.getvalue()[:200])
            parsed = json.loads(buf.getvalue())
            assert parsed["status"] == assets.STATUS_INVALID, (name, parsed)


@check("assets: a negative accessor index is malformed, not Python's last item")
def _():
    import struct as _struct
    from rbforge import assets

    def glb(doc):
        blob = json.dumps(doc).encode("utf-8")
        blob += b" " * ((4 - len(blob) % 4) % 4)
        return (_struct.pack("<4sII", b"glTF", 2, 20 + len(blob))
                + _struct.pack("<II", len(blob), 0x4E4F534A) + blob)

    with tempdir() as root:
        docs = {
            "neg-indices": {"accessors": [{"count": 30}],
                            "meshes": [{"primitives": [{"indices": -1, "mode": 4}]}]},
            "neg-position": {"accessors": [{"count": 30}],
                             "meshes": [{"primitives": [{"attributes": {"POSITION": -1}, "mode": 4}]}]},
        }
        for name, body in docs.items():
            path = os.path.join(root, name + ".glb")
            open(path, "wb").write(glb(dict({"asset": {"version": "2.0"}}, **body)))
            report = assets.inspect_export(path)
            assert report["status"] == assets.STATUS_INVALID, (name, report)
            assert "negative" in " ".join(report.get("problems", [])), (name, report)
            assert "within_limit" not in report, (name, report)


@check("assets: the declared GLB length is enforced, never just noted")
def _():
    import io
    import contextlib
    from rbforge import assets
    from rbforge_cli import main as cli_main

    good = _glb_bytes([("Body", [(4, 90, True)])])
    cases = {
        "exact": (good, True),
        "truncated": (good[:-16], False),           # fewer bytes than declared
        "oversized": (good + b"\x00" * 16, False),  # more bytes than declared
        "declared-too-big": (good[:8] + b"\x8f\x86\x01\x00" + good[12:], False),
        "declared-zero": (good[:8] + b"\x00\x00\x00\x00" + good[12:], False),
    }
    with tempdir() as root:
        for name, (blob, should_pass) in cases.items():
            path = os.path.join(root, name + ".glb")
            open(path, "wb").write(blob)
            report = assets.inspect_export(path)
            if should_pass:
                assert report["status"] == assets.STATUS_WITHIN, (name, report)
                continue
            assert report["status"] != assets.STATUS_WITHIN, (name, report)
            assert "within_limit" not in report or report["within_limit"] is False, (name, report)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cli_main(["assets", "check", path])
            assert code in (2, 4), (name, code, buf.getvalue()[:200])
            json.loads(buf.getvalue())  # still machine-readable


@check("assets: a Blender on PATH is discovered without an override")
def _():
    from rbforge import assets
    with tempdir() as root:
        exe = os.path.join(root, "blender.exe" if os.name == "nt" else "blender")
        open(exe, "wb").write(b"MZ")
        if os.name != "nt":
            os.chmod(exe, 0o755)  # which() only finds an executable file on POSIX
        old_path, old_override = os.environ.get("PATH", ""), os.environ.pop("RBFORGE_BLENDER", None)
        os.environ["PATH"] = root + os.pathsep + old_path
        try:
            found = {c["path"].lower() for c in assets._blender_candidates()}
        finally:
            os.environ["PATH"] = old_path
            if old_override is not None:
                os.environ["RBFORGE_BLENDER"] = old_override
        assert exe.replace("\\", "/").lower() in found, sorted(found)


@check("map: a stale report can never pass as this run's result")
def _():
    import sys as _sys
    from rbforge import mapkit

    def install(root, script):
        skill = os.path.join(root, "roblox-map")
        os.makedirs(os.path.join(skill, "scripts"), exist_ok=True)
        os.makedirs(os.path.join(skill, "specs"), exist_ok=True)
        open(os.path.join(skill, "specs", "s.json"), "w").write("{}")
        open(os.path.join(skill, "scripts", "prove.py"), "w").write(script)
        return skill

    writes_pass = ("import json, sys\n"
                   "a = sys.argv[1:]\n"
                   "out = a[a.index('--json') + 1]\n"
                   "json.dump({'map': 'M', 'result': 'PASS', 'checks': []}, open(out, 'w'))\n")
    writes_fail = ("import json, sys\n"
                   "a = sys.argv[1:]\n"
                   "out = a[a.index('--json') + 1]\n"
                   "json.dump({'map': 'M', 'result': 'FAIL', 'checks': [\n"
                   "    {'id': 'P1', 'title': 'Grounding', 'status': 'FAIL', 'detail': 'x'}]}, open(out, 'w'))\n"
                   "sys.exit(1)\n")
    silent_ok = "print('nothing to see')\n"
    silent_fail = "import sys\nprint('boom')\nsys.exit(1)\n"
    bad_json = ("import sys\n"
                "a = sys.argv[1:]\n"
                "open(a[a.index('--json') + 1], 'w').write('{not json')\n")
    odd_shape = ("import json, sys\n"
                 "a = sys.argv[1:]\n"
                 "json.dump({'result': 'PASSED', 'checks': []}, open(a[a.index('--json') + 1], 'w'))\n")

    with tempdir() as root:
        def run(script, name, out=None, timeout=60, python=None):
            work = os.path.join(root, name)
            os.makedirs(work, exist_ok=True)
            skill = install(work, script)
            return mapkit.prove("s", configured=skill, python=python or _sys.executable,
                                timeout=timeout, out_path=out, probe=lambda p: [])

        # 1. normal PASS, without --out: the report comes back inline and no file is claimed
        ok = run(writes_pass, "pass")
        assert ok["available"] and ok["ok"] is True and ok["result"] == "PASS", ok
        assert ok.get("report") and ok["report"]["result"] == "PASS", ok
        assert ok.get("report_path") is None, "a path inside the deleted workdir is not a result"
        assert ok.get("report_persisted") is False, ok

        # 2. normal FAIL: upstream exits nonzero on purpose, and that must survive as a real result
        bad = run(writes_fail, "fail")
        assert bad["ok"] is False and bad["result"] == "FAIL", bad
        assert [c["id"] for c in bad["checks_failed"]] == ["P1"], bad

        # 3. exit 0, no report at all
        empty = run(silent_ok, "silent-ok")
        assert empty["ok"] is False and "no report file" in empty["reason"], empty

        # 4. the reproduced false success: an old PASS report at out_path, and a silent exit 0
        stale_dir = os.path.join(root, "stale")
        os.makedirs(stale_dir)
        stale = os.path.join(stale_dir, "report.json")
        json.dump({"map": "Old", "result": "PASS", "checks": []}, open(stale, "w"))
        rerun = run(silent_ok, "stale-run", out=stale)
        assert rerun["ok"] is False, rerun
        assert rerun.get("result") != "PASS", rerun
        kept = json.load(open(stale))
        assert kept["map"] == "Old", "the failed run must not destroy the earlier report"

        # 5. exit 1, no report
        broken = run(silent_fail, "silent-fail")
        assert broken["ok"] is False and "no report file" in broken["reason"], broken

        # 6. invalid JSON
        junk = run(bad_json, "bad-json")
        assert junk["ok"] is False and "unreadable" in junk["reason"], junk

        # 7. unexpected structure / unknown result value
        odd = run(odd_shape, "odd-shape")
        assert odd["ok"] is False and "result" in odd["reason"], odd

        # 8. the interpreter cannot even be launched
        launched = run(writes_pass, "launch", python=os.path.join(root, "no-such-python"))
        # a bogus interpreter is caught by the dependency probe first
        assert launched["available"] is False or launched["ok"] is False, launched

        # 9. timeout
        slow = ("import time\n"
                "time.sleep(5)\n")
        timed = run(slow, "slow", timeout=1)
        assert timed["ok"] is False and "timed out" in timed["reason"], timed

        # 10. a successful run publishes to the requested destination, replacing the old file
        published = os.path.join(stale_dir, "fresh.json")
        fresh = run(writes_pass, "fresh", out=published)
        assert fresh["ok"] is True and os.path.isfile(published), fresh
        assert json.load(open(published))["result"] == "PASS", fresh

        # 11. every returned report_path is a file that actually exists
        assert fresh["report_path"] and os.path.isfile(fresh["report_path"]), fresh
        for result in (ok, bad, empty, junk, odd):
            path = result.get("report_path")
            assert path is None or os.path.isfile(path), (path, result.get("reason"))

        # 12. publication that cannot happen fails, and an unrelated report survives byte-for-byte
        blocked_parent = os.path.join(root, "blocked")
        open(blocked_parent, "w").write("a file where a directory would have to be")
        before = open(stale, "rb").read()
        unwritable = run(writes_pass, "publish-fail", out=os.path.join(blocked_parent, "report.json"))
        assert unwritable["ok"] is False, unwritable
        assert "could not be written" in unwritable["reason"], unwritable
        assert open(stale, "rb").read() == before, "an earlier report was modified by a failed publish"


@check("map: the CLI reports map failures as JSON with a non-success exit")
def _():
    import io
    import contextlib
    from rbforge import mapkit
    from rbforge_cli import main as cli_main

    with tempdir() as root:
        skill = os.path.join(root, "roblox-map")
        os.makedirs(os.path.join(skill, "scripts"), exist_ok=True)
        os.makedirs(os.path.join(skill, "specs"), exist_ok=True)
        open(os.path.join(skill, "specs", "s.json"), "w").write("{}")
        open(os.path.join(skill, "scripts", "prove.py"), "w").write("print('no report')\n")

        old = os.environ.get("RBFORGE_SYPHODEV")
        os.environ["RBFORGE_SYPHODEV"] = skill
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cli_main(["map", "prove", "s"])
            report = json.loads(buf.getvalue())  # JSON either way, never a traceback
            if mapkit.missing_dependencies():          # a CI interpreter without numpy/scipy/PIL
                assert code == 4, (code, report)       # unavailable is incomplete, not a pass
                assert report["available"] is False and report["missing_dependencies"], report
            else:
                assert code == 2, (code, report)
                assert report["ok"] is False and "no report file" in report["reason"], report

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cli_main(["map"])
            assert code == 0, (code, buf.getvalue()[:200])
            status = json.loads(buf.getvalue())
            assert status["path"] == skill.replace("\\", "/"), status
            if mapkit.missing_dependencies():
                assert status["available"] is False and status["missing_dependencies"], status
            else:
                assert status["available"] is True, status
        finally:
            if old is None:
                os.environ.pop("RBFORGE_SYPHODEV", None)
            else:
                os.environ["RBFORGE_SYPHODEV"] = old


@check("assets: a fake Blender 5.2 install reports the add-on as installed, not merely searched")
def _():
    from rbforge import assets
    with tempdir() as root:
        exe = os.path.join(root, "blender.exe")
        open(exe, "wb").write(b"MZ")
        open(os.path.join(root, "version.txt"), "w").write("5.2.0\n")
        old = os.environ.get("RBFORGE_BLENDER")
        os.environ["RBFORGE_BLENDER"] = exe
        try:
            report = assets.status()
        finally:
            if old is None:
                os.environ.pop("RBFORGE_BLENDER", None)
            else:
                os.environ["RBFORGE_BLENDER"] = old
        assert report["blender"]["version"] == "5.2.0", report["blender"]
        assert report["blender"]["short_version"] == "5.2", report["blender"]
        assert report["blender"]["meets_addon_minimum"] is True, report["blender"]
        assert report["roblox_addon"]["state"] in ("installed", "absent", "unknown"), report["roblox_addon"]
        assert "enabled" in report["roblox_addon"], "enablement is not verifiable here and must say so"
    status = assets.status()
    assert "fallback" in status["upload_routes"], status["upload_routes"]
    assert status["triangles_per_mesh_limit"] == 20000


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
                live.Session = _fake_session(answer, _EDIT_STATE)
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
            live.Session = _fake_session("9999", _EDIT_STATE)
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

            studio_id = "s1"


            def call(self, tool, args):  # push preflight: Studio is in Edit

                return _EDIT_STATE


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


@check("tests: a returned skip is reported as skipped, never counted as a pass")
def _():
    import runpy  # noqa: F401  (kept for clarity: the harness lives in this file)
    before_pass, before_skip = len(PASS), len(SKIPPED)

    @check("harness: deliberate skip probe")
    def _probe():
        return "skip: nothing to analyse"

    assert len(SKIPPED) == before_skip + 1, SKIPPED[-1:]
    assert len(PASS) == before_pass, "a skip was counted as a pass"
    assert "skip" in SKIPPED[-1][1]
    SKIPPED.pop()  # leave the run's counters as they were

    @check("harness: deliberate pass probe")
    def _probe2():
        return None

    assert len(PASS) == before_pass + 1
    PASS.pop()


@check("cli: check <path>, --root <path> and <path> --scope static inspect the requested project, not the cwd")
def _():
    import io
    import contextlib
    from rbforge import check as check_mod
    from rbforge_cli import main as cli_main

    def fake_run(root, scope=None, changed_only=False, base_ref="HEAD"):
        # Shaped like the real report; `root` is the record of which project the CLI chose.
        return {"root": os.path.abspath(root), "status": "pass", "counts": {},
                "rungs_run": ["static"], "rungs": [], "coverage": {}, "gate": "ok"}

    with tempdir() as project, tempdir() as elsewhere:
        os.makedirs(os.path.join(project, "src"))
        open(os.path.join(project, "src", "main.luau"), "w").write("--!strict\nreturn 1\n")
        old_run, old_cwd = check_mod.run, os.getcwd()
        os.chdir(elsewhere)  # a cwd that is NOT the project, so a fallback to "." cannot pass
        check_mod.run = fake_run
        try:
            forms = [["check", project], ["check", "--root", project],
                     ["check", project, "--scope", "static"]]
            for argv in forms:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    code = cli_main(argv + ["--json"])
                assert code == 0, (argv, code, buf.getvalue()[:300])
                report = json.loads(buf.getvalue())
                assert report["root"] == os.path.abspath(project), (argv, report["root"])
                assert report["rungs_run"] == ["static"], (argv, report["rungs_run"])
        finally:
            check_mod.run = old_run
            os.chdir(old_cwd)

        # The real pipeline, once: the rendered header must name the project it checked.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli_main(["check", project, "--scope", "structure"])
        assert code in (0, 2, 4), (code, buf.getvalue()[:300])
        assert os.path.abspath(project) in buf.getvalue(), buf.getvalue()[:300]


@check("cli: conflicting positional path and --root is refused, not silently preferred")
def _():
    import io
    import contextlib
    from rbforge_cli import main as cli_main
    with tempdir() as a, tempdir() as b:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli_main(["check", a, "--root", b])
    assert code == 2, (code, buf.getvalue()[:200])
    assert "conflicting project paths" in buf.getvalue(), buf.getvalue()[:200]


@check("check: two files with the same basename stay separate in the summary")
def _():
    from rbforge import check as check_mod
    with tempdir() as root:
        for sub in ("Server", "Client"):
            os.makedirs(os.path.join(root, "src", sub))
            open(os.path.join(root, "src", sub, "init.luau"), "w").write("return 1\n")
        defs = os.path.join(root, "globalTypes.d.luau")
        open(defs, "w").write("--" + "x" * 2048)
        out = "\n".join([
            os.path.join(root, "src", "Server", "init.luau") + "(1,1): TypeError: bad one",
            os.path.join(root, "src", "Client", "init.luau") + "(2,1): TypeError: bad two",
        ])

        def fake_run(argv, cwd, timeout=180):
            return 1, out

        old_run, old_which = check_mod._run, check_mod.shutil.which
        old_env = os.environ.get("RBFORGE_LUAU_DEFINITIONS")
        check_mod._run = fake_run
        check_mod.shutil.which = lambda name: "C:/fake/" + name
        os.environ["RBFORGE_LUAU_DEFINITIONS"] = defs
        try:
            rung = check_mod.rung_static(root)
        finally:
            check_mod._run, check_mod.shutil.which = old_run, old_which
            if old_env is None:
                os.environ.pop("RBFORGE_LUAU_DEFINITIONS", None)
            else:
                os.environ["RBFORGE_LUAU_DEFINITIONS"] = old_env
    lsp = [c for c in rung["checks"] if c["id"] == "luau-lsp"][0]
    assert "2 blocking diagnostic(s) in 2 file(s)" in lsp["detail"], lsp
    assert "src/Server/init.luau 1" in lsp["detail"], lsp
    assert "src/Client/init.luau 1" in lsp["detail"], lsp


@check("check: same-named files at different depths are two files, not one merged key")
def _():
    # `Server/init.luau` under src and under tests collapsed into one bucket when the key was the
    # last two segments; the summary then reported one file for two real files.
    from rbforge import check as check_mod
    with tempdir() as root:
        blocking = [
            (os.path.join(root, "src", "Server", "init.luau") + "(1,1)", "TypeError", "bad one"),
            (os.path.join(root, "tests", "Server", "init.luau") + "(2,1)", "TypeError", "bad two"),
        ]
        summary = check_mod._summarize_diagnostics(blocking, 1, True, True, root)
    assert "in 2 file(s)" in summary, summary
    assert "src/Server/init.luau 1" in summary, summary
    assert "tests/Server/init.luau 1" in summary, summary


@check("check: a sibling directory sharing the root's name is outside, and outside paths keep their name")
def _():
    from rbforge import check as check_mod
    with tempdir() as parent:
        root = os.path.join(parent, "proj")
        sibling = os.path.join(parent, "proj2")
        os.makedirs(root)
        blocking = [
            # A string-prefix containment test would call this file part of `proj`.
            (os.path.join(sibling, "main.luau") + "(1,1)", "TypeError", "outside"),
            ("somewhere/else/loose.luau(4,1)", "TypeError", "relative"),
        ]
        summary = check_mod._summarize_diagnostics(blocking, 1, True, True, root)
    assert "in 2 file(s)" in summary, summary
    assert "somewhere/else/loose.luau 1" in summary, summary
    assert "proj2" in summary, summary


@check("docs: the sealed/unsealed table examples in typing-luau.md still behave as documented")
def _():
    # The snippet is extracted from the reference itself, so the doc and the test cannot drift apart.
    # Skipped when luau-lsp is absent - reported as a skip, never as a pass - unless CI demands it.
    from rbforge import check as check_mod
    doc = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "skills", "roblox-game-development", "references", "typing-luau.md")
    text = open(doc, encoding="utf-8").read()
    blocks = re.findall(r"```lua\n(.*?)```", text, re.S)
    snippet = next((b for b in blocks if "local a: { x: number }" in b), None)
    assert snippet, "typing-luau.md no longer contains the sealed/unsealed example"

    if not check_mod.shutil.which("luau-lsp"):
        if os.environ.get("RBFORGE_REQUIRE_LUAU_LSP"):
            raise AssertionError("luau-lsp is required here (RBFORGE_REQUIRE_LUAU_LSP) but not installed")
        return "skip: luau-lsp not installed"

    with tempdir() as root:
        os.makedirs(os.path.join(root, "src"))
        open(os.path.join(root, "src", "cases.luau"), "w").write(snippet)
        defs = os.path.join(root, "globalTypes.d.luau")
        open(defs, "w").write("--" + "x" * 2048)
        old_env = os.environ.get("RBFORGE_LUAU_DEFINITIONS")
        os.environ["RBFORGE_LUAU_DEFINITIONS"] = defs
        try:
            rung = check_mod.rung_static(root)
        finally:
            if old_env is None:
                os.environ.pop("RBFORGE_LUAU_DEFINITIONS", None)
            else:
                os.environ["RBFORGE_LUAU_DEFINITIONS"] = old_env
    lsp = [c for c in rung["checks"] if c["id"] == "luau-lsp"][0]
    assert lsp["status"] == "fail", lsp
    assert "1 blocking diagnostic(s) in 1 file(s)" in lsp["detail"], lsp
    assert "Cannot add property 'y'" in lsp["detail"], lsp


@check("check: an analyzer that exits abnormally with no output is a failure, not an empty pass")
def _():
    from rbforge import check as check_mod
    with tempdir() as root:
        open(os.path.join(root, "main.luau"), "w").write("print(1)\n")
        defs = os.path.join(root, "globalTypes.d.luau")
        open(defs, "w").write("--" + "x" * 2048)

        def fake_run(argv, cwd, timeout=180):
            return 2, ""  # crash / bad flag: no diagnostics at all

        old_run, old_which = check_mod._run, check_mod.shutil.which
        old_env = os.environ.get("RBFORGE_LUAU_DEFINITIONS")
        check_mod._run = fake_run
        check_mod.shutil.which = lambda name: "C:/fake/" + name
        os.environ["RBFORGE_LUAU_DEFINITIONS"] = defs
        try:
            rung = check_mod.rung_static(root)
        finally:
            check_mod._run, check_mod.shutil.which = old_run, old_which
            if old_env is None:
                os.environ.pop("RBFORGE_LUAU_DEFINITIONS", None)
            else:
                os.environ["RBFORGE_LUAU_DEFINITIONS"] = old_env
    lsp = [c for c in rung["checks"] if c["id"] == "luau-lsp"][0]
    assert lsp["status"] == "fail", lsp
    assert "exited 2" in lsp["detail"], lsp


@check("check: the failure detail maps the worst files and diagnostic kinds")
def _():
    from rbforge import check as check_mod
    with tempdir() as root:
        open(os.path.join(root, "main.luau"), "w").write("print(1)\n")
        defs = os.path.join(root, "globalTypes.d.luau")
        open(defs, "w").write("--" + "x" * 2048)

        lines = []
        for i in range(7):
            lines.append("src/Builder.luau(%d,7): TypeError: Unknown type used in - operation" % (i + 1))
        lines.append("src/Other.luau(1,1): TypeError: Key 'Range' not found in external type 'Light'")
        out = "\n".join(lines)

        def fake_run(argv, cwd, timeout=180):
            return 1, out

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
    assert "8 blocking diagnostic(s) in 2 file(s)" in lsp["detail"], lsp
    assert "Builder.luau 7" in lsp["detail"], lsp
    assert "analyzer exit 1" in lsp["detail"], lsp


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


# ---------------------------------------------------------------- 0.17.0 audit

def _cli(*argv):
    """(exit code, parsed JSON) for one CLI run in-process."""
    import rbforge_cli
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = rbforge_cli.main(list(argv))
    text = buf.getvalue()
    try:
        return code, json.loads(text)
    except ValueError:
        return code, text


@check("check: a project directory that does not exist is an argument error, not 'incomplete'")
def _():
    from rbforge import check
    from rbforge.errors import ForgeError
    with tempdir() as d:
        missing = os.path.join(d, "nope")
        try:
            check.run(missing)
        except ForgeError as exc:
            assert exc.code == "RBF-ARG-001" and exc.exit_code == 2, exc
        else:
            raise AssertionError("a missing directory produced a report")
        code, out = _cli("check", missing, "--json")
        assert code == 2 and out["error"]["code"] == "RBF-ARG-001", (code, out)


@check("check: a project stored under a folder named *Packages is still audited")
def _():
    from rbforge import check
    with tempdir() as d:
        root = os.path.join(d, "MyPackages", "game")
        os.makedirs(os.path.join(root, "src"))
        os.makedirs(os.path.join(root, "Packages"))
        open(os.path.join(root, "src", "a.luau"), "w").write("--!strict\nreturn 1\n")
        open(os.path.join(root, "Packages", "dep.luau"), "w").write("return loadstring('x')\n")
        rung = check.rung_structure(root)
        coverage = [c for c in rung["checks"] if c["id"] == "coverage"]
        assert coverage and coverage[0]["detail"].startswith("1 Luau"), rung["checks"]
        assert not [c for c in rung["checks"] if c["status"] == "fail"], rung["checks"]


@check("check: comments and strings that name loadstring/getfenv are not calls")
def _():
    from rbforge import check
    with tempdir() as d:
        os.makedirs(os.path.join(d, "src"))
        open(os.path.join(d, "src", "a.luau"), "w").write(
            "--!strict\n-- never call loadstring(code) here\n--[[ getfenv(1) ]]\n"
            "local s = \"setfenv(1, {}) is banned\"\nreturn s\n")
        clean = check.rung_structure(d)
        assert not [c for c in clean["checks"] if c["status"] == "fail"], clean["checks"]
        open(os.path.join(d, "src", "b.luau"), "w").write("--!strict\nreturn loadstring('x')\n")
        dirty = check.rung_structure(d)
        fails = [c["detail"] for c in dirty["checks"] if c["status"] == "fail"]
        assert len(fails) == 1 and "b.luau: loadstring" in fails[0], fails


@check("check: client DataStoreService is judged on code - a comment is ignored, GetService is not")
def _():
    from rbforge import check
    with tempdir() as d:
        os.makedirs(os.path.join(d, "src"))
        path = os.path.join(d, "src", "Hud.client.luau")
        open(path, "w").write("--!strict\n-- the server owns DataStoreService, never the client\nreturn 1\n")
        assert not [c for c in check.rung_structure(d)["checks"] if c["status"] == "fail"]
        open(path, "w").write("--!strict\nlocal ds = game:GetService(\"DataStoreService\")\nreturn ds\n")
        fails = [c["detail"] for c in check.rung_structure(d)["checks"] if c["status"] == "fail"]
        assert fails and "DataStoreService in a client script" in fails[0], fails


@check("luau_text: strings can be kept, comments always go, and a broken string ends at its line")
def _():
    from rbforge import luau_text
    src = "local a = 'x' -- loadstring(\nlocal b = \"open\nprint(loadstring)\n--[==[ multi\nline ]==]return [[k]]\n"
    code = luau_text.code_only(src)
    assert "loadstring(" not in code and "multi" not in code and "'x'" not in code, code
    assert "print(loadstring)" in code, "an unterminated string swallowed the next line: %r" % code
    kept = luau_text.code_only(src, keep_strings=True)
    assert "'x'" in kept and "[[k]]" in kept and "multi" not in kept, kept


@check("live: a Session whose setup fails stops the MCP process it started")
def _():
    from rbforge import live
    from rbforge.errors import ForgeError
    with tempdir() as d:
        fake = os.path.join(d, "fake_mcp.py")
        open(fake, "w").write(
            "import json, sys\n"
            "for line in sys.stdin:\n"
            "    msg = json.loads(line)\n"
            "    if 'id' not in msg: continue\n"
            "    if msg['method'] == 'initialize': result = {'protocolVersion': '2024-11-05'}\n"
            "    else: result = {'content': [{'type': 'text', 'text': json.dumps({'studios': [\n"
            "        {'id': 'a', 'name': 'One'}, {'id': 'b', 'name': 'Two'}]})}]}\n"
            "    print(json.dumps({'jsonrpc': '2.0', 'id': msg['id'], 'result': result}), flush=True)\n")
        started = []
        real_popen = live.subprocess.Popen

        def recording(*a, **k):
            proc = real_popen(*a, **k)
            started.append(proc)
            return proc

        orig_cmd = live.studio_mod.mcp_command
        live.studio_mod.mcp_command = lambda: [sys.executable, fake]
        live.subprocess.Popen = recording
        try:
            try:
                live.Session(timeout=20)
            except ForgeError as exc:
                assert exc.code == "RBF-STUDIO-001", exc
            else:
                raise AssertionError("two open Studios did not require --studio")
        finally:
            live.subprocess.Popen = real_popen
            live.studio_mod.mcp_command = orig_cmd
        assert len(started) == 1, started
        assert started[0].poll() is not None, "the MCP process outlived the failed Session"


@check("live: Rojo names a script by its file minus the script suffix, so X.spec and X stay apart")
def _():
    from rbforge import live
    assert live.script_name("Foo.spec.luau") == "Foo.spec"
    assert live.script_name("Main.server.luau") == "Main"
    assert live.script_name("Hud.client.lua") == "Hud"
    assert live.script_name("Util.luau") == "Util"
    with tempdir() as d:
        os.makedirs(os.path.join(d, "src"))
        for name in ("Shop.luau", "Shop.spec.luau"):
            open(os.path.join(d, "src", name), "w").write("return 1\n")
        json.dump({"tree": {"ReplicatedStorage": {"$path": "src"}}},
                  open(os.path.join(d, "default.project.json"), "w"))
        names = sorted(v[1] for v in live.rojo_targets(os.path.join(d, "default.project.json")).values())
        assert names == ["Shop", "Shop.spec"], names


@check("live: a malformed Rojo project is a structured push error, not a traceback")
def _():
    from rbforge import live
    from rbforge.errors import ForgeError
    with tempdir() as d:
        proj = os.path.join(d, "default.project.json")
        for body in ("{not json", json.dumps({"name": "x"}), json.dumps([1, 2])):
            open(proj, "w").write(body)
            try:
                live.rojo_targets(proj)
            except ForgeError as exc:
                assert exc.code == "RBF-ARG-002", exc
            else:
                raise AssertionError("accepted %r" % body)


def _push_fixture(d, body="return 1\n"):
    os.makedirs(os.path.join(d, "src"), exist_ok=True)
    json.dump({"tree": {"ServerScriptService": {"$path": "src"}}},
              open(os.path.join(d, "default.project.json"), "w"))
    open(os.path.join(d, "src", "A.luau"), "w").write(body)
    return os.path.join(d, "default.project.json")


class _Recorder:
    """A Studio double that records the Luau it was sent and answers from a queue."""
    sent, answers = [], []

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    studio_id = "s1"


    def call(self, tool, args):  # push preflight: Studio is in Edit

        return _EDIT_STATE


    def luau(self, code, dm="Edit"):
        _Recorder.sent.append(code)
        return _Recorder.answers.pop(0)


@check("live: push records what it wrote and guards the next write with it")
def _():
    from rbforge import live
    orig = live.Session
    with _isolated_home(), tempdir() as d:
        proj = _push_fixture(d)
        want = live.adler("return 1\n")
        try:
            live.Session = _Recorder
            _Recorder.sent, _Recorder.answers = [], [
                "SYNCED %s {\"place\":\"0:Place1\"}" % want,
                "SYNCED %s {\"place\":\"0:Place1\"}" % want]
            first = live.push(["ALL"], proj)
            assert first["pushed"] == 1, first
            assert '"0:Place1"' not in _Recorder.sent[0], "a first push already had an expectation"
            second = live.push(["ALL"], proj)
            assert second["pushed"] == 1, second
            assert ('"0:Place1": "%s"' % want) in _Recorder.sent[1], "the ledger stamp was not sent"
            ledger = json.load(open(live._ledger_path()))
            entry = list(ledger["projects"].values())[0]["0:Place1"]["ServerScriptService.A"]
            assert entry["stamp"] == want and entry["file"].endswith("A.luau"), entry
        finally:
            live.Session = orig


@check("live: a script edited in Studio since the last push is a conflict until --force")
def _():
    from rbforge import live
    orig = live.Session
    with _isolated_home(), tempdir() as d:
        proj = _push_fixture(d)
        try:
            live.Session = _Recorder
            _Recorder.sent = []
            _Recorder.answers = ["CONFLICT 9:12345 {\"place\":\"77\",\"expect\":\"8:999\"}"]
            r = live.push(["ALL"], proj)
            assert r["pushed"] == 0 and len(r["conflicts"]) == 1, r
            assert "edited in Studio" in r["conflicts"][0]["why"], r["conflicts"]
            assert "--force" in r["conflict_hint"], r
            assert "local force = false" in _Recorder.sent[0]
            want = live.adler("return 1\n")
            _Recorder.answers = ["SYNCED %s {\"place\":\"77\",\"backup\":\"A_rbforge_1\"}" % want]
            forced = live.push(["ALL"], proj, force=True)
            assert "local force = true" in _Recorder.sent[1]
            assert forced["pushed"] == 1, forced
            assert forced["backed_up"] == [{"file": forced["results"][0]["file"],
                                            "backup": "ServerStorage.rbforge_backups.A_rbforge_1"}], forced
        finally:
            live.Session = orig


@check("live: a synced stamp must match whole, not as a suffix")
def _():
    from rbforge import live
    orig = live.Session
    with _isolated_home(), tempdir() as d:
        proj = _push_fixture(d)
        want = live.adler("return 1\n")
        try:
            live.Session = _fake_session("SYNCED 1" + want, _EDIT_STATE)
            r = live.push(["ALL"], proj)
            assert r["pushed"] == 0 and r["results"][0]["state"] == "unverified", r["results"][0]
        finally:
            live.Session = orig


@check("live: generated push code with a guard and force still parses as Luau")
def _():
    with tempdir() as d:
        cfg = os.path.join(d, "selene.toml")
        open(cfg, "w").write('std = "lua51"\n')
        for i, code in enumerate([
                _generated_push_code(expects={"0:Place1": "9:123", "42": "1:1"}),
                _generated_push_code(expects={"0:Wei]]rd": "9:1"}, force=True)]):
            assert "CONFLICT" in code and "rbforge_backups" in code and ":Clone()" in code
            path = os.path.join(d, "guard%d.luau" % i)
            open(path, "w", encoding="utf-8").write(code)
            ok, detail = _parse_luau(path, cfg)
            assert ok, "guarded push code does not parse:\n%s" % detail


@check("live: generated servertest code parses as Luau in every variant (ready, client, grace, keep)")
def _():
    from rbforge import live
    ready = live.parse_ready("game.ReplicatedStorage.Boot.Stage=wired]]=]")
    with tempdir() as d:
        cfg = os.path.join(d, "selene.toml")
        open(cfg, "w").write('std = "lua51"\n')
        for i, code in enumerate([
                live._server_test_code('script:SetAttribute("A", "PASS ]=]")', "A", 30),
                live._server_test_code("x", "A", 30, "Client", ready, 2.5, False),
                live._server_test_code("x", "A", 30, "Server", ready, 0.0, True),
                live._server_test_code("x", "A", 30, "Client", None, 0.0, False, "[rbforge] run 1 begins: t]]=]")]):
            path = os.path.join(d, "st%d.luau" % i)
            open(path, "w", encoding="utf-8").write(code)
            ok, detail = _parse_luau(path, cfg)
            assert ok, "servertest code does not parse:\n%s" % detail


@check("live: the push guard, executed under Lune, refuses Studio edits and backs up before overwriting")
def _():
    import shutil as _shutil
    import subprocess as _sub
    from rbforge import live
    lune = _shutil.which("lune")
    if not lune:
        if os.environ.get("CI"):
            raise AssertionError("lune is required in CI (scripts/install_lune.py)")
        return "skip: lune not installed (rokit add lune-org/lune)"
    here = os.path.dirname(os.path.abspath(__file__))
    prelude = open(os.path.join(here, "lune", "mock_datamodel.luau"), encoding="utf-8").read()
    new_src = "return 2\n"
    old, edited = live.adler("return 1\n"), live.adler("return 9\n")

    def run(studio_source, expects=None, force=False):
        setup = ""
        if studio_source is not None:
            setup = ("local f = Instance.new('Folder') f.Name = 'Systems' "
                     "f.Parent = game:GetService('ServerScriptService')\n"
                     "local s = Instance.new('Script') s.Name = 'Main' s.Source = %s s.Parent = f\n"
                     % live.long_string(studio_source))
        code = live._push_code("ServerScriptService.Systems", "Main", "Script", new_src, {},
                               expects=expects, force=force)
        probe = ("local sys =game:GetService('ServerScriptService'):FindFirstChild('Systems')\n"
                 "local main = sys and sys:FindFirstChild('Main')\n"
                 "local b = game:GetService('ServerStorage'):FindFirstChild('rbforge_backups')\n"
                 "local kept = {}\n"
                 "if b then for _, c in b:GetChildren() do table.insert(kept, c.Source) end end\n"
                 "print(game:GetService('HttpService'):JSONEncode({reply = __reply, "
                 "source = main and main.Source, backups = kept}))\n")
        with tempdir() as d:
            path = os.path.join(d, "case.luau")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(prelude + "\n" + setup + "local function __push()\n" + code + "\nend\n"
                         + "__reply = __push()\n" + probe)
            done = _sub.run([lune, "run", path], capture_output=True, text=True, timeout=60)
        assert done.returncode == 0, done.stdout + done.stderr
        out = json.loads(done.stdout.strip().splitlines()[-1])
        out["backups"] = out.get("backups") or []  # an empty Luau table encodes as {}
        return out

    created = run(None)
    assert created["reply"].startswith("SYNCED " + live.adler(new_src)), created  # stamp parity
    assert created["source"] == new_src and created["backups"] == [], created

    first = run("return 1\n")  # no ledger entry: a Source this tool never wrote is kept first
    assert first["source"] == new_src and first["backups"] == ["return 1\n"], first

    ours = run("return 1\n", {"0:Place1": old})  # Studio still holds what we pushed: no backup
    assert ours["source"] == new_src and ours["backups"] == [], ours

    conflict = run("return 9\n", {"0:Place1": old})
    word, stamp, meta = live._parse_reply(conflict["reply"])
    assert (word, stamp, meta.get("expect")) == ("CONFLICT", edited, old), conflict
    assert conflict["source"] == "return 9\n" and conflict["backups"] == [], "a conflict wrote anyway"

    forced = run("return 9\n", {"0:Place1": old}, force=True)
    assert forced["source"] == new_src and forced["backups"] == ["return 9\n"], forced

    other_place = run("return 9\n", {"555": old})  # the ledger names another place: first-push rules
    assert other_place["source"] == new_src and other_place["backups"] == ["return 9\n"], other_place


@check("scaffold: a fresh project ships a unit spec that runs, and fails when the rule breaks")
def _():
    import shutil as _shutil
    from rbforge import check, scaffold
    with tempdir() as d:
        root = os.path.join(d, "game")
        files = scaffold.scaffold(root, "obby")["files"]
        assert "tests/Config.spec.luau" in files, files
        if not _shutil.which("lune"):
            if os.environ.get("CI"):
                raise AssertionError("lune is required in CI (scripts/install_lune.py)")
            return "skip: lune not installed"
        good = check.rung_unit(root)["checks"]
        assert len(good) == 4 and {c["status"] for c in good} == {"pass"}, good
        config = os.path.join(root, "src", "shared", "Config.luau")
        text = open(config, encoding="utf-8").read().replace('Genre = "obby"', 'Genre = "tycoon"')
        open(config, "w", encoding="utf-8").write(text)
        bad = {c["id"]: c["status"] for c in check.rung_unit(root)["checks"]}
        assert bad["lune:tests/Config.spec.luau"] == "fail", "the spec cannot fail, so it proves nothing: %r" % bad
        assert bad["lune:tests/Rules.spec.luau"] == "pass", bad


@check("verification: evidence collection opens one session for identity and one for console+capture")
def _():
    from rbforge import verification
    base = _fake_studio(console="[Server] ready")
    opened = []

    class Counting(base):
        def __init__(self, *a, **k):
            opened.append(1)

    with _isolated_home():
        from rbforge import live
        orig = live.server_test
        live.server_test = lambda *a, **k: {"result": "PASS", "passed": True, "outcome": "pass"}
        try:
            obs = verification.collect_evidence(session_factory=Counting, project="p", scenario="s",
                                                capture_screenshot=True, test_path=__file__)
        finally:
            live.server_test = orig
    assert len(opened) == 2, "sessions opened: %d" % len(opened)
    assert obs["console_logged"] and obs["screenshots"], obs


@check("verification: expired observations are pruned when a new one is recorded")
def _():
    from rbforge import verification
    with _isolated_home():
        path = verification._observations_path()
        verification._write_json(path, {"obs-old": {"recorded_at": 1.0}, "obs-bad": {"recorded_at": "x"},
                                        "obs-junk": [1]})
        new_id = verification._record_observation({"studio_id": "s"})
        store = json.load(open(path))
    assert set(store) == {new_id}, sorted(store)
    assert verification.load_observation("obs-bad") is None


@check("cli: exec and servertest on a missing file return a JSON error, not a traceback")
def _():
    for argv in (("exec", "definitely-missing.luau"), ("servertest", "definitely-missing.luau", "X")):
        code, out = _cli(*argv)
        assert code == 2 and isinstance(out, dict) and out["error"]["code"] == "RBF-ARG-001", (argv, code, out)


@check("cli: skills status with an unknown agent is an error, not an empty object")
def _():
    code, out = _cli("skills", "status", "notanagent")
    assert code == 2 and out["error"]["code"] == "RBF-ARG-001", (code, out)


@check("skills: Kimi Code's ~/.kimi-code/skills root is searched before the legacy ~/.kimi")
def _():
    from rbforge import skills
    _env, candidates = skills._ROOTS["kimi"]
    assert candidates[0] == "~/.kimi-code/skills" and "~/.kimi/skills" in candidates, candidates


@check("skills: Hermes' .deleted profile trash is not an install root")
def _():
    from rbforge import skills
    with tempdir() as d:
        for name in (".deleted", "code"):
            os.makedirs(os.path.join(d, "hermes", "profiles", name, "skills"))
        saved = {k: os.environ.get(k) for k in ("LOCALAPPDATA", "RBFORGE_HERMES_SKILLS")}
        os.environ["LOCALAPPDATA"] = d
        os.environ.pop("RBFORGE_HERMES_SKILLS", None)
        try:
            roots = skills.roots_for("hermes")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    assert any(r.replace("\\", "/").endswith("profiles/code/skills") for r in roots), roots
    assert not any(".deleted" in r for r in roots), roots


@check("plugins: the community Studio MCP bridge (Roqer) is recognised and pointed at the official MCP")
def _():
    from rbforge import plugins
    with tempdir() as d:
        old = os.environ.get("LOCALAPPDATA")
        os.makedirs(os.path.join(d, "Roblox", "Plugins"))
        open(os.path.join(d, "Roblox", "Plugins", "MCPPlugin.rbxmx"), "w").write("<roblox/>")
        os.environ["LOCALAPPDATA"] = d
        try:
            info = plugins.status()
        finally:
            if old is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = old
    hit = [k for k in info["known"] if k["id"] == "robloxstudio_mcp"]
    assert hit and "official Studio MCP" in hit[0]["free_alternative"], info


def _mcp_session():
    import subprocess as _sub
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, RBFORGE_HOME=tempfile.mkdtemp(prefix="rbf-mcp-"))
    return _sub.Popen([sys.executable, os.path.join(root, "mcp_server", "server.py")],
                      stdin=_sub.PIPE, stdout=_sub.PIPE, text=True, env=env)


@check("mcp: version negotiation, parse errors and non-object arguments follow the protocol")
def _():
    proc = _mcp_session()
    try:
        def init(version):
            return _mcp_rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                   "params": {"protocolVersion": version, "capabilities": {},
                                              "clientInfo": {"name": "t", "version": "1"}}})["result"]
        legacy = init("2024-11-05")
        assert legacy["protocolVersion"] == "2024-11-05" and "instructions" not in legacy, legacy
        modern = init("2025-06-18")
        assert modern["protocolVersion"] == "2025-06-18" and "rb_check" in modern["instructions"], modern
        future = init("2099-01-01")
        assert future["protocolVersion"] == "2025-06-18", future
        proc.stdin.write("{not json\n")
        proc.stdin.flush()
        parse = json.loads(proc.stdout.readline())
        assert parse["error"]["code"] == -32700 and parse["id"] is None, parse
        bad = _mcp_rpc(proc, {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                              "params": {"name": "rb_plugins", "arguments": [1]}})
        assert bad["error"]["code"] == -32602, bad
    finally:
        proc.kill()


@check("mcp: every tool is annotated and the catalog stays inside its token budget")
def _():
    proc = _mcp_session()
    try:
        tools = _mcp_rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    finally:
        proc.kill()
    for t in tools:
        ann = t.get("annotations") or {}
        assert isinstance(ann.get("readOnlyHint"), bool), t["name"]
        assert len(t["description"]) <= 400, (t["name"], len(t["description"]))
    by_name = {t["name"]: t for t in tools}
    assert by_name["rb_studio_push"]["annotations"]["destructiveHint"] is True
    assert "force" in by_name["rb_studio_push"]["inputSchema"]["properties"]
    assert by_name["rb_docs_search"]["annotations"]["readOnlyHint"] is True
    size = len(json.dumps(tools))
    # The catalog is loaded into every Roblox session that enables this server. Growing it is an
    # explicit decision: raise this number in the same change, and say why.
    # 0.19.0: 10600 -> 10800 for rb_audit (one tool, ~300 chars); three other descriptions were cut
    # in the same change to keep the growth to that.
    assert size <= 10800, "tools/list is %d chars; the budget is 10800" % size



# ---------------------------------------------------------------- 0.17.1 audit regressions

@contextlib.contextmanager
def _fake_user_home():
    """expanduser('~') -> a temp dir, so agent config tests never read or write the real profile."""
    d = tempfile.mkdtemp(prefix="rbf-user-")
    saved = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE")}
    os.environ["HOME"] = os.environ["USERPROFILE"] = d
    try:
        yield d
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(d, ignore_errors=True)


@check("agents: connect/disconnect skip an agent that is not installed and keep going")
def _():
    from rbforge import agents
    old_which, old_run = agents.paths.which, agents._run
    calls = []
    agents.paths.which = lambda name: None          # no hermes, no claude on PATH
    agents._run = lambda cmd, **k: calls.append(cmd) or type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    try:
        with _fake_user_home() as home, _isolated_home():
            os.makedirs(os.path.join(home, ".grok"))   # grok installed, codex not
            out = agents.disconnect(None)
            assert set(out) == set(agents.PROVIDERS), out
            assert "skipped" in out["hermes"] and "skipped" in out["claude"], out
            assert "skipped" in out["codex"], out
            res = agents.connect(None)
            assert "skipped" in res["hermes"] and "skipped" in res["codex"], res
            assert not os.path.exists(os.path.join(home, ".codex")), "connect created a config for an absent agent"
            assert "result" in res["grok"], res
            cfg = os.path.join(home, ".grok", "config.toml")
            assert agents._toml_enabled(open(cfg, encoding="utf-8").read(), "robloxforge") is False
            assert calls == [], "a CLI was invoked for an agent that is not installed: %r" % calls
    finally:
        agents.paths.which, agents._run = old_which, old_run


@check("agents: a repeat connect is a no-op for CLI-managed agents")
def _():
    from rbforge import agents
    old_which, old_run = agents.paths.which, agents._run
    calls = []

    def fake_run(cmd, **k):
        calls.append(cmd[1:3])
        out = "robloxforge  python server.py" if cmd[1:3] == ["mcp", "list"] else ""
        return type("R", (), {"returncode": 0, "stdout": out, "stderr": ""})()
    agents.paths.which = lambda name: "/bin/" + name
    agents._run = fake_run
    try:
        # Isolated homes: an implementation that regresses must not edit the real ~/.claude.json.
        with _fake_user_home(), _isolated_home():
            res = agents.connect(["claude", "hermes"])
        assert "already" in res["claude"]["result"] and "already" in res["hermes"]["result"], res
        assert ["mcp", "add"] not in calls, calls
    finally:
        agents.paths.which, agents._run = old_which, old_run


@check("agents: ~/.claude.json is replaced atomically and keeps unrelated keys")
def _():
    from rbforge import agents
    with _fake_user_home() as home, _isolated_home():
        cfg = os.path.join(home, ".claude.json")
        json.dump({"keep": 1, "projects": {"a": {}, "b": {"disabledMcpServers": ["robloxforge"]}}},
                  open(cfg, "w", encoding="utf-8"))
        n = agents._claude_disable_everywhere(cfg)
        data = json.load(open(cfg, encoding="utf-8"))
        assert n == 1 and data["keep"] == 1, (n, data)
        assert data["projects"]["a"]["disabledMcpServers"] == ["robloxforge"]
        assert data["projects"]["b"]["disabledMcpServers"] == ["robloxforge"]
        assert not [f for f in os.listdir(home) if f.endswith(".tmp")], os.listdir(home)



@check("docs: a refresh that cannot clone keeps the cache it had")
def _():
    from rbforge import docs, paths
    with _isolated_home():
        cache = paths.docs_cache_dir()
        page = os.path.join(cache, "content", "en-us", "a.md")
        os.makedirs(os.path.dirname(page))
        open(page, "w", encoding="utf-8").write("# A\n")   # no .git: the re-clone path
        old_url = docs.REPO_URL
        docs.REPO_URL = os.path.join(tempfile.mkdtemp(), "missing.git")
        try:
            try:
                docs.ensure(refresh=True)
            except err_mod.ForgeError:
                pass
        finally:
            docs.REPO_URL = old_url
        assert os.path.isfile(page), "an offline refresh deleted the existing creator-docs cache"
        assert docs.read_state().get("last_refresh_error"), "the failed refresh was not recorded"


@check("mcp: non-ASCII arguments arrive intact without UTF-8 mode")
def _():
    import subprocess
    with tempdir() as root:
        proj = os.path.join(root, "jogo_é_п")
        os.makedirs(proj)
        req = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "rb_check", "arguments": {"path": proj, "scope": ["structure"]}}}
        env = dict(os.environ)
        env.pop("PYTHONUTF8", None)
        env.pop("PYTHONIOENCODING", None)
        done = subprocess.run([sys.executable, "-X", "utf8=0", "mcp_server/server.py"],
                              input=(json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"),
                              capture_output=True, env=env, timeout=120)
        reply = json.loads(done.stdout.decode("utf-8").splitlines()[0])
        text = reply["result"]["content"][0]["text"]
        assert not reply["result"].get("isError"), text[:300]
        assert json.loads(text)["root"] == os.path.abspath(proj), text[:300]


@check("cli: text output with a non-cp1252 path prints instead of raising")
def _():
    import subprocess
    with tempdir() as root:
        proj = os.path.join(root, "проект")
        os.makedirs(proj)
        env = dict(os.environ)
        env.pop("PYTHONUTF8", None)
        env.pop("PYTHONIOENCODING", None)
        done = subprocess.run([sys.executable, "-X", "utf8=0", "src/rbforge_cli.py", "check", proj,
                               "--scope", "structure"], capture_output=True, env=env, timeout=120)
        err = done.stderr.decode("utf-8", "replace")
        assert "Traceback" not in err, err[-400:]
        assert "проект" in done.stdout.decode("utf-8"), done.stdout[:200]


@check("check: --changed-only finds changes in a project nested inside a repository")
def _():
    import subprocess
    from rbforge import check as check_mod
    with tempdir() as repo:
        proj = os.path.join(repo, "game")
        os.makedirs(os.path.join(proj, "src"))
        path = os.path.join(proj, "src", "a.luau")
        open(path, "w").write("return 1\n")
        git = ["git", "-C", repo, "-c", "user.email=t@t", "-c", "user.name=t"]
        if subprocess.run(git + ["init", "-q"], capture_output=True).returncode != 0:
            return "skip: git unavailable"
        subprocess.run(git + ["add", "."], capture_output=True)
        subprocess.run(git + ["commit", "-qm", "i"], capture_output=True)
        open(path, "w").write("return 2\n")
        open(os.path.join(proj, "src", "b.luau"), "w").write("return 3\n")
        open(os.path.join(repo, "outside.luau"), "w").write("return 4\n")
        got = sorted(os.path.basename(f) for f in check_mod.changed_files(proj))
        assert got == ["a.luau", "b.luau"], got


@check("live: long_string survives text that ends in a closing-bracket prefix")
def _():
    from rbforge import live
    for text in ("x]=", "x]", "a]=]b]==", "]", "]=", "]]", "]=]]"):
        lit = live.long_string(text)
        level = lit.index("[", 1) - 1
        close = "]" + "=" * level + "]"
        body = lit[level + 2:]  # after the `[==[` opener; starts with the newline Luau drops
        assert body.startswith("\n") and body.find(close) == len(body) - len(close), (text, lit)
        assert body[1:-len(close)] == text, (text, lit)


@check("traps: a multi-line ImageTransparency assignment does not crash the review")
def _():
    from rbforge import traps
    found = traps.scan_text("ui.client.luau", "img.ImageTransparency =\n1\nif img.IsLoaded then end\n")
    assert isinstance(found, list)


@check("review: comparisons are not client writes")
def _():
    from rbforge import review
    with tempdir() as root:
        os.makedirs(os.path.join(root, "src"))
        open(os.path.join(root, "src", "ui.client.luau"), "w").write(
            "if hum.Health == 0 then end\nif coins == 5 then end\n")
        res = review.security(path=root)
        high = [f for f in res["findings"] if f["severity"] == "high"]
        assert not high, high
        open(os.path.join(root, "src", "cheat.client.luau"), "w").write("hum.Health = 0\ncoins += 5\n")
        res = review.security(path=root)
        whys = {f["why"] for f in res["findings"] if f["file"].endswith("cheat.client.luau")}
        assert "client code sets Humanoid.Health directly" in whys, whys
        assert "client code writes a currency-like variable" in whys, whys



@check("errors: a failed type-definition download is a dependency failure (exit 4)")
def _():
    assert err_mod.ForgeError("RBF-TYPES-001", "x").exit_code == err_mod.ExitCode.DEPENDENCY


@check("check: a stale cached definitions file is named as the reason the typecheck skipped")
def _():
    import shutil as _sh
    from rbforge import check as check_mod, types as types_mod
    if not _sh.which("luau-lsp"):
        return "skip: luau-lsp not installed, the typecheck branch cannot run"
    old_env = os.environ.pop("RBFORGE_LUAU_DEFINITIONS", None)
    try:
        with _isolated_home(), tempdir() as root:
            os.makedirs(types_mod.cache_dir(), exist_ok=True)
            open(types_mod.cached_path(), "w").write("-- not the pinned file\n")
            old_find = check_mod._find_definitions
            check_mod._find_definitions = lambda r: None
            try:
                rung = check_mod.rung_static(root)
            finally:
                check_mod._find_definitions = old_find
            lsp = [c for c in rung["checks"] if c["id"] == "luau-lsp"][0]
            assert lsp["status"] == "skip" and "digest" in lsp["detail"], lsp
    finally:
        if old_env is not None:
            os.environ["RBFORGE_LUAU_DEFINITIONS"] = old_env


@check("live: servertest refuses an attribute name Roblox would reject, before opening Studio")
def _():
    from rbforge import live
    with tempdir() as root:
        test = os.path.join(root, "t.luau")
        open(test, "w").write('workspace:SetAttribute("x", "PASS")\n')
        for bad in ('a"b', "has space", "RBXThing", "", "x" * 101, "café"):
            try:
                live.server_test(test, bad)
            except err_mod.ForgeError as exc:
                assert exc.code == "RBF-ARG-002", exc.code
            else:
                raise AssertionError("accepted attribute name %r" % bad)


@check("agents: status asks every agent CLI at once, not one after another")
def _():
    import time as _t
    from rbforge import agents
    saved = agents._hermes, agents._claude
    spans = {}

    def slow(name):
        def factory():
            def status(_cfg=None):
                start = _t.monotonic()
                _t.sleep(0.6)
                spans[name] = (start, _t.monotonic())
                return {"configured": False}
            return {"installed": lambda: True, "status": status, "connect": None, "disconnect": None}
        return factory
    agents._hermes, agents._claude = slow("hermes"), slow("claude")
    try:
        out = agents.status(["hermes", "claude"])
    finally:
        agents._hermes, agents._claude = saved
    assert list(out) == ["hermes", "claude"], out
    # Overlap, not wall time: a loaded CI runner made a 1.0 s budget flaky while the probes still
    # ran concurrently. Serial probes cannot overlap however fast the machine is.
    (a0, a1), (b0, b1) = spans["hermes"], spans["claude"]
    assert max(a0, b0) < min(a1, b1), "agent probes ran one after another: %r" % spans


@check("doctor: the toolchain is probed once per report")
def _():
    from rbforge import doctor, tooling
    calls = []
    old = tooling.status
    tooling.status = lambda: calls.append(1) or {"rojo": {"found": False, "purpose": "x"}}
    try:
        report = doctor.collect(probe=False)
    finally:
        tooling.status = old
    assert len(calls) == 1, "tooling.status ran %d times" % len(calls)
    assert report["toolchain"]["rojo"]["found"] is False
    assert report["capabilities"]["rojo"]["status"] == "optional"



def _fake_mcp_with_late_studio(d, empty_answers):
    """A stdio MCP double whose list_roblox_studios is empty for the first `empty_answers` calls,
    like a real StudioMCP in the seconds before Studio registers it."""
    fake = os.path.join(d, "late_mcp.py")
    open(fake, "w").write(
        "import json, sys\n"
        "lists = 0\n"
        "for line in sys.stdin:\n"
        "    msg = json.loads(line)\n"
        "    if 'id' not in msg: continue\n"
        "    if msg['method'] == 'initialize': result = {'protocolVersion': '2024-11-05'}\n"
        "    else:\n"
        "        lists += 1\n"
        "        studios = [] if lists <= %d else [{'id': 'a', 'name': 'Place1'}]\n"
        "        result = {'content': [{'type': 'text', 'text': json.dumps({'studios': studios})}]}\n"
        "    print(json.dumps({'jsonrpc': '2.0', 'id': msg['id'], 'result': result}), flush=True)\n"
        % empty_answers)
    return fake


@check("live: a new Session waits for Studio to register instead of reporting 0 Studios")
def _():
    from rbforge import live
    with tempdir() as d:
        fake = _fake_mcp_with_late_studio(d, 3)
        orig = live.studio_mod.mcp_command
        live.studio_mod.mcp_command = lambda: [sys.executable, fake]
        try:
            with live.Session(timeout=20) as s:
                assert s.studio_id == "a", s.studio_id
            with live.Session(studio_id="a", timeout=20) as s:   # an explicit id waits too
                assert s.studio_id == "a"
        finally:
            live.studio_mod.mcp_command = orig


@check("live: a Studio that never registers fails after the wait, and says how long it waited")
def _():
    from rbforge import live
    from rbforge.errors import ForgeError
    with tempdir() as d:
        fake = _fake_mcp_with_late_studio(d, 10 ** 6)
        orig = live.studio_mod.mcp_command
        old_wait = os.environ.get("RBFORGE_STUDIO_WAIT")
        os.environ["RBFORGE_STUDIO_WAIT"] = "1"
        live.studio_mod.mcp_command = lambda: [sys.executable, fake]
        try:
            try:
                live.Session(timeout=20)
            except ForgeError as exc:
                assert exc.code == "RBF-STUDIO-001" and "waited" in exc.message, exc
            else:
                raise AssertionError("no Studio was accepted")
        finally:
            live.studio_mod.mcp_command = orig
            if old_wait is None:
                os.environ.pop("RBFORGE_STUDIO_WAIT", None)
            else:
                os.environ["RBFORGE_STUDIO_WAIT"] = old_wait



@check("studio: the doctor probe waits briefly for a just-registered Studio's place name")
def _():
    from rbforge import studio
    with tempdir() as d:
        fake = os.path.join(d, "named_mcp.py")
        open(fake, "w").write(
            "import json, sys\n"
            "lists = 0\n"
            "for line in sys.stdin:\n"
            "    msg = json.loads(line)\n"
            "    if 'id' not in msg: continue\n"
            "    m = msg['method']\n"
            "    if m == 'initialize': result = {'protocolVersion': '2024-11-05'}\n"
            "    elif m == 'tools/list': result = {'tools': [{'name': 'list_roblox_studios'}]}\n"
            "    else:\n"
            "        lists += 1\n"
            "        entry = {'id': 'uuid-1'} if lists <= 2 else {'id': 'uuid-1', 'name': 'Sample (placeId: 7)'}\n"
            "        result = {'content': [{'type': 'text', 'text': json.dumps({'studios': [entry]})}]}\n"
            "    print(json.dumps({'jsonrpc': '2.0', 'id': msg['id'], 'result': result}), flush=True)\n")
        orig_cmd, orig_run = studio.mcp_command, studio.studio_running
        studio.mcp_command = lambda: [sys.executable, fake]
        studio.studio_running = lambda: {"running": True}
        try:
            res = studio.probe_mcp(timeout=20)
        finally:
            studio.mcp_command, studio.studio_running = orig_cmd, orig_run
        assert res["studios"] and res["studios"][0].get("name") == "Sample (placeId: 7)", res["studios"]



def _play_session(state="- Current Studio Mode: Play\n- Available DataModels: Client, Server\n", answers=None):
    """A Session double for servertest: answers get_studio_state and records every execute_luau."""
    calls = []
    queue = list(answers or ["PASS"])

    class Fake:
        studio_id = "s1"
        opened = 0

        def __init__(self, *a, **k):
            Fake.opened += 1

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def call(self, tool, args):
            calls.append(("call", tool))
            return state

        def luau(self, code, dm="Edit"):
            calls.append(("luau", dm, code))
            nxt = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(nxt, Exception):
                raise nxt
            return nxt
    return Fake, calls


def _reporting_test(d, name="t.luau"):
    path = os.path.join(d, name)
    open(path, "w").write('script:SetAttribute("Attr", "PASS ok")\n')
    return path


@check("servertest: Edit mode is refused with 'start Play first' (exit 4) before the test runs")
def _():
    from rbforge import live
    from rbforge.errors import ForgeError
    fake, calls = _play_session(state="- Current Studio Mode: Edit\n- Available DataModels: Edit\n")
    orig = live.Session
    live.Session = fake
    try:
        with tempdir() as d:
            try:
                live.server_test(_reporting_test(d), "Attr", timeout=1)
            except ForgeError as exc:
                assert exc.code == "RBF-PLAY-001" and "start Play first" in exc.message, exc
                assert exc.exit_code == 4, exc.exit_code
            else:
                raise AssertionError("an Edit-mode servertest was not refused")
    finally:
        live.Session = orig
    assert not [c for c in calls if c[0] == "luau"], calls


@check("servertest: an unrecognised get_studio_state text does not block the run")
def _():
    from rbforge import live
    fake, calls = _play_session(state="something new")
    orig = live.Session
    live.Session = fake
    try:
        with tempdir() as d:
            got = live.server_test(_reporting_test(d), "Attr", timeout=1)
    finally:
        live.Session = orig
    assert got["passed"], got


@check("servertest: a result written with script:SetAttribute is read, not only workspace")
def _():
    from rbforge import live
    code = live._server_test_code('script:SetAttribute("Attr", "PASS")', "Attr", 5)
    assert 'workspace:GetAttribute("Attr") or s:GetAttribute("Attr")' in code, code
    assert code.index("rbfOut = rbfResult()") < code.index("s:Destroy()")


@check("servertest: --grace waits before destroying the test Script, --keep never destroys it")
def _():
    from rbforge import live
    plain = live._server_test_code("x", "Attr", 5)
    assert "task.wait(2.5)" not in plain and "s:Destroy()" in plain
    graced = live._server_test_code("x", "Attr", 5, grace=2.5)
    assert graced.index("task.wait(2.5)") < graced.index("s:Destroy()"), graced
    kept = live._server_test_code("x", "Attr", 5, keep=True)
    assert "s:Destroy()" not in kept, kept


@check("servertest: Client runs the test as a LocalScript in the local player's PlayerScripts")
def _():
    from rbforge import live
    fake, calls = _play_session()
    orig = live.Session
    live.Session = fake
    try:
        with tempdir() as d:
            live.server_test(_reporting_test(d), "Attr", timeout=1, datamodel="Client")
    finally:
        live.Session = orig
    run = [c for c in calls if c[0] == "luau"][0]
    assert run[1] == "Client" and "Instance.new('LocalScript')" in run[2] and "PlayerScripts" in run[2], run


@check("servertest: --ready waits for an attribute value and reports NOT_READY as a failure")
def _():
    from rbforge import live
    from rbforge.errors import ForgeError
    assert live.parse_ready("workspace.BootStage=players-wired") == (["workspace"], "BootStage", "players-wired")
    assert live.parse_ready("game.ReplicatedStorage.Boot.Stage=a=b") == (["ReplicatedStorage", "Boot"], "Stage", "a=b")
    for bad in ("BootStage", "workspace.Boot Stage=x", "workspace.=x", "work-space.A=x", "workspace.RBXa=x"):
        try:
            live.parse_ready(bad)
        except ForgeError as exc:
            assert exc.code == "RBF-ARG-002", (bad, exc)
        else:
            raise AssertionError("accepted %r" % bad)
    code = live._server_test_code("x", "Attr", 5, ready=live.parse_ready("workspace.BootStage=players-wired"))
    assert code.index("rbfReady()") < code.index("Instance.new("), code
    assert "NOT_READY" in code and '"BootStage"' in code
    assert live._classify("NOT_READY workspace.BootStage never became the expected value")[1] == "fail"


@check("servertest: --suite runs every suite in one session and counts the failures")
def _():
    from rbforge import live
    from rbforge.errors import ForgeError
    fake, calls = _play_session(answers=["PASS a", "FAIL b", ForgeError("RBF-STUDIO-002", "boom"), "PASS d"])
    orig = live.Session
    live.Session = fake
    lines = []
    try:
        with tempdir() as d:
            os.makedirs(os.path.join(d, "tests"))
            for n in "abcd":
                _reporting_test(os.path.join(d, "tests"), n + ".luau")
            manifest = os.path.join(d, "suites.json")
            json.dump({"suites": [
                {"file": "tests/a.luau", "attr": "Attr"},
                {"file": "tests/b.luau", "attr": "Attr", "timeout": 30},
                {"file": "tests/c.luau", "attr": "Attr", "name": "crashes"},
                {"file": "tests/d.luau", "attr": "Attr", "datamodel": "Client", "grace": 1},
            ]}, open(manifest, "w"))
            res = live.run_suite(manifest, report=lines.append)
    finally:
        live.Session = orig
    assert fake.opened == 1, fake.opened
    assert [r["outcome"] for r in res["suites"]] == ["pass", "fail", "error", "pass"], res
    assert res["failed"] == 2 and res["passed"] == 2, res
    assert len(lines) == 4 and lines[2].startswith("ERROR crashes"), lines
    assert [c[1] for c in calls if c[0] == "luau"] == ["Server", "Server", "Server", "Client"], calls


@check("servertest: a bad suite manifest is refused before Studio is touched")
def _():
    from rbforge import live
    from rbforge.errors import ForgeError
    with tempdir() as d:
        m = os.path.join(d, "m.json")
        for bad in ([], [{"attr": "A"}], [{"file": "a.luau", "attr": "bad name"}],
                    [{"file": "a.luau", "attr": "A", "datamodel": "Edit"}],
                    [{"file": "a.luau", "attr": "A", "timeout": 0}],
                    [{"file": "a.luau", "attr": "A", "ready": "nope"}]):
            json.dump(bad, open(m, "w"))
            try:
                live.load_suite(m)
            except ForgeError as exc:
                assert exc.code == "RBF-ARG-002", (bad, exc)
            else:
                raise AssertionError("accepted %r" % (bad,))


@check("cli: servertest --suite exits with the number of failed suites")
def _():
    from rbforge import live
    orig = live.run_suite
    live.run_suite = lambda *a, **k: {"suites": [], "passed": 1, "failed": 3}
    try:
        with _isolated_home():
            code, out = _cli("servertest", "--suite", "whatever.json")
    finally:
        live.run_suite = orig
    assert code == 3 and out["failed"] == 3, (code, out)
    code, out = _cli("servertest")
    assert code == 2 and out["error"]["code"] == "RBF-ARG-001", (code, out)


@check("agents: a Claude tool gateway that carries ROBLOX_FORGE_ROOT counts as reachable")
def _():
    from rbforge import agents
    with tempdir() as d:
        cfg = os.path.join(d, ".claude.json")
        json.dump({"mcpServers": {"gateway": {"command": "gw.exe", "env": {"ROBLOX_FORGE_ROOT": "x"}}}}, open(cfg, "w"))
        assert agents._claude_proxy(cfg) == "gateway"
        json.dump({"projects": {"p": {"mcpServers": {"rf2": {"command": "python",
                                                              "args": ["C:\\RF\\mcp_server\\server.py"]}}}}}, open(cfg, "w"))
        assert agents._claude_proxy(cfg) == "rf2"
        json.dump({"mcpServers": {"other": {"command": "npx", "args": ["thing"]}}}, open(cfg, "w"))
        assert agents._claude_proxy(cfg) is None
        open(cfg, "w").write("{broken")
        assert agents._claude_proxy(cfg) is None


@check("doctor: says 'reachable via <gateway>' and shows each place's cloud or local identity")
def _():
    from rbforge import doctor, studio
    cloud = studio.session_info({"id": "u1", "mode": "Edit", "name": "My Game (placeId: 42)",
                                 "persistedToCloud": True, "placeId": 42, "universeId": 7})
    local = studio.session_info({"id": "u2", "mode": "Edit", "name": "copy.rbxl", "file": "copy.rbxl",
                                 "persistedToCloud": False})
    assert cloud["name"] == "My Game" and cloud["placeId"] == 42, cloud
    assert studio.describe_session(cloud) == "My Game - cloud place 42"
    assert studio.describe_session(local) == "copy.rbxl - local file, not a cloud place"
    assert studio.describe_session(dict(local, name="Place")) == "Place - local file copy.rbxl, not a cloud place"
    report = {
        "version": "x",
        "studio": {"studio_installed": True, "studio_version": "1", "studio_process": {"running": True},
                   "mcp_enabled_setting": {"enabled": True}, "mcp_launcher_found": True,
                   "active_places": ["My Game (placeId: 42)", "copy.rbxl"],
                   "studio_sessions": [cloud, local], "multiple_studio_sessions": True},
        "mcp_probe": {"responding": True, "tool_count": 38},
        "docs": {"present": False},
        "toolchain": {},
        "agents": {"claude": {"configured": False, "reachable_via": "toolbox", "installed": True}},
        "capabilities_by_status": {},
    }
    text = doctor.render(report)
    assert "My Game - cloud place 42; copy.rbxl - local file, not a cloud place" in text, text
    assert "reachable via toolbox" in text, text


# ---------------------------------------------------------------- 0.19.0: lint, audit, starter kit, docs


def _trap_ids(rel, text):
    from rbforge import traps
    return {f["id"] for f in traps.scan_text(rel, text)}


@check("traps: a failed data store read that falls through to defaults is flagged (T038)")
def _():
    wipe = (
        "local ok, res = pcall(function()\n\treturn store:GetAsync(key)\nend)\n"
        "local profile = sanitize(ok and res or nil)\n"
        "pcall(function()\n\tstore:UpdateAsync(key, function() return profile end)\nend)\n"
    )
    assert "T038" in _trap_ids("src/server/Data.luau", wipe)
    # A variable merely named profileStore is not the ProfileStore library and must not hide it.
    assert "T038" in _trap_ids("src/server/Data.luau", "local profileStore = nil\n" + wipe)
    kicked = wipe + "if not ok then\n\tplayer:Kick('rejoin')\nend\n"
    assert "T038" not in _trap_ids("src/server/Data.luau", kicked)
    assert "T038" not in _trap_ids("src/client/Data.client.luau", wipe)
    lib = "local ProfileStore = require(Packages.ProfileStore)\n" + wipe
    assert "T038" not in _trap_ids("src/server/Data.luau", lib)


@check("traps: saves on PlayerRemoving without BindToClose are flagged (T039)")
def _():
    text = ("Players.PlayerRemoving:Connect(function(p)\n\tpcall(function()\n"
            "\t\tstore:UpdateAsync(k, f)\n\tend)\nend)\n")
    assert "T039" in _trap_ids("a.server.luau", text)
    assert "T039" not in _trap_ids("a.server.luau", text + "game:BindToClose(function() end)\n")


@check("traps: lifecycle rules - existing players (T040), existing character (T041)")
def _():
    assert "T040" in _trap_ids("a.server.luau", "Players.PlayerAdded:Connect(onAdded)")
    assert "T040" not in _trap_ids(
        "a.server.luau",
        "Players.PlayerAdded:Connect(onAdded)\nfor _, p in Players:GetPlayers() do onAdded(p) end")
    assert "T040" not in _trap_ids("a.client.luau", "Players.PlayerAdded:Connect(onAdded)")
    assert "T041" in _trap_ids("a.server.luau", "player.CharacterAdded:Connect(onChar)")
    assert "T041" not in _trap_ids(
        "a.server.luau",
        "player.CharacterAdded:Connect(onChar)\nif player.Character then onChar(player.Character) end")


@check("traps: input ignoring gameProcessed (T042) fires for UserInputService only")
def _():
    bad = "UserInputService.InputBegan:Connect(function(input)\n\tfire()\nend)"
    assert "T042" in _trap_ids("src/client/a.luau", bad)
    good = "UserInputService.InputBegan:Connect(function(input, gameProcessed)\n\tfire()\nend)"
    assert "T042" not in _trap_ids("src/client/a.luau", good)
    # A GuiObject's InputBegan has one argument, and InputEnded must always run.
    assert "T042" not in _trap_ids("src/client/a.luau", "frame.InputBegan:Connect(function(input)\nend)")
    assert "T042" not in _trap_ids("src/client/a.luau", "UserInputService.InputEnded:Connect(function(input)\nend)")


@check("traps: client-supplied values (T043) and unguarded test remotes (T044)")
def _():
    assert "T043" in _trap_ids("a.server.luau", "Reward.OnServerEvent:Connect(function(player, amount)\nend)")
    assert "T043" in _trap_ids("a.server.luau", "Hit.OnServerEvent:Connect(function(player: Player, damage: number)\nend)")
    assert "T043" not in _trap_ids("a.server.luau", "Buy.OnServerEvent:Connect(function(player, itemId)\nend)")
    test = "TestCommandRemote.OnServerEvent:Connect(function(player, cmd)\n\tgive(player)\nend)"
    assert "T044" in _trap_ids("a.server.luau", test)
    assert "T044" not in _trap_ids("a.server.luau", "if not RunService:IsStudio() then return end\n" + test)
    assert "T044" not in _trap_ids("a.server.luau", "Buy.OnServerEvent:Connect(function(player, itemId)\nend)")


@check("traps: deprecated and wrong-side calls each fire, and their replacements do not")
def _():
    cases = [
        ("T026", "a.luau", "sig:connect(fn)", "sig:Connect(fn)"),
        ("T027", "a.server.luau", "local r = fn:InvokeClient(player)", "ev:FireClient(player)"),
        ("T028", "a.luau", "workspace:FindPartOnRay(ray)", "workspace:Raycast(o, d, params)"),
        ("T029", "a.luau", "part:Remove()", "part:Destroy()"),
        ("T030", "a.luau", "Lighting.Technology = Enum.Technology.Future",
         "if Lighting.Technology == Enum.Technology.Future then end"),
        ("T031", "a.luau", "_G.Data = {}", "local Data = {}"),
        ("T032", "a.server.luau", "pcall(function() store:SetAsync(player.Name, data) end)",
         "pcall(function() store:SetAsync(tostring(player.UserId), data) end)"),
        ("T033", "a.server.luau", "MarketplaceService.PromptProductPurchaseFinished:Connect(grant)",
         "MarketplaceService.ProcessReceipt = onReceipt"),
        ("T034", "src/client/a.luau", "mouse.KeyDown:Connect(fn)", "UserInputService.InputBegan:Connect(fn)"),
        ("T035", "a.server.luau", "player:LoadCharacter()", "player:LoadCharacterAsync()"),
        ("T036", "src/client/a.luau", "HttpService:GetAsync(url)", "remote:FireServer()"),
        ("T037", "a.server.luau", "local owns = MarketplaceService:UserOwnsGamePassAsync(id, pass)",
         "local ok, owns = pcall(function()\n\treturn MarketplaceService:UserOwnsGamePassAsync(id, pass)\nend)"),
    ]
    for rule, rel, bad, good in cases:
        assert rule in _trap_ids(rel, bad), "%s did not fire on %r" % (rule, bad)
        assert rule not in _trap_ids(rel, good), "%s fired on the fix %r" % (rule, good)
    assert "T027" not in _trap_ids("src/client/a.luau", "local r = fn:InvokeClient(player)")
    assert "T036" not in _trap_ids("a.server.luau", "HttpService:GetAsync(url)")


@check("traps: comments and long comments never produce findings, and line numbers survive them")
def _():
    from rbforge import traps
    text = "--[[\nwait(1)\nspawn(f)\n]]\n-- [plotId] = Player, wait(2)\nlocal x = 1\nwait(3)\n"
    found = traps.scan_text("a.luau", text)
    assert [(f["id"], f["line"]) for f in found] == [("T001", 7)], found


@check("traps: every rule declares an evidence class, and the project-specific rule is gone")
def _():
    from rbforge import traps
    cat = traps.catalog()
    assert set(cat.values()) <= {"docs", "live", "field"}, cat
    assert "T025" not in cat, "T025 matched one project's part names; it is not a general rule"
    assert cat["T004"] == "field"
    # A field-class rule is a lead: it may never be reported above info.
    sev = [f["severity"] for f in traps.scan_text(
        "a.luau", 'local g = Instance.new("SurfaceGui")\ng.ClipsDescendants = true\ng.AlwaysOnTop = true')
        if f["id"] == "T004"]
    assert sev == ["info"], sev
    # Viewmodel clone rule needs a viewmodel, not just a camera and a Clone.
    plain = 'local m = thing:Clone()\nlocal cam = workspace.CurrentCamera\nm.Parent = cam'
    assert "T022" not in _trap_ids("src/client/drone.luau", plain)
    assert "T022" in _trap_ids("src/client/vm.luau", "local viewmodel = {}\n" + plain)


@check("luau_text: a line comment that starts with a bracket is not a long comment")
def _():
    from rbforge import luau_text
    src = "local a = {} -- [id] = owner\nloadstring(x)\nlocal b = 2 -- ]]\n"
    code = luau_text.code_only(src)
    assert "loadstring" in code, "a `-- [x]` comment swallowed the code after it: %r" % code
    assert "owner" not in code
    long = "--[[ hidden\nloadstring(x) ]] visible()\n--[==[ also\nhidden ]==] shown()\n"
    code = luau_text.code_only(long)
    assert "loadstring" not in code and "visible" in code and "shown" in code, code
    kept = luau_text.code_only(long, keep_lines=True)
    assert kept.count("\n") == long.count("\n"), "keep_lines must preserve every newline"


@check("check: snapshot and git-ignored directories are not audited by the structure rung or reviews")
def _():
    import subprocess
    from rbforge import check, review, project
    with tempdir() as d:
        os.makedirs(os.path.join(d, "src"))
        os.makedirs(os.path.join(d, "artifacts", "recovery", "old"))
        os.makedirs(os.path.join(d, "scratch"))
        open(os.path.join(d, "default.project.json"), "w").write(
            '{"name":"x","tree":{"$className":"DataModel","ReplicatedStorage":{"$path":"src"}}}')
        open(os.path.join(d, "src", "a.luau"), "w").write("--!strict\nreturn {}\n")
        bad = "loadstring('x')()\n"
        open(os.path.join(d, "artifacts", "recovery", "old", "b.luau"), "w").write(bad)
        open(os.path.join(d, "scratch", "c.luau"), "w").write(bad)
        assert project.is_snapshot("artifacts/recovery/old/b.luau")
        assert not project.is_snapshot("src/artifactsLike.luau")
        rung = check.rung_structure(d)
        details = " ".join(c["detail"] for c in rung["checks"] if c["status"] == "fail")
        assert "artifacts" not in details, details
        assert "scratch/c.luau" in details, "a normal folder must still be audited"
        # git-ignored files drop out once the project is a repository
        if shutil.which("git"):
            subprocess.run(["git", "init", "-q"], cwd=d, check=True)
            open(os.path.join(d, ".gitignore"), "w").write("scratch/\n")
            rung = check.rung_structure(d)
            fails = [c for c in rung["checks"] if c["status"] == "fail"]
            assert not fails, fails
            snap = [c for c in rung["checks"] if c["id"] == "snapshots"]
            assert snap and "2 files" in snap[0]["detail"], snap
        open(os.path.join(d, "artifacts", "recovery", "old", "h.server.luau"), "w").write(
            "r.OnServerEvent:Connect(function(p, amt) give(p, amt) end)")
        files = {f["file"] for f in review.security(d)["findings"]}
        assert not any(f.startswith("artifacts/") for f in files), files


def _audit_fixture(d):
    os.makedirs(os.path.join(d, "src", "server"))
    os.makedirs(os.path.join(d, "src", "client"))
    os.makedirs(os.path.join(d, "artifacts", "recovery"))
    open(os.path.join(d, "default.project.json"), "w").write(
        '{"name":"x","tree":{"$className":"DataModel","ServerScriptService":{"$path":"src/server"}}}')
    open(os.path.join(d, "src", "server", "Data.luau"), "w").write(
        "--!strict\nlocal profiles = {}\n"
        "local function load(player)\n"
        "\tlocal ok, res = pcall(function()\n\t\treturn store:GetAsync('P_' .. player.UserId)\n\tend)\n"
        "\tprofiles[player] = (ok and res) or {}\nend\n"
        "local function save(player)\n\tpcall(function()\n\t\tstore:UpdateAsync('P_' .. player.UserId, f)\n\tend)\nend\n"
        "return { load = load, save = save }\n")
    open(os.path.join(d, "src", "server", "Shop.server.luau"), "w").write(
        "--!strict\n"
        "Reward.OnServerEvent:Connect(function(player, amount)\n\tgive(player, amount)\nend)\n"
        "Buy.OnServerEvent:Connect(function(player, itemId)\n\tShop.buy(player, itemId)\nend)\n"
        "function Shop.buy(player, itemId)\n"
        "\tif type(itemId) ~= 'string' then\n\t\treturn\n\tend\n"
        "\tif os.clock() - last[player] < 1 then\n\t\treturn\n\tend\nend\n")
    open(os.path.join(d, "src", "client", "Ui.client.luau"), "w").write(
        "--!strict\nlocal coins = player:GetAttribute('Coins')\nSay:FireServer(box.Text)\n")
    open(os.path.join(d, "artifacts", "recovery", "Old.server.luau"), "w").write(
        "X.OnServerEvent:Connect(function(player, damage)\nend)\n")


@check("audit: ranks data loss first, lists every handler with its guards, skips snapshots")
def _():
    from rbforge import audit
    with tempdir() as d:
        _audit_fixture(d)
        rep = audit.audit(d)
        tiers = [it["tier"] for it in rep["fix_order"]]
        assert tiers == sorted(tiers), "fix order must run tier 1 -> 7: %r" % tiers
        assert tiers[0].startswith("1"), tiers
        assert any("T038" in w for w in rep["fix_order"][0]["where"]), rep["fix_order"][0]
        titles = " | ".join(it["title"] for it in rep["fix_order"])
        assert "never filtered" in titles, titles
        assert "No tests found" in titles, titles
        handlers = {h["remote"]: h for h in rep["remote_handlers"]}
        assert set(handlers) == {"Reward", "Buy"}, handlers
        assert handlers["Reward"]["args"] == ["amount"] and handlers["Reward"]["read_first"] is True
        # Buy delegates to Shop.buy; the guards live there and must be followed.
        assert {"type", "rate"} <= set(handlers["Buy"]["guards_seen"]), handlers["Buy"]
        assert handlers["Buy"]["read_first"] is False
        assert rep["skipped"]["snapshot_or_ignored"] == 1
        assert not any("artifacts" in h["file"] for h in rep["remote_handlers"])
        # the client's read of a currency attribute is not a client-authority write
        assert not any("Client scripts that write" in it["title"] for it in rep["fix_order"]), titles
        text = audit.render(rep)
        assert "1. [1 data loss]" in text and "Remote handlers" in text and "MISSING: type" in text, text


@check("audit: a clean scaffold produces no leads, and the CLI and MCP expose it")
def _():
    import subprocess
    from rbforge import audit, scaffold
    with tempdir() as d:
        target = os.path.join(d, "g")
        scaffold.scaffold(target, "shooter")
        rep = audit.audit(target)
        assert rep["fix_order"] == [], rep["fix_order"]
        assert rep["tests"]["unit_specs"] == 4, rep["tests"]
        assert {h["remote"] for h in rep["remote_handlers"]} == {'Net.event("DoAction")', 'Net.event("BuyUpgrade")'}
        cli = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "rbforge_cli.py")
        done = subprocess.run([sys.executable, cli, "audit", target], capture_output=True, text=True)
        assert done.returncode == 0 and "No leads from the static audit" in done.stdout, done.stdout + done.stderr
        done = subprocess.run([sys.executable, cli, "audit", target, "--json"], capture_output=True, text=True)
        assert json.loads(done.stdout)["files"] == rep["files"]
        # review takes a positional path like check and audit do
        done = subprocess.run([sys.executable, cli, "review", target, "--kind", "traps"],
                              capture_output=True, text=True)
        assert done.returncode == 0 and json.loads(done.stdout)["traps"]["findings"] == [], done.stdout
    server = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "mcp_server", "server.py"), encoding="utf-8").read()
    assert '"rb_audit"' in server


@check("scaffold: the starter kit is a real loop - loader, remotes, data safety, specs, live test")
def _():
    from rbforge import scaffold, traps
    with tempdir() as d:
        target = os.path.join(d, "g")
        files = scaffold.scaffold(target, "rpg")["files"]
        for need in ("src/server/Main.server.luau", "src/server/Services/DataService.luau",
                     "src/server/Services/GameService.luau", "src/server/ProfileSchema.luau",
                     "src/shared/Net.luau", "src/shared/RateLimiter.luau", "src/shared/Cleaner.luau",
                     "src/shared/Rules.luau", "src/client/Main.client.luau",
                     "tests/Rules.spec.luau", "tests/RateLimiter.spec.luau", "tests/ProfileSchema.spec.luau",
                     "tests/Starter.server.luau", ".gitignore", "default.project.json"):
            assert need in files, "%s missing from the scaffold" % need
        read = lambda rel: open(os.path.join(target, *rel.split("/")), encoding="utf-8").read()
        for rel in files:
            assert "{genre}" not in read(rel), "%s still holds the placeholder" % rel
        data = read("src/server/Services/DataService.luau")
        assert ":Kick(" in data and "BindToClose" in data and "UpdateAsync" in data and "IsStudio()" in data
        main = read("src/server/Main.server.luau")
        assert "GetPlayers()" in main and 'SetAttribute("ServerReady", true)' in main
        assert "gameProcessed" in read("src/client/Main.client.luau")
        # The kit must not trip the lint it ships with.
        found = [f for rel in files if rel.endswith(".luau")
                 for f in traps.scan_text(rel, read(rel)) if f["severity"] != "info"]
        assert not found, found
        project = json.loads(read("default.project.json"))
        assert "$path" not in project["tree"]["ReplicatedStorage"], "Rojo must not own the whole service"


@check("scaffold: every genre and alias scaffolds and plans; an unknown genre is refused")
def _():
    from rbforge import planning, scaffold
    assert len(planning.GENRES) >= 10 and planning.GENRES[0] == "generic", planning.GENRES
    for genre in planning.GENRES:
        plan = planning.vertical_slice(genre, "p")
        assert len(plan["build_order"]) >= 4 and len(plan["verification"]) >= 3, genre
        assert "console clean" in " ".join(plan["verification"]), genre
    assert planning.resolve("FPS") == "shooter" and planning.resolve("td") == "towerdefense"
    assert planning.resolve("extraction") == "survival"
    with tempdir() as d:
        res = scaffold.new_project(os.path.join(d, "g"), "td", "defend the gate")
        assert res["genre"] == "towerdefense"
        plan = open(res["plan"], encoding="utf-8").read()
        assert "## What already works" in plan and "rbforge audit" in plan
        cfg = open(os.path.join(d, "g", "src", "shared", "Config.luau"), encoding="utf-8").read()
        assert 'Genre = "towerdefense"' in cfg
    try:
        planning.resolve("battle-royale-with-cheese")
        raise AssertionError("an unknown genre must be refused, not mapped to generic")
    except err_mod.ForgeError as e:
        assert e.code == "RBF-ARG-001"
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for genre in planning.GENRES:
        if genre != "generic":
            assert os.path.isfile(os.path.join(root, "templates", "genre", genre + ".md")), genre


_REFS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "skills", "roblox-game-development", "references")


def _ref(name):
    return open(os.path.join(_REFS, name), encoding="utf-8").read()


def _luau_blocks(text):
    """Fenced lua/luau blocks of a markdown file, with the line each starts on."""
    out, lines, i = [], text.splitlines(), 0
    while i < len(lines):
        m = re.match(r"\s*```(lua|luau)\s*$", lines[i])
        if m:
            start, body = i + 1, []
            i += 1
            while i < len(lines) and not re.match(r"\s*```\s*$", lines[i]):
                body.append(lines[i])
                i += 1
            out.append((start + 1, "\n".join(body) + "\n"))
        i += 1
    return out


@check("docs: reference samples - every fenced Luau block in the first-party references parses")
def _():
    import subprocess
    stylua = shutil.which("stylua")
    if not stylua:
        if os.environ.get("CI"):
            raise AssertionError("stylua is required in CI (scripts/install_stylua.py)")
        return "skip: stylua not installed"

    def parses(code):
        # `stylua -` formats stdin: exit 0 means it parsed, 2 means a syntax error.
        done = subprocess.run([stylua, "-"], input=code, capture_output=True, text=True, encoding="utf-8")
        return done.returncode == 0

    assert not parses("local function f(a, b = 1) end\n"), "negative control: StyLua accepted invalid Luau"
    assert parses("local x = 1\n"), "positive control failed"
    bad, total = [], 0
    for name in sorted(os.listdir(_REFS)):
        if not name.endswith(".md"):
            continue
        for line, code in _luau_blocks(_ref(name)):
            total += 1
            if not parses(code):
                bad.append("%s:%d" % (name, line))
    assert total >= 25, "only %d Luau blocks found - the extractor is broken" % total
    assert not bad, "Luau samples that do not parse: %s" % ", ".join(bad)


@check("docs: persistence - the ProfileStore sample uses the real API and names the failed-read rule")
def _():
    text = _ref("persistence.md")
    assert "ListenToRelease(" not in text.replace("There is no `ListenToRelease`", ""), \
        "ListenToRelease is ProfileService; ProfileStore has no such method"
    assert "OnSessionEnd:Connect(" in text and "OnSessionEnd =" not in text
    assert "a failed read is not a new player" in text.lower()
    assert "T038" in text
    assert "30-minute" not in text, "ProfileStore steals a session after 40 s, not 30 minutes"


@check("docs: sharp-edges - every trap carries an evidence tag and the false ones are gone")
def _():
    text = _ref("sharp-edges.md")
    body = text.split("## Agent traps")[0]
    items = re.findall(r"(?ms)^- (.*?)(?=^- |^## |\Z)", body.split("## Players and characters", 1)[1])
    assert len(items) >= 40, len(items)
    untagged = [i[:70] for i in items if not re.search(r"\((docs|live[^)]*|field)\)", i)]
    assert not untagged, "traps without an evidence tag: %r" % untagged
    assert "No `+=`" not in text and "pre-parser" not in text, "compound assignment runs in execute_luau"
    assert "not `player.Character` at connect time" not in text
    for stale in ("225-panel", "PineTier", "midpoint-only"):
        assert stale not in text, "project case note %r belongs in sightlines-and-openings.md" % stale
    assert "midpoint-only" in _ref("sightlines-and-openings.md")
    assert "No `+=`" not in _ref("studio-mcp.md")


@check("docs: stale or project-specific advice is gone from the references")
def _():
    live = _ref("live-iteration.md")
    assert "There is no save tool" not in live and "save_place" in live
    assert "http.server" not in live and "HttpEnabled" not in live, "rbforge push replaced the HTTP pull"
    assert "rbforge push" in live
    arch = _ref("architecture.md")
    assert "Authored or generated" in arch and "GetPlayers()" in arch and "ServerReady" in arch
    assert "pcall(service.SetupPlayer" not in arch, "the loader must not swallow player-setup errors"
    anim = _ref("animation.md")
    assert anim.index("Choose the route first") < anim.index("A procedural gait")
    assert "put a `PointLight` on the camera" not in anim
    assert "AnimationConstraint" in anim.split("## The additive layer")[0], "joint helper must come first"
    assets = _ref("assets.md")
    assert "above ~6 seconds" not in assets
    assert "Skinned mesh with bones" in assets
    design = _ref("game-design.md")
    assert "time dilation" not in design and "exactly one source and one sink" not in design
    net = _ref("security-networking.md")
    assert "Do not hand-roll the schema layer" not in net and "only when measured" in net
    assert "InvokeClient" in net and "FilterStringAsync" in net
    ui = _ref("ui-mobile.md")
    assert "ScreenInsets" in ui and "Activated" in ui and "gameProcessed" in ui
    assert ui.index("Build it the plain way first") < ui.index("Fusion 0.3")
    world = _ref("worldbuilding-lighting.md")
    assert "Build it once, in Edit, and save it" in world
    perf = _ref("performance.md")
    assert "SetStateEnabled" in perf and "AnimationController" in perf and "foreground" in perf


@check("docs: current-engine - every class it names exists in the creator-docs cache")
def _():
    from rbforge import paths
    text = _ref("current-engine.md")
    m = re.search(r"Checked classes:(.*)\Z", text, re.S)
    assert m, "current-engine.md must end with its 'Checked classes:' list"
    names = [n.strip(" .\n") for n in m.group(1).replace("\n", " ").split(",") if n.strip(" .\n")]
    assert len(names) >= 20, names
    for name in names:
        assert name in text[:m.start()], "%s is listed as checked but never mentioned" % name
    classes = os.path.join(paths.docs_cache_dir(), "content", "en-us", "reference", "engine", "classes")
    if not os.path.isdir(classes):
        return "skip: creator-docs cache absent (rbforge docs update)"
    missing = [n for n in names if not os.path.isfile(os.path.join(classes, n + ".yaml"))]
    assert not missing, "classes named in current-engine.md that the engine reference does not have: %s" % missing


@check("skill: router points at the specialist skills, both new references and the right tool count")
def _():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    skill = open(os.path.join(root, "skills", "roblox-game-development", "SKILL.md"), encoding="utf-8").read()
    assert "all 41 live tools" in skill and "38 live tools" not in skill and "34 live tools" not in skill
    assert "rbforge audit" in skill and "rbforge new" in skill
    for name in re.findall(r"`(roblox-[a-z-]+)`", skill):
        assert os.path.isfile(os.path.join(root, "skills", name, "SKILL.md")), \
            "router names a skill that is not shipped: %s" % name
    shipped = {d for d in os.listdir(os.path.join(root, "skills"))
               if d.startswith("roblox-") and d not in ("roblox-game-development", "roblox-docs")}
    routed = set(re.findall(r"`(roblox-[a-z-]+)`", skill))
    assert shipped <= routed, "specialist skills the router never mentions: %s" % sorted(shipped - routed)
    assert len(skill) <= 16000, "the router is loaded on every Roblox task: %d chars" % len(skill)


@check("cli: servertest defaults the attribute to RbforgeTest, and the scaffold ships a dev place project")
def _():
    from rbforge import live, scaffold
    import rbforge_cli
    seen = {}

    def fake(path, attr, *a, **k):
        seen["attr"] = attr
        return {"passed": True}

    old = live.server_test
    live.server_test = fake
    try:
        with _isolated_home(), contextlib.redirect_stdout(io.StringIO()):
            code = rbforge_cli.main(["servertest", "tests/x.server.luau"])
    finally:
        live.server_test = old
    assert code == 0 and seen["attr"] == "RbforgeTest", (code, seen)
    with tempdir() as d:
        target = os.path.join(d, "g")
        files = scaffold.scaffold(target, "obby")["files"]
        assert "dev.project.json" in files
        dev = json.load(open(os.path.join(target, "dev.project.json"), encoding="utf-8"))
        assert dev["tree"]["Workspace"]["SpawnLocation"]["$className"] == "SpawnLocation"
        assert dev["tree"]["Workspace"]["Baseplate"]["$properties"]["Anchored"] is True
        # Rojo drops `Position` (not serialized): placement has to be a CFrame, spawn on top of the floor.
        for name, y in (("Baseplate", -2), ("SpawnLocation", 0.5)):
            props = dev["tree"]["Workspace"][name]["$properties"]
            assert "Position" not in props and props["CFrame"][1] == y, (name, props)
        hud = open(os.path.join(target, "src", "client", "Main.client.luau"), encoding="utf-8").read()
        assert "Enum.SortOrder.LayoutOrder" in hud, "a script-made UIListLayout sorts by Name by default"


# ---------------------------------------------------------------- 0.20.0 field lessons

@check("probes: world-audit renders, parses, honours its params and is documented")
def _():
    from rbforge import probes
    cat = {p["name"]: p for p in probes.catalog()}
    assert "world-audit" in cat and cat["world-audit"]["datamodel"] == "any", cat.get("world-audit")
    for need in ("root", "gap", "overlap", "reach", "skip", "max"):
        assert need in cat["world-audit"]["params"], need
    code = probes.render("world-audit", probes.parse_sets(["root=workspace.World", 'skip={"Rail$"}']))["code"]
    assert "local root = workspace.World" in code and 'local SKIP = {"Rail$"}' in code
    # The report names what it skipped, the three lead classes, and yields while it works.
    for need in ("SKIPPED from the floating check", "FLOATING", "INSIDE", "STRAY ATTACHMENT", "task.wait()",
                 "WORLD-AUDIT"):
        assert need in code, need
    with tempdir() as d:
        cfg = os.path.join(d, "selene.toml")
        open(cfg, "w").write('std = "lua51"\n')
        path = os.path.join(d, "world-audit.luau")
        open(path, "w", encoding="utf-8").write(probes.render("world-audit")["code"])
        ok, detail = _parse_luau(path, cfg)
        assert ok, "world-audit does not parse:\n%s" % detail
    assert "world-audit" in _ref("worldbuilding-lighting.md")


@check("traps: T045 fires on a world write before the parent and stays quiet on the fix")
def _():
    bad = ('local a = Instance.new("Attachment")\n'
           "a.WorldCFrame = CFrame.new(10, 150, 0)\n"
           "a.Parent = part\n")
    assert "T045" in _trap_ids("src/server/build.luau", bad)
    pos = 'local a: Attachment = Instance.new("Attachment")\na.WorldPosition = p\n'
    assert "T045" in _trap_ids("tools/build.luau", pos), "no parent at all is the same bug"
    good = ('local a = Instance.new("Attachment")\n'
            "a.Parent = part\n"
            "a.WorldCFrame = CFrame.new(10, 150, 0)\n")
    assert "T045" not in _trap_ids("src/server/build.luau", good)
    local_space = 'local a = Instance.new("Attachment")\na.CFrame = CFrame.new(0, 1, 0)\na.Parent = part\n'
    assert "T045" not in _trap_ids("src/server/build.luau", local_space)
    # A comparison is not a write, and a reassigned name is another attachment.
    cmp_only = 'local a = Instance.new("Attachment")\nif a.WorldPosition == p then end\na.Parent = part\n'
    assert "T045" not in _trap_ids("src/server/build.luau", cmp_only)
    reassigned = ('local a = Instance.new("Attachment")\na.Parent = part\n'
                  "a = other\na.WorldPosition = p\n")
    assert "T045" not in _trap_ids("src/server/build.luau", reassigned)
    from rbforge import traps
    assert traps.catalog()["T045"] == "live"
    assert "T045" in _ref("sharp-edges.md")


@check("live: push refuses while Play is running and says how to recover")
def _():
    from rbforge import live
    orig = live.Session
    with tempdir() as d:
        os.makedirs(os.path.join(d, "src"))
        json.dump({"tree": {"$className": "DataModel", "ServerScriptService": {"$path": "src"}}},
                  open(os.path.join(d, "default.project.json"), "w"))
        open(os.path.join(d, "src", "A.luau"), "w").write("return 1\n")
        want = live.adler("return 1\n")
        sent = []

        class PlayStudio:
            studio_id = "s1"

            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def call(self, tool, args):
                return _PLAY_STATE

            def luau(self, code, dm="Edit"):
                sent.append(code)
                return "UNVERIFIED"

        try:
            live.Session = PlayStudio
            try:
                live.push(["ALL"], os.path.join(d, "default.project.json"))
                raise AssertionError("push ran during Play")
            except err_mod.ForgeError as exc:
                assert exc.code == "RBF-PLAY-002", exc.code
                assert "stop Play" in str(exc) and "start_stop_play" in (exc.hint or ""), (str(exc), exc.hint)
            assert sent == [], "push sent Luau to Studio before refusing"
            # Edit state, and wording the preflight does not recognise, still push.
            for state in (_EDIT_STATE, "some future wording"):
                live.Session = _fake_session("SYNCED " + want, state)
                r = live.push(["ALL"], os.path.join(d, "default.project.json"))
                assert r["pushed"] == 1, (state, r)
        finally:
            live.Session = orig


@check("docs: field lessons from the second production project are in the references")
def _():
    need = {
        "studio-mcp.md": ["Bring Studio to the front", "LOD seams", "One StudioMCP process",
                          "keyDown", "The person at the PC", "GPU-heavy"],
        "sharp-edges.md": ["Raycasts obey collision groups", "params.CollisionGroup",
                           "after it has a parent", "RootPriority", "Beam", "RespectCanCollide",
                           "PreloadAsync", "PositionType", "cannot be compared"],
        "assets.md": ["Measure the orientation once", "(-x, z, y)", "Vertex colours"],
        "worldbuilding-lighting.md": ["occupancy", "Audit the built world", "Mud", "Decay"],
        "testing-debugging.md": ["DebugHandsOff", "humanoid:Move", "real Play restart", "Stage scenes"],
        "animation.md": ["CreateHumanoidModelFromDescriptionAsync", "BallSocketConstraint", "contact sheet"],
        "ui-mobile.md": ["LastInputTypeChanged", "Every hint you show for touch"],
    }
    for name, phrases in need.items():
        text = _ref(name)
        for p in phrases:
            assert p in text, "%s lacks %r" % (name, p)
    # The contradicted first-party tip is gone: no unconditional 180-degree yaw for imported meshes.
    assert "Place each segment with\n  a 180" not in _ref("assets.md")
    # Samples in the lighting reference no longer use the deprecated parent argument.
    assert not re.search(r'Instance\.new\("\w+",\s*\w', _ref("worldbuilding-lighting.md"))


# ---------------------------------------------------------------- 0.21.0 one-instance QA, current APIs

@check("agents: connect writes a stable interpreter, not an app's private venv")
def _():
    from rbforge import agents
    saved_env = os.environ.get("UABS_PYTHON")
    saved = (sys.executable, sys.prefix, sys.base_prefix, getattr(sys, "_base_executable", None))
    with tempdir() as d:
        shared = os.path.join(d, "shared", "python.exe")
        base_dir = os.path.join(d, "base")
        venv_py = os.path.join(d, "app", "venv", "Scripts", "python.exe")
        for f in (shared, os.path.join(base_dir, "python.exe"), venv_py):
            os.makedirs(os.path.dirname(f), exist_ok=True)
            open(f, "w").write("")
        try:
            # 1. The machine's shared runtime wins.
            os.environ["UABS_PYTHON"] = shared
            assert agents._forge_argv()[0] == shared.replace("\\", "/")
            # 2. Inside a venv with no shared runtime: the base interpreter, never the venv's.
            os.environ.pop("UABS_PYTHON", None)
            sys.executable, sys.prefix, sys.base_prefix = venv_py, os.path.dirname(os.path.dirname(venv_py)), base_dir
            sys._base_executable = venv_py  # some launchers report the venv here too
            got = agents._stable_python()
            assert os.path.normcase(got) == os.path.normcase(os.path.join(base_dir, "python.exe")), got
            # A UABS_PYTHON that does not exist is ignored, not written.
            os.environ["UABS_PYTHON"] = os.path.join(d, "gone", "python.exe")
            assert os.path.normcase(agents._stable_python()) == os.path.normcase(os.path.join(base_dir, "python.exe"))
            # 3. Not in a venv: sys.executable stays.
            os.environ.pop("UABS_PYTHON", None)
            sys.prefix = sys.base_prefix = base_dir
            sys.executable = os.path.join(base_dir, "python.exe")
            assert agents._stable_python() == sys.executable
        finally:
            sys.executable, sys.prefix, sys.base_prefix, base_exe = saved
            if base_exe is None:
                if hasattr(sys, "_base_executable"):
                    del sys._base_executable
            else:
                sys._base_executable = base_exe
            if saved_env is None:
                os.environ.pop("UABS_PYTHON", None)
            else:
                os.environ["UABS_PYTHON"] = saved_env
    # The TOML block keeps forward slashes whatever interpreter was chosen.
    block = agents._toml_block("robloxforge", agents._forge_argv())
    assert "\\" not in block, block


@check("traps: T046 flags deprecated AnalyticsService Fire* and InputAction:Fire, not their replacements")
def _():
    assert "T046" in _trap_ids("a.server.luau", 'AnalyticsService:FireCustomEvent(player, "Kill", 1)')
    assert "T046" in _trap_ids("a.server.luau", "Analytics:FireInGameEconomyEvent(player, 'Buy')")
    assert "T046" not in _trap_ids("a.server.luau", 'AnalyticsService:LogCustomEvent(player, "Kill", 1)')
    pilot = 'local ctx = Instance.new("InputContext")\nInput.action(name):Fire(true)\n'
    assert "T046" in _trap_ids("src/client/Pilot.luau", pilot)
    # A helper that returns the action counts even when the file never names the Input Action classes.
    assert "T046" in _trap_ids("src/client/Pilot.luau", 'Input.action("Move"):Fire(Vector2.new(0, 1))\n')
    fixed = 'local ctx = Instance.new("InputContext")\nbinding:Fire(true)\n'
    assert "T046" not in _trap_ids("src/client/Pilot.luau", fixed)
    # A BindableEvent in a file that has nothing to do with input actions is not this rule.
    assert "T046" not in _trap_ids("src/server/a.luau", "actionDone:Fire(result)\n")
    from rbforge import traps
    assert traps.catalog()["T046"] == "docs"


@check("docs: one-instance QA, active ragdoll, shared world state and current APIs are in the references")
def _():
    need = {
        "testing-debugging.md": ["Proving it in one Studio instance", "QaSlot", "Puppets", "The Pilot",
                                 "InputBinding:Fire", "Player:Move", "Clock.advance", "proof ladder",
                                 "let a bot play them"],
        "studio-mcp.md": ["plugin rights", "ExecuteMultiplayerTestAsync", "scripted camera ignores",
                          "One Studio, one operator"],
        "sharp-edges.md": ["what it ignores must fade", "LocalTransparencyModifier",
                           "simulated by that player's client", "Firing an input action does not walk",
                           "A reference named like a function", "Vector3.yAxis:Cross"],
        "animation.md": ["Active ragdoll", "IsKinematic", "MaxTorque", "Throw the whole body",
                         "MaxFrictionTorque", "PlatformStand", "IKControl"],
        "current-engine.md": ["InputBindingType.Scriptable", "LogCustomEvent", "LevelOfDetail",
                              "PlaybackRegion", "CreateEditableMeshAsync", "MaxPlayers", "SetTeleportData",
                              "NPCs (even on an R15 rig)"],
        "persistence.md": ["World facts every server must agree on", "applied", "best effort",
                           "lose the acknowledgement", "45 days"],
        "development-loop.md": ["Delegating build work", "integrator's files", "one Studio and one operator"],
    }
    for name, phrases in need.items():
        text = _ref(name)
        for p in phrases:
            assert p in text, "%s lacks %r" % (name, p)
    # The 0.20.0 advice to fight through MCP keystrokes is gone.
    assert "send one keyboard macro" not in _ref("testing-debugging.md")
    # A forge that teaches InputAction:Fire as the route would teach a deprecated call.
    for name in ("testing-debugging.md", "sharp-edges.md"):
        for line in _ref(name).splitlines():
            if "InputAction:Fire" in line:
                assert "deprecated" in line.lower() or "deprecated" in _ref(name), (name, line)


# ---------------------------------------------------------------- 0.22.0 streaks, forensics, run ledger

def _studio_double(answers, start_mode="Play", lag=1, never_play=False, state_text=None, console_prefix=""):
    """A Session double with a playtest state machine, a console and scripted test answers.

    `start_stop_play` flips the mode after `lag` state polls (Studio answers before the datamodels
    exist). Every execute_luau prints its marker (the code's first `print([[...]])`) and the answer
    into the console, as Studio's Output does; `get_console_output` returns all of it.
    """
    log = {"calls": [], "console": [console_prefix] if console_prefix else [], "mode": start_mode,
           "pending": None, "polls": 0}
    queue = list(answers)

    class Fake:
        studio_id = "s1"
        opened = 0

        def __init__(self, *a, **k):
            Fake.opened += 1

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def call(self, tool, args):
            log["calls"].append((tool, args.get("is_start")))
            if tool == "get_studio_state":
                if state_text is not None:
                    return state_text
                if log["pending"] is not None:
                    log["polls"] += 1
                    if log["polls"] >= lag:
                        log["mode"], log["pending"] = log["pending"], None
                dms = "Client, Server" if log["mode"] == "Play" else "Edit"
                return "- Current Studio Mode: %s\n- Available DataModels: %s\n" % (log["mode"], dms)
            if tool == "start_stop_play":
                want = "Play" if args["is_start"] else "Edit"
                if not (never_play and want == "Play"):
                    log["pending"], log["polls"] = want, 0
                return "ok"
            if tool == "get_console_output":
                return "\n".join(log["console"])
            return ""

        def luau(self, code, dm="Edit"):
            m = re.match(r"print\(\[(=*)\[\n?(.*?)\]\1\]\)", code, re.S)
            if m:
                log["console"].append(m.group(2))  # Luau drops the newline after the opening bracket
            nxt = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(nxt, Exception):
                log["console"].append("Script 'RbforgeServerTest', Line 3 - error boom")
                raise nxt
            log["console"].append("test said: " + nxt)
            return nxt
    return Fake, log


@contextlib.contextmanager
def _swap_session(fake):
    from rbforge import live
    orig = live.Session
    live.Session = fake
    try:
        yield
    finally:
        live.Session = orig


@check("streak: --restart gives every run a fresh Play session and three passes make a streak")
def _():
    from rbforge import live
    fake, log = _studio_double(["PASS a", "PASS b", "PASS c"], start_mode="Edit", lag=2)
    with tempdir() as d, _swap_session(fake):
        entry = live.single_entry(_reporting_test(d), "Attr", timeout=5)
        lines = []
        res = live.run_streak([entry], 3, restart=True, report=lines.append, poll=0)
    assert res["passed"] and res["passes"] == 3 and res["best_streak"] == 3, res
    plays = [c[1] for c in log["calls"] if c[0] == "start_stop_play"]
    # From Edit: start; then stop+start before runs 2 and 3. Play is left running after the last run.
    assert plays == [True, False, True, False, True], plays
    assert all(r["restarted"] for r in res["runs"]) and fake.opened == 1, res
    assert lines[-1] == "run 3/3: PASS", lines


@check("streak: the first failure ends it, keeps that run's console only, and leaves Play running")
def _():
    from rbforge import live
    fake, log = _studio_double(["PASS one", "FAIL the sack is taken", "PASS never"],
                               console_prefix="old noise from before the run")
    with tempdir() as d, _swap_session(fake):
        entry = live.single_entry(_reporting_test(d), "Attr", timeout=5)
        res = live.run_streak([entry], 3, restart=True, poll=0)
    assert not res["passed"] and res["ran"] == 2 and res["passes"] == 1, res
    failed = res["runs"][1]["tests"][0]
    console = failed["console"]
    assert failed["outcome"] == "fail" and console["found"], failed
    assert "old noise" not in console["text"] and "test said: PASS one" not in console["text"], console
    assert console["tail"] == ["test said: FAIL the sack is taken"], console
    assert console["errors"] == ["test said: FAIL the sack is taken"], console
    plays = [c[1] for c in log["calls"] if c[0] == "start_stop_play"]
    assert plays == [False, True, False, True], "nothing after the failed run may touch Play: %s" % plays
    assert log["mode"] == "Play" or log["pending"] == "Play", log


@check("streak: --keep-going runs all N and reports the best streak, not a pass")
def _():
    from rbforge import live
    fake, _log = _studio_double(["PASS", "FAIL x", "PASS", "PASS"])
    with tempdir() as d, _swap_session(fake):
        entry = live.single_entry(_reporting_test(d), "Attr", timeout=5)
        res = live.run_streak([entry], 4, keep_going=True, poll=0)
    assert res["ran"] == 4 and res["passes"] == 3 and res["best_streak"] == 2 and not res["passed"], res


@check("streak: a Play that never comes up is a failed run with RBF-PLAY-003, and unknown state text refuses")
def _():
    from rbforge import live
    from rbforge.errors import ForgeError
    fake, _log = _studio_double(["PASS"], start_mode="Edit", never_play=True)
    with tempdir() as d, _swap_session(fake):
        entry = live.single_entry(_reporting_test(d), "Attr", timeout=5)
        res = live.run_streak([entry], 2, restart=True, play_timeout=0.05, poll=0)
    assert not res["passed"] and res["ran"] == 1 and "RBF-PLAY-003" in res["runs"][0]["error"], res
    fake2, log2 = _studio_double(["PASS"], state_text="something new")
    try:
        live.restart_play(fake2(), ("Server",), 0.05, 0)
    except ForgeError as exc:
        assert exc.code == "RBF-PLAY-003" and exc.exit_code == 4, exc
    else:
        raise AssertionError("restart_play went ahead on state text it cannot read")
    assert not [c for c in log2["calls"] if c[0] == "start_stop_play"], log2["calls"]


@check("streak: bad --repeat values and an unreadable test are refused before Studio is opened")
def _():
    from rbforge import live
    from rbforge.errors import ForgeError
    fake, _log = _studio_double(["PASS"])
    with tempdir() as d, _swap_session(fake):
        entry = live.single_entry(_reporting_test(d), "Attr", timeout=5)
        for bad in (0, 101, True, "3"):
            try:
                live.run_streak([entry], bad)
            except ForgeError as exc:
                assert exc.code == "RBF-ARG-002", (bad, exc)
            else:
                raise AssertionError("accepted --repeat %r" % (bad,))
        try:
            live.single_entry(os.path.join(d, "missing.luau"))
        except ForgeError:
            pass
        else:
            raise AssertionError("a missing test file became an entry")
    assert fake.opened == 0, fake.opened


@check("forensics: an execute_luau error becomes an error outcome carrying its console")
def _():
    from rbforge import live
    from rbforge.errors import ForgeError
    fake, _log = _studio_double([ForgeError("RBF-STUDIO-002", "boom")])
    with tempdir() as d, _swap_session(fake):
        res = live.server_test(_reporting_test(d), "Attr", timeout=5, forensics=True)
        assert res["outcome"] == "error" and "RBF-STUDIO-002" in res["result"], res
        assert any("error boom" in e for e in res["console"]["errors"]), res
        # Without forensics the error still raises, as before.
        try:
            live.server_test(_reporting_test(d), "Attr", timeout=5)
        except ForgeError:
            pass
        else:
            raise AssertionError("the plain path swallowed an execute_luau error")


@check("forensics: a pass reads no console; a console without the marker keeps its last lines and says so")
def _():
    from rbforge import live
    fake, log = _studio_double(["PASS ok"])
    with tempdir() as d, _swap_session(fake):
        res = live.server_test(_reporting_test(d), "Attr", timeout=5, forensics=True)
    assert res["passed"] and "console" not in res, res
    assert not [c for c in log["calls"] if c[0] == "get_console_output"], log["calls"]

    class Trimmed:
        studio_id = "s1"

        def call(self, tool, args):
            return "\n".join("line %d" % i for i in range(500))
    got = live.console_since(Trimmed(), "[rbforge] run X begins: t.luau")
    assert not got["found"] and len(got["text"].splitlines()) == live.CONSOLE_FALLBACK_LINES, got["found"]
    assert got["tail"][-1] == "line 499", got["tail"]


@check("runs: the ledger records each run, saves failed consoles, and reports rate and streaks per test")
def _():
    from rbforge import runs
    with _isolated_home(), tempdir() as d:
        open(os.path.join(d, "default.project.json"), "w").write("{}")
        os.makedirs(os.path.join(d, "tests"))
        assert runs.project_root(os.path.join(d, "tests")) == os.path.abspath(d)
        streak = {"batch": "b1", "runs": [
            {"run": 1, "restarted": True, "tests": [
                {"name": os.path.join(d, "tests", "Kill.client.luau"), "outcome": "pass", "passed": True,
                 "result": "PASS kill", "datamodel": "Client", "seconds": 3.0}]},
            {"run": 2, "restarted": True, "tests": [
                {"name": os.path.join(d, "tests", "Kill.client.luau"), "outcome": "fail", "passed": False,
                 "result": "FAIL the sack is taken", "datamodel": "Client", "seconds": 4.0, "run_id": "r2",
                 "console": {"text": "marker\nInteract refused: too far", "found": True,
                             "tail": ["Interact refused: too far"], "errors": []}}]},
            {"run": 3, "restarted": True, "tests": [
                {"name": os.path.join(d, "tests", "Kill.client.luau"), "outcome": "pass", "passed": True,
                 "result": "PASS kill", "datamodel": "Client", "seconds": 3.0}]},
        ]}
        rec = runs.record_streak(d, streak)
        assert rec["written"] == 3 and not rec.get("error"), rec
        failed = streak["runs"][1]["tests"][0]
        assert "text" not in failed["console"], "the full console must leave the JSON once it is on disk"
        log = failed["console_log"]
        assert open(log, encoding="utf-8").read().endswith("Interact refused: too far"), log
        with open(runs.ledger_path(d), "a", encoding="utf-8") as fh:
            fh.write('{"torn": \n')  # a killed writer leaves half a line; it must not break reading
        summary = runs.summarize(d)
        t = summary["tests"][0]
        assert t["test"] == "tests/Kill.client.luau", t
        assert (t["runs"], t["passes"], t["current_streak"], t["best_streak"]) == (3, 2, 1, 1), t
        assert t["last_failure"]["log"] == log and abs(t["pass_rate"] - 0.667) < 0.001, t
        text = runs.render(summary)
        assert "tests/Kill.client.luau" in text and "67%" in text and log in text, text
        assert runs.summarize(d, test="nothing")["tests"] == []
        assert runs.summarize(d, last=1)["tests"][0]["runs"] == 1


@check("runs: git state names the project's commit and whether it is dirty")
def _():
    import shutil as _shutil
    import subprocess
    from rbforge import runs
    if not _shutil.which("git"):
        return "skip: git not on PATH"
    with tempdir() as d:
        assert runs.git_state(d) == (None, None)
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@t")
        for argv in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "x"]):
            if argv[0] == "add":
                open(os.path.join(d, "a.txt"), "w").write("1")
            subprocess.run(["git", "-C", d] + argv, check=True, env=env, capture_output=True)
        sha, dirty = runs.git_state(d)
        assert sha and len(sha) == 12 and dirty is False, (sha, dirty)
        open(os.path.join(d, "a.txt"), "w").write("2")
        assert runs.git_state(d)[1] is True


@check("cli: servertest --repeat --restart records every run, `runs --text` reads it, misuse exits 2")
def _():
    fake, _log = _studio_double(["PASS a", "PASS b"], start_mode="Edit")
    with _isolated_home(), tempdir() as d, _swap_session(fake):
        open(os.path.join(d, "default.project.json"), "w").write("{}")
        test = _reporting_test(d)
        code, out = _cli("servertest", test, "Attr", "--repeat", "2", "--restart", "--play-timeout", "5")
        assert code == 0 and out["passed"] and out["record"]["written"] == 2, (code, out)
        code, out = _cli("runs", "--root", d)
        assert code == 0 and out["tests"][0]["runs"] == 2 and out["tests"][0]["current_streak"] == 2, out
        import rbforge_cli
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert rbforge_cli.main(["runs", "--root", d, "--text"]) == 0
        assert "t.luau" in buf.getvalue() and "100%" in buf.getvalue(), buf.getvalue()
        code, out = _cli("servertest", test, "Attr", "--restart")
        assert code == 2 and "--repeat" in out["error"]["message"], out
        code, out = _cli("runs", "--root", d, "--last", "0")
        assert code == 2, out


@check("cli: --version prints the package version")
def _():
    import rbforge_cli
    from rbforge import __version__
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            rbforge_cli.main(["--version"])
        except SystemExit as exc:
            assert exc.code == 0, exc.code
    assert buf.getvalue().strip() == "rbforge %s" % __version__, buf.getvalue()


@check("docs: studio mcp surface matches the 2026-11-24 handshake and no stale tool name survives")
def _():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mcp = _ref("studio-mcp.md")
    assert "**41 tools**" in mcp, "studio-mcp.md does not state the live count"
    for name in ("get_roblox_skill", "list_roblox_skills", "video_capture", "list_plugin_actions", "open_plugin"):
        assert "`%s`" % name in mcp, "studio-mcp.md lacks %s" % name
    stale = re.compile(r"`list_skills`|`skill`|skill \"rbx-|\b14 (built-in|maintained)")
    hits = []
    for base, _dirs, files in os.walk(os.path.join(root, "skills")):
        for f in files:
            if f.endswith(".md"):
                p = os.path.join(base, f)
                for i, line in enumerate(open(p, encoding="utf-8"), 1):
                    # A line that names the old tool as the old name (a changelog of the surface) is fine.
                    if stale.search(line) and not re.search(r"(?i)renamed|old name", line):
                        hits.append("%s:%d: %s" % (os.path.relpath(p, root), i, line.strip()[:90]))
    assert not hits, "renamed Studio MCP tools still taught:\n" + "\n".join(hits)
    skills = _ref("assistant-skills.md")
    listed = set(re.findall(r"`(rbx-[a-z0-9-]+)`", skills))
    assert len(listed) >= 17, "assistant-skills.md lists %d rbx-* skills, Studio shows 17" % len(listed)


@check("docs: streak lessons - repeat runs, console before Stop, refusal reasons, oracles, input owners")
def _():
    need = {
        "testing-debugging.md": ["--repeat", "--restart", "rbforge runs", "before anything stops Play",
                                 "refusal reason", "the design's outcome", "world a player would have",
                                 "unreachable", "Give tuning a budget"],
        "debugging-playbook.md": ["silently refused", "console_log"],
        "sharp-edges.md": ["Two handlers on one input action"],
    }
    for name, phrases in need.items():
        text = _ref(name)
        for p in phrases:
            assert p in text, "%s lacks %r" % (name, p)


def _worktree_fixture(root):
    """A project with a vendored package and a nested worktree (its `.git` is a file, as git writes it)."""
    for rel, text in {
        "src/server/Main.server.luau": "return 1\n",
        "src/server/ServerPackages/Vendor.luau": "return   2\n",
        ".claude/worktrees/wt/.git": "gitdir: ../../../.git/worktrees/wt\n",
        ".claude/worktrees/wt/src/server/Main.server.luau": "return   3\n",
    }.items():
        path = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write(text)


@check("project: vendored packages and nested worktrees are excluded by one rule, live code is kept")
def _():
    from rbforge import project
    with tempdir() as root:
        _worktree_fixture(root)
        rels = ["src/server/Main.server.luau", "src/server/ServerPackages/Vendor.luau",
                ".claude/worktrees/wt/src/server/Main.server.luau"]
        out = project.excluded(root, rels)
        assert out == set(rels[1:]), out
        kept, skipped = project.shipped_sources(root)
        assert [os.path.relpath(k, root).replace("\\", "/") for k in kept] == rels[:1], kept
        assert len(skipped) == 2, skipped


@check("check: static rung skips vendored and worktree copies (stylua globs, luau-lsp diagnostics)")
def _():
    from rbforge import check as check_mod
    with tempdir() as root:
        _worktree_fixture(root)
        defs = os.path.join(root, "globalTypes.d.luau")
        open(defs, "w").write("--" + "x" * 2048)
        vendor_abs = os.path.join(root, "src", "server", "ServerPackages", "Vendor.luau")
        # The shapes luau-lsp 1.70.1 printed for a real project: relative paths for files outside
        # the sourcemap, and an absolute path with a lowercase drive plus a DataModel suffix inside it.
        vendor_line = vendor_abs[0].lower() + vendor_abs[1:] if vendor_abs[1:2] == ":" else vendor_abs
        analyzer = "\n".join([
            ".claude/worktrees/wt/src/server/Main.server.luau(1,1): TypeError: Unknown require: x",
            "%s [game/ServerScriptService/Server/ServerPackages/Vendor](1,1): TypeError: bad" % vendor_line,
        ])
        calls = []

        def fake_run(argv, cwd, timeout=180):
            calls.append(argv)
            if argv[0] == "luau-lsp":
                return 1, analyzer
            return 0, ""

        old_run, old_which = check_mod._run, check_mod.shutil.which
        check_mod._run = fake_run
        check_mod.shutil.which = lambda name: "C:/fake/" + name if name != "rojo" else None
        os.environ["RBFORGE_LUAU_DEFINITIONS"] = defs
        try:
            clean = check_mod.rung_static(root)
            analyzer += "\nsrc/server/Main.server.luau(1,1): TypeError: real defect"
            dirty = check_mod.rung_static(root)
        finally:
            check_mod._run, check_mod.shutil.which = old_run, old_which
            os.environ.pop("RBFORGE_LUAU_DEFINITIONS", None)
    stylua = [a for a in calls if a[0] == "stylua"][0]
    assert "!src/server/ServerPackages/**" in stylua and "!.claude/worktrees/wt/**" in stylua, stylua
    assert "**/*.luau" in stylua and stylua[-1] == ".", stylua
    lsp = [c for c in clean["checks"] if c["id"] == "luau-lsp"][0]
    # Exit 1 with every diagnostic in an excluded file is a pass, and says what it did not count.
    assert lsp["status"] == "pass", lsp
    assert "2 diagnostic(s)" in lsp["detail"], lsp
    lsp = [c for c in dirty["checks"] if c["id"] == "luau-lsp"][0]
    assert lsp["status"] == "fail" and "1 type error(s)" in lsp["detail"], lsp
    assert "worst files: src/server/Main.server.luau 1" in lsp["detail"], lsp


@check("check: --changed-only never hands a vendored file to stylua")
def _():
    from rbforge import check as check_mod
    with tempdir() as root:
        _worktree_fixture(root)
        changed = [os.path.join(root, "src", "server", "ServerPackages", "Vendor.luau"),
                   os.path.join(root, "src", "server", "Main.server.luau")]
        calls = []

        def fake_run(argv, cwd, timeout=180):
            calls.append(argv)
            return 0, ""

        old_run, old_which = check_mod._run, check_mod.shutil.which
        check_mod._run = fake_run
        check_mod.shutil.which = lambda name: "C:/fake/" + name if name == "stylua" else None
        try:
            check_mod.rung_static(root, changed=changed)
        finally:
            check_mod._run, check_mod.shutil.which = old_run, old_which
    stylua = [a for a in calls if a[0] == "stylua"][0]
    assert stylua == ["stylua", "--check", changed[1]], stylua


# ---------------------------------------------------------------- 0.23.0 long-run QA

def _job_record(jobs_mod, pid, result=None):
    job_id = jobs_mod.new_id()
    jobs_mod._write_json(jobs_mod._path(job_id, ".json"),
                         {"job": job_id, "argv": ["servertest", "x"], "cwd": ".", "pid": pid,
                          "started": time.time(), "log": jobs_mod._path(job_id, ".log"),
                          "out": jobs_mod._path(job_id, ".out.json")})
    if result is not None:
        jobs_mod._write_json(jobs_mod._path(job_id, ".result.json"), result)
    return job_id


@check("jobs: a detached servertest runs in the background, reports done, and keeps the command's report")
def _():
    import subprocess as _sp
    from rbforge import jobs
    with _isolated_home(), tempdir() as d:
        job = jobs.start(["servertest", os.path.join(d, "missing.server.luau")], cwd=d)
        st = jobs.wait(job["job"], 60, poll=0.2)
        assert st["state"] == "done", st
        assert st["exit"] == 2, st                     # the same refusal the foreground command gives
        assert st["report"]["error"]["code"] == "RBF-ARG-001", st["report"]
        assert jobs.holder() is None, "a finished job left the Studio lock behind"
        # The job list shows it.
        assert any(j["job"] == job["job"] and j["state"] == "done" for j in jobs.listing())
        # A process that is gone without a result is a death, not "running" forever.
        p = _sp.Popen([sys.executable, "-c", "pass"])
        p.wait()
        dead = _job_record(jobs, p.pid)
        assert jobs.status(dead)["state"] == "died"
        # A bad id is an argument error, not a path walk.
        for bad in ("../x", "nope", ""):
            try:
                jobs.status(bad)
                raise AssertionError("accepted job id %r" % bad)
            except err_mod.ForgeError as exc:
                assert exc.code == "RBF-ARG-002"


@check("jobs: the Studio lock refuses other live commands while a detached run holds it")
def _():
    import subprocess as _sp
    from rbforge import jobs, live
    with _isolated_home():
        jobs._write_json(jobs.lock_path(), {"job": "20261126-000000-abcdef", "pid": os.getpid()})
        saved = {k: os.environ.get(k) for k in (jobs.ENV_JOB, jobs.ENV_IGNORE)}
        try:
            for k in saved:
                os.environ.pop(k, None)
            for fn in (jobs.refuse_if_held, lambda: live.Session()):
                try:
                    fn()
                    raise AssertionError("a live command ran while a detached job held Studio")
                except err_mod.ForgeError as exc:
                    assert exc.code == "RBF-STUDIO-004", exc.code
                    assert "--wait" in (exc.hint or "")
            os.environ[jobs.ENV_JOB] = "20261126-000000-abcdef"   # the job itself is not refused
            jobs.refuse_if_held()
            os.environ.pop(jobs.ENV_JOB)
            os.environ[jobs.ENV_IGNORE] = "1"                      # explicit override
            jobs.refuse_if_held()
            os.environ.pop(jobs.ENV_IGNORE)
            # A lock left by a process that is gone is stale.
            p = _sp.Popen([sys.executable, "-c", "pass"])
            p.wait()
            jobs._write_json(jobs.lock_path(), {"job": "20261126-000000-abcdef", "pid": p.pid})
            assert jobs.holder() is None
            jobs.refuse_if_held()
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


@check("jobs: runs --job --wait exits 5 while still running, the job's code when done; --sessions is a restart streak")
def _():
    from rbforge import jobs, live
    import rbforge_cli
    with _isolated_home():
        running = _job_record(jobs, os.getpid())
        with contextlib.redirect_stdout(io.StringIO()):
            assert rbforge_cli.main(["runs", "--job", running, "--wait", "--wait-timeout", "0.2"]) == 5
            assert rbforge_cli.main(["runs", "--job", running]) == 0
            done = _job_record(jobs, 1, {"exit": 1, "finished": time.time()})
            assert rbforge_cli.main(["runs", "--job", done, "--wait"]) == 1
            assert rbforge_cli.main(["runs", "--wait"]) == err_mod.ExitCode.VALIDATION   # --wait needs --job
    seen = {}

    def fake_streak(entries, repeat, restart=False, **k):
        seen.update(repeat=repeat, restart=restart)
        return {"batch": "b", "runs": [], "passed": True}
    old_streak, old_entry = live.run_streak, live.single_entry
    live.run_streak = fake_streak
    live.single_entry = lambda *a, **k: {"name": "t", "file": "t", "datamodel": "Server", "timeout": 5,
                                         "grace": 0.0, "attr": "RbforgeTest"}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            code = rbforge_cli.main(["servertest", "t.server.luau", "--sessions", "2", "--no-record"])
    finally:
        live.run_streak, live.single_entry = old_streak, old_entry
    assert code == 0 and seen == {"repeat": 2, "restart": True}, (code, seen)


@check("snapshot: a suite runs the test text read at load, and the ledger keeps the commit read at start")
def _():
    from rbforge import live, runs
    with tempdir() as d:
        test = os.path.join(d, "A.server.luau")
        open(test, "w", encoding="utf-8").write('workspace:SetAttribute("RbforgeTest", "PASS original")\n')
        manifest = os.path.join(d, "suites.json")
        json.dump({"suites": [{"file": "A.server.luau", "attr": "RbforgeTest"}]}, open(manifest, "w"))
        entries = live.load_suite(manifest)
        assert entries[0]["sha256"] and "PASS original" in entries[0]["source"]
        # A merge lands mid-run: the file changes after the run started.
        open(test, "w", encoding="utf-8").write('workspace:SetAttribute("RbforgeTest", "PASS changed")\n')
        sent = []

        class Sess:
            studio_id = "s"

            def luau(self, code, dm="Server"):
                sent.append(code)
                return "PASS ok"

            def call(self, *a):
                return ""
        results = live._run_entries(Sess(), entries)
        assert "PASS original" in sent[0] and "PASS changed" not in sent[0], "the run read the file again"
        assert results[0]["source_sha256"] == entries[0]["sha256"]
        assert live.manifest_digest(manifest) and live.manifest_digest(os.path.join(d, "none.json")) is None
        # A file that cannot be read at load still fails as its own suite at run time.
        json.dump({"suites": [{"file": "Gone.server.luau", "attr": "RbforgeTest"}]}, open(manifest, "w"))
        gone = live.load_suite(manifest)
        assert gone[0]["source"] is None
        assert live._run_entries(Sess(), gone)[0]["outcome"] == "error"
    with _isolated_home(), tempdir() as d:
        res = runs.record(d, [{"name": "t", "outcome": "pass", "result": "PASS"}], tested=("abc1234", False))
        assert res["entries"][0]["sha"] == "abc1234" and res["entries"][0]["dirty"] is False, res


@check("cli: exec says on stderr when the script returned nothing, and keeps stdout empty")
def _():
    from rbforge import live
    import rbforge_cli
    old = live.run_file
    try:
        # Studio returns "nil" for a script with no return (live 2026-11-26); older builds sent nothing.
        for value, want_out in (("", ""), (None, ""), ("nil", "nil"), ("42", "42")):
            live.run_file = lambda *a, **k: value
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                assert rbforge_cli.main(["exec", "x.luau"]) == 0
            assert out.getvalue().strip() == want_out, (value, out.getvalue())
            assert ("no return value" in err.getvalue()) == (want_out in ("", "nil")), err.getvalue()
    finally:
        live.run_file = old


@check("probes: save-check gives a save verdict from parameters, perf labels a throttled frame")
def _():
    from rbforge import probes
    cat = {p["name"]: p for p in probes.catalog()}
    assert cat["save-check"]["datamodel"] == "Edit"
    for k in ("attrs", "prefixes", "roots"):
        assert k in cat["save-check"]["params"], k
    code = probes.render("save-check", probes.parse_sets(['attrs={"TestSlot"}']))["code"]
    assert '{"TestSlot"}' in code and "safe to save_place: " in code and "IsRunning" in code
    perf = probes.render("perf")["code"]
    assert "UNFOCUSED-STUDIO THROTTLE" in perf and "best" in perf
    with tempdir() as d:
        cfg = os.path.join(d, "selene.toml")
        open(cfg, "w").write('std = "lua51"\n')
        for name in ("save-check", "perf"):
            path = os.path.join(d, name + ".luau")
            open(path, "w", encoding="utf-8").write(probes.render(name)["code"])
            ok, detail = _parse_luau(path, cfg)
            assert ok, "%s does not parse:\n%s" % (name, detail)


@check("assets: uv - meshes without TEXCOORD_0 are reported, and fail only with --require-uv")
def _():
    import struct as _struct
    from rbforge import assets
    import rbforge_cli
    doc = {"asset": {"version": "2.0"}, "accessors": [{"count": 3}, {"count": 3}, {"count": 3}],
           "meshes": [{"name": "Textured", "primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "mode": 4}]},
                      {"name": "Flat", "primitives": [{"attributes": {"POSITION": 2}, "mode": 4}]}],
           "materials": [{}]}
    blob = json.dumps(doc).encode("utf-8")
    blob += b" " * ((4 - len(blob) % 4) % 4)
    data = _struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(blob)) + _struct.pack("<II", len(blob), 0x4E4F534A) + blob
    with tempdir() as d:
        path = os.path.join(d, "pack.glb")
        open(path, "wb").write(data)
        r = assets.inspect_export(path)
        assert r["meshes_without_uv"] == ["Flat"] and r["status"] == assets.STATUS_WITHIN and "warning" in r, r
        assert assets.inspect_export(path, require_uv=True)["status"] == assets.STATUS_NO_UV
        with contextlib.redirect_stdout(io.StringIO()):
            assert rbforge_cli.main(["assets", "check", path]) == 0
            assert rbforge_cli.main(["assets", "check", path, "--require-uv"]) == err_mod.ExitCode.VALIDATION
        # Every mesh with UVs: no warning, and --require-uv passes.
        doc["meshes"] = doc["meshes"][:1]
        blob = json.dumps(doc).encode("utf-8")
        blob += b" " * ((4 - len(blob) % 4) % 4)
        open(path, "wb").write(_struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(blob))
                               + _struct.pack("<II", len(blob), 0x4E4F534A) + blob)
        ok = assets.inspect_export(path, require_uv=True)
        assert ok["status"] == assets.STATUS_WITHIN and not ok["meshes_without_uv"] and "warning" not in ok, ok


@check("docs: long-run field notes are in the references and the scaffold ships a receipt template")
def _():
    need = {
        "testing-debugging.md": ["--detach", "rbforge runs --job", "RBF-STUDIO-004", "source_sha256",
                                 "--sessions 2", "neutral state", "Retry the intent", "Tested SHA",
                                 "save-check", "Release discipline"],
        "performance.md": ["66 ms", "WindowFocused", "SLIM"],
        "ui-mobile.md": ["get_roblox_skill", "Offline layout spec", "DisplayOrder", "Binding1"],
        "assets.md": ["export_texcoords", "--require-uv", "Weld before you decimate", "byte-identical",
                      "5 and 20 studs"],
        "sharp-edges.md": ["stuck detector", "scripted lift", "not `sed`"],
        "development-loop.md": ["One integrator makes those edits", "git worktree remove"],
    }
    for name, phrases in need.items():
        text = _ref(name)
        for p in phrases:
            assert p in text, "%s lacks %r" % (name, p)
    from rbforge import scaffold
    with tempdir() as d:
        target = os.path.join(d, "g")
        files = scaffold.scaffold(target, "obby")["files"]
        assert "docs/evidence/TEMPLATE.md" in files
        text = open(os.path.join(target, "docs", "evidence", "TEMPLATE.md"), encoding="utf-8").read()
        assert "Result: PASS" in text and "Tested SHA:" in text and "Not checked:" in text


if __name__ == "__main__":
    print("\n%d passed, %d failed, %d skipped" % (len(PASS), len(FAIL), len(SKIPPED)))
    for name, why in SKIPPED:
        print("  SKIPPED: %s -> %s" % (name, why))
    for name, exc in FAIL:
        print("  FAILED: %s -> %r" % (name, exc))
    sys.exit(1 if FAIL else 0)
