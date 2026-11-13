"""Fetch the room's licensed assets (all CC0, from Poly Haven) into site/assets, and write their credits.

    python tools/fetch_assets.py [--cache DIR]      # from parrot/site

Every model, texture and light probe the page uses comes from Poly Haven (polyhaven.com), whose
assets are CC0 (public domain). For each the tool downloads the 1k files, checks each file's MD5
against the one Poly Haven's API states, packs a model's glTF, buffer and textures into one .glb,
and writes `assets/CREDITS.json`: the asset, its page, its authors, its licence, the files fetched
with their MD5, and the SHA-256 of the file the page loads. The parrot itself is made by the page's
own code (parrot.js); it uses no third-party asset.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import urllib.request
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
ASSETS = SITE / "assets"
API = "https://api.polyhaven.com"
UA = {"User-Agent": "cadence-demos-asset-fetch/1"}

# kind on the page -> Poly Haven model
MODELS = {
    "apple": "food_apple_01",
    "ball": "baseball_01",
    "cup": "tea_set_01",
    "banana": "bananas",
    "duck": "rubber_duck_toy",
    "lemon": "lemon",
    "pear": "food_pears_asian_01",
}
# use on the page -> Poly Haven texture (diffuse, normal (GL), roughness or ARM)
TEXTURES = {
    "table": "wood_table_001",
    "floor": "wood_floor",
    "wall": "beige_wall_001",
    "bark": "bark_brown_02",
    "block": "plywood",
    "post": "oak_veneer_01",
}
HDRI = "lebombo"


def get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def get_json(url: str) -> dict:
    return json.loads(get(url))


def fetch(url: str, md5: str | None, cache: Path) -> bytes:
    """A file from Poly Haven, from the cache when it is there, its MD5 checked."""
    path = cache / url.split("/file/", 1)[-1]
    if path.exists():
        data = path.read_bytes()
    else:
        data = get(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    if md5 and hashlib.md5(data).hexdigest() != md5:
        raise SystemExit(f"MD5 mismatch for {url}")
    return data


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pad4(b: bytes, fill: bytes = b"\x00") -> bytes:
    return b + fill * ((4 - len(b) % 4) % 4)


def pack_glb(gltf: dict, files: dict[str, bytes]) -> bytes:
    """One .glb from a glTF and the files it names: its buffer first, then each image."""
    assert len(gltf.get("buffers", [])) == 1, "one buffer expected"
    blob = pad4(files[gltf["buffers"][0]["uri"]])
    for image in gltf.get("images", []):
        data = files[image.pop("uri")]
        mime = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
        gltf["bufferViews"].append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)})
        image["bufferView"] = len(gltf["bufferViews"]) - 1
        image["mimeType"] = mime
        blob = pad4(blob + data)
    gltf["buffers"] = [{"byteLength": len(blob)}]
    text = pad4(json.dumps(gltf, separators=(",", ":")).encode(), b" ")
    body = struct.pack("<II", len(text), 0x4E4F534A) + text + struct.pack("<II", len(blob), 0x004E4942) + blob
    return struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body


def credit(asset: str, kind: str) -> dict:
    info = get_json(f"{API}/info/{asset}")
    return {"asset": asset, "name": info.get("name"), "type": kind, "page": f"https://polyhaven.com/a/{asset}",
            "authors": sorted(info.get("authors", {})), "licence": "CC0 1.0 (public domain)",
            "licence_url": "https://polyhaven.com/license"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", type=Path, default=SITE / ".asset-cache", help="downloads land here first")
    args = ap.parse_args()
    (ASSETS / "models").mkdir(parents=True, exist_ok=True)
    (ASSETS / "tex").mkdir(parents=True, exist_ok=True)
    credits = []
    for kind, asset in MODELS.items():
        entry = get_json(f"{API}/files/{asset}")["gltf"]["1k"]["gltf"]
        main_bytes = fetch(entry["url"], entry.get("md5"), args.cache)
        files = {}
        fetched = [{"url": entry["url"], "md5": entry.get("md5")}]
        for name, inc in entry["include"].items():
            files[name] = fetch(inc["url"], inc.get("md5"), args.cache)
            fetched.append({"url": inc["url"], "md5": inc.get("md5")})
        glb = pack_glb(json.loads(main_bytes), files)
        out = ASSETS / "models" / f"{kind}.glb"
        out.write_bytes(glb)
        c = credit(asset, "model")
        c.update({"used_as": kind, "file": f"assets/models/{kind}.glb", "sha256": sha256(glb), "fetched": fetched})
        credits.append(c)
        print(f"{kind:7s} {asset:22s} {len(glb) / 1e6:5.2f} MB")
    for use, asset in TEXTURES.items():
        maps = get_json(f"{API}/files/{asset}")
        fetched, written = [], {}
        for key, short in (("Diffuse", "diff"), ("nor_gl", "nor"), ("Rough", "rough")):
            if key not in maps or "1k" not in maps[key]:
                continue
            f = maps[key]["1k"]["jpg"]
            data = fetch(f["url"], f.get("md5"), args.cache)
            out = ASSETS / "tex" / f"{use}_{short}.jpg"
            out.write_bytes(data)
            fetched.append({"url": f["url"], "md5": f.get("md5")})
            written[f"assets/tex/{use}_{short}.jpg"] = sha256(data)
        c = credit(asset, "texture")
        c.update({"used_as": use, "files": written, "fetched": fetched})
        credits.append(c)
        print(f"{use:7s} {asset:22s} {len(written)} maps")
    f = get_json(f"{API}/files/{HDRI}")["hdri"]["1k"]["hdr"]
    data = fetch(f["url"], f.get("md5"), args.cache)
    (ASSETS / "room.hdr").write_bytes(data)
    c = credit(HDRI, "hdri")
    c.update({"used_as": "light", "file": "assets/room.hdr", "sha256": sha256(data), "fetched": [{"url": f["url"], "md5": f.get("md5")}]})
    credits.append(c)
    (ASSETS / "CREDITS.json").write_text(json.dumps({"source": "Poly Haven (polyhaven.com)", "licence": "CC0 1.0", "assets": credits}, indent=1) + "\n")
    print(f"{len(credits)} assets credited in assets/CREDITS.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
