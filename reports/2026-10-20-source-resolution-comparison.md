# Source-resolution comparison — 2026-10-20

Source detail contributes to Gemini's failures on this scene. With a clearer
3000 × 1926 web copy, it identified Waldo in all three target crops and rejected
all three distractors. The wide crop produced a repeatable contrast: **present
3/3 with source detail, absent 3/3 after controlled degradation**, despite exactly
equal input dimensions. GPT still produced false positives on every sharp
distractor, so higher resolution did not make its presence judgments reliable.

## Source verification

The larger copy was retrieved from
[Wallpapers.com](https://wallpapers.com/wallpapers/where-s-waldo-beach-crowd-d614ctoxorwugf1b.html),
using its linked
[3000 × 1926 JPEG](https://wallpapers.com/images/hd/where-s-waldo-beach-crowd-d614ctoxorwugf1b.jpg).
Its download SHA-256 is
`e599391125592f8fa4460340eef5c4dee65f2b198bdb667ab43d22a030019d14`.
Artwork remains local and ignored by Git. Its history before that host is unknown;
it is not described as a verified publisher scan.

Visual inspection confirmed the same target, windbreak, changing huts and
distractors, with clearer line detail. Registration maps the earlier image's
coordinates to the larger copy using `x′ = x × 25/9`, `y′ = y × 25/9 + 51`.
The additional 51 pixels are sky at the top. Full-scene vertical edge correlation
after reduction was 0.9713, with a clear optimum at that offset. This supports a
close content match rather than relying on matching file dimensions alone.
Waldo's prior approximate torso point (668, 253) maps to approximately (1856, 754).

## Controlled test

Each of the six previously reviewed crop bounds was mapped to the larger copy.
Two inputs were made from each high-resolution crop:

1. **Source:** the unresized crop from the larger copy.
2. **Degraded:** that same crop reduced to the earlier crop's pixel dimensions,
   then enlarged back to exactly the source crop's dimensions using Lanczos.

Both members have identical scene bounds, input dimensions, colors before
filtering, and provenance. The control deliberately removes fine detail while
preserving presented size. It is derived from the larger copy, rather than the
older file, to avoid attributing changes in edition, scan color or margins to
resolution. This filtering is not a byte-for-byte reconstruction of the older
image's unknown degradation pipeline.

Both 2026 models used the unchanged appearance reference, occlusion prompt, high
reasoning, 8,192-token response cap, structured JSON and 180-second timeout.
Ground-truth labels and coordinates were withheld. Model IDs, returned models,
reference hash, settings and crop hashes were checked. No image-detail API option
or search defaults changed.

| Case | Content / truth | Equal input dimensions | Gemini source | Gemini degraded | GPT source | GPT degraded |
| --- | --- | --- | --- | --- | --- | --- |
| A | Wide target / present | 1162 × 725 | Present 99% | Absent 97% | Present 95% | Present 86% |
| B | Medium target / present | 375 × 375 | Present 99% | Present 98% | Present 98% | Present 78% |
| C | Tight target / present | 180 × 181 | Present 100% | Present 98% | Present 88% | Uncertain 78% |
| D | Earlier wrong region / absent | 1081 × 725 | Absent 95% | Absent 98% | Present 97% | Present 82% |
| E | Striped-shirt lookalike / absent | 180 × 180 | Absent 98% | Absent 95% | Present 91% | Present 94% |
| F | Changing-hut lookalikes / absent | 181 × 181 | Absent 98% | Absent 95% | Present 97% | Uncertain 76% |

Confidence is each model's own uncalibrated judgment. Gemini's sharp A–C
descriptions point to the actual figure above/behind the green-and-white
windbreak, including his carried gear. GPT's sharp A and B descriptions also
improve in location. Its degraded B still points to a nonexistent bottom-edge
Waldo, and its sharp C description has an ambiguous relationship to another
figure. Presence alone is not treated as independently verified localization.

## Repeated wide-crop pair

Two additional calls per model/condition repeated case A with byte-identical
inputs and settings, giving three observations per condition including the first
pass. There were no retries of errors.

| Model | Source crop | Degraded crop |
| --- | --- | --- |
| Gemini 4 Argon | Present 3/3, each 99%; correct windbreak location | Absent 3/3, confidence 97%, 97%, 98% |
| GPT-6.1 Sol | Present 3/3, confidence 95%, 96%, 97%; descriptions match the target area | Present 3/3; less consistent location evidence |

This is a repeatable within-image effect for Gemini's wide crop. Smaller degraded
crops B/C were already sufficient for it, consistent with the earlier finding
that reducing clutter and enlarging inputs can help even without additional
source information. The sharper source helped the wider search succeed too.

GPT's continued sharp distractor positives, including the short-sleeved striped
lookalike and the changing-hut group, show that resolution alone does not explain
its failures. Sharper source detail can help visual grounding while leaving
recognition and false-positive problems unresolved.

No AI-generated upscale was used because a matching, visibly more detailed copy
was found. A generative reconstruction would not establish what the original
fine features were; inventing a hat or glasses would contaminate this detection
test. That is an experimental limitation, not a claim that generative enlargement
can never look useful.

## Records and reproduction

The main matrix made 24 concurrent calls in 72.2 seconds. All started before the
first completed. Eight additional concurrent calls tested the wide-crop pair.
All **32 responses were valid**, with no errors, truncations or fallbacks.
Provider-reported cost was **$0.4840112**: $0.382758 for the matrix and $0.1012532
for repeats, with a cost field returned for every request.

Local records under `runs/source-resolution-2026-10-20/` include `results.json`,
`wide-replicates.json`, the exact `input.png`, `reference.png`, crop PNGs and
`review.html`. The HTML sheet displays both conditions and repeat counts without
altering historical predictions. These records and artwork remain ignored by Git.

The scene-specific preparation script pins the downloaded file hash and refuses
an existing output directory. The default command is offline; `--live` explicitly
makes the 24-call matrix:

```bash
uv --config-file uv.toml run python -m experiments.source_resolution \
  --source data/resolution-candidates/candidate-2.jpg \
  --output runs/source-resolution-preview
uv --config-file uv.toml run python -m experiments.source_resolution \
  --source data/resolution-candidates/candidate-2.jpg \
  --output runs/source-resolution-repeat --live
```

Validation checked exact source-crop bytes, all 12 PNG hashes, equal paired
dimensions and degradation transforms, all 32 response/input/settings bindings,
returned model IDs, the shared reference and concurrent dispatch. Ruff checks
pass; the review sheet was inspected in the native in-app browser.

These remain three nested views of one character, three hand-selected negative
crops and a few repeated calls. Results support a source-detail effect on this
scene, not a general accuracy estimate or a guarantee of reliable detection.
