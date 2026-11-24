#!/usr/bin/env python3
"""rbforge CLI - every MCP tool has a CLI equivalent here.

Exit codes: 0 ok, 1 generic, 2 validation, 3 not-found, 4 dependency, 5 refused.
All output is JSON (machine-readable by default).
"""
import argparse
import json
import sys
import time

import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rbforge.errors import ForgeError, ExitCode
from rbforge.planning import GENRE_CHOICES as GENRES


def _emit(obj):
    print(json.dumps(obj, indent=2, default=str))


def _fail(exc):
    _emit(exc.to_dict())
    return exc.exit_code


def _utf8_output():
    """Print UTF-8 whatever the console code page: a path outside cp1252 (a Cyrillic user name)
    used to raise UnicodeEncodeError from `print` and turn a finished check into a traceback."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    _utf8_output()
    parser = argparse.ArgumentParser(prog="rbforge",
                                     description="RobloxForge - AI-operable Roblox development workbench")
    from rbforge import __version__
    parser.add_argument("--version", action="version", version="rbforge %s" % __version__)
    sub = parser.add_subparsers(dest="cmd")

    p_doc = sub.add_parser("doctor", help="full health report")
    p_doc.add_argument("--no-probe", action="store_true", help="skip live MCP handshake")
    p_doc.add_argument("--vision", choices=["yes", "no"], default=None,
                       help="declare whether the host model can inspect images")

    sub.add_parser("capabilities", help="honest capability matrix")

    p_docs = sub.add_parser("docs", help="creator-docs knowledge cache")
    p_docs.add_argument("action", choices=["status", "update", "search", "read"])
    p_docs.add_argument("query", nargs="?", help="search query or document path")
    p_docs.add_argument("--limit", type=int, default=8)
    p_docs.add_argument("--around", help="read around this phrase")

    p_tools = sub.add_parser("tools", help="optional Luau toolchain status")
    p_tools.add_argument("action", nargs="?", default="status", choices=["status"])

    p_opt = sub.add_parser("optimize", help="which optimization levels this project has earned")
    p_opt.add_argument("--root", default=".", help="project directory to scan")
    p_opt.add_argument("--premise", default="", help="one line describing the game")
    p_opt.add_argument("--text", action="store_true", help="human-readable instead of JSON")

    p_types = sub.add_parser("types", help="Roblox type definitions for the luau-lsp typecheck")
    p_types.add_argument("action", nargs="?", default="status", choices=["status", "fetch"])
    p_types.add_argument("--force", action="store_true", help="re-download even when cached")

    p_assets = sub.add_parser("assets", help="Blender/add-on detection and mesh export validation")
    p_assets.add_argument("action", nargs="?", default="status", choices=["status", "check"])
    p_assets.add_argument("path", nargs="?", help="export to check (.glb/.gltf/.fbx/.obj)")
    p_map = sub.add_parser("map", help="optional external map prover (SyphoDev roblox-map)")
    p_map.add_argument("action", nargs="?", default="status", choices=["status", "prove"])
    p_map.add_argument("spec", nargs="?", help="spec name in its specs/ folder, or a path to a .json")
    p_map.add_argument("--out", help="where to write the JSON report")
    p_map.add_argument("--res", type=float, help="surface sampling resolution in studs (upstream default 4)")

    p_check = sub.add_parser("check", help="offline verification gate (run before Studio)")
    # Both `rbforge check .` and `rbforge check --root .` are documented; accept either.
    p_check.add_argument("path", nargs="?", help="project directory (same as --root)")
    p_check.add_argument("--root", default=None, help="project directory to check")
    p_check.add_argument("--scope", nargs="+", choices=["static", "unit", "structure"],
                         help="limit which rungs run")
    p_check.add_argument("--changed-only", action="store_true",
                         help="limit format/lint to files changed in git (never claims the project is clean)")
    p_check.add_argument("--base-ref", default="HEAD",
                         help="with --changed-only: diff against this commit (default HEAD = working tree)")
    p_check.add_argument("--json", action="store_true", help="machine-readable report")

    p_agents = sub.add_parser("agent", help="agent MCP wiring + skills")
    p_agents.add_argument("action", choices=["status", "connect", "disconnect"])
    p_agents.add_argument("name", nargs="?", help="hermes|claude|codex|grok|kimi (or 'all')")

    p_scaf = sub.add_parser("scaffold", help="create a project from a genre template")
    p_scaf.add_argument("path")
    p_scaf.add_argument("--genre", default="generic",
                        choices=GENRES)

    p_new = sub.add_parser("new", help="scaffold + slice plan + next steps in one go")
    p_new.add_argument("path")
    p_new.add_argument("--genre", default="generic",
                       choices=GENRES)
    p_new.add_argument("--premise", default="", help="one sentence: what the game is")

    p_plan = sub.add_parser("plan", help="vertical-slice plan for a premise")
    p_plan.add_argument("genre", choices=GENRES)
    p_plan.add_argument("premise")

    p_audit = sub.add_parser("audit", help="ranked health report for an existing project: what to fix first")
    p_audit.add_argument("path", nargs="?", default=".")
    p_audit.add_argument("--json", action="store_true", help="machine-readable report")

    p_rev = sub.add_parser("review", help="static architecture/security review")
    p_rev.add_argument("target", nargs="?", default=None, help="project root (same as --path)")
    p_rev.add_argument("--path", default=".")
    p_rev.add_argument("--live", action="store_true", help="review the live Studio place")
    p_rev.add_argument("--kind", default="both", choices=["both", "architecture", "security", "traps", "all"],
                       help="traps = engine-trap lint (Luau that compiles but breaks in Roblox); all = everything")

    p_probe = sub.add_parser("probe", help="ready-made Luau diagnostics for execute_luau (list, or render one)")
    p_probe.add_argument("name", nargs="?", help="probe name; omit to list")
    p_probe.add_argument("--set", action="append", default=[], metavar="KEY=LUAU",
                         help='override a parameter with a Luau expression, e.g. --set pattern=\"Door\"')
    p_probe.add_argument("--json", action="store_true", help="emit JSON instead of raw code")
    p_probe.add_argument("--run", action="store_true", help="run it in Studio now (official MCP) and print the result")
    p_probe.add_argument("--dm", choices=["Edit", "Client", "Server"], help="datamodel for --run (default: the probe's)")
    p_probe.add_argument("--studio", help="Studio id for --run (auto when one Studio is open)")

    p_push = sub.add_parser("push", help="set Studio script sources from disk via the official MCP, checksum-verified")
    p_push.add_argument("paths", nargs="+", help="source files mapped by the Rojo project, or ALL")
    p_push.add_argument("--project", default="default.project.json")
    p_push.add_argument("--studio")
    p_push.add_argument("--force", action="store_true",
                        help="overwrite scripts edited in Studio since the last push (backed up first)")

    p_exec = sub.add_parser("exec", help="run a Luau file in Studio (official MCP) and print what it returns")
    p_exec.add_argument("file")
    p_exec.add_argument("--dm", default="Edit", choices=["Edit", "Client", "Server"])
    p_exec.add_argument("--studio")

    p_st = sub.add_parser("servertest", help="run a test as a temporary server Script in Play (shares module cache)")
    p_st.add_argument("file", nargs="?")
    p_st.add_argument("attr", nargs="?",
                      help="attribute the test sets to 'PASS ...' or 'FAIL ...' on workspace or its own Script "
                           "(default RbforgeTest)")
    p_st.add_argument("--timeout", type=int, default=120)
    p_st.add_argument("--studio")
    p_st.add_argument("--dm", default="Server", choices=["Server", "Client"],
                      help="Client runs the test as a LocalScript in the local player's PlayerScripts")
    p_st.add_argument("--ready", help="wait for <instance path>.<Attribute>=<value> before the test starts")
    p_st.add_argument("--grace", type=float, default=0.0,
                      help="seconds to wait after the result before destroying the test Script "
                           "(destroying it kills the threads it started)")
    p_st.add_argument("--keep", action="store_true", help="leave the test Script in place (stopping Play discards it)")
    p_st.add_argument("--suite", help="JSON manifest of suites; exit code is the number of failed suites")
    p_st.add_argument("--repeat", type=int, default=None,
                      help="run the test (or the whole --suite) N times; exit 0 only for N passes in a row")
    p_st.add_argument("--restart", action="store_true",
                      help="with --repeat: a fresh Play session before every run (starts Play from Edit)")
    p_st.add_argument("--keep-going", action="store_true",
                      help="with --repeat: run all N even after a failure (default: stop and leave Play running)")
    p_st.add_argument("--play-timeout", type=float, default=90.0,
                      help="seconds to wait for Play to stop or start with --restart (default 90)")
    p_st.add_argument("--no-record", action="store_true",
                      help="do not append this run to the project's run ledger (`rbforge runs`)")

    p_runs = sub.add_parser("runs", help="live test history for a project: pass rate and streaks per test")
    p_runs.add_argument("--root", default=".", help="project directory (default: the current one)")
    p_runs.add_argument("--test", help="only tests whose name contains this")
    p_runs.add_argument("--last", type=int, help="only each test's N newest runs")
    p_runs.add_argument("--text", action="store_true", help="a table instead of JSON")

    p_proj = sub.add_parser("project", help="analyze an existing project layout")
    p_proj.add_argument("path", nargs="?", default=".")

    sub.add_parser("plugins", help="detected Studio plugins and their free alternatives")

    p_skills = sub.add_parser("skills", help="install/update RobloxForge skills into agents")
    p_skills.add_argument("action", choices=["status", "install", "update", "remove"])
    p_skills.add_argument("name", nargs="?", help="hermes|claude|codex|grok|kimi or all")

    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return ExitCode.OK

    try:
        return _dispatch(args)
    except ForgeError as exc:
        return _fail(exc)
    except OSError as exc:
        # Backstop for a file the caller named: every failure is JSON with a code, never a traceback.
        return _fail(ForgeError("RBF-ARG-001", "%s: %s" % (type(exc).__name__, exc),
                                hint="check the path you passed"))


def _dispatch(args):
    from rbforge import agents, capabilities, doctor, docs as docs_mod, skills, tooling

    if args.cmd == "doctor":
        report = doctor.collect(probe=not args.no_probe,
                                host_vision={"yes": True, "no": False}.get(args.vision))
        print(doctor.render(report))
        return ExitCode.OK

    if args.cmd == "capabilities":
        _emit(capabilities.compute(host_vision=None))
        return ExitCode.OK

    if args.cmd == "docs":
        if args.action == "status":
            _emit(docs_mod.freshness())
        elif args.action == "update":
            _emit(docs_mod.ensure(refresh=True))
        elif args.action == "search":
            if not args.query:
                raise ForgeError("RBF-ARG-001", "docs search needs a query",
                                 hint='rbforge docs search "TweenService:Create"')
            _emit(docs_mod.search(args.query, limit=args.limit))
        elif args.action == "read":
            if not args.query:
                raise ForgeError("RBF-ARG-001", "docs read needs a path",
                                 hint="use a path returned by docs search")
            _emit(docs_mod.read(args.query, around=args.around))
        return ExitCode.OK

    if args.cmd == "tools":
        _emit(tooling.status())
        return ExitCode.OK

    if args.cmd == "optimize":
        from rbforge import optimize as opt_mod

        prof = opt_mod.profile(args.root, args.premise)
        _emit(prof if not args.text else {"text": opt_mod.render(prof)})
        return ExitCode.OK

    if args.cmd == "assets":
        from rbforge import assets

        if args.action == "check":
            if not args.path:
                _emit({"error": "check needs an export path",
                       "detail": "rbforge assets check <file.glb|file.fbx>"})
                return ExitCode.VALIDATION
            report = assets.inspect_export(args.path)
            _emit(report)
            status = report.get("status")
            if status == assets.STATUS_INVALID:
                return ExitCode.VALIDATION   # malformed or wrong type: the file is the problem
            if status == assets.STATUS_OVER:
                return ExitCode.VALIDATION   # measured, and over Roblox's per-mesh cap
            if status == assets.STATUS_UNVERIFIED:
                return ExitCode.DEPENDENCY   # recognised but nothing was proven: cannot pass a gate
            return ExitCode.OK
        _emit(assets.status())
        return ExitCode.OK

    if args.cmd == "map":
        from rbforge import mapkit

        if args.action == "prove":
            if not args.spec:
                _emit({"error": "prove needs a spec",
                       "detail": "rbforge map prove <name|path.json> [--out report.json]"})
                return ExitCode.VALIDATION
            report = mapkit.prove(args.spec, out_path=args.out, res=args.res)
            _emit(report)
            if not report.get("available"):
                return ExitCode.DEPENDENCY       # external prover absent or unusable: incomplete, not a pass
            if report.get("reason") and not report.get("report"):
                return ExitCode.VALIDATION       # ran nothing, or wrote nothing readable
            return ExitCode.OK if report.get("ok") else ExitCode.VALIDATION
        _emit(mapkit.status())
        return ExitCode.OK

    if args.cmd == "types":
        from rbforge import types as types_mod

        if args.action == "fetch":
            path, digest, size = types_mod.fetch(force=args.force)
            _emit({"ok": True, "path": path, "sha256": digest, "bytes": size})
        else:
            _emit(types_mod.status())
        return ExitCode.OK

    if args.cmd == "check":
        from rbforge import check as check_mod

        if args.path and args.root and os.path.abspath(args.path) != os.path.abspath(args.root):
            _emit({"error": "conflicting project paths",
                   "detail": "pass the project directory once: `check [path]` or `check --root <dir>`",
                   "path": args.path, "root": args.root})
            return ExitCode.VALIDATION
        target = args.path or args.root or "."
        report = check_mod.run(target, scope=args.scope, changed_only=args.changed_only,
                               base_ref=args.base_ref)
        if args.json:
            _emit(report)
        else:
            print(check_mod.render(report))
        # 0 = clean, 2 = a defect was proven, 4 = tooling missing so not verified.
        return {"pass": ExitCode.OK, "fail": ExitCode.VALIDATION,
                "incomplete": ExitCode.DEPENDENCY}[report["status"]]

    if args.cmd == "agent":
        names = None if (not args.name or args.name == "all") else [args.name]
        if args.action == "status":
            st = agents.status(names)
            _emit(st)
        elif args.action == "connect":
            _emit(agents.connect(names))
        elif args.action == "disconnect":
            _emit(agents.disconnect(names))
        return ExitCode.OK

    if args.cmd == "skills":
        names = None if (not args.name or args.name == "all") else [args.name]
        if args.action == "status":
            # status() covers every agent at once; filter client-side, but a typo is an error,
            # not an empty object that reads like "nothing installed".
            if names and names[0] not in skills._ROOTS:
                raise ForgeError("RBF-ARG-001", "unknown agent %r" % names[0],
                                 hint="one of: %s, or all" % ", ".join(sorted(skills._ROOTS)))
            st = skills.status()
            _emit(st if names is None else {k: v for k, v in st.items()
                                            if k in names})
        else:
            fn = {"install": skills.install, "update": skills.install,
                  "remove": skills.remove}[args.action]
            _emit(fn(names))
        return ExitCode.OK

    if args.cmd == "scaffold":
        from rbforge import scaffold
        _emit(scaffold.scaffold(args.path, args.genre))
        return ExitCode.OK

    if args.cmd == "new":
        from rbforge import scaffold
        _emit(scaffold.new_project(args.path, args.genre, args.premise))
        return ExitCode.OK

    if args.cmd == "plan":
        from rbforge import planning
        _emit(planning.vertical_slice(args.genre, args.premise))
        return ExitCode.OK

    if args.cmd == "audit":
        from rbforge import audit
        report = audit.audit(args.path)
        if args.json:
            _emit(report)
        else:
            print(audit.render(report))
        return ExitCode.OK

    if args.cmd == "review":
        from rbforge import review
        if args.target:
            args.path = args.target
        out = {}
        if args.kind in ("both", "architecture", "all"):
            out["architecture"] = review.architecture(path=args.path, live=args.live)
        if args.kind in ("both", "security", "all"):
            out["security"] = review.security(path=args.path, live=args.live)
        if args.kind in ("traps", "all"):
            from rbforge import traps
            out["traps"] = traps.review(args.path)
        _emit(out)
        return ExitCode.OK

    if args.cmd == "probe":
        from rbforge import probes
        if not args.name:
            _emit({"probes": probes.catalog(),
                   "usage": "rbforge probe <name> [--set key=luau]  ->  paste into execute_luau"})
            return ExitCode.OK
        if args.run:
            from rbforge import live
            out = live.run_probe(args.name, probes.parse_sets(args.set), args.dm, args.studio)
            print(out["output"])
            return ExitCode.OK
        res = probes.render(args.name, probes.parse_sets(args.set))
        if args.json:
            _emit(res)
        else:
            print("-- run: %s" % res["run"])
            print(res["code"])
        return ExitCode.OK

    if args.cmd == "push":
        from rbforge import live
        res = live.push(args.paths, args.project, args.studio, force=args.force)
        _emit(res)
        return ExitCode.OK if not res["failed"] else 1

    if args.cmd == "exec":
        from rbforge import live
        print(live.run_file(args.file, args.dm, args.studio))
        return ExitCode.OK

    if args.cmd == "servertest":
        from rbforge import live, runs
        progress = lambda line: print(line, file=sys.stderr, flush=True)  # noqa: E731 - stdout stays JSON
        if args.suite and (args.file or args.attr):
            raise ForgeError("RBF-ARG-001", "pass either --suite or FILE ATTR, not both")
        if not args.suite and not args.file:
            raise ForgeError("RBF-ARG-001", "servertest needs FILE [ATTR], or --suite MANIFEST")
        if args.repeat is None and (args.restart or args.keep_going):
            raise ForgeError("RBF-ARG-001", "--restart and --keep-going belong to --repeat N",
                             hint="for one fresh run: --repeat 1 --restart")
        root = runs.project_root(args.suite or args.file)

        def keep(res, streak):
            # Ledger + logs, then the full console text leaves the JSON either way (logs hold it).
            if args.no_record:
                runs.compact(streak)
            else:
                res["record"] = runs.record_streak(root, streak)

        if args.repeat is not None:
            entries = live.load_suite(args.suite) if args.suite else [live.single_entry(
                args.file, args.attr or "RbforgeTest", args.timeout, args.dm, args.ready, args.grace, args.keep)]
            res = live.run_streak(entries, args.repeat, restart=args.restart, keep_going=args.keep_going,
                                  studio_id=args.studio, report=progress, play_timeout=args.play_timeout)
            keep(res, res)
            _emit(res)
            return ExitCode.OK if res["passed"] else 1
        if args.suite:
            # One progress line per suite on stderr; the JSON report stays the only stdout.
            res = live.run_suite(args.suite, args.studio, report=progress, forensics=True)
            keep(res, {"runs": [{"run": 1, "tests": res["suites"]}]})
            _emit(res)
            return min(res["failed"], 100)
        # The documented default: a test that reports through `RbforgeTest` needs no second argument.
        t0 = time.time()
        res = live.server_test(args.file, args.attr or "RbforgeTest", args.timeout, args.studio, datamodel=args.dm,
                               ready=args.ready, grace=args.grace, keep=args.keep, forensics=True)
        res.setdefault("name", args.file)
        res.setdefault("datamodel", args.dm)
        res.setdefault("seconds", round(time.time() - t0, 2))
        keep(res, {"runs": [{"run": 1, "tests": [res]}]})
        _emit(res)
        return ExitCode.OK if res["passed"] else 1

    if args.cmd == "runs":
        from rbforge import runs
        if args.last is not None and args.last < 1:
            raise ForgeError("RBF-ARG-002", "--last must be 1 or more")
        summary = runs.summarize(runs.project_root(args.root), test=args.test, last=args.last)
        if args.text:
            print(runs.render(summary))
        else:
            _emit(summary)
        return ExitCode.OK

    if args.cmd == "project":
        from rbforge import project
        _emit(project.analyze(args.path))
        return ExitCode.OK

    if args.cmd == "plugins":
        from rbforge import plugins
        _emit(plugins.status())
        return ExitCode.OK

    return ExitCode.GENERIC


if __name__ == "__main__":
    sys.exit(main())
