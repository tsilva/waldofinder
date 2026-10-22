"""Build hosted static assets from hash-pinned public sources; artwork stays out of Git."""

import hashlib
import json
import shutil
import sys
from pathlib import Path

import httpx
import pymupdf
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from waldofinder.reference import PUBLISHER_SHA256, PUBLISHER_SOURCE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "hosted-assets"
PUBLIC = ROOT / "public"
PDF_URL = "https://waldo.candlewick.com/pdf/WaldoCharacterSheets20.pdf"
PDF_SHA = "8a4033c7d3602c6664966bcc7c47c8e6f3e43a5e324870818cffe20bfbc840e1"
SAMPLE_URL = "https://wallpapers.com/images/hd/where-s-waldo-beach-crowd-d614ctoxorwugf1b.jpg"
SAMPLE_SHA = "e599391125592f8fa4460340eef5c4dee65f2b198bdb667ab43d22a030019d14"


def download(url, expected):
    response = httpx.get(url, timeout=60, follow_redirects=True)
    response.raise_for_status()
    if hashlib.sha256(response.content).hexdigest() != expected:
        raise ValueError("Public source changed; review asset provenance before deployment.")
    return response.content


def build():
    ASSETS.mkdir(exist_ok=True)
    PUBLIC.mkdir(exist_ok=True)
    shutil.copytree(ROOT / "src/waldofinder/static", PUBLIC, dirs_exist_ok=True)
    (ASSETS / "waldo-reference.jpg").write_bytes(download(PUBLISHER_SOURCE, PUBLISHER_SHA256))
    with pymupdf.open(stream=download(PDF_URL, PDF_SHA), filetype="pdf") as document:
        for name, (page_index, box) in {
            "wenda": (2, (330, 55, 835, 1435)),
            "odlaw": (4, (220, 55, 940, 1435)),
        }.items():
            page = document[page_index]
            scale = 1500 / max(page.rect.width, page.rect.height)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).crop(box)
            image.thumbnail((700, 1121))
            image.save(ASSETS / f"{name}-reference.png")
    (PUBLIC / "sample.jpg").write_bytes(download(SAMPLE_URL, SAMPLE_SHA))
    for name, src in [
        ("waldo", "waldo-reference.jpg"),
        ("wenda", "wenda-reference.png"),
        ("odlaw", "odlaw-reference.png"),
    ]:
        shutil.copyfile(ASSETS / src, PUBLIC / src)
    manifest = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in ASSETS.iterdir() if p.is_file()
    }
    (ASSETS / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Hosted assets built; public source hashes verified.")


if __name__ == "__main__":
    build()
