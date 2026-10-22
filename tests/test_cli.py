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


def test_cli_exposes_reasoning_effort():
    args = parser().parse_args(
        [
            "run",
            "scene.png",
            "--model",
            "test",
            "--reasoning-effort",
            "high",
            "--max-tokens",
            "8192",
        ]
    )
    assert args.reasoning_effort == "high" and args.max_tokens == 8192


def test_direct_box_preview_exports_one_full_resolution_image(tmp_path):
    scene = tmp_path / "scene.png"
    Image.new("RGB", (17, 11), "white").save(scene)
    output = tmp_path / "direct-preview"
    args = parser().parse_args(
        ["preview", str(scene), "--strategy", "bbox", "--tiles", "200", "--output", str(output)]
    )
    assert execute(args) == 0
    rows = json.loads((output / "regions.json").read_text())
    assert len(rows) == 1 and rows[0]["crop_box"] == [0, 0, 17, 11]
    assert Image.open(output / "crops/root.jpg").size == (17, 11)
