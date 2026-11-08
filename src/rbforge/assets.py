"""Optional 3D asset route: Blender, the official Roblox upload add-on, and export validation.

RobloxForge does not do 3D and does not upload anything. This module answers three questions an agent
actually needs before it promises a mesh pipeline:

  * is Blender here, and which version (the official add-on needs 3.2+);
  * is Roblox's "Upload to Roblox" add-on installed for that Blender;
  * does a finished export fit Roblox's limits (20,000 triangles per mesh), and what is in it.

The upload itself stays where Roblox put it: the add-on for interactive use, or Studio's own importer and
Open Cloud for scripted work. Nothing here authenticates, uploads or touches an account.
"""
import glob
import json
import os
import re
import shutil
import struct

ROBLOX_TRI_LIMIT = 20000
ADDON_NAME = "Upload to Roblox"
ADDON_MIN_BLENDER = (3, 2, 0)

# glTF primitive modes (Khronos spec 3.7.2.1). Only 4/5/6 produce triangles.
MODE_TRIANGLES, MODE_STRIP, MODE_FAN = 4, 5, 6
NON_TRIANGLE_MODES = {0: "POINTS", 1: "LINES", 2: "LINE_LOOP", 3: "LINE_STRIP"}

STATUS_WITHIN = "within_limit"
STATUS_OVER = "over_limit"
STATUS_INVALID = "invalid"
STATUS_UNVERIFIED = "unverified"


def _version_tuple(text):
    m = re.search(r"(\d+)\.(\d+)", text or "")
    return (int(m.group(1)), int(m.group(2)), 0) if m else None


def _short_version(text):
    """Blender's own folder name is major.minor, never the patch: 5.2.0 -> 5.2."""
    parts = [p for p in re.split(r"[.\- ]", (text or "").strip()) if p.isdigit()]
    return ".".join(parts[:2]) if len(parts) >= 2 else ((text or "").strip() or None)


def _blender_candidates():
    """Common install locations plus an explicit override. Nothing is executed."""
    out = []
    override = os.environ.get("RBFORGE_BLENDER")
    if override:
        out.append(override)
    for pattern in (
        r"C:/Program Files/Blender Foundation/Blender */blender.exe",
        r"C:/Program Files (x86)/Steam/steamapps/common/Blender/blender.exe",
        r"C:/Program Files (x86)/Steam/steamapps/common/Blender/*/blender.exe",
        r"/Applications/Blender.app/Contents/MacOS/Blender",
        r"/usr/bin/blender",
        r"/usr/local/bin/blender",
        r"/snap/bin/blender",
    ):
        out.extend(glob.glob(pattern))
    on_path = shutil.which("blender") or shutil.which("blender.exe")
    if on_path:
        out.append(on_path)
    for path in out:
        if not os.path.isfile(path):
            continue
        version = None
        sibling = os.path.join(os.path.dirname(path), "version.txt")
        if os.path.isfile(sibling):
            try:
                version = _version_tuple(open(sibling, encoding="utf-8", errors="replace").read())
            except OSError:
                version = None
        if not version:
            version = _version_tuple(os.path.basename(os.path.dirname(path)))
        if not version:
            # Steam keeps a "5.2" folder beside blender.exe instead of naming the install.
            try:
                children = sorted(os.listdir(os.path.dirname(path)), reverse=True)
            except OSError:
                children = []
            for child in children:
                candidate = _version_tuple(child)
                if candidate and os.path.isdir(os.path.join(os.path.dirname(path), child)):
                    version = candidate
                    break
        joined = ".".join(map(str, version)) if version else None
        yield {"path": path.replace("\\", "/"), "version": joined, "short_version": _short_version(joined)}


def find_blender():
    """The first usable Blender install, or None. Never runs the binary."""
    return next(_blender_candidates(), None)


def addons_dir(blender_version):
    """Blender's per-user add-on folder. Blender names that folder major.minor, not major.minor.patch."""
    base = os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender")
    short = _short_version(blender_version)
    if short:
        return os.path.join(base, short, "scripts", "addons")
    hits = sorted(glob.glob(os.path.join(base, "*", "scripts", "addons")))
    return hits[-1] if hits else os.path.join(base, "<version>", "scripts", "addons")


def extensions_dir(blender_version):
    """Blender 4.2+ also loads extensions; the Roblox add-on may be installed in either place."""
    base = os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender")
    short = _short_version(blender_version)
    if short:
        return os.path.join(base, short, "extensions")
    hits = sorted(glob.glob(os.path.join(base, "*", "extensions")))
    return hits[-1] if hits else os.path.join(base, "<version>", "extensions")


def search_dirs(blender):
    """Every place the add-on could live, as (path, required).

    Required roots are the two Blender itself always uses; extras are portable layouts that only some
    installs have. A missing extra does not make the search inconclusive - a missing required root does.
    """
    if not blender or not blender.get("path"):
        return []
    install = os.path.dirname(blender["path"])
    short = blender.get("short_version")
    dirs = [(addons_dir(blender.get("version")), True),
            (extensions_dir(blender.get("version")), False)]
    if short:
        dirs.append((os.path.join(install, "portable", short, "scripts", "addons"), False))
        dirs.append((os.path.join(install, short, "scripts", "addons"), False))
    return dirs


def _manifest_text(path):
    for name in ("__init__.py", "blender_manifest.toml"):
        candidate = os.path.join(path, name)
        if os.path.isfile(candidate):
            try:
                return open(candidate, encoding="utf-8", errors="replace").read(4000)
            except OSError:
                return ""
    return ""


def find_addon(directory):
    """An add-on folder in this directory whose manifest names the Roblox uploader, or None."""
    if not directory or not os.path.isdir(directory):
        return None
    for entry in sorted(os.listdir(directory)):
        candidate = os.path.join(directory, entry)
        if not os.path.isdir(candidate):
            continue
        text = _manifest_text(candidate)
        if not text:
            continue
        lowered = text.lower()
        if ADDON_NAME in text or ("roblox" in lowered and "upload" in lowered):
            return candidate.replace("\\", "/")
    return None


def find_addon_anywhere(blender):
    """(path, searched, complete). `complete` is False when a required root is missing - absence is not a fact."""
    searched, complete = [], True
    for directory, required in search_dirs(blender):
        exists = os.path.isdir(directory)
        searched.append({"path": directory.replace("\\", "/"), "exists": exists,
                         "required": required})
        if not exists:
            if required:
                complete = False
            continue
        found = find_addon(directory)
        if found:
            return found, searched, True
    return None, searched, complete


def _accessor_count(accessors, index, label):
    """(count, problem, kind). Negative indices are refused: Python must not repair a malformed file."""
    if isinstance(index, bool) or not isinstance(index, int):
        return None, "%s is not an integer" % label, STATUS_INVALID
    if index < 0:
        return None, "%s is negative (%s)" % (label, index), STATUS_INVALID
    if index >= len(accessors):
        return None, "%s references accessor %s out of range" % (label, index), STATUS_INVALID
    accessor = accessors[index]
    if not isinstance(accessor, dict):
        return None, "accessor %s is not an object" % index, STATUS_INVALID
    count = accessor.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        return None, "accessor %s has no usable count" % index, STATUS_INVALID
    return count, None, None


def _triangles_for_primitive(prim, accessors):
    """(triangles, problem, kind) for one primitive, respecting glTF mode and indexed/non-indexed geometry.

    `kind` is STATUS_INVALID for a structure that violates the spec, STATUS_UNVERIFIED for something
    we simply cannot measure (an unknown mode), and None when the primitive was counted.
    """
    mode = prim.get("mode", MODE_TRIANGLES)
    if isinstance(mode, bool) or not isinstance(mode, int):
        return 0, "primitive mode is not an integer", STATUS_INVALID
    if mode in NON_TRIANGLE_MODES:
        return 0, None, None  # points and lines legitimately carry no triangles
    if mode not in (MODE_TRIANGLES, MODE_STRIP, MODE_FAN):
        return 0, "unsupported primitive mode %s" % mode, STATUS_UNVERIFIED
    idx = prim.get("indices")
    if idx is not None:
        count, problem, kind = _accessor_count(accessors, idx, "indices")
    else:
        attributes = prim.get("attributes")
        if not isinstance(attributes, dict):
            return 0, "attributes is not an object", STATUS_INVALID
        if "POSITION" not in attributes:
            return 0, "primitive has neither indices nor a POSITION attribute", STATUS_INVALID
        count, problem, kind = _accessor_count(accessors, attributes["POSITION"], "POSITION")
    if problem or count is None:
        return 0, problem or "unusable accessor count", kind or STATUS_INVALID
    if mode == MODE_TRIANGLES:
        return count // 3, None, None
    return max(0, count - 2), None, None  # STRIP/FAN: n vertices give n-2 triangles


def glb_summary(path):
    """Mesh metadata from a GLB, or a structured reason it cannot be trusted.

    Reads the JSON chunk only: counts are exact for TRIANGLES/STRIP/FAN, and the geometry itself (vertex
    validity, degenerate faces, normals) is not inspected - which is why `counts_geometry` is False.
    """
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            header = f.read(12)
            if len(header) < 12:
                return {"status": STATUS_INVALID, "error": "file is shorter than a GLB header"}
            magic, version, declared = struct.unpack("<4sII", header)
            if magic != b"glTF":
                return {"status": STATUS_INVALID, "error": "not a GLB (missing glTF magic)"}
            if version != 2:
                return {"status": STATUS_INVALID, "error": "unsupported GLB version %s" % version}
            chunk_header = f.read(8)
            if len(chunk_header) < 8:
                return {"status": STATUS_INVALID, "error": "GLB JSON chunk header is truncated"}
            chunk_len, chunk_type = struct.unpack("<II", chunk_header)
            if chunk_type != 0x4E4F534A:
                return {"status": STATUS_INVALID, "error": "first GLB chunk is not JSON"}
            raw = f.read(chunk_len)
            if len(raw) < chunk_len:
                return {"status": STATUS_INVALID,
                        "error": "GLB JSON chunk declares %d bytes, file holds %d" % (chunk_len, len(raw))}
    except OSError as exc:
        return {"status": STATUS_INVALID, "error": "cannot read file: %s" % exc}

    try:
        doc = json.loads(raw.decode("utf-8", "replace"))
    except ValueError as exc:
        return {"status": STATUS_INVALID, "error": "GLB JSON chunk is not valid JSON: %s" % exc}
    if not isinstance(doc, dict):
        return {"status": STATUS_INVALID, "error": "GLB JSON chunk is not an object"}

    accessors = doc.get("accessors") or []
    meshes = doc.get("meshes") or []
    if not isinstance(accessors, list) or not isinstance(meshes, list):
        return {"status": STATUS_INVALID, "error": "accessors or meshes is not a list"}

    per_mesh, problems, total, kinds = [], [], 0, set()
    for index, mesh in enumerate(meshes):
        if not isinstance(mesh, dict):
            problems.append("mesh %d is not an object" % index)
            kinds.add(STATUS_INVALID)
            continue
        primitives = mesh.get("primitives")
        if not isinstance(primitives, list):
            problems.append("mesh %d has no primitives array" % index)
            kinds.add(STATUS_INVALID)
            continue
        count = 0
        for prim in primitives:
            if not isinstance(prim, dict):
                problems.append("mesh %d has a primitive that is not an object" % index)
                kinds.add(STATUS_INVALID)
                continue
            tris, problem, kind = _triangles_for_primitive(prim, accessors)
            if problem:
                problems.append("mesh %d: %s" % (index, problem))
                kinds.add(kind or STATUS_INVALID)
            count += tris
        total += count
        per_mesh.append({"name": mesh.get("name") or "mesh%d" % index, "triangles": count})

    over = [m for m in per_mesh if m["triangles"] > ROBLOX_TRI_LIMIT]
    out = {
        "format": "glb",
        "version": version,
        "bytes": size,
        "declared_bytes": declared,
        "meshes": len(per_mesh),
        "materials": len(doc.get("materials") or []),
        "triangles": total,
        "per_mesh": per_mesh,
        "over_limit": over,
        "counts_geometry": False,
        "note": "counts come from accessor counts by primitive mode; vertex data is not inspected",
    }
    if declared and declared != size:
        out["declared_bytes_mismatch"] = True
        problems.append("header declares %d bytes, file holds %d" % (declared, size))
        kinds.add(STATUS_UNVERIFIED)
    if problems:
        # A structure that violates the spec is invalid; something we simply cannot measure is unverified.
        # Neither may pass: a file we could not fully account for cannot close a gate.
        out["status"] = STATUS_INVALID if STATUS_INVALID in kinds else STATUS_UNVERIFIED
        out["problems"] = problems
        return out
    out["status"] = STATUS_OVER if over else STATUS_WITHIN
    out["within_limit"] = not over
    return out


def fbx_summary(path):
    """Enough to tell a real FBX from a bad export; triangle counts need Blender itself."""
    try:
        with open(path, "rb") as f:
            head = f.read(27)
    except OSError as exc:
        return {"status": STATUS_INVALID, "error": "cannot read file: %s" % exc}
    size = os.path.getsize(path)
    if head.startswith(b"Kaydara FBX Binary") or head.lstrip().startswith(b"; FBX"):
        kind = "fbx-binary" if head.startswith(b"Kaydara") else "fbx-ascii"
        return {"status": STATUS_UNVERIFIED, "format": kind, "bytes": size, "triangles": None,
                "note": "FBX needs Blender to count triangles; only the header was checked"}
    return {"status": STATUS_INVALID, "error": "not an FBX (no Kaydara header)"}


def inspect_export(path):
    """Summarise a mesh export. `status` is within_limit / over_limit / invalid / unverified."""
    if not os.path.isfile(path):
        return {"status": STATUS_INVALID, "error": "no such file", "path": path}
    ext = os.path.splitext(path)[1].lower()
    if ext == ".glb":
        out = glb_summary(path)
    elif ext == ".fbx":
        out = fbx_summary(path)
    elif ext in (".gltf", ".obj"):
        out = {"status": STATUS_UNVERIFIED, "format": ext.lstrip("."), "bytes": os.path.getsize(path),
               "triangles": None,
               "note": "%s is not measured here: import it to Studio, or check it in Blender" % ext}
    else:
        return {"status": STATUS_INVALID, "error": "unsupported export type", "path": path,
                "supported": [".glb", ".fbx", ".gltf", ".obj"]}
    out["path"] = path
    return out


def status():
    """What this machine can actually do for 3D work, and what happens when it cannot."""
    blender = find_blender()
    out = {
        "blender": blender or {"path": None},
        "triangles_per_mesh_limit": ROBLOX_TRI_LIMIT,
        "upload_routes": {
            "interactive": "Blender: Roblox add-on panel (Log in, Upload to Roblox)",
            "studio": "official Studio MCP / Studio 3D importer with Studio-managed authorization",
            "open_cloud_key": "Open Cloud Asset API with a creator API key, if you choose to use one",
            "fallback": "no Blender: build parts in Luau, or import a finished .glb/.fbx through Studio",
        },
    }
    if not blender:
        out["roblox_addon"] = {"installed": None, "state": "unknown",
                              "detail": "no Blender found, so no add-on directory could be identified"}
        return out

    found, searched, complete = find_addon_anywhere(blender)
    version = _version_tuple(blender.get("version"))
    state = "installed" if found else ("absent" if complete else "unknown")
    out["addons_searched"] = searched
    out["roblox_addon"] = {
        "path": found,
        "installed": bool(found) if state != "unknown" else None,
        "state": state,
        "enabled": None,
        "detail": ("found; whether it is enabled in Blender's preferences is not verified here" if found
                   else "not found in any add-on root that exists on this machine" if complete
                   else "not found, but at least one add-on root does not exist - not proof of absence"),
    }
    out["blender"]["meets_addon_minimum"] = bool(version and version >= ADDON_MIN_BLENDER) if version else None
    return out
