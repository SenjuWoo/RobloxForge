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
import struct

ROBLOX_TRI_LIMIT = 20000
ADDON_NAME = "Upload to Roblox"
ADDON_MIN_BLENDER = (3, 2, 0)


def _version_tuple(text):
    m = re.search(r"(\d+)\.(\d+)", text or "")
    return (int(m.group(1)), int(m.group(2)), 0) if m else None


def _blender_candidates():
    """Common install locations plus PATH, newest first. Nothing is executed."""
    out = []
    for pattern in (
        r"C:/Program Files/Blender Foundation/Blender */blender.exe",
        r"C:/Program Files (x86)/Steam/steamapps/common/Blender/blender.exe",
        r"C:/Program Files (x86)/Steam/steamapps/common/Blender/*/blender.exe",
    ):
        out.extend(glob.glob(pattern))
    found = os.environ.get("RBFORGE_BLENDER")
    if found:
        out.insert(0, found)
    for path in out:
        if not os.path.isfile(path):
            continue
        version = None
        # Blender portable builds keep the version in a sibling folder or a version.txt.
        sibling = os.path.join(os.path.dirname(path), "version.txt")
        if os.path.isfile(sibling):
            version = _version_tuple(open(sibling, encoding="utf-8", errors="replace").read())
        if not version:
            version = _version_tuple(os.path.basename(os.path.dirname(path)))
        if not version:
            # The Steam layout keeps a "5.2" folder beside blender.exe instead of naming the install.
            for child in sorted(os.listdir(os.path.dirname(path)), reverse=True):
                candidate = _version_tuple(child)
                if candidate and os.path.isdir(os.path.join(os.path.dirname(path), child)):
                    version = candidate
                    break
        yield {"path": path.replace("\\", "/"), "version": ".".join(map(str, version)) if version else None}


def find_blender():
    """The first usable Blender install, or None. Never runs the binary."""
    return next(_blender_candidates(), None)


def addons_dir(blender_version):
    """Blender's per-user add-on folder for a version like \"5.2\"."""
    base = os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender")
    if blender_version:
        return os.path.join(base, blender_version, "scripts", "addons")
    hits = sorted(glob.glob(os.path.join(base, "*", "scripts", "addons")))
    return hits[-1] if hits else os.path.join(base, "<version>", "scripts", "addons")


def find_addon(directory):
    """Locate an add-on folder whose manifest names the Roblox uploader."""
    if not directory or not os.path.isdir(directory):
        return None
    for entry in sorted(os.listdir(directory)):
        init = os.path.join(directory, entry, "__init__.py")
        if not os.path.isfile(init):
            continue
        try:
            head = open(init, encoding="utf-8", errors="replace").read(4000)
        except OSError:
            continue
        if ADDON_NAME in head or "open cloud" in head.lower() and "roblox" in head.lower():
            return os.path.join(directory, entry).replace("\\", "/")
    return None


def glb_summary(path):
    """Triangles, meshes and materials from a GLB, read from its JSON chunk without decoding geometry."""
    with open(path, "rb") as f:
        header = f.read(12)
        if len(header) < 12 or header[:4] != b"glTF":
            return {"error": "not a GLB (missing glTF magic)"}
        _, version, total = struct.unpack("<4sII", header)
        chunk_len, chunk_type = struct.unpack("<II", f.read(8))
        if chunk_type != 0x4E4F534A:
            return {"error": "first GLB chunk is not JSON"}
        doc = json.loads(f.read(chunk_len).decode("utf-8", "replace"))
    accessors = doc.get("accessors", [])
    triangles = 0
    per_mesh = []
    for mesh in doc.get("meshes", []):
        count = 0
        for prim in mesh.get("primitives", []):
            idx = prim.get("indices")
            if idx is not None and idx < len(accessors):
                n = accessors[idx].get("count", 0)
            else:
                pos = prim.get("attributes", {}).get("POSITION")
                n = accessors[pos].get("count", 0) if pos is not None and pos < len(accessors) else 0
            count += n // 3
        triangles += count
        per_mesh.append({"name": mesh.get("name"), "triangles": count})
    return {
        "format": "glb",
        "version": version,
        "bytes": total,
        "meshes": len(doc.get("meshes", [])),
        "materials": len(doc.get("materials", [])),
        "triangles": triangles,
        "per_mesh": per_mesh,
        "over_limit": [m for m in per_mesh if m["triangles"] > ROBLOX_TRI_LIMIT],
    }


def fbx_summary(path):
    """Enough to tell a real FBX from a bad export; triangle counts need Blender itself."""
    with open(path, "rb") as f:
        head = f.read(27)
    size = os.path.getsize(path)
    if head.startswith(b"Kaydara FBX Binary"):
        return {"format": "fbx-binary", "bytes": size, "triangles": None,
                "note": "triangle counts need Blender; Roblox caps 20,000 per mesh"}
    if head.lstrip().startswith(b"; FBX"):
        return {"format": "fbx-ascii", "bytes": size, "triangles": None,
                "note": "triangle counts need Blender; Roblox caps 20,000 per mesh"}
    return {"error": "not an FBX (no Kaydara header)"}


def inspect_export(path):
    """Summarise a mesh export and flag anything Roblox will reject or silently decimate."""
    if not os.path.isfile(path):
        return {"error": "no such file", "path": path}
    ext = os.path.splitext(path)[1].lower()
    if ext == ".glb":
        out = glb_summary(path)
    elif ext == ".fbx":
        out = fbx_summary(path)
    elif ext in (".gltf", ".obj"):
        out = {"format": ext.lstrip("."), "bytes": os.path.getsize(path), "triangles": None,
               "note": "count triangles in Blender or import straight to Studio and check there"}
    else:
        return {"error": "unsupported export type", "path": path,
                "supported": [".glb", ".gltf", ".fbx", ".obj"]}
    out["path"] = path
    tris = out.get("triangles")
    if isinstance(tris, int):
        out["within_limit"] = tris <= ROBLOX_TRI_LIMIT
    return out


def status():
    """What this machine can actually do for 3D work, and what happens when it cannot."""
    blender = find_blender()
    out = {
        "blender": blender or {"path": None},
        "roblox_addon": {"path": None},
        "upload_routes": {
            "interactive": "Blender: Roblox add-on panel (Log in, Upload to Roblox)",
            "scripted": "Studio 3D importer, or Open Cloud Asset API with an approved creator key",
            "fallback": "no Blender: build parts in Luau, or import a finished .glb/.fbx through Studio",
        },
    }
    if blender:
        directory = addons_dir(blender.get("version"))
        out["addons_dir"] = directory.replace("\\", "/")
        found = find_addon(directory)
        out["roblox_addon"]["path"] = found
        out["roblox_addon"]["installed"] = bool(found)
        version = _version_tuple(blender.get("version"))
        out["blender"]["meets_addon_minimum"] = bool(
            version and version >= ADDON_MIN_BLENDER) if version else None
    else:
        out["roblox_addon"]["installed"] = False
    out["triangles_per_mesh_limit"] = ROBLOX_TRI_LIMIT
    return out
