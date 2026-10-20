# Gemini full-scene searches with original image detail — 2026-10-20

**Gemini found the confirmed Waldo in all five grid searches and all five binary
searches.** Each strategy also returned one extra candidate in two runs. These
results support repeatable detection on this scene, with visual review still
needed to reject close lookalikes.

The app and CLI now explicitly request `original` detail for search crops and
`auto` for the separate appearance reference. Saved results, session exports,
history and crop review distinguish these requests from historical implicit
`auto` runs. The prompt and search algorithm were unchanged.

## Time, cost and reliability

| Metric | 3 × 3 full grid | Binary, depth four |
| --- | ---: | ---: |
| Runs returning the correct region | 5/5 | 5/5 |
| Runs returning only the correct candidate | 3/5 | 3/5 |
| Extra final candidates across five runs | 2 | 2 |
| Average time until the correct candidate | 10.84 s | 56.02 s |
| Average time until all in-flight requests finish | 48.55 s | 72.80 s |
| Median completion time | 52.94 s | 70.16 s |
| Completion-time range | 33.31–62.21 s | 55.25–102.09 s |
| Average calls per search | 9 | 8.8 |
| Average reported cost per search | $0.16788146 | $0.13383056 |
| Total calls | 45 | 44 |
| Total reported cost | $0.8394073 | $0.6691528 |

Binary was **49.95% slower to finish and 20.28% cheaper on average**. The grid
also produced the useful correct candidate much sooner because its nine regions
start together; binary waits for each parent before testing its descendants.
Completion time includes slow sibling calls already in flight when a terminal
candidate is found. Median times and individual runs are included because that
tail latency varied substantially.

There were **89 calls, 89 distinct generation IDs, no errors or retries**, and
reported costs for every call: **$1.5085601 total**. Cached input billing and
variable output/reasoning lengths affect these measured costs; fewer calls do
not by themselves explain the cost difference.

## Matched setup and grounding

- One normalized 3000 × 1926 source image and the same separate reference PNG.
  Every run used byte-identical input and reference files. The source RGB pixel
  SHA-256 remained `7eb348bcac98a3b8b36895dd587474c5b0f07d462ef7792c14b8e5edb0271c96`.
- Requested and returned model: `google/gemini-4-argon`; provider: Google in all
  89 responses. The existing Infisical Agent Vault credential workflow was used.
- Existing occlusion-aware presence prompt `waldo-reference-occlusion-v2`, high
  reasoning, 8192 output tokens, structured JSON, timeout 180 seconds, threshold
  0.7, overlap 8%, concurrency cap 32, request cap 32 per search.
- Grid: nine regions. Binary: longest-side splitting, maximum depth four,
  minimum size 64, negative pruning enabled, and stop new submissions after the
  first confident terminal candidate. In-flight calls finish. Negative-branch
  exploration and continuing after the first candidate were disabled.
- Five alternating grid/binary pairs, one complete search at a time, so the
  strategies did not compete for request slots. All nine grid requests started
  before the first completion in every repetition.

Only search-image detail changed from the earlier app searches. In particular,
these full-scene runs use the app's presence prompt, **not the bounding-box
prompt from the preceding controlled crop experiment**. OpenRouter's exact
provider-side interpretation of `original` remains provider-dependent, as
discussed in the [image-detail test](2026-10-20-image-detail.md).

The correct grid region was always `r1c1`, padded bounds
`[920, 591, 2080, 1335]` (1160 × 744). The correct binary terminal region was
always `root.1.0.0.1`, padded bounds `[1440, 442, 2310, 1002]` (870 × 560).
All ten correct answers had confidence 0.99 and described the real character
behind the right end of the green-and-white windbreak. I checked their described
locations against the source and the existing independently mapped point
`[1856, 754]` in the user-confirmed center region. Region containment alone was
not treated as sufficient evidence of correct grounding.

No binary repetition pruned a target-containing branch. In particular,
`root.1.0`, the exact input previously rejected at 98% confidence, was retained
on every traversal. The five target paths reached the correct terminal region.

## Remaining false alarms

Grid repetitions 3 and 4 also marked `r1c2` positive, at 98% and 96% confidence.
Binary repetitions 2 and 5 also returned terminal `root.1.0.1.1`, at 98%.
Their descriptions point to the same red-and-white-clad character above the
striped umbrella near source coordinate `(2310, 780)`, outside the confirmed
Waldo location. The region bounds and a magnified view were checked.

This is a very close lookalike with a striped bobble hat, glasses and striped
shirt. Its appearance resembles Wenda in the publisher's
[official character sheets](https://waldo.candlewick.com/pdf/WaldoCharacterSheets20.pdf);
that identity is a visual inference, not independently verified for this exact
scene. The false-positive label here means it is not the previously confirmed
Waldo target, rather than that the model invented every reported visual feature.

Binary also made three off-target positive **internal** branch decisions, which
caused extra exploration; these are separate from its two extra final candidates.
In repetition 4, one such internal response finished after early stopping and
left two children untested. Thus equal final false-candidate counts do not imply
equal specificity or exhaustive coverage. Binary and grid test different crops
and return different-sized terminal regions.

## Individual runs

Each row found Waldo. “Extra” counts off-target final candidates.

| Strategy | Repeat | Calls | Completion | Cost | Extra | Run ID |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Grid | 1 | 9 | 62.2076 s | $0.2065940 | 0 | `web-a2402119b6f84cb7b5832f63806fe828` |
| Binary | 1 | 8 | 55.2544 s | $0.1357360 | 0 | `web-5adbefca94114f68b8decb5fe58ffb4f` |
| Grid | 2 | 9 | 52.9373 s | $0.1559120 | 0 | `web-e899e43412994d5bb04377560620ee00` |
| Binary | 2 | 10 | 70.1572 s | $0.1530585 | 1 | `web-29ceed6169d64fb2a4889dbd17066fcb` |
| Grid | 3 | 9 | 33.3140 s | $0.1514120 | 1 | `web-115a14a29b6e4fc080c43ef1612acd65` |
| Binary | 3 | 8 | 102.0917 s | $0.1320123 | 0 | `web-d7f480014b1c40cc966943afa6ed6635` |
| Grid | 4 | 9 | 40.5854 s | $0.1549220 | 1 | `web-d6d3bb1d37fe41bcb38408f47c2af2d2` |
| Binary | 4 | 8 | 74.8117 s | $0.1030605 | 0 | `web-b13f31fc0d1a4e2eaa8dd9a10f096de2` |
| Grid | 5 | 9 | 53.7200 s | $0.1705673 | 0 | `web-a5aabe39e0ee4b4fa9104930fdbb0233` |
| Binary | 5 | 10 | 61.7098 s | $0.1452855 | 1 | `web-9434e39cbf784872a88b463661e3854a` |

## Earlier default-detail context

The [previous strategy comparison](2026-10-20-binary-vs-grid.md) recorded one
Gemini run per strategy at implicit `auto` detail:

| Historical Gemini search | Outcome | Calls | Completion | Cost |
| --- | --- | ---: | ---: | ---: |
| Grid, auto | Correct candidate only | 9 | 41.5321 s | $0.167228 |
| Binary, auto | False-negative pruning; no terminal candidate | 4 | 46.6728 s | $0.079372 |

Original detail now succeeds repeatedly on the binary target path, whereas the
historical binary run stopped unsuccessfully after four calls. Those older runs
included GPT concurrently and were not repeated default-detail controls for this
new experiment; their timing and cost are context, not a controlled effect-size
estimate for changing detail.

## Verification and saved evidence

The app remains at `http://127.0.0.1:63239/`. Its history contains all ten live
searches. After every search completed, the existing ground-truth point was added
to each run as a reference marker. Every prediction-file hash stayed unchanged.
No marker, target coordinate, selected region or review was sent to Gemini.

Local evidence is under `runs/original-detail-searches-2026-10-20/`:

- `comparison.json`: the ten searches, settings and aggregate metrics.
- `verification.json`: exact source/reference/crop checks, unique generation
  counts, per-run event timings and pre-annotation reviews.
- `post-run-markers.json`: marker provenance and unchanged prediction checks.
- `binary-final-verified.png` and `distractor-zoom.png`: browser and grounding
  review evidence. Each original `web-*` folder retains exact crops and events.
- `masks-running-verified.png` and `masks-completed-verified.png`: the subsequent
  UI masks, verified through the native in-app browser. Yellow running masks
  were checked with a recorded replay, adding no paid model calls; a saved
  two-model uncertain case verified blue consideration masks even when the
  other model rejected the region. Red discarded and green candidate masks
  were checked on the completed binary run. The existing 443 × 853 viewport
  displayed the entire source without page scrolling.

Python 3.14 and 3.11 passed all 83 tests. Ruff lint/format checks, JavaScript
syntax checking, and whitespace checks passed. The UI changes followed the live
search experiment and did not alter its model inputs, predictions or metrics.

The scene-specific `experiments/original_searches.py` repeats searches through
the same local app API. It requires `--live` for paid searches and a first grid
run started in the app. Completed attempts are retained on resume; the helper
does not retry errors. Existing run assets stay ignored by Git.

These are repeated searches on **one scene**, with a known target and a small
set of recurring distractors. They establish repeatability here, not performance
across independent images. Grid is the faster tested option; binary offers a
smaller final region and lower measured cost while retaining false positives.
