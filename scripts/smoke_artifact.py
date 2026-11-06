"""Smoke-test an unpacked RobloxForge release artifact.

The release workflow used to run `python tests/run_tests.py || echo "tests not shipped"` inside the
archive - a check that could not fail, because tests/ is deliberately not shipped. This script
tests what a downloader actually gets: the package imports, the CLI starts, an offline command
produces real output, both skills are present, and the MCP server answers `initialize` and
`tools/list`. Any failure exits non-zero so the release stops.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "src", "rbforge_cli.py")
SERVER = os.path.join(ROOT, "mcp_server", "server.py")
EXPECTED_TOOLS = ("rb_check", "rb_verify_receipt", "rb_studio_push", "rb_traps_review")


def fail(message):
    print("SMOKE FAIL: %s" % message)
    sys.exit(1)


def run(argv):
    return subprocess.run([sys.executable] + argv, capture_output=True, text=True)


def main():
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import rbforge

    print("import rbforge %s" % rbforge.__version__)

    out = run([CLI, "--help"])
    if out.returncode != 0 or "check" not in out.stdout:
        fail("CLI --help rc=%s %s" % (out.returncode, (out.stderr or out.stdout)[:300]))
    print("cli --help ok")

    out = run([CLI, "probe"])
    if out.returncode != 0 or "console" not in out.stdout:
        fail("rbforge probe rc=%s %s" % (out.returncode, (out.stderr or out.stdout)[:300]))
    print("probe list ok")

    for name in ("roblox-game-development", "roblox-docs"):
        if not os.path.isfile(os.path.join(ROOT, "skills", name, "SKILL.md")):
            fail("missing skill %s" % name)
    print("skills present")

    proc = subprocess.Popen([sys.executable, SERVER], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, text=True)
    assert proc.stdin is not None and proc.stdout is not None
    try:
        def rpc(message):
            proc.stdin.write(json.dumps(message) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
            if not line:
                fail("MCP server closed the pipe")
            return json.loads(line)

        init = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "smoke", "version": "1"}}})
        if "result" not in init:
            fail("initialize returned %s" % json.dumps(init)[:300])
        listed = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = (listed.get("result") or {}).get("tools") or []
        names = {t.get("name") for t in tools}
        missing = [n for n in EXPECTED_TOOLS if n not in names]
        if missing:
            fail("tools/list missing %s (got %d tools)" % (missing, len(names)))
        print("mcp handshake ok: %d tools" % len(names))
    finally:
        proc.kill()

    print("SMOKE OK")


if __name__ == "__main__":
    main()
