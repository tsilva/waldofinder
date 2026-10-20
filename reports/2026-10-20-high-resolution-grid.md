# Higher-resolution full-grid search — 2026-10-20

**Gemini found Waldo without a preselected target crop.** Its full 3 × 3 search
returned exactly one candidate, the correct center region `r1c1`, at 99%
self-reported confidence. The description matches the actual figure above the
right end of the green-and-white windbreak. GPT also selected the center, but
returned five additional, visually checked false positives.

## App run

The 3000 × 1926 source copy was loaded through the app's Upload image control.
It is now available locally as `data/beach-high-resolution.jpg`, byte-identical
to `data/resolution-candidates/candidate-2.jpg`. The original 1080 × 675 file and
historical runs were preserved. The current app run persists the higher-resolution
scene and restores it on reload.

The source download hash remains
`e599391125592f8fa4460340eef5c4dee65f2b198bdb667ab43d22a030019d14`.
The app's normalized RGB pixel hash is
`7eb348bcac98a3b8b36895dd587474c5b0f07d462ef7792c14b8e5edb0271c96`.
Source provenance and the earlier same-size detail controls are documented in the
[source-resolution comparison](2026-10-20-source-resolution-comparison.md).

Run ID: `web-b4872a7fd7d14060ac51271fa2cf2d99`.

- Live full-scene fixed grid: nine regions, 8% padding, 0.7 confidence threshold.
- Models: `google/gemini-4-argon` and `openai/gpt-6.1-sol`.
- High reasoning, 8,192-token response cap, 180-second transport timeout,
  structured JSON and a shared concurrency limit of 32.
- Same `waldo-reference-occlusion-v2` prompt and separate reference image,
  normalized reference hash
  `f0a36974cd6019fe8e825fa104f765195d4044ef4b1390188c1aaddda388ac21`.
- All 18 calls started before the first completed. No retries, errors or
  model fallbacks occurred; returned model IDs matched the requests.

The regular grid was generated from the entire image. All regions were submitted
to both models, without a prior positive-region selection or target-dependent
crop adjustment. Inference images were neither enlarged nor annotated. No
location coordinates or human labels were sent to the models. The new image has
additional sky, so this grid's exact bounds differ slightly from the earlier
low-resolution grid; the previous controlled detail experiment isolates source
detail more precisely than a direct comparison of these two full grids.

## Predictions

| Region | Gemini | GPT |
| --- | --- | --- |
| r0c0 | Absent 98% | Absent 85% |
| r0c1 | Absent 98% | Absent 88% |
| r0c2 | Absent 99% | Present 84% — false positive |
| r1c0 | Absent 98% | Present 99% — false positive |
| r1c1 | **Present 99% — correct location** | **Present 97% — correct location** |
| r1c2 | Absent 99% | Present 88% — false positive |
| r2c0 | Absent 99% | Absent 90% |
| r2c1 | Absent 97% | Present 98% — false positive |
| r2c2 | Absent 95% | Present 98% — false positive |

Gemini's center response described the upper-right part of its crop, just behind
the right end of the green-and-white windbreak, including the striped shirt,
hat, glasses, blue trousers and carried gear. This matches the independently
verified character. The exact padded crop was `[920, 591, 2080, 1335]`,
**1160 × 744 pixels**. This is the ordinary center grid crop, not the earlier
hand-selected medium/tight crop.

GPT's center description also matches the target area. Its five extra candidates
refer to other changing-hut figures, an umbrella, boundary figures and striped
lookalikes elsewhere in the scene. Those crops were visually checked and labeled
absent separately from predictions. Confidence remains uncalibrated; it is not
treated as detection accuracy. No whole-grid accuracy is inferred merely from
whether a crop contains the reference point.

| Model | Calls | Candidates | Errors | Model completion time | Reported cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gemini 4 Argon | 9 | 1 | 0 | 41.5 s | $0.167228 |
| GPT-6.1 Sol | 9 | 6 | 0 | 93.1 s | $0.1907715 |

Both models ran concurrently. The full run took about 93 seconds and reported
**$0.3579995** in total cost, with usage/cost returned for every call.

## Review and verification

After completion, the previous independently verified torso point was mapped to
approximately **(1856, 754)** and added to the app. Center-present reviews for
both models and five GPT-negative reviews were stored in `review.json`, with an
initial review backup. The `results.json` hash was checked before and after these
updates to confirm that predictions were unchanged. Ground-truth provenance is
saved separately in `data/beach-high-resolution-ground-truth.json` and this run's
`ground-truth.json`.

Verification checked all 18 exact crop files against the normalized source,
request settings, returned model IDs, reference binding and parallel dispatch.
In-app browser checks verified the uploaded 3000 × 1926 dimensions, saved
configuration, live progress, completed decisions, Gemini's crop review, marker
and review persistence after reload. The full image fits the current viewport
without document scrolling. Screenshots are saved inside the run folder.

The app is left on the completed higher-resolution full-grid run with the target
marker visible. For a fresh app session that should use this file as its startup
sample, run:

```bash
uv --config-file uv.toml run waldofinder serve --port auto \
  --image data/beach-high-resolution.jpg
```

This demonstrates successful full-grid localization for Gemini on this image in
this run. It is not a general reliability estimate across images or repeated full
grid searches.
