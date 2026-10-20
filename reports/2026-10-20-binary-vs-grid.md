# Binary partitioning versus full grid — 2026-10-20

**The full grid was more useful on this image.** Gemini's binary search initially
recognized Waldo, then pruned his branch after an incorrect negative and returned
no terminal candidate. GPT's binary search returned the correct terminal region
and four false positives, using more than twice the requests of its grid search.

## Results, elapsed time and reported cost

Times below are per-model search completion times, including dependency waits and
all requests already in flight when early stopping was triggered. Both models
ran concurrently within each strategy; their times should not be added.

| Model | Strategy | Final result | Calls | Time | Reported cost |
| --- | --- | --- | ---: | ---: | ---: |
| Gemini 4 Argon | 3 × 3 grid | One correct candidate | 9 | 41.5 s | $0.167228 |
| Gemini 4 Argon | Binary | Coarse match, then false-negative pruning; no terminal candidate | 4 | 46.7 s | $0.079372 |
| GPT-6.1 Sol | 3 × 3 grid | One correct candidate + five false positives | 9 | 93.1 s | $0.1907715 |
| GPT-6.1 Sol | Binary | One correct candidate + four false positives | 20 | 142.7 s | $0.3047875 |

Gemini's binary run cost **52.5% less**, but did not finish with a detection and
took **12.4% longer**. GPT's binary run cost **59.8% more** and took **53.4% longer**.
Its smaller false-positive count is not evidence of an accuracy improvement:
the two strategies tested different regions and binary left branches untested.

Together, binary made **24 calls**, took **142.7 seconds** and reported
**$0.3841595**, versus grid's **18 calls**, **93.1 seconds** and **$0.3579995**.
All 24 binary responses were valid; there were no errors or retries, and cost
and usage were returned for every call.

## Matched setup and stopping rules

- Grid run: `web-b4872a7fd7d14060ac51271fa2cf2d99`.
- Binary run: `web-3f839032a69c4275a0f14ed32430280e`.
- Byte-identical normalized 3000 × 1926 image and appearance reference; identical
  prompt, high reasoning, 8,192-token response cap, 180-second timeout, structured
  output, 8% padding, 0.7 threshold and shared concurrency limit of 32.
- Same requested and returned model IDs: `google/gemini-4-argon` and
  `openai/gpt-6.1-sol`. Ground-truth location and reviews were withheld.
- Binary uses the app defaults: split the longest side, maximum depth four,
  minimum size 64, and a 32-call cap per model. Confident negatives are pruned.
  Positive or uncertain nonterminal regions are split. The first terminal
  positive stops new submissions for that model; existing requests still finish
  and can contribute additional candidates. Negative-branch exploration and
  continuing after the first terminal candidate were disabled.

The grid's nine regions cover the scene directly. A complete depth-four binary
tree could make 30 calls per model. Its terminal cells are approximately
750 × 481–482 unpadded pixels, smaller than the grid's 1000 × 642 cells. This is
a comparison of the existing strategies with default binary stopping rules,
not a comparison at exactly equal terminal-region area.

## Gemini: a false negative removed the correct branch

The initial left half (`root.0`) was correctly rejected. In the right half
(`root.1`), Gemini answered present at 99% confidence and described the actual
target near 30% across and 38% down, above the green-and-white windbreak.

After splitting that half, it answered **absent at 98%** for `root.1.0`, whose
padded bounds were `[1380, 0, 3000, 1040]`. The exact input visibly contains
Waldo at the independently checked point (1856, 754). This confident false
negative pruned the branch; the other child was also negative, leaving no
terminal candidate. The correct depth-four path would have been:

```text
root.1             present 99%, split
  root.1.0         absent 98%, pruned incorrectly
    root.1.0.0     never requested by Gemini
      root.1.0.0.1 never requested by Gemini; contains the target
```

The initial coarse recognition therefore did not survive refinement. This is a
concrete example of how negative pruning can turn one model error into a failed
search, despite the same model succeeding on a full grid of the same source.

## GPT: more exploration and an early false terminal match

GPT marked both initial halves positive and explored several branches. Its first
terminal candidate was the false-positive `root.1.1.0.1`, about **86.5 seconds**
after search start. The true terminal input was already in flight, so it still
completed and became a candidate at approximately **91.5 seconds**. New calls
were not submitted after early stopping, but existing calls continued until
142.7 seconds. Eight queued regions remained untested.

The final candidates were:

- `root.1.0.0.1`: correct; padded bounds `[1440, 442, 2310, 1002]`, 870 × 560
  pixels. Its description places Waldo behind the central green-and-white
  windbreak, consistent with the target.
- `root.1.1.0.1`, `root.1.1.0.0`, `root.1.0.1.0`, `root.1.0.1.1`: visually checked
  false positives outside the target area.

For comparison, correct grid candidates arrived at about **10.0 seconds** for
Gemini and **26.2 seconds** for GPT. These are event timestamps from search start,
including crop preparation/dispatch, rather than just provider latency. Binary
requires parent decisions before descendants can run, so a high concurrency cap
cannot remove the sequential dependency along each path.

## Review, artifacts and limits

After completion, the target marker and seven independent reviews were saved:
Gemini's correct coarse positive and false-negative child, plus GPT's five
terminal candidates. The prediction-file hash was unchanged by review updates.
All 24 exact PNG inputs were checked against their source bounds and all response
settings, reference bindings and returned model IDs were verified. Byte identity
of image, reference and prompt against the grid run was also checked.

The app is left on the completed binary run with the ground-truth marker. Its
history retains the full-grid comparison. An upward arrow on a binary-region
badge indicates a decision inherited from a parent, not an additional model call.
Gemini's false-negative parent can be inspected by clicking its inherited status
or selecting `root.1.0` in the review dialog.

The machine-readable comparison is local
`runs/strategy-comparison-2026-10-20.json`. Exact inputs, events, predictions,
reviews and ground-truth provenance remain in the two run folders, ignored by
Git. No inference or stopping behavior was changed for this experiment.

This is one run per strategy on one image. Timing, cached input usage and generated
tokens vary between calls. Here, the grid is the stronger tested choice for
Gemini; binary's lower Gemini bill came with a failed terminal search. The result
does not establish a universal strategy ranking.
