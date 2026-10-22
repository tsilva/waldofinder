"""Integer, half-open regions in original-image coordinates."""

from dataclasses import dataclass
from math import ceil, floor, isfinite, isqrt, sqrt


def validate_bbox(box):
    """Normalized xyxy coordinates; reject ambiguous, inverted or out-of-range boxes."""
    if (
        not isinstance(box, list)
        or len(box) != 4
        or any(type(v) not in (int, float) or not isfinite(v) or not 0 <= v <= 1000 for v in box)
        or box[0] >= box[2]
        or box[1] >= box[3]
    ):
        raise ValueError("Use a nonempty xyxy box in the 0–1000 coordinate space.")


def bbox_to_pixels(box, size):
    validate_bbox(box)
    w, h = size
    return [
        floor(box[0] * w / 1000),
        floor(box[1] * h / 1000),
        ceil(box[2] * w / 1000),
        ceil(box[3] * h / 1000),
    ]


@dataclass(frozen=True)
class Region:
    id: str
    box: tuple[int, int, int, int]
    depth: int = 0

    @property
    def width(self):
        return self.box[2] - self.box[0]

    @property
    def height(self):
        return self.box[3] - self.box[1]

    def padded(self, size: tuple[int, int], overlap: float):
        dx, dy = round(self.width * overlap), round(self.height * overlap)
        x0, y0, x1, y1 = self.box
        return max(0, x0 - dx), max(0, y0 - dy), min(size[0], x1 + dx), min(size[1], y1 + dy)

    def split(self):
        x0, y0, x1, y1 = self.box
        if self.width >= self.height and self.width > 1:
            mid = (x0 + x1) // 2
            boxes = [(x0, y0, mid, y1), (mid, y0, x1, y1)]
        elif self.height > 1:
            mid = (y0 + y1) // 2
            boxes = [(x0, y0, x1, mid), (x0, mid, x1, y1)]
        else:
            return []
        return [Region(f"{self.id}.{i}", b, self.depth + 1) for i, b in enumerate(boxes)]


def grid(size: tuple[int, int], tiles: int, columns: int | None = None):
    """Cover every pixel exactly once, including non-square and prime tile counts."""
    w, h = size
    if tiles < 1 or tiles > w * h:
        raise ValueError("tiles must be between 1 and the number of image pixels")
    if columns is not None:
        if columns < 1 or tiles % columns or columns > w or tiles // columns > h:
            raise ValueError("columns must divide tiles and fit the image dimensions")
        counts = [columns] * (tiles // columns)
    else:
        square = isqrt(tiles)
        if square * square == tiles and square <= min(size):
            return grid(size, tiles, square)
        rows = min(h, max((tiles + w - 1) // w, round(sqrt(tiles * h / w)), 1))
        rows = min(rows, tiles)
        counts = [tiles // rows + (i < tiles % rows) for i in range(rows)]
    regions = []
    for row, count in enumerate(counts):
        y0, y1 = row * h // len(counts), (row + 1) * h // len(counts)
        for col in range(count):
            regions.append(
                Region(f"r{row}c{col}", (col * w // count, y0, (col + 1) * w // count, y1))
            )
    return regions
