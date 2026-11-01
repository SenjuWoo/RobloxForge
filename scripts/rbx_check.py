#!/usr/bin/env python3
"""Project-local entry point for the verification gate.

Exists so an agent working inside a *game* repo can run the same gate without
knowing where RobloxForge is installed:

    python scripts/rbx_check.py .          # copy this file into the project
    rbforge check .                        # or run it from the install

Nothing here reimplements checks - it adds src/ to sys.path when present and
delegates to rbforge.check, so the rules live in exactly one place.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if os.path.isdir(os.path.join(ROOT, "rbforge")):
    sys.path.insert(0, ROOT)
elif os.path.isdir(os.path.join(ROOT, "src", "rbforge")):
    sys.path.insert(0, os.path.join(ROOT, "src"))
else:
    sys.stderr.write("rbforge package not found; run `rbforge check` instead\n")
    sys.exit(4)

from rbforge import check  # noqa: E402

target = sys.argv[1] if len(sys.argv) > 1 else "."
report = check.run(target)
print(check.render(report))
sys.exit({"pass": 0, "fail": 2, "incomplete": 4}[report["status"]])
