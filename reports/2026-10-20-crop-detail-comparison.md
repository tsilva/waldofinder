# Crop detail comparison — 2026-10-20

Smaller crops plus enlargement helped Gemini identify the actual Waldo in this
probe. Cropping alone and enlargement of the wide crop did not. GPT still
confused distractors with Waldo and supplied inconsistent locations. This is
evidence that input scale and clutter matter, particularly for Gemini; it does
not establish missing source detail as the only bottleneck.

## Matched conditions

Both `google/gemini-4-argon` and `openai/gpt-6.1-sol` received six crops, each at
native size and enlarged 4× with Pillow Lanczos interpolation: **24 calls**.
All calls used high reasoning, an 8,192-token response cap, a 180-second transport
timeout, structured JSON, the unchanged `waldo-reference-occlusion-v2` prompt and
the same separate appearance reference. No explicit image-detail setting was
changed. Provider-reported models and providers matched the requested models.

The source was the same 1080 × 675 RGB beach image, pixel SHA-256
`5e45fdbdf048e26123dd8c1d030a0c27e0878dde3630b7dea38b5b0549e09c02`.
The normalized reference SHA-256 remained
`f0a36974cd6019fe8e825fa104f765195d4044ef4b1390188c1aaddda388ac21`.

Labels were fixed before inference using the user-confirmed center region and
the previously checked approximate character center (668, 253). Positive crops
contain his visible head and torso; the distractors were visually inspected and
exclude that character. Ground-truth metadata remains in
`data/beach-ground-truth.json`. Labels, coordinates, case IDs and annotations
were never supplied to either model. The appearance reference was not taken
from these target crops.

| Case | Content | Source bounds, half-open | Native input | Enlarged input | Truth |
| --- | --- | --- | --- | --- | --- |
| A | Original padded center grid crop | [331, 207, 749, 468] | 418 × 261 | 1672 × 1044 | Present |
| B | Waldo with medium context | [600, 190, 735, 325] | 135 × 135 | 540 × 540 | Present |
| C | Waldo with tight context | [635, 220, 700, 285] | 65 × 65 | 260 × 260 | Present |
| D | Gemini's earlier false-positive region | [0, 207, 389, 468] | 389 × 261 | 1556 × 1044 | Absent |
| E | Striped-shirt lookalike | [555, 230, 620, 295] | 65 × 65 | 260 × 260 | Absent |
| F | Changing-hut lookalikes | [90, 220, 155, 285] | 65 × 65 | 260 × 260 | Absent |

All 24 requests started before the first completed. Completion took **71 seconds**;
there were no errors, truncations or retries. Provider-reported total cost was
**$0.3750041**, with a cost returned for every request. Exact PNG hashes, settings,
usage, model answers and timestamps are preserved in
`runs/crop-detail-2026-10-20/results.json`.

## Results

Percentages are the model's self-reported decision confidence, not calibrated
probabilities or independent accuracy measurements.

| Case | Gemini native | Gemini 4× | GPT native | GPT 4× |
| --- | --- | --- | --- | --- |
| A · Waldo, wide | Absent 97% | Absent 95% | Present 89% | Present 92% |
| B · Waldo, medium | Absent 95% | **Present 95%** | Present 88% | Present 93% |
| C · Waldo, tight | Absent 93% | **Present 88%** | Present 84% | Uncertain 78% |
| D · Wrong region | Present 98% | **Absent 97%** | Uncertain 78% | Present 91% |
| E · Striped lookalike | Absent 95% | Absent 95% | Present 91% | Present 94% |
| F · Hut lookalikes | Absent 95% | Absent 98% | Present 90% | **Absent 84%** |

Gemini changed from zero to two positive answers across the three nested Waldo
crops, and from one false positive to none across the three negatives. Its
enlarged B and C answers describe the central figure just above/behind the
green-and-white windbreak, matching Waldo's actual location. This is stronger
evidence of a detection than simply saying present in a positive crop. Some
claimed fine features remain difficult to verify at the source resolution.

GPT gave two false positives at each scale, with the specific errors changing.
Its native B answer placed Waldo at the bottom edge and C placed him at the
upper-right edge; the target is near the center of both. Enlarged B still claimed
he was cropped at the bottom. Thus its positive answers should not be counted as
verified localizations. Enlarged C became uncertain, which appropriately
acknowledged ambiguity but did not produce a detection.

## Interpretation and limits

The native and enlarged members of each pair contain exactly the same scene
content. Enlargement creates interpolated pixels; it cannot recover lost source
detail. Gemini's changed answers therefore suggest sensitivity to presented scale
or downstream image processing. They cannot prove what the provider's internal
vision pipeline did. Google reported identical prompt-token counts within every
scale pair, while OpenAI's counts increased with enlargement; those totals do not
reveal the internal image representation.

The wide positive crop remained a Gemini false negative even after enlargement,
whereas the enlarged smaller crops worked. That pattern suggests both surrounding
clutter and presented character scale matter here. It supports testing smaller
overlapping crops with explicit enlargement before increasing reasoning further.
It does not show that enlargement fixes recognition generally, or that a higher
resolution original would be unnecessary.

There was one request per condition and three nested positives of the same
character in one image. These are not three independent examples. Model variance,
interpolation and automatic image preprocessing remain possible explanations.
No broad accuracy claim or causal attribution follows from this small probe.

## Reproduce and inspect

`experiments/crop_detail.py` is specific to this labeled scene and refuses another
pixel hash or an existing output directory. Offline preparation makes no API calls:

```bash
uv --config-file uv.toml run python experiments/crop_detail.py \
  --image data/beach.png --output runs/crop-detail-preview
# Makes exactly 24 paid calls through the existing Infisical-backed provider:
uv --config-file uv.toml run python experiments/crop_detail.py \
  --image data/beach.png --output runs/crop-detail-repeat --live
```

Each output contains an HTML review sheet, exact submitted crop PNGs, reference,
source and JSON results. The local completed sheet is at
`runs/crop-detail-2026-10-20/review.html`; it shows both scales and the unedited
answers. It is separate from the dashboard's historical grid runs. No search
defaults or historical predictions were changed.

Validation checked all 12 PNG transforms and hashes against the source, all 24
unique response bindings, fixed settings/reference and concurrent dispatch. Ruff
checks pass. The review sheet and linked crop images were inspected in the native
in-app browser. Images and run records remain ignored by Git.
