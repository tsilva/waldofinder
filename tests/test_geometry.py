import pytest

from waldofinder.geometry import Region, bbox_to_pixels, grid


@pytest.mark.parametrize("size", [(11, 7), (1, 17), (17, 1), (3, 2)])
def test_grid_covers_every_pixel_once(size):
    w, h = size
    for n in range(1, w * h + 1):
        regions = grid(size, n)
        assert len(regions) == n
        counts = [[0] * w for _ in range(h)]
        for r in regions:
            assert r.width > 0 and r.height > 0
            x0, y0, x1, y1 = r.box
            for y in range(y0, y1):
                for x in range(x0, x1):
                    counts[y][x] += 1
        assert all(c == 1 for row in counts for c in row)


def test_regular_grid_and_invalid_inputs():
    assert [r.box for r in grid((11, 7), 4, 2)] == [
        (0, 0, 5, 3),
        (5, 0, 11, 3),
        (0, 3, 5, 7),
        (5, 3, 11, 7),
    ]
    for n, cols in [(0, None), (78, None), (5, 2), (4, 0), (4, 20)]:
        with pytest.raises(ValueError):
            grid((11, 7), n, cols)


def test_binary_partition_and_overlap():
    root = Region("root", (0, 0, 11, 7))
    a, b = root.split()
    assert a.box == (0, 0, 5, 7) and b.box == (5, 0, 11, 7)
    assert a.depth == 1 and a.split()[0].box == (0, 0, 5, 3)
    assert a.padded((11, 7), 0.5) == (0, 0, 7, 7)
    assert Region("pixel", (0, 0, 1, 1)).split() == []


def test_square_tile_counts_default_to_regular_square_grids():
    for n, side in [(4, 2), (9, 3), (16, 4)]:
        regions = grid((1080, 675), n)
        assert len({r.box[1] for r in regions}) == side
        assert len({r.box[0] for r in regions}) == side


def test_normalized_xyxy_boxes_use_correct_axes_on_nonsquare_images():
    assert bbox_to_pixels([100, 200, 300, 400], (101, 67)) == [10, 13, 31, 27]
    assert bbox_to_pixels([0, 0, 1000, 1000], (101, 67)) == [0, 0, 101, 67]
    assert bbox_to_pixels([0.01, 0.01, 0.02, 0.02], (101, 67)) == [0, 0, 1, 1]
