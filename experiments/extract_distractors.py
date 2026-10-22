"""Extract local Wenda/Odlaw references from Candlewick's character-sheet PDF."""

import argparse
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

PDF_SHA256 = "8a4033c7d3602c6664966bcc7c47c8e6f3e43a5e324870818cffe20bfbc840e1"
PAGES = {"wenda": (3, (330, 55, 835, 1435)), "odlaw": (5, (220, 55, 940, 1435))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data"))
    args = parser.parse_args()
    if hashlib.sha256(args.pdf.read_bytes()).hexdigest() != PDF_SHA256:
        parser.error("Publisher PDF changed; review its pages before defining new crop bounds")
    executable = shutil.which("pdftoppm")
    if not executable:
        parser.error("Install Poppler (pdftoppm) to render the publisher PDF")
    args.output.mkdir(parents=True, exist_ok=True)
    if any((args.output / f"{name}-reference.png").exists() for name in PAGES):
        parser.error("Output references already exist; choose another directory")
    with tempfile.TemporaryDirectory() as folder:
        for name, (page, bounds) in PAGES.items():
            prefix = str(Path(folder) / name)
            subprocess.run(
                [
                    executable,
                    "-f",
                    str(page),
                    "-l",
                    str(page),
                    "-scale-to",
                    "1500",
                    "-singlefile",
                    "-png",
                    str(args.pdf),
                    prefix,
                ],
                check=True,
            )
            with Image.open(prefix + ".png") as source:
                image = source.convert("RGB").crop(bounds)
            image.thumbnail((700, 1121))
            destination = args.output / f"{name}-reference.png"
            image.save(destination)
            print(
                f"{destination}: {image.width}x{image.height}; SHA-256 {hashlib.sha256(destination.read_bytes()).hexdigest()}"
            )


if __name__ == "__main__":
    main()
