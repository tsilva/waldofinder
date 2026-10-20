# Repeating the confidently rejected crop — 2026-10-20

**Gemini repeated its confident false negative in 8 of 10 new calls.** The other
two calls correctly identified Waldo. Wrong answers had 97–99% self-reported
confidence and correct answers had 98–99%, so confidence did not distinguish
success from failure on this crop. A majority vote would still have rejected it.

GPT correctly identified the location in all nine usable responses; one further
attempt returned an unusable answer. That error was not counted as absent and
was not retried.

## Exact input and controls

The input was Gemini's incorrectly pruned `root.1.0` crop from binary run
`web-3f839032a69c4275a0f14ed32430280e`: source bounds
`[1380, 0, 3000, 1040]`, **1620 × 1040 pixels**. Waldo is visibly present above
the green-and-white windbreak, around 29% across and 73% down. The same crop was
originally supplied to both models. PNG SHA-256:

`49b18d7ee39560c15c86212c90b29cf99c2e49d13343b6b132a71ebbbac4336c`

Ten new requests per model used byte-identical crop and reference images, the
unchanged `waldo-reference-occlusion-v2` prompt, high reasoning, an 8,192-token
response cap, a 180-second transport timeout and structured JSON. Every valid
response recorded settings identical to that model's original binary request.
Returned models and providers remained `google/gemini-4-argon` / Google and
`openai/gpt-6.1-sol` / OpenAI. Gemini requests retained temperature zero; GPT's
advertised parameter set did not include temperature, as in the baseline.

These were **separate fresh single-turn API requests**, not multiple copies of
the crop inside one prompt. No earlier answers, expected verdict, coordinates,
replicate numbers or review labels were sent to the models. All 20 requests
started before the first completed. Replicate IDs identify submitted jobs; rows
below are not completion order. Each valid response had a distinct generation ID.
Separate calls do not imply statistically independent errors, especially with
fixed input and decoding settings.

## Answers

The original trigger response was Gemini absent 98%; GPT's original response on
this crop was present 99% with a correct windbreak location. Neither baseline
response is included in the following ten new attempts per model.

| New attempt | Gemini | GPT |
| --- | --- | --- |
| 1 | Absent 98% — wrong | Present 99% |
| 2 | Present 99% | Present 98% |
| 3 | Absent 97% — wrong | Unusable answer |
| 4 | Absent 98% — wrong | Present 99% |
| 5 | Absent 98% — wrong | Present 99% |
| 6 | Absent 99% — wrong | Present 99% |
| 7 | Present 98% | Present 98% |
| 8 | Absent 99% — wrong | Present 98% |
| 9 | Absent 98% — wrong | Present 98% |
| 10 | Absent 98% — wrong | Present 99% |

Gemini's two positive descriptions both match the actual position above/behind
the green-and-white windbreak and left of the red-and-white changing hut. One
also specifies approximately 29% across and 70% down. Its negatives instead
describe striped distractors and claim no character has the required identifying
features. The nine usable GPT responses consistently describe the lower-left
target beside that windbreak, rather than merely asserting presence somewhere.

GPT attempt 3 failed answer validation, with no usable finish reason or usage
returned. The redacted category is “invalid, refused or truncated”; the evidence
does not distinguish those causes, so it is not specifically called a truncation
or refusal. It remains a separate error with no confidence score.

## What repetition establishes here

The original Gemini miss was not a unique anomaly. It can repeatedly reject a
crop that contains Waldo while expressing almost the same confidence when it
occasionally recognizes him. Keeping temperature zero did not eliminate observed
response variation; the experiment does not establish its backend cause.

Majority voting over these ten answers would preserve the false negative
(eight absent versus two present). Retrying until a positive appears would give
a different result on this target crop, but this experiment contains no repeated
negative control and does not establish that policy's false-positive behavior.
GPT's success here does not remove its earlier false positives elsewhere.

This was a deliberately selected failure case from one image. The observed
8/10 error frequency describes these requests, not Gemini's general detection
accuracy or a population calibration estimate. Confidence is a model-reported
judgment, not an independently measured probability of correctness.

## Artifacts and reproduction

The request phase took **39.5 seconds**. Provider-reported cost was
**$0.249179**: Gemini $0.1992927 and GPT $0.0498863. The unusable GPT call returned
no usage/cost, so the total is incomplete and that call may have incurred an
unreported charge. There were 20 attempts, 19 usable responses and no retries.

Local `runs/repeated-false-negative-2026-10-20/` contains exact `crop.png` and
`reference.png`, the baseline observations, full prompt, request settings,
individual responses, usage, generation IDs and summary in `results.json`, plus
`answers.csv`. These files remain ignored by Git. Earlier app runs and predictions
were not modified.

`experiments/repeat_crop.py` defaults to offline preparation and refuses existing
outputs or a changed prompt. `--expected` is review metadata only, never part of
the inference prompt. To reproduce the 20-call test:

```bash
uv --config-file uv.toml run python -m experiments.repeat_crop \
  --source-run runs/web-3f839032a69c4275a0f14ed32430280e \
  --region root.1.0 --repeats 10 --expected present \
  --output runs/repeated-crop-repeat --live
```

Omit `--live` to prepare the inputs without API calls. Validation checked exact
crop/reference equality to the original binary run, PNG re-encoding identity,
all 20 unique model/replicate bindings, 19 unique valid generation IDs, recorded
request settings, returned model IDs and concurrent dispatch. Ruff checks pass.
