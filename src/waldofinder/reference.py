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
