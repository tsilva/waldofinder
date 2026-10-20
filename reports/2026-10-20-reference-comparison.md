# Visual reference and partial-occlusion comparison — 2026-10-20

Adding the exemplar and stronger occlusion instructions changed only one of the
18 region decisions. Gemini retained its single candidate; GPT moved from nine
positive regions to eight. This run does **not establish an accuracy improvement**.
Subsequent user confirmation and visual verification placed Waldo in `r1c1`:
Gemini's sole candidate was wrong, and it missed the confirmed center region in
both runs. The ground-truth follow-up below records the marker and provenance.

## Matched setup

- Baseline: `web-0199d9b9a2e14498a77623ce80106ff2`, original text-only prompt.
- Intervention: `web-94049e8c82254bf2a13e1ff69f874df7`, prompt version
  `waldo-reference-occlusion-v2`, with a separately labeled reference image.
- The same 1080 × 675 image, 3 × 3 grid, 8% padding, 0.7 confidence threshold,
  32 shared concurrent slots, 32-attempt per-model cap, 2048 output tokens,
  90-second timeout, structured JSON, and the same two model IDs.
- Configuration objects matched exactly. All 18 search-crop PNGs matched the
  baseline byte for byte. Non-prompt request settings also matched. Returned
  providers remained Google and OpenAI respectively.

The exemplar is the standalone character illustration from
[Candlewick's Waldo site](https://waldo.candlewick.com/), not a crop of the target
scene: [original reference image](https://waldo.candlewick.com/images/waldo-wave.jpg).
It shows a full figure on white, measuring 500 × 1121 pixels.

- Original JPEG SHA-256:
  `526ecd2f0f2a9263d458f1010ef0c4810724ed9397630f265f49a0626c5a1614`
- Normalized PNG SHA-256, sent with every request:
  `f0a36974cd6019fe8e825fa104f765195d4044ef4b1390188c1aaddda388ac21`

The new prompt distinguishes the REFERENCE from the SEARCH CROP, explicitly
forbids counting the exemplar as a detection, allows partial visibility and
crop-edge truncation, and avoids requiring every identifying feature together.
It still requires visible identifying evidence, warns against striped distractors,
and permits uncertainty. The full instruction and exact reference are stored
with the new run; original baseline artifacts are preserved.

## Results

Each model made nine requests with zero API errors in both runs. Candidate counts
mean model-positive crops above the threshold, not verified detections.

| Model | Candidates before | Candidates after | Cost before | Cost after | Input tokens before → after |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gemini 4 Argon | 1 / 9 | 1 / 9 | $0.033458 | $0.057638 | 13,199 → 25,439 |
| GPT-6.1 Sol | 9 / 9 | 8 / 9 | $0.029566 | $0.0520915 | 2,878 → 11,374 |

Gemini still selected `r1c0`, the middle-left grid region, at 95% confidence.
GPT's only decision change was `r2c0`, the bottom-left region: **present 86% →
absent 90%**. Both are self-reported confidence values. The remaining decisions
were unchanged, though some confidence values and explanations differed.

Total reported cost increased from **$0.063024 to $0.1097295**, about 74%.
The additional exemplar and longer prompt increased input tokens. This is one
before/after pair on one image, with both interventions changed together; it
cannot separate their individual contributions or distinguish a small effect
from ordinary model variation. No ground-truth annotations were added.

## Review and verification

The local dashboard is left on the new run. Click a model's status inside a
region to inspect its exact search crop and save a separate human review.
Configuration includes the reference preview and full prompt. History labels
reference-assisted runs separately from text-only runs. Session JSON exports
include the new prompt and reference manifest; `reference.png` remains available
among the saved run artifacts. Images and generated runs stay ignored by Git.

61 offline tests pass on Python 3.11.15 and 3.14.5, including ordered reference/
search-image payload validation, occlusion and exemplar-exclusion instructions,
reference normalization and hash binding, missing/oversized reference rejection,
run provenance persistence, historical prompt recovery, and HTTP reference serving.


## Ground-truth follow-up

The user subsequently confirmed **the center region, `r1c1`**, as containing Waldo.
Assistant inspection, corroborated against published solution screenshots from
[Destructoid](https://www.destructoid.com/how-to-solve-level-11-of-im-not-a-robot-and-find-waldo/)
and [I'm Not a Robot Guide](https://imnotarobot.cc/level/11/), localized a point on
his visible striped torso at approximately **(668, 253)** in the 1080 × 675 image.
He is immediately above the pale blue/green windbreak and left of the red-and-white
changing hut. The region is user-confirmed; the exact marker pixel is assistant-
localized. At this source resolution it should not be treated as a segmentation
boundary.

Gemini's sole positive region was `r1c0`, whose actual padded crop spans
`[0, 207, 389, 468]`. It does not contain Waldo. Gemini classified the confirmed
center region `r1c1` as **absent, 95% confidence**. Thus its selected region was a
**false positive**, and its center-region decision was a **false negative** in
both the text-only baseline and the reference-assisted rerun. GPT marked the
confirmed center region present in both runs, alongside many other positives.

The marker and separate review labels (`r1c0`: absent, `r1c1`: present) were saved
for both matched runs. Original predictions, confidence values and model reports
remain unchanged. Local `data/beach-ground-truth.json` and each matched run's
`ground-truth.json` record the image pixel hash, point, user confirmation and
verification sources. The earlier no-ground-truth statements describe the state
at the time of the initial comparison.

No whole-grid accuracy score is inferred from the marker alone: the top-center
padded crop reaches into the character's upper area, so valid partial visibility
must be reviewed separately rather than treating point containment as an exhaustive
presence label.
