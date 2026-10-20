# Initial experiment — 2026-10-20

Input: user-supplied beach illustration, 1080 × 675 pixels.
SHA-256: `fdac50a3addc9980518595a78eeecd3adfbd4c1217e8e670af6014f8133d085a`.
The image and exact local traces remain in ignored `data/` and `runs/` directories.

All requests used OpenRouter through the existing Infisical Agent Vault proxy,
with native structured outputs, temperature 0, 512 output tokens, concurrency 4,
threshold 0.7, 8% padding on every crop side and no retries or model fallbacks.
Each selected model independently evaluated its own search. Binary depth was 4;
minimum longest side was 64 pixels. Costs are provider-reported USD, and every
response in these runs supplied a cost.

| Strategy | Model | Requests | API/parse errors | Final candidates | Reported cost |
| --- | --- | ---: | ---: | ---: | ---: |
| Fixed 4×4 grid | `google/gemini-2.5-flash` | 16 | 0 | 0 | $0.00375060 |
| Fixed 4×4 grid | `openai/gpt-4.1-mini` | 16 | 0 | 0 | $0.00328960 |
| Binary, negative pruning | `google/gemini-2.5-flash` | 12 | 0 | 0 | $0.00278494 |
| Binary, negative pruning | `openai/gpt-4.1-mini` | 4 | 0 | 0 | $0.00147520 |
| Binary, explore negatives | `google/gemini-2.5-flash` | 30 | 0 | 0 | $0.00708624 |
| Binary, explore negatives | `openai/gpt-4.1-mini` | 30 | 0 | 0 | $0.00731360 |

The fixed grid used 16 calls per model. Guided binary searches allowed 24 calls
per model; neither reached that cap. The negative-exploration searches allowed
30 calls per model and exhausted the depth-4 tree. A terminal candidate requires
a `present` answer at or above the confidence threshold.

These runs demonstrate working crop dispatch, model comparisons and bounded
recursive search. They do **not** establish a verified Waldo localization or
accuracy. Earlier pilot crops produced positive model claims that disappeared
with smaller crops. Without independent human ground truth, those claims cannot
be scored as correct or incorrect. Both pruning errors and changing visual
context remain hypotheses; the no-pruning intervention did not restore a final
candidate at this depth.

All live smoke, pilot and comparison runs together made 130 API requests,
with a total reported cost of **$0.03092688**. No API or parse errors occurred.
Wall times were recorded locally; some pilot runs overlapped, so do not interpret
their timing differences as controlled speed benchmarks.

Validation: 32 offline tests passed on Python 3.11.15 and Python 3.14.5;
Ruff checks and formatting passed; wheel and source distribution built. Package
contents were inspected to exclude the beach illustration. GitHub CI has not run
until the repository is published.

Reproduce using the commands in the root README. Each output path must be new.
The next useful evaluation step is an independently annotated target and several
additional images before drawing model-accuracy conclusions.
