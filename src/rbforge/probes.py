"""Studio probes: ready-made Luau diagnostics for the official MCP's execute_luau.

Small models lose most of their time writing ad-hoc inspection code that is
subtly wrong (a raycast that skips CanQuery=false parts, a box query that does
the same, a camera that moves between captures). A probe is a reviewed snippet
with a header:

    -- probe: <name>
    -- datamodel: Edit | Client | Server | any
    -- params: key=default key2="string default"
    -- purpose: one paragraph (continued on lines starting with "--   ")

`{{key}}` in the body is replaced by a Luau expression (the default or an
override). Rendering never runs anything; the agent passes the code to
execute_luau with the datamodel the header names.
"""
import os
import re
import shlex

from .errors import ForgeError
from . import paths

_HEADER = re.compile(r"^--\s*(probe|datamodel|params|purpose):\s*(.*)$")
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def probes_dir():
    return os.path.join(paths.templates_dir(), "probes")


def _parse(path):
    meta = {"name": None, "datamodel": "any", "params": {}, "purpose": ""}
    in_purpose = False
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    for line in lines:
        m = _HEADER.match(line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            in_purpose = key == "purpose"
            if key == "probe":
                meta["name"] = val
            elif key == "datamodel":
                meta["datamodel"] = val
            elif key == "params":
                for tok in shlex.split(val, posix=False):
                    k, _, v = tok.partition("=")
                    meta["params"][k] = v
            else:
                meta["purpose"] = val
            continue
        if in_purpose and line.startswith("--   "):
            meta["purpose"] += " " + line[5:].strip()
            continue
        break  # header ends at the first non-header line
    meta["code"] = "\n".join(lines)
    return meta


def catalog():
    d = probes_dir()
    if not os.path.isdir(d):
        raise ForgeError("RBF-ARG-001", "probe templates missing: %s" % d,
                         hint="reinstall RobloxForge; templates/probes ships with it")
    out = []
    for name in sorted(os.listdir(d)):
        if name.endswith(".luau"):
            meta = _parse(os.path.join(d, name))
            out.append({"name": meta["name"] or name[:-5], "datamodel": meta["datamodel"],
                        "params": meta["params"], "purpose": meta["purpose"]})
    return out


def render(name, overrides=None):
    """Return the probe's code with parameters filled in, plus how to run it."""
    path = os.path.join(probes_dir(), "%s.luau" % name)
    if not re.fullmatch(r"[a-z0-9-]+", name or "") or not os.path.isfile(path):
        names = ", ".join(p["name"] for p in catalog())
        raise ForgeError("RBF-ARG-001", "unknown probe %r" % name, hint="available: " + names)
    meta = _parse(path)
    values = dict(meta["params"])
    for k, v in (overrides or {}).items():
        if k not in values:
            raise ForgeError("RBF-ARG-001", "probe %s has no parameter %r" % (name, k),
                             hint="parameters: " + (", ".join(values) or "none"))
        v = str(v)
        if "\n" in v or "\r" in v:
            raise ForgeError("RBF-ARG-001", "parameter %r must be a single-line Luau expression" % k)
        values[k] = v
    code = _PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), meta["code"])
    left = _PLACEHOLDER.findall(code)
    if left:
        raise ForgeError("RBF-ARG-001", "probe %s has unfilled placeholders: %s" % (name, ", ".join(left)))
    dm = meta["datamodel"]
    return {
        "probe": name,
        "datamodel": dm,
        "purpose": meta["purpose"],
        "params": values,
        "run": ("execute_luau with datamodel_type=%s" % dm) if dm != "any"
               else "execute_luau with datamodel_type=Edit, Client or Server (whichever you are inspecting)",
        "code": code,
    }


def parse_sets(pairs):
    """['k=v', ...] -> dict. Values are Luau expressions: quote strings yourself ("Door")."""
    out = {}
    for p in pairs or []:
        k, sep, v = p.partition("=")
        if not sep or not k:
            raise ForgeError("RBF-ARG-001", "expected key=value, got %r" % p)
        out[k.strip()] = v.strip()
    return out
