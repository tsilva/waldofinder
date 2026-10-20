import json

from PIL import Image

from waldofinder.cli import execute, parser


def test_offline_preview_and_refuse_overwrite(tmp_path):
    image = tmp_path / "test.png"
    Image.new("RGB", (17, 11)).save(image)
    output = tmp_path / "preview"
    args = parser().parse_args(["preview", str(image), "--tiles", "7", "--output", str(output)])
    assert execute(args) == 0
    assert len(json.loads((output / "regions.json").read_text())) == 7
    import pytest

    with pytest.raises(FileExistsError):
        execute(args)
