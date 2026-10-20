Place the user-supplied beach test image at `data/beach.png`. Images in this folder
are ignored by Git, apart from this notice. The supplied illustration remains
local test data; no redistribution rights are assumed. Source image SHA-256:

`fdac50a3addc9980518595a78eeecd3adfbd4c1217e8e670af6014f8133d085a`

The program can use any local PNG, JPEG or WebP image. Results and crops in `runs/`
are also ignored. Do not commit credentials or private image data.

The default visual exemplar is `data/waldo-reference.jpg`, downloaded separately
from Candlewick's publisher site:
https://waldo.candlewick.com/images/waldo-wave.jpg

Source SHA-256:
`526ecd2f0f2a9263d458f1010ef0c4810724ed9397630f265f49a0626c5a1614`

It is a standalone illustration and contains no location information from the
beach scene. It remains local and ignored by Git. No redistribution license is
assumed. Pass `--reference PATH` to use another local appearance exemplar.

The source-resolution experiment uses a separately downloaded 3000 × 1926 copy
from [this source page](https://wallpapers.com/wallpapers/where-s-waldo-beach-crowd-d614ctoxorwugf1b.html),
stored locally at `data/resolution-candidates/candidate-2.jpg`. Download SHA-256:

`e599391125592f8fa4460340eef5c4dee65f2b198bdb667ab43d22a030019d14`

It matches the scene with additional sky at the top; the experiment maps existing
crop bounds to this copy before inference. Its history before that host is
unknown. It remains ignored by Git and is not redistributed. See the
[source-resolution report](../reports/2026-10-20-source-resolution-comparison.md)
for alignment, controls and limitations.

`data/beach-high-resolution.jpg` is a byte-identical local copy for uploading into
the app or passing to `serve --image`. Its full-grid experiment and post-run
ground-truth marker are documented in the
[higher-resolution grid report](../reports/2026-10-20-high-resolution-grid.md).
The original `data/beach.png` remains unchanged for earlier experiment controls.
