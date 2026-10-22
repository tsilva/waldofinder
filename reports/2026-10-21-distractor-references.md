# Named visual distractor crop test — 2026-10-21

Adding Wenda and Odlaw examples plus explicit exclusion instructions produced a
perfect result for Gemini on this small test, but did not resolve GPT or Sonnet
false positives. This is a repeated test of three fixed crops from one scene,
not a general accuracy estimate.

## Results

Each model received five repetitions of the positive crop and five each of two
negative crops (15 calls/model). Correct positives must localize the actual Waldo;
correct negatives must return `absent`. `Uncertain` is not a correct absence.

| Model | Correct outcomes, before → after | Correct Waldo boxes | Negative false positives | Median seconds, before → after | Cost for 15 calls, before → after |
| --- | --- | --- | --- | --- | --- |
| Gemini 4 Argon | 14/15 → 15/15 | 5/5 → 5/5 | 1/10 → 0/10 | 30.57 → 27.06 | $0.36407 → $0.43651 |
| GPT-6.1 Sol | 5/15 → 5/15 | 5/5 → 5/5 | 10/10 → 10/10 | 41.55 → 45.78 | $0.21798 → $0.32655 |
| Claude Sonnet 5.5 | 4/15 → 4/15 | 4/5 → 4/5 | 9/10 → 10/10 | 13.61 → 10.44 | $0.19468 → $0.26959 |

All 45 new calls returned usable responses, successful finishes, fresh generation
IDs and reported costs. New total: **$1.0326508**. No automatic retries. The earlier
45 baseline calls cost $0.7767343 and were reused, not billed again.

At the app candidate threshold of 0.7, the new results are:

| Model | Correct positive candidates | Negative false candidates |
| --- | --- | --- |
| Gemini 4 Argon | 5/5 | 0/10 |
| GPT-6.1 Sol | 5/5 | 10/10 |
| Claude Sonnet 5.5 | 2/5 | 5/10 |

Sonnet changed from 3/5 to 2/5 correct positive candidates at this threshold, while
retaining 5/10 false candidates. Its unthresholded positive localization stayed
4/5. Its negatives changed from nine `present` and one `uncertain` to ten `present`.
GPT continued returning confident false positives (0.91–0.97) on all ten negative
trials. Gemini returned `absent` for all ten.

## What still went wrong

Sonnet positive replicate 5 boxed the Wenda-like figure above the red-and-white
umbrella instead of the actual gear-carrying Waldo. Its explanation treated the
absence of a visible skirt or striped tights as evidence against Wenda, despite
the prompt explicitly forbidding that inference from hidden features.

On the left negative crop, GPT and Sonnet generally selected a red-and-white
striped beachgoer beside the yellow-and-black Odlaw; occasional repetitions chose
another figure at the crop edge. On the bottom negative crop, both repeatedly
selected the same small striped child. Teaching Odlaw’s appearance does not by
itself distinguish every other striped person from Waldo. These are model output
and visual-review observations; they do not establish a particular internal cause.

## Matched inputs and protocol

- Search source: local 3000 × 1926 `data/beach-high-resolution.jpg`; source hash
  `e599391125592f8fa4460340eef5c4dee65f2b198bdb667ab43d22a030019d14`.
- Exact original crop PNG bytes reused, each 1620 × 1040: positive
  `[1380,0,3000,1040]`, negative-left `[0,0,1620,1040]`, negative-bottom
  `[1380,886,3000,1926]`. No scene-derived distractor exemplar was supplied.
- Frozen ground-truth box `[1818,703,1896,801]`, point `[1856,754]`. The user
  confirmed the central character; the assistant annotated exact bounds. Neither
  bounds nor point nor labels were sent to models. A correct box contains the point
  and has IoU ≥ 0.25. Every new correct box also exceeds IoU 0.5.
- Original Waldo reference bytes unchanged. Added independent publisher Wenda and
  Odlaw illustrations, extracted from PDF pages 3 and 5; sources, extraction
  command and hashes are in [data/README.md](../data/README.md).
- Four labeled images: Waldo reference, Wenda distractor, Odlaw distractor, then
  search crop. Only the final crop counts as a detection. Reference detail `auto`,
  search detail `original`.
- Prompt `waldo-distractor-occlusion-v3` explicitly separates identities, permits
  partial occlusion, forbids invented hidden features, and requests uncertainty
  when identity cannot be resolved. It also states that carrying gear alone does
  not exclude Waldo. Localization schema and coordinate convention unchanged.
- Requested reasoning `high`, output cap 8192, timeout 180 seconds, temperature 0
  only when advertised by the model. Adaptive reasoning need not use identical
  thinking budgets. Streaming with structured JSON and no fallback.
- Providers pinned to Google, OpenAI and Anthropic respectively. Returned model
  IDs exactly match `google/gemini-4-argon`, `openai/gpt-6.1-sol` and
  `anthropic/claude-sonnet-5.5`; catalog capabilities saved.
- Three parallel positive probes counted as replicate 1, then the remaining 42
  calls submitted in shuffled order with a global concurrency limit of 32. Total
  inference-phase elapsed time was 169.86 seconds, excluding preparation/rendering.
  The longest single call took 137.54 seconds. Latency is per request, including
  any provider queueing; do not add model medians to estimate parallel wall time.
- Median input tokens increased: Gemini 4100 → 6529, GPT 3257 → 4867, Sonnet
  4051 → 5938. Token counts are provider-specific. Actual reported cost includes
  reference overhead, model output and any reported caching; it is not a price quote.

## Limitations

Before/after trials were not interleaved: Gemini/GPT baselines and the completed
Sonnet baseline were saved on October 20; new trials ran October 21. Provider load,
routing internals and stochasticity can affect timing and answers. The test changes
both visual examples and prompt text, so it does not isolate their individual
contributions. A change of one result in five repeats is weak evidence of a durable
improvement. Perfect results on these crops do not establish reliability on new
images or full-scene searches. No new full-grid/binary calls were made.

OpenRouter accepted `original`, but none of the 45 streamed replies included the
requested upstream debug echo. Native provider resolution forwarding remains
unverified; `original` is the requested OpenRouter setting, not proof of identical
pixel budgets across models.

The first Sonnet baseline attempts in `runs/sonnet-original-detail-2026-10-20/`
failed at local proxy TLS verification and produced no usable generations/usage.
They are excluded from baseline accuracy, latency and reported cost. The existing
proxy was refreshed with certificate verification retained; the successful baseline
is the separate `-verified-tls` folder.

## Saved evidence and app changes

Local ignored artifacts: `runs/distractor-references-2026-10-21/` contains
`results.json`, `verification.json`, the six exact input PNGs, contact sheets and
`review.html`. The review page switches model, crop, repeat and **Stage** (saved
baseline versus with distractor examples), with green ground truth and pink model
boxes. The export embeds exact prompts, schemas, hashes, baseline hashes, measured
usage, provider/model IDs and all 90 before/after observations.

Baseline inputs/results are preserved at `runs/image-detail-2026-10-20/` and
`runs/sonnet-original-detail-2026-10-20-verified-tls/`. The old localization prompt
is now frozen in `experiments/occlusion-v2-box-prompt.txt` so app prompt updates
cannot silently alter it. `experiments.compare_claude` reproduces the prior
three-model baseline comparison without new calls unless `--live` is requested.

New live app and CLI searches send all three appearance examples; configuration
previews the distractors and complete prompt. Both distractor PNGs are snapshotted
per run and their hashes exported; historical replays keep their original examples
and prompt. The extraction helper checks the known publisher PDF hash and refuses
to overwrite local references. See [usage](../docs/usage.md#named-distractor-experiment)
for preparation, paid-run switches and resumability.

Verification: 89 tests passed on Python 3.14 and Python 3.11; Ruff, JavaScript
syntax and Git whitespace checks passed. Native in-app browser review checked
all three reference previews, the exclusion prompt and baseline/after overlays.
