# Explicit image detail and bounding-box test — 2026-10-20

Requesting OpenRouter's `original` detail changed Gemini's behavior on the exact
crop it had confidently rejected: default `auto` missed Waldo in 5/5 new calls;
`original` correctly localized him in 5/5. Gemini also made one confident false
positive in ten negative-control calls at `original`. GPT-6.1 Sol localized the
real target at both settings but falsely detected Waldo in every negative trial.

This strongly supports an image-detail bottleneck for this Gemini crop, alongside
a separate specificity problem for GPT. It does not establish general reliability
across images or prove the provider's internal preprocessing configuration.

## Matched experiment

The scene, reference and failing crop are unchanged from the
[repeated-crop experiment](2026-10-20-repeated-crop.md). Each call is a fresh
conversation containing the separate appearance reference and one unmarked PNG.

- Models: `google/gemini-4-argon` and `openai/gpt-6.1-sol`, routed to Google and
  OpenAI respectively, with fallbacks disabled and required parameters enabled.
- High reasoning, 8192 output tokens, 180-second timeout. Temperature zero for
  Gemini, whose catalog entry supports it; no temperature for GPT.
- Search-image detail: explicit `auto` versus explicit `original`. Reference
  detail is fixed at `auto` in both arms.
- One positive and two negative crops, each 1620 × 1040, each repeated five times
  per detail setting and model: **60 calls, 60 distinct generation IDs, no retries,
  no invalid or incomplete answers**. Up to 32 concurrent requests.
- The four initial positive probes are included as replicate 1, followed by the
  remaining 56 calls. Subsequent jobs were shuffled with a fixed seed. The two
  batches took 145.970 seconds combined, excluding the analysis gap between them;
  this is not the wall time of a single 60-call batch.
- The occlusion-aware prompt now requires a tight normalized bounding box for
  `present` and null for `absent` or `uncertain`. **The same bounding-box prompt is
  used in both detail arms.** Historical presence-only calls are contextual
  evidence, not a matched estimate of the bounding-box prompt's effect.

Source-coordinate bounds:

| Case | Bounds `[left, top, right, bottom]` | Expected |
| --- | --- | --- |
| Previously pruned `root.1.0` | `[1380, 0, 3000, 1040]` | Present |
| Left-side huts and striped distractors | `[0, 0, 1620, 1040]` | Absent |
| Lower beach and striped distractors | `[1380, 886, 3000, 1926]` | Absent |

The positive PNG's SHA-256 is
`49b18d7ee39560c15c86212c90b29cf99c2e49d13343b6b132a71ebbbac4336c`,
identical to the earlier failing input. Inputs, hashes, full prompt, schema,
request hashes, generation IDs, usage and final answers are saved locally in
`runs/image-detail-2026-10-20/results.json`. Images and run artifacts stay ignored
by Git; credentials and raw provider envelopes are not saved.

## Grounding and results

Before paid requests, I visually checked and froze the visible-character box at
`[1818, 703, 1896, 801]` and the existing target point at `[1856, 754]` on the
3000 × 1926 source. This is an assistant annotation of the user-confirmed Waldo,
not a new user-confirmed pixel rectangle. Ground truth never enters requests.

A localization passes only when the predicted box contains the target point and
its intersection-over-union (IoU) with the frozen rectangle is at least 0.25. A
box covering the whole crop therefore fails. Every successful positive box also
passes the stricter IoU ≥ 0.5 criterion. Negative controls exclude the entire
ground-truth rectangle.

| Model | Detail | Correct positive boxes / 5 | False alarms / 10 negative calls | Median call latency | Reported total cost |
| --- | --- | ---: | ---: | ---: | ---: |
| Gemini 4 Argon | auto | 0 | 0 | 31.127 s | $0.3716260 |
| Gemini 4 Argon | original | 5 | 1 | 30.565 s | $0.3640737 |
| GPT-6.1 Sol | auto | 5 | 10 | 42.314 s | $0.2543402 |
| GPT-6.1 Sol | original | 5 | 10 | 41.548 s | $0.2179806 |

**Total: $1.2080205**, with reported cost available for every call. Costs include
provider caching effects and variable reasoning/output lengths, so this table
does not establish that higher detail is inherently cheaper. The positive box
IoU ranges were 0.689–0.721 for Gemini `original`, 0.795–0.888 for GPT `auto`, and
0.768–0.841 for GPT `original`.

Gemini's five default-detail false negatives had confidence 0.98–0.99. Its one
`original` false positive had confidence 0.98 and pointed near Odlaw and a man
between blue-and-white huts, far from the true target. I inspected a magnified
view: the box is a genuine false detection. GPT's false positives remained
confident (0.93–0.99 at `auto`, 0.96–0.99 at `original`). Bounding-box output makes
these errors checkable; it does not by itself prevent them.

These are **one positive crop and two distinct negative crops**, repeatedly
sampled. Five correct repetitions do not measure performance across five
independent scenes, and ten negative trials are not ten independent crops.

## What image-detail handling was actually verified

OpenRouter's [published OpenAPI schema](https://openrouter.ai/openapi.json)
defines `original` as an extension requesting original-resolution media and says
it falls back to `high` for providers without that tier. Google's
[media-resolution guide](https://ai.google.dev/gemini-api/docs/generate-content/media-resolution)
describes native per-image resolution levels. OpenAI's
[vision guide](https://developers.openai.com/api/docs/guides/images-vision)
describes model-dependent detail settings; its sizing table did not document
GPT-6.1 Sol specifically when checked, so no other model's pixel/token budget
was assumed for Sol.

Every request used streaming and requested `debug.echo_upstream_body`, documented
in the [OpenRouter API reference](https://openrouter.ai/docs/api-reference/overview).
**None of the 60 responses supplied the requested upstream echo.** Therefore the
experiment cannot verify whether Google received native HIGH or ULTRA_HIGH, nor
the exact upstream OpenAI representation. There is no claim that native maximum
resolution was independently confirmed.

However, provider-reported input-token counts were consistent in all 15 calls
of each arm, including equally sized negative controls:

| Model | auto input tokens | original input tokens |
| --- | ---: | ---: |
| Gemini 4 Argon | 2983 | 4100 |
| GPT-6.1 Sol | 3257 | 3257 |

Only the search-image detail field differs between matched arm requests. Gemini's
1117 additional input tokens support the inference that `original` increased its
visual representation budget. GPT's unchanged count supplies no evidence of an
increased visual budget; its default may already use the same effective detail.
Token totals alone do not expose internal pixels, tiles, or native resolution.

## Local review and reproduction

`runs/image-detail-2026-10-20/review.html` lets the user select model, detail, crop
and repetition. Green marks frozen ground truth; pink marks the returned model
box. It shows decision, confidence, IoU, time, cost and visible-evidence reason.
The review was tested through the native in-app browser: positive overlays,
default-detail misses, both models' negative-control errors, and full image fit
without page scrolling at the existing 1280 × 720 viewport. Contact sheets and a
browser verification screenshot are saved beside it.

The scene-specific helper `experiments/image_detail.py` prepares crops offline;
`--live` explicitly enables paid requests. Existing results are resumed without
retrying completed attempts, including errors. Choose a new output folder for a
fresh experiment:

```bash
uv --config-file uv.toml run python -m experiments.image_detail \
  --output runs/image-detail-new --repeats 5
# Add --live to make 60 paid requests; --live --probe makes just four initial calls.
```

The helper requires the locally saved source image and binary-run reference/crop;
these ignored assets are not distributed with the public repository. The main
grid/binary app's inference defaults have not been changed by this experiment.
Both Python 3.14 and 3.11 passed all 81 tests; Ruff passed.
