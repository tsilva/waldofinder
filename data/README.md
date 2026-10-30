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

The Wenda and Odlaw distractor examples are extracted from the publisher's
[character sheets](https://waldo.candlewick.com/pdf/WaldoCharacterSheets20.pdf),
pages 3 and 5 (one-based). PDF SHA-256:
`8a4033c7d3602c6664966bcc7c47c8e6f3e43a5e324870818cffe20bfbc840e1`.

Render at 1500 pixels on the long edge with Poppler, crop character bounds
Wenda `[330,55,835,1435]`, Odlaw `[220,55,940,1435]`, then thumbnail within
700 × 1121 without upscaling. `python -m experiments.extract_distractors PDF`
implements this procedure and refuses a changed PDF or existing output files.
Rendered bytes may vary with Poppler versions; every run records its actual hash.
This experiment's local files:

- `wenda-reference.png` (410 × 1121), SHA-256
  `bb8b3a65870b72677d9da9f20925654b318e044749634d28803519373624d1d7`
- `odlaw-reference.png` (585 × 1121), SHA-256
  `5ba45b067d60bb1efbf7acb31ab3b3344294fdf66fbcb68ae65efd2a8ab52ea9`

These independent appearance examples contain no beach-scene coordinates. They
remain local and ignored by Git; no redistribution license is assumed.

## Additional full-scene candidates (2026-10-21)

`data/online-waldo-scenes/` contains 19 full-scene JPEGs selected from the
[Charlie-DB original-image collection](https://github.com/pekatour/Charlie-DB),
pinned to commit `e97f7646a2f0e72ddcc02bbb6f7a179dae63e174`. These are type `0`
(full image), excluding the repository's half-page and crop variants. Actual
decoded dimensions range from 2560 × 1680 to 3591 × 2244. The source bytes were
saved unchanged (54.6 MB total); no local upscaling or enhancement was applied.

`manifest.json` records each source URL, commit, decoded size, SHA-256, descriptive
scene label and visual quality notes. `index.html` is a local browsable catalog;
`shortlist.jpg` previews eight varied scenes. The separate candidate index under
`data/online-waldo-candidates/` records header dimensions for the 100 source files
checked. Original artwork, thumbnails and manifests remain ignored by Git.

Some originals include printed story panels, standalone character examples, page
seams, margins or dark scans. The studio introduction has several inset scenes
and appearance references and is flagged for exclusion from an initial benchmark.
The moon colony, castle siege and hedge maze have no large printed legend observed.
These notes do not certify that source files were never resized before upload.
No model calls were made during acquisition. Repository software licensing does
not establish redistribution rights for the book illustrations.

For the subsequent all-19 BSP experiment, upstream annotations from the same commit
were downloaded separately to `annotations/`. Class 0 is Charlie/Waldo. Each selected
main-scene target was visually checked before paid searches; printed appearance
examples were excluded. `4-9-0.jpg` needs line 3 of the separate head annotation:
the full-body file labels only the printed example. The experiment freezes these
coordinates, annotation hashes and provenance in `ground-truth.json`, separately
from model inputs. These are assistant-verified annotations, not independent human
confirmation. All 19 scenes are included, including the studio introduction, with
one common instruction to ignore printed portraits and reference panels.

## License

[MIT License](../LICENSE).
