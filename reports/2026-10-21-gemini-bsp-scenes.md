# Gemini 4 Argon BSP across 19 scenes

Gemini was **not consistently successful** under this BSP configuration. Visual
review confirmed **7 finds, 6 model misses and 6 inconclusive searches**. Among
the eight searches with no gateway errors anywhere, three found Waldo and five
missed him. Missing provider responses are not counted as model mistakes.

The six conclusive misses all rejected Waldo's root half at **97–98% confidence**.
This prevented BSP from ever checking smaller crops around him. Four terminal
candidate boxes across three scenes were off target; two overlapping forest
candidates identified **Wenda**, despite the example image and explicit exclusion.

## Inputs and protocol

- All 19 full-scene JPEGs from the pinned
  [Charlie-DB collection](https://github.com/pekatour/Charlie-DB/tree/e97f7646a2f0e72ddcc02bbb6f7a179dae63e174/original-images),
  2560 × 1680 through 3591 × 2244. Source hashes and URLs are preserved locally.
- Before any paid calls, the assistant visually checked upstream class-0
  annotations for the main-scene character and froze coordinates separately.
  Printed examples do not count. The dinosaurs scene uses the separately verified
  head annotation because its body annotation lists only the printed portrait.
  These annotations have not been independently confirmed by the user.
- Model: `google/gemini-4-argon`, returned provider Google on successful calls;
  `original` crop detail, high reasoning, 8192 output tokens, strict decision JSON,
  temperature 0 when supported, no provider fallbacks.
- The app's production BSP engine: split the full image into two halves, 8%
  overlap, maximum depth 4, minimum size 64, confidence threshold 0.7, region cap
  32. Confident negatives prune permanently; positives/uncertain regions split.
  Stop submitting after a confident terminal candidate; calls in flight finish.
- One search per scene; no automatic retries. Up to eight scenes and 32 inference
  calls overlap, subject to a separate 5.8 MB upload budget.
- Same three independent references: Waldo, Wenda and Odlaw. Prompt version
  `waldo-scene-distractors-v4` adds one common instruction to ignore printed
  portraits, appearance guides and reference panels. Target coordinates, upstream
  annotations and scene-specific hints are never sent to the model.

The transport condition changed from earlier PNG experiments: search crops are
**JPEG quality 90, 4:4:4 chroma, with no resizing**. This is lossy compression and
could affect tiny features; it is not a controlled replication of the beach PNG
experiments. The separate appearance-reference PNGs remain unchanged. Exact sent
JPEGs, hashes, dimensions, encoding settings, wire sizes and queue times are saved.

## Per-scene results

“Found” requires a candidate covering the frozen target **and** a visually matched
explanation. A miss has a successful negative on the target branch with no failed
target-containing branch that might recover it. A failed target path is
inconclusive, even if another overlapping branch confidently rejects Waldo.
Errors outside the target path do not erase a verified find or conclusive miss.

| Scene | Result | Calls / errors | Seconds¹ | Reported USD² |
| --- | --- | ---: | ---: | ---: |
| Department store (`1-11-0`) | Inconclusive | 4 / 1 | 102.5 | $0.09227 |
| Moon colony (`2-12-0`) | Found | 18 / 1 | 186.9 | $0.38438 |
| Medieval fair (`2-6-0`) | Found | 8 / 1 | 614.6 | $0.13719 |
| The Gobbling Gluttons (`3-1-0`) | Found | 8 / 2 | 182.9 | $0.14302 |
| The Underground Hunters (`3-11-0`) | Found | 8 / 0 | 629.9 | $0.19737 |
| The Fighting Foresters (`3-7-0`) | Inconclusive | 14 / 2 | 1717.3 | $0.32817 |
| The Deep-Sea Divers (`3-8-0`) | Miss | 2 / 0 | 323.7 | $0.06427 |
| The Knights of the Magic Flag (`3-9-0`) | Found | 10 / 0 | 1498.4 | $0.22371 |
| Movie-studio introduction (`4-1-0`) | Miss | 2 / 0 | 573.4 | $0.07207 |
| Robin Hood movie set (`4-10-0`) | Found | 10 / 0 | 1394.5 | $0.25657 |
| Hollywood red carpet (`4-11-0`) | Found | 10 / 1 | 1040.2 | $0.21551 |
| Silent-movie set (`4-2-0`) | Inconclusive | 2 / 1 | 374.7 | $0.03363 |
| Castle siege (`4-3-0`) | Miss | 2 / 0 | 522.9 | $0.08385 |
| Foreign Legion movie set (`4-4-0`) | Miss | 2 / 1 | 887.8 | $0.03755 |
| Musical movie set (`4-5-0`) | Miss | 2 / 0 | 988.3 | $0.06357 |
| Ali Baba movie set (`4-6-0`) | Inconclusive | 2 / 1 | 344.3 | $0.03851 |
| The Swashbuckling Musketeers (`4-8-0`) | Inconclusive | 2 / 1 | 271.3 | $0.05595 |
| Dinosaurs and aliens movie set (`4-9-0`) | Inconclusive | 2 / 1 | 120.9 | $0.02590 |
| Hedge maze (`7-8-0`) | Miss | 2 / 0 | 224.8 | $0.07491 |

¹ Times include source/crop processing, upload queueing, network upload, inference
and report writes while other scenes compete for capacity. Active batch execution
was **2009.75 s (33.5 minutes)**; median scene time was **522.91 s**. These are not
isolated model-latency measurements and cannot be compared directly with the
previous beach-search timings.

² The JPEG batch made **110 calls: 97 usable responses and 13 gateway errors**.
Reported cost is **$2.5284032**, with incomplete billing for failed requests. An
authenticated text-only diagnostic separately reported **$0.000128**. Reported
total for these calls is **$2.5285312**; unknown charges are not assumed zero.

## Visual audit details

- Moon: the balcony candidate matches the true character; the restaurant candidate
  is off target.
- Gluttons: the identified character behind the banquet table, left of the central
  roasting fire, matches the target.
- Medieval fair: Waldo carrying books above the thatched roof matches the target.
- Underground: Waldo among the blue-clad rope carriers right of the dragon matches.
- Robin Hood: the explanation correctly locates Waldo peeking over the orange roof.
- Red carpet: the explanation correctly locates Waldo behind the tuxedoed man
  between the red curtains.
- Magic Flag: two overlapping candidates identify the same Waldo below a pink
  banner. A third box is off target; overlapping boxes are not separate detections.
- Forest: the true terminal target-path call failed. Both terminal positive boxes
  identify the same Wenda among the knights. Independent upstream class-2 labeling
  and the visual appearance agree. Confidences were 98% and 95%.
- Department store: the half containing Waldo failed. The positive in the other
  half was nonterminal and disappeared after subdivision; it is not evidence that
  the actual target was first found and then pruned.
- Musketeers: the target lies in the overlap of the root crops. One was rejected
  at 98%; the other failed. The overall result remains inconclusive.

Acquisition labels incorrectly called the department store “Wild West frontier”
and the musketeer scene “Monster movie set.” Their catalog labels were corrected
after the batch. The original manifest is snapshotted and hash-verified; image
bytes, frozen target coordinates and model inputs did not change.

## Gateway failures and provenance

Three preserved PNG attempts made **42 calls, all failing with HTTP 502**, before
the JPEG condition. They produced no usable decisions, generation IDs or reported
cost. Together with the JPEG condition, there were **152 image-call attempts and
55 gateway failures**. These failures are excluded from recognition scoring and
their potential charges remain unknown.

Authenticated small requests worked. A 64 KB invalid-model transport probe returned
the expected validation error in 0.46 s; the same probe with a 4 MB body took
35.90 s. The inspected
[Infisical CLI proxy source](https://github.com/Infisical/cli/blob/main/packages/agentvault/proxy.go)
declares a 60-second inner request-body read timeout. This supports slow large
uploads as a cause of the original failures. Refreshing the proxy and enabling
streaming alone did not fix them. Older DNS failures were historical; current
system DNS and authenticated access worked. Some JPEG calls still returned 502,
so upload compression did not resolve every gateway failure, and the cause of
each remaining error is not established. No credentials were extracted, exposed,
or moved out of the existing Infisical proxy workflow.

Local, Git-ignored artifacts:

```text
runs/gemini-bsp-19-scenes-2026-10-21/                    # 38 failed PNG calls
runs/gemini-bsp-19-scenes-2026-10-21-streaming/          # 2 failed PNG calls
runs/gemini-bsp-19-scenes-2026-10-21-verified-connection/ # 2 failed PNG calls
runs/gemini-bsp-19-scenes-2026-10-21-jpeg90/
  comparison.json            # frozen protocol, raw coarse scores, capabilities
  source-manifest.json       # original acquisition metadata snapshot
  ground-truth.json           # frozen targets, never model inputs
  visual-review.json          # assistant's per-scene visual judgments
  evaluated-results.json      # checked outcomes and final aggregates
  review.html                # scene markers, candidates, target context, reasons
  transport-inputs/*.jpg      # exact transmitted search images, named by SHA-256
  SCENE/events.jsonl          # timestamped live search trace
  SCENE/results.json         # full predictions, usage, settings and crop bounds
```

`experiments.bsp_scenes` runs the paid protocol; `experiments.review_bsp_scenes`
builds the offline visual audit. Root-level coarse summaries conservatively count
only wholly error-free searches as evaluable. The final visual audit additionally
uses target-path evidence to distinguish seven verified successes, six misses and
six unresolved searches; it does not relabel provider failures as negative answers.

## Interpretation and checks

This establishes a limitation of **this model-plus-BSP configuration on this
collection**, not a general ranking of vision models. One search per scene does
not measure repeatability. Scans differ in darkness, crowd density and character
size. The prompt and JPEG encoding differ from the earlier beach experiment, and
public-image exposure during model training is unknown.

The immediate algorithmic weakness is relying on one coarse negative to eliminate
an entire branch. A follow-up could test overlapping smaller grid cells or require
independent checks before pruning, while keeping first-run outcomes intact.

Verification: **102 tests passed on both Python 3.11 and 3.14**, repository Ruff
checks and `git diff --check`. All 97 successful transmitted JPEGs were checked
against their saved hashes and crop dimensions; every response reported Gemini 4
Argon / Google. The local review was opened and inspected through the native
in-app browser. No dependencies, credentials or app defaults were changed for this test.
