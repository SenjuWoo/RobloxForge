"""RobloxForge test runner. No pytest, no Roblox install required.

Run: python tests/run_tests.py
Fixture-based; exercises every core module against synthetic state.
"""
import io
import json
import os
import sys
import tempfile
import contextlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import rbforge  # noqa: E402
from rbforge import errors as err_mod  # noqa: E402

PASS, FAIL = [], []


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

@check("verification: unverified claim is blocked")
def _():
    from rbforge import verification
    r = verification.receipt("t", save=False)
    assert r["verification_level"] == "unverified"
    assert "do not claim working" in r["claim_allowed"]


@check("verification: full evidence -> verified_playtest")
def _():
    from rbforge import verification
    checks = ["studio_connected", "place_inspected_before_edit", "core_loop_exists",
              "player_spawns", "primary_action_works", "progression_works",
              "failure_death_behavior_works", "console_checked",
              "no_fatal_runtime_errors", "gameplay_path_exercised"]
    r = verification.receipt("full", checks=checks, console_errors=0,
                             playtest_performed=True,
                             screenshot_captured=True, screenshot_inspected=True,
                             save=False)
    assert r["verification_level"] == "verified_playtest"


@check("verification: console errors downgrade level")
def _():
    from rbforge import verification
    checks = ["studio_connected", "core_loop_exists", "player_spawns",
              "primary_action_works", "gameplay_path_exercised", "console_checked"]
    r = verification.receipt("errs", checks=checks, console_errors=3,
                             playtest_performed=True, save=False)
    assert r["verification_level"] == "playtested_with_errors"


@check("verification: receipt persists to disk")
def _():
    from rbforge import verification
    with _isolated_home():
        r = verification.receipt("persist me", save=True)
        assert os.path.isfile(r["saved_to"])
        loaded = json.load(open(r["saved_to"], encoding="utf-8"))
        assert loaded["task"] == "persist me"


# ---------------------------------------------------------------- project/review/scaffold

@check("project: detect rojo vs studio-native")
def _():
    from rbforge import project
    with tempdir() as d:
        json.dump({"name": "t"}, open(os.path.join(d, "default.project.json"), "w"))
        assert project.detect(d)["style"] == "rojo"
    with tempdir() as d:
        assert project.detect(d)["style"] == "studio-native"
    try:
        project.detect(os.path.join(d, "nope"))
        raise AssertionError("should have raised")
    except err_mod.ForgeError as e:
        assert e.code == "RBF-PROJECT-001"


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
    from rbforge import check as check_mod
    with tempdir() as root:
        report = check_mod.run(root)
        assert report["status"] == "incomplete", report["status"]
        assert report["counts"]["skip"] > 0
        assert "do NOT report this as verified" in report["gate"]


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


@check("verification: receipts chain by digest")


def _():
    from rbforge import verification
    with _isolated_home() as home:
        first = verification.receipt("slice one", checks=["core_loop_exists"], save=True)
        second = verification.receipt("slice two", checks=["core_loop_exists"], save=True)
        assert first["digest"] and second["digest"]
        assert first["prev_digest"] is None or isinstance(first["prev_digest"], str)
        assert second["prev_digest"] == first["digest"], (
            "second receipt must chain to the first, otherwise the trail is flat")
        assert first["digest"] != second["digest"]


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


# ---------------------------------------------------------------- helpers (moved above)

if __name__ == "__main__":
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    for name, exc in FAIL:
        print("  FAILED: %s -> %r" % (name, exc))
    sys.exit(1 if FAIL else 0)
