# Native OpenAI and image-generation controls — 2026-10-21

Direct OpenAI GPT-6.1 Sol reproduced the same false-positive pattern as the saved
OpenRouter comparison. GPT Image 2.5 Sunburst also marked every negative crop,
and several generated images changed the very character being identified.
Neither control establishes a reliable Waldo detector on these crops.

## Results

Each arm has 15 trials: five repetitions of one Waldo crop and five each of two
negative crops. All calls succeeded with usable output. The OpenRouter rows were
reused from the previous experiment; 30 native calls were newly billed.

| Arm | Correct Waldo location | Correct negative decisions | False positives on negatives | Correct outcomes | Median request time | Cost for 15 trials |
| --- | --- | --- | --- | --- | --- | --- |
| Sol through OpenRouter, saved | 5/5 | 0/10 | 10/10 | 5/15 | 45.78 s | $0.32655 reported |
| Sol directly through OpenAI | 5/5 | 0/10 | 10/10 | 5/15 | 34.83 s | $0.35329 estimated |
| Image 2.5 Sunburst directly | 4/5* | 0/10 | 10/10 | 4/15 location-only* | 39.12 s | $1.03505 estimated |

*The image score tests where the output circle lands relative to the original
source ground truth. It does **not** certify that the source character was preserved.
Assistant visual review found clear material character changes in 7/15 outputs.
Three of those were positive trials, including two whose circles overlapped the
correct location. The other eight outputs are not certified pixel-unchanged.
The original-source crops, not the modified figures, determine ground truth.

New total cost estimate: **$1.3883334**. This excludes the previously billed
OpenRouter baseline and includes every native trial. Full inference-phase elapsed
time: **144.29 seconds**, with two parallel positive probes followed by the remaining
28 calls under a global concurrency limit of 15. Per-arm latency includes provider
queueing and, for images, response-image transfer; it excludes offline review.
Sol mean latency was 43.29 s and Sunburst mean latency 39.15 s. Native timings were
not measured simultaneously with the saved OpenRouter baseline.

## Direct Sol control

This control intentionally keeps **Chat Completions** to isolate the routing change.
It does not also change to Responses or add tools. Requests go to
`https://api.openai.com/v1/chat/completions` without OpenRouter or its Infisical
proxy (`trust_env=False`, ordinary TLS verification). No generation retries.

The messages, image labels, exact PNG bytes and localization JSON schema match the
completed named-distractor experiment. Search detail is native `original`, all
three appearance references use `auto`, reasoning is `high`, output cap is 8192
(`max_completion_tokens` natively), and service tier is explicitly `default`.
No unsupported temperature is sent. Native `reasoning_effort=high` replaces the
OpenRouter reasoning wrapper; OpenRouter provider/debug parameters are omitted.
Streaming preserves comparable text-response timing. Requested and returned model
IDs are `gpt-6.1-sol`, with 15 unique native generation IDs and request IDs.

The native API accepted `original`. Every native request reported **4867 prompt
tokens**, exactly matching the saved OpenRouter condition. This supports the input
mapping being comparable, though token-count equality does not prove identical
internal image representations. All native positives correctly localized Waldo;
all ten negatives falsely returned present, at confidence **0.90–0.95**. Every
response finished successfully without hitting the output cap.

This result substantially weakens the hypothesis that OpenRouter alone caused
Sol's false positives. It does not rule out prompt effects, task-specific model
limitations, or a different result with another endpoint/tool-assisted workflow.

## Image 2.5 control and visual integrity

Model: `gpt-image-2.5-sunburst`, requested directly through native
`POST https://api.openai.com/v1/images/edits`. The returned Images envelopes did
not echo a model identifier; the requested model and native request IDs are saved.
No mainline language model rewrote the image prompt or chose the detection first.
This uses a native API evaluation harness, rather than the built-in image tool,
so requested model, settings, latency and returned usage can be recorded.

Each call has four exact inputs: search crop first, then standalone Waldo, Wenda
and Odlaw references. These are the same saved files as Sol's condition, with
roles explicitly described by index. `quality=high`, `size=1616x1040`, `n=1`, PNG
output; no mask, resizing of the supplied input, or scene-derived target hint.
The four-pixel output-width difference meets the API's multiple-of-16 constraint;
coordinate scoring scales by actual output dimensions. Image inputs do not take
Sol's `detail` parameter; the two APIs do not promise equal vision token budgets.

The complete saved circle prompt:

```text
Input image 1 is the SEARCH CROP and the only image to edit/search.
Input image 2 is the Waldo REFERENCE, appearance only.
Input image 3 is the Wenda DISTRACTOR REFERENCE, NOT Waldo.
Input image 4 is the Odlaw DISTRACTOR REFERENCE, NOT Waldo.
Never count or output characters from the reference images as search detections.

Waldo wears a red-and-white horizontally striped shirt, a white bobble hat with a red
band and pom-pom, round glasses, and blue trousers. His pose and clothing visibility
can differ from the reference. He is often partially occluded, including at crop edges.
Do not require every identifying feature to be visible. Stripes alone are insufficient.
Do not confuse Waldo with Wenda or Odlaw. Wenda shares the red-and-white shirt, hat
and glasses; longer dark hair, a blue skirt and striped tights distinguish her when
visible. Odlaw wears yellow-and-black stripes, dark glasses, moustache and dark trousers.
Use only visible evidence; do not invent hidden hair, a skirt, trousers or colours.
Carrying bags or other gear does not by itself exclude Waldo.
Waldo may be absent. Do not assume every crop contains him. If identity is ambiguous,
do not circle a merely plausible striped person.

Return ONLY image 1, preserving its entire composition, characters, colours and geometry.
If Waldo is present, add exactly one thin, bright magenta (#FF00FF) ellipse tightly
surrounding the visible Waldo character. Make the ellipse approximately 5 pixels thick.
If Waldo is absent or cannot be identified reliably, leave the crop unmarked.
Do not add text, a legend, arrows, panels, reference examples, or any other marks.
Do not create, remove, move, enlarge or redraw a character to make a detection correct.
```

All fifteen images contained one magenta ellipse. Saturated-magenta connected
components proposed bounds; the assistant reviewed every full scene and a local
original/output pair before accepting the proposed ellipse. The circle's bounding
box is mapped to original crop coordinates. A positive location hit requires the
frozen target point inside plus IoU >= 0.25 with the frozen rectangle, the same
criterion used for Sol's boxes. Four positive circles pass (IoU 0.717, 0.683,
0.732, 0.390); positive trial 1 misses completely. All negative circles are false.
Image outputs provide no confidence score or separate absent/uncertain distinction.

Visual review observed:

- Positive #1: a clean Waldo is drawn at a wrong location near an umbrella, replacing
  another beachgoer, then circled. The real Waldo remains elsewhere.
- Positive #2 and #5: the circle overlaps the real location, but the original
  gear-carrying Waldo is simplified/redrawn. These count as location hits only.
- Left negative #1 and #3: other beachgoers are redrawn as clean Waldo figures.
- Bottom negative #2 and #3: a person in a blue top and red skirt is replaced by a
  clean striped Waldo, then circled. These are invented targets in negative inputs.
- Other negative trials select striped or red-capped people despite Waldo being
  absent. Positive #3 and #4 preserve the recognizable gear-carrying character
  while circling its correct location, although fine rendering details change.

These are observed output differences, not evidence of an internal model mechanism.
Image-generation/editing quality therefore cannot substitute for checking whether
an annotation refers to a character in the **original** input.

## Inputs, costs and limitations

Source: local 3000 x 1926 beach image, SHA-256
`e599391125592f8fa4460340eef5c4dee65f2b198bdb667ab43d22a030019d14`.
Three exact 1620 x 1040 crops: positive `[1380,0,3000,1040]`, negative-left
`[0,0,1620,1040]`, negative-bottom `[1380,886,3000,1926]`. Frozen truth rectangle
`[1818,703,1896,801]`, point `[1856,754]`; neither supplied to models. Exact
annotations are assistant-verified against the user-confirmed character.
Reference files and hashes come from the preceding
[named-distractor experiment](2026-10-21-distractor-references.md).

Native API usage contains tokens rather than an invoiced dollar amount. Estimates
use the fetched [OpenAI Standard pricing](https://developers.openai.com/api/docs/pricing):
Sol $2/M uncached input, $0.10/M cached input, $10/M output; Sunburst $5/M text
input, $8/M image input, $30/M image output. Sol reported cached input is included
at its documented rate. Images API caching discounts are not applied; the pricing
page limits GPT Image 2.5 cached rates to Responses image generation. Taxes,
account credits, billing adjustments and regional premiums are not inferred.

Each Sunburst call reported 435 text input tokens, 3216 image input tokens and 1370
image output tokens, yielding $0.069003 per image. All token usage and calculation
settings are saved. This is a cost estimate, not an account billing audit.

Only one scene and three correlated crops were tested, with no interleaved rerun
of the OpenRouter baseline. Output formats and image processing differ between
Sol and Sunburst. The image prompt necessarily asks for a visual annotation
instead of structured JSON; its negative abstention instruction also merges absent
and uncertain. All ten negatives were marked, so that distinction cannot rescue
the observed results. This experiment does not establish shared training, shared
weights, or a general ranking of model visual capability.

The temporary user-provided key was read through a hidden terminal prompt, used
in memory only for these native commands, and discarded when the process exited.
It was not added to Infisical, repository files, environment configuration, request
metadata or exported results. No account permissions or API keys were changed.

## Local evidence and reproduction

Ignored directory: `runs/native-openai-controls-2026-10-21/` contains results and
verification JSON, original PNG inputs, fifteen unmodified generated PNG outputs,
full-scene contact sheets, local paired review figures and a comparison page.
The review switches among native Sol, saved OpenRouter Sol and native Sunburst,
with original input beside the output and green source-ground-truth overlays.
The export preserves the exact prompts, input/output hashes, request IDs, usage,
latencies, manual-review notes and 45 baseline/native observations.

```bash
# Prepare or summarize without API calls:
uv --config-file uv.toml run python -m experiments.openai_controls   --output runs/native-openai-controls-2026-10-21
# --live enables native paid calls and asks for a key with terminal echo disabled.
# Existing completed attempts are skipped; credentials are never read from files.

# Propose magenta-circle bounds and render local review assets, no API calls:
uv --config-file uv.toml run python -m experiments.review_openai_controls   runs/native-openai-controls-2026-10-21
```

Stored circle proposals are not automatically accepted as detections. Final image
scores in this run carry explicit assistant visual-review notes bound to each
output's hash. Input and baseline hashes are checked before any live requests.

Implementation checks: 95 tests passed on Python 3.14 and 3.11; Ruff and Git
whitespace checks passed. Native in-app browser testing verified the side-by-side
original/generated viewer, crop/repetition selection and visible review notes.
