"""Vercel Flask application."""

import sys
from pathlib import Path

# Vercel bundles src/ without installing this checkout as an editable package.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from waldofinder.gateway import create_app  # noqa: E402

app = create_app()
