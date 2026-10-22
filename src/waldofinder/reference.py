"""Local visual exemplars, normalized once and bound to each run by a hash."""

import base64
import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

DEFAULT_REFERENCE = Path("data/waldo-reference.jpg")
PUBLISHER_SOURCE = "https://waldo.candlewick.com/images/waldo-wave.jpg"
PUBLISHER_SHA256 = "526ecd2f0f2a9263d458f1010ef0c4810724ed9397630f265f49a0626c5a1614"


@dataclass(frozen=True)
class VisualReference:
    png: bytes
    source_sha256: str
    width: int
    height: int

    @property
    def sha256(self):
        return hashlib.sha256(self.png).hexdigest()

    @property
    def data_url(self):
        return "data:image/png;base64," + base64.b64encode(self.png).decode("ascii")

    @property
    def manifest(self):
        return dict(
            file="reference.png",
            sha256=self.sha256,
            source_sha256=self.source_sha256,
            source_url=PUBLISHER_SOURCE if self.source_sha256 == PUBLISHER_SHA256 else None,
            width=self.width,
            height=self.height,
        )


def load_reference(path):
    try:
        path = Path(path).expanduser()
        if path.stat().st_size > 10_000_000:
            raise ValueError
        raw = path.read_bytes()
        with Image.open(BytesIO(raw)) as source:
            if source.width * source.height > 4_000_000:
                raise ValueError
            image = ImageOps.exif_transpose(source).convert("RGB")
        stream = BytesIO()
        image.save(stream, format="PNG")
        return VisualReference(
            stream.getvalue(), hashlib.sha256(raw).hexdigest(), image.width, image.height
        )
    except (OSError, ValueError, Image.DecompressionBombError):
        raise ValueError(
            "Choose a valid Waldo reference image with --reference (up to 10 MB / 4 megapixels)."
        ) from None


DISTRACTOR_SOURCE = "https://waldo.candlewick.com/pdf/WaldoCharacterSheets20.pdf"
DISTRACTOR_HASHES = {
    "wenda": "bb8b3a65870b72677d9da9f20925654b318e044749634d28803519373624d1d7",
    "odlaw": "5ba45b067d60bb1efbf7acb31ab3b3344294fdf66fbcb68ae65efd2a8ab52ea9",
}
DISTRACTOR_LABELS = {
    "wenda": "DISTRACTOR REFERENCE — Wenda, NOT Waldo. Appearance example only; never count this image.",
    "odlaw": "DISTRACTOR REFERENCE — Odlaw, NOT Waldo. Appearance example only; never count this image.",
}


def load_distractors(args):
    paths = getattr(args, "distractor_references", None)
    if paths is None:
        paths = {
            name: getattr(args, f"{name}_reference", Path(f"data/{name}-reference.png"))
            for name in DISTRACTOR_LABELS
        }
    if set(paths) not in (set(), set(DISTRACTOR_LABELS)):
        raise ValueError("Provide both Wenda and Odlaw references.")
    result = {}
    for name, path in paths.items():
        try:
            result[name] = load_reference(path)
        except ValueError:
            raise ValueError(
                f"Choose a valid {name.title()} reference with --{name}-reference (up to 10 MB / 4 megapixels)."
            ) from None
    return result


def distractor_manifest(references):
    return {
        name: reference.manifest
        | {
            "file": f"{name}-reference.png",
            "source_url": DISTRACTOR_SOURCE
            if reference.source_sha256 == DISTRACTOR_HASHES[name]
            else None,
            "source_page": {"wenda": 3, "odlaw": 5}[name]
            if reference.source_sha256 == DISTRACTOR_HASHES[name]
            else None,
            "label": DISTRACTOR_LABELS[name],
        }
        for name, reference in references.items()
    }


def distractor_content(references):
    content = []
    for name, reference in references.items():
        content.extend(
            [
                {"type": "text", "text": DISTRACTOR_LABELS[name]},
                {"type": "image_url", "image_url": {"url": reference.data_url, "detail": "auto"}},
            ]
        )
    return content
