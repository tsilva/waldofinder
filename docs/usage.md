# Usage and reference

[Back to the README](../README.md). Run all commands from the repository root.

## Visual experiment lab

```bash
uv --config-file uv.toml run waldofinder serve --port auto
```

Open the printed local URL. The dashboard uses your existing Infisical connection;
credentials stay on the Python server. Every live call receives separate Waldo,
Wenda and Odlaw examples followed by the search crop. Instructions exclude the two
distractors while accounting for partial occlusion. Search crops request `original`
image detail; the three references use `auto`. It includes:

- A supplied beach scene or an uploaded PNG, JPEG or WebP (20 MB maximum).
- Fixed grids, binary partitioning, or direct full-image bounding-box inference.
  Grid/binary modes expose overlap, depth, confidence and request caps.
- A 2026-only vision catalog. The default comparison is **Gemini 4 Argon** and
  **GPT-6.1 Sol**, with **Claude Sonnet 5.5** available as a third preset. The release
  year comes from OpenRouter metadata; floating routers, batch IDs and image
  generators are excluded. Older experiment files remain preserved on disk.
- All selected models share one concurrent request pool: 32 calls by default,
  configurable from 1 to 64 in the UI. Free slots are filled immediately, including
  newly discovered binary children, without waiting for slow sibling requests.
- The entire scene fits the viewport without page scrolling. Each region shows
  every selected model's live state and decision directly on the image.
  Translucent masks cover each region: yellow while running, red when discarded,
  green for candidates, and blue for queued or uncertain regions
  still under consideration. Running calls take mask priority; a region is red
  only when all selected models reject it. Per-model badges keep individual
  decisions visible. Binary branches can differ between models; an upward arrow
  marks a decision inherited
  from a larger parent crop. Click a model's status to inspect its actual crop.
- A compact toolbar for configuration, upload, history, export and Run/Stop.
  Configuration and crop review open in dialogs, leaving the scene unobstructed.
  Choose **Present**, **Absent** or **Unsure** to save a human review independently
  of model predictions. **Mark Waldo** stores a reference pixel coordinate.
- Saved run history and JSON export containing both predictions and human reviews.
  Reloading the page reconnects to an active run.
- A post-run metrics panel comparing models against your saved crop labels,
  including confusion counts, recall/sensitivity/TPR, specificity/TNR, precision,
  accuracy and F1. Expand **Definitions & more metrics** for NPV, false positive
  and negative rates, balanced accuracy, errors, abstentions and review gaps.

### Post-benchmark metrics

The panel appears automatically after a run finishes, including partial results
for cancelled, failed or interrupted runs. Click a model name to review its
crops. **Present** and **Absent** label whether Waldo is actually in that crop;
they are not endorsements of the model's explanation. Scores update immediately,
persist through the saved reviews, reload from history and appear in JSON exports.
Clearing or changing a label recalculates scores. **Mark Waldo** alone supplies no
crop labels, and a review is scoped to its model/region pair.

The scoring unit is a completed crop decision, including BSP parent crops and
overlapping crops. Predictions of Present/Absent are eligible only at or above
the run's saved confidence threshold. Uncertain or lower-confidence answers
abstain. Failed requests, abstentions, unreviewed crops and **Unsure** reviews do
not enter the confusion matrix. The **Scored** denominator includes all completed
calls, so coverage remains visible even when scores exclude failures or abstentions.
These are metrics on the reviewed subset, not a complete-benchmark estimate.
They measure crop presence, not exact localization, correct grounding of a
description, independent samples, or scene-level search success.

| Metric | Definition |
| --- | --- |
| Sensitivity = Recall = True positive rate (TPR) | TP / (TP + FN) |
| Specificity = True negative rate (TNR) | TN / (TN + FP) |
| Precision | TP / (TP + FP) |
| Accuracy | (TP + TN) / (TP + FP + TN + FN) |
| F1 | 2TP / (2TP + FP + FN) |
| Negative predictive value (NPV) | TN / (TN + FN) |
| False positive rate | FP / (FP + TN) |
| False negative rate | FN / (FN + TP) |
| Balanced accuracy | (Sensitivity + Specificity) / 2; both must be defined |

A zero denominator is shown as **—** and exported as JSON `null`, not zero or
100%. Until eligible crops have ground-truth labels, scores remain unavailable.
Confidence is self-reported rather than calibrated.

Direct bounding-box runs use the same rates for **full-image presence** (one
decision per model). A positive presence label does not certify the proposed
coordinates. Box correctness is inspected separately against the image and any
marked reference point; containment of that point alone is not IoU or identity proof.

`GET /api/runs/RUN_ID` and the JSON export include a derived `metrics` object
with `version`, `unit`, `ground_truth`, `threshold` and per-model `counts`, `rates`
and `coverage`. Rates are fractions in `[0, 1]` or `null`; the UI shows percentages.
The review POST response retains its existing review fields and adds `metrics`.
Completion/review SSE events include updated metrics. These values are computed
from saved predictions and independent `review.json` labels; the original
prediction report is not rewritten when a reviewer changes their mind.

**Stop** prevents new calls and lets calls already in flight finish. Results
and events are saved under `runs/web-*/`; human labels and the target marker are in
`review.json`. Refreshing the page resumes the current run. A server restart marks
unfinished sessions interrupted and preserves completed observations. The server
binds to `127.0.0.1`, validates request origin and requires a per-session token for
writes. This describes the local `serve` command. The Vercel adapter below uses a
separate request lifecycle and browser-local history.

For another image, pass `--image /path/to/scene.png`. The `serve` command accepts
the same Infisical binding options as `run`, plus `--runs-dir` for a different local
experiment folder. `--reference /path/to/waldo.png` selects the appearance exemplar
(default `data/waldo-reference.jpg`). `--wenda-reference` and `--odlaw-reference`
select the distractor files (defaults `data/wenda-reference.png` and
`data/odlaw-reference.png`); their previews and the full prompt are available
under **Reference & prompt for new searches** in configuration. The UI uses bundled HTML, CSS and JavaScript with no npm build
or external frontend dependencies.

## Hosted Vercel app

The hosted app keeps the same grid, BSP and direct-box engine and prompts.
`api/index.py` exposes `HostedHandler`: a search runs inside one active streaming
POST request, not a detached serverless task. A cancellation timer stops new work
after 180 seconds; in-flight calls finish within their 90-second per-call timeout.
The Function has a 300-second duration limit. Disconnecting cancels scheduling
when the server detects it; already-sent requests may still be billed. There are
no automatic inference retries. A lost connection or page reload preserves received
observations as an interrupted run and never silently starts a replacement.

The browser saves source bytes, exact transmitted crop bytes, predictions,
configuration and manual reviews in IndexedDB. History and JSON export read that
browser's data. Storage is not shared across visitors, browsers or devices; clearing
site data deletes it. Export before clearing data. Review metrics use the same
Python calculator as local runs. A browser storage failure is shown explicitly.

Hosted uploads accept PNG/JPEG/WebP up to 3 MB and 40 megapixels. The encoded JSON
request is capped at 4.2 MB to fit the platform request limit. The source is not
automatically recompressed or resized. Limits are 32 requests/model, 8,192 tokens
and 90 seconds/call. These are request limits, not a dollar budget. Public visitors
use the production key; control the total budget on that key in OpenRouter.

Build assets are fetched from hash-pinned sources in `scripts/build_hosted.py`.
The original beach JPEG is byte-identical to the source-resolution experiment.
Wenda/Odlaw are rendered from the same pinned publisher PDF using PyMuPDF, so
rendered reference bytes differ from the local Poppler condition. Every run saves
actual reference hashes; do not present this as the old byte-identical benchmark.
Artwork stays out of Git. Run `uv --config-file uv.toml run python scripts/build_hosted.py`
to prepare assets, then `uv --config-file uv.toml run python scripts/serve_hosted.py
--port auto --fixture` for an explicit synthetic, zero-inference UI check.

Production access uses an environment-injected `OPENROUTER_API_KEY`; there is no
fallback to a developer's Agent Vault or another project's key. The key is delivered
from an isolated Infisical Production vault by the ordered GitHub Actions workflow.
See [production delivery](production-delivery.md) for pinned identities and setup.

## Quick start

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and access to OpenRouter
through [Infisical](https://infisical.com/docs/cli/overview).

```bash
uv --config-file uv.toml sync --locked
# Download the publisher's standalone character illustration for local testing.
curl --fail --location https://waldo.candlewick.com/images/waldo-wave.jpg \
  --output data/waldo-reference.jpg
# Requires Poppler's pdftoppm. Extract publisher PDF pages 3 (Wenda) and 5 (Odlaw).
curl --fail --location https://waldo.candlewick.com/pdf/WaldoCharacterSheets20.pdf \
  --output /tmp/WaldoCharacterSheets20.pdf
uv --config-file uv.toml run python -m experiments.extract_distractors /tmp/WaldoCharacterSheets20.pdf
uv --config-file uv.toml run waldofinder models
# Put your own test image at data/beach.png, or pass another local image path.
uv --config-file uv.toml run waldofinder preview data/beach.png --tiles 9 --output runs/preview
uv --config-file uv.toml run waldofinder run data/beach.png --tiles 9 \
  --model google/gemini-4-argon \
  --model openai/gpt-6.1-sol --output runs/grid
uv --config-file uv.toml run waldofinder run data/beach.png --strategy binary --max-depth 5 \
  --model google/gemini-4-argon --max-requests 32 --output runs/binary
```

The default authentication uses an existing Infisical Agent Vault proxy configured
by an owner-only `~/.config/agentbridge/.env` containing `OPENROUTER_PROXY_URL` and
`OPENROUTER_CA_FILE`. The proxy must allow OpenRouter chat-completion requests.
`--vault-config PATH` selects another config. OpenRouter's real key stays in
Infisical; proxy credentials are used only in memory. Public model discovery
connects directly to OpenRouter without credentials.

For a normal Infisical Secrets Management project, log into the Infisical CLI,
store an OpenRouter key there, and select its binding explicitly:

```bash
infisical login
uv --config-file uv.toml run waldofinder run data/beach.png --tiles 4 \
  --model google/gemini-4-argon --auth infisical \
  --infisical-project YOUR_PROJECT_UUID --infisical-env dev \
  --infisical-path / --infisical-secret OPENROUTER_API_KEY
```

Use `--infisical-domain https://eu.infisical.com` for EU Cloud. Only the named
secret is fetched, with expansion, imports and personal overrides disabled. Keys
are never exported to files. Live runs send cropped images to OpenRouter and its
selected model provider and incur API charges. Offline `preview` needs no login.

## Search strategies

**Grid:** `--tiles N` creates exactly N regions covering the whole image. Each
selected model evaluates every region independently. All models run concurrently
within the shared `--concurrency 32` default limit. With M models, a complete grid
costs N × M requests. Model wall times overlap and include waiting for pool slots. `--columns 3 --tiles 12` forces a
regular 3-column, 4-row grid. Square tile counts use square grids. Other counts use balanced rows and may be ragged.

**Binary:** split the longest side into two and classify both halves; split
positive or uncertain branches again. A confident negative prunes its branch.
The default stops after the first confident positive terminal region, at
`--max-depth 4`, `--min-size 64` (longest side), or an indivisible region. Use
`--all-candidates` to continue through all promising branches, or
`--explore-negatives` to split negative branches too. The latter checks whether
coarse-scale false negatives hide the target. Each completed answer can add new
children immediately; other pending calls continue in parallel. Early stopping
prevents further submissions for that model while its in-flight calls finish. Depth one means the initial halves;
an exhaustive depth D uses at most 2^(D+1) − 2 requests before size limits.

Both strategies use 8% padding on each side (`--overlap 0.08`) to help with boundary
cuts. Boxes use original, EXIF-corrected image pixels and half-open coordinates
`[left, top, right, bottom]`. Crops are neither rescaled nor annotated before
inference. A candidate applies to its padded crop; Waldo may be just outside the
unpadded region. Adjacent positive crops may describe the same character.

`--threshold 0.7` applies to the model's self-reported decision confidence.
Uncertain and low-confidence decisions continue through binary search; they do
not count as detections. This score is not a calibrated probability.

### Direct bounding box

Select **Configure → Mode → Direct bounding box**, or use `--strategy bbox`.
Each selected model receives the complete scene once; requests share the normal
concurrency limit. Grid size, overlap and binary refinement settings do not split
the image in this mode. The same Waldo/Wenda/Odlaw references, occlusion guidance,
`original` search detail and reasoning controls apply.

The versioned localization prompt asks the model to locate Waldo without a hint
and return `decision`, `confidence`, `reason` and `bbox`. For a present answer,
`bbox` is `[x_min, y_min, x_max, y_max]` in a normalized **0–1000** space, x left to
right and y top to bottom, relative only to the search image. Absent and uncertain
answers must use `bbox: null`. The prompt excludes printed portraits and reference
panels. It asks for a tight box around the visible character, including partial
occlusion, rather than an imagined hidden body.

Malformed, non-finite, inverted or out-of-range boxes are errors; they are not
silently clamped or counted as negatives. Valid bounds are converted to original
image pixels, rounding the left/top down and right/bottom up. Observations preserve
both normalized `bbox` and half-open `bbox_pixels` alongside usage and generation ID.

The image displays distinct box colours for each model, with matching clickable
status badges. Low-confidence present boxes are dashed proposals and do not count
as confident candidates. Absent/uncertain replies draw no box. Crop review displays
the exact full-image input and the predicted box; a human marker reports whether
the marked point lies inside or outside the returned box. The scene remains fitted
to the viewport. History, replay, annotations and JSON exports preserve the mode
and coordinates.

Full images use **JPEG quality 90, 4:4:4 chroma, without resizing**, to reduce upload
size relative to PNG. This adds lossy compression, so it is a separate input
condition from the grid/binary PNG default. The exact sent JPEG is saved as
`model-XX/crops/root.jpg`; its SHA-256 and encoding settings are recorded in
`request_settings`. Large uploads can still fail through a credential proxy.

```sh
uv --config-file uv.toml run waldofinder run data/beach-high-resolution.jpg \
  --strategy bbox --model google/gemini-4-argon --model openai/gpt-6.1-sol \
  --reasoning-effort high --max-tokens 8192 --structured --output runs/direct-box-new
```

This command makes paid calls. Use `preview IMAGE --strategy bbox --output NEW_DIR`
for a single full-image input preview without inference.

## Prompt and visual reference

Each request contains the text instruction, a labeled Waldo **REFERENCE**, separate
**DISTRACTOR REFERENCE** images for Wenda and Odlaw, then the **SEARCH CROP**.
Only the crop counts as detection evidence. These are independent publisher
illustrations, never examples extracted from the scene under test.

Prompt `waldo-distractor-occlusion-v3` explicitly excludes Wenda and Odlaw. Wenda
shares the red-and-white shirt, hat and glasses; visible long hair, skirt or striped
tights help distinguish her. Odlaw has yellow-and-black stripes, dark glasses and
a moustache. The prompt permits partial occlusion and crop-edge truncation,
forbids inventing hidden features, and requests `uncertain` when identity cannot
be resolved. Carrying gear alone is not a reason to exclude Waldo.

All three references are required for live inference. `run` and `serve` accept
`--reference PATH`, `--wenda-reference PATH` and `--odlaw-reference PATH`;
offline `preview` needs none. See the quick start for publisher downloads and
local extraction. Artwork remains ignored by Git and is not redistributed.
References are normalized to RGB PNG and copied into each run as `reference.png`,
`wenda-reference.png` and `odlaw-reference.png`. Results and session exports save
the prompt, version, dimensions, source and normalized hashes. Observations save
the hashes of all three inputs. Replays preserve original prompts and references;
old runs do not silently acquire the new examples.

New live searches in both the app and CLI use OpenRouter's `original` detail for
the search image and `auto` for each reference. Exact image detail is
provider-dependent; saved run metadata and each observation's `request_settings`
record the requested levels. History and crop review display the search detail;
older runs without this metadata retain their implicit `auto` label. Replays
preserve the original run's settings.

Reference images add input tokens and cost to each call. A before/after change
in candidate counts is not an accuracy result: visually confirm the target and
review negative crops before judging improvement. Changing both the prompt and
reference together tests their combined effect, not their individual contributions.

## Limits and model compatibility

- `--max-requests 64` caps HTTP attempts **per model**, including failed attempts.
  There are no automatic retries or cross-model fallbacks. This is a call cap,
  not a dollar cap; control provider spending limits separately.
- `--max-tokens 2048` caps reasoning plus the visible final answer, not just the
  JSON response. [OpenRouter's reasoning documentation](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens)
  explains how this shared budget applies even when reasoning text is excluded.
  For higher-effort comparisons, use the same larger cap for every
  effort level (for example `--max-tokens 8192`) and include a low-effort control.
  The dashboard permits 64–32,768 tokens. `--timeout 90` bounds each HTTP timeout
  phase. A transport timeout may still have incurred a charge. Truncated answers
  remain errors and retain the provider finish reason; they are never negatives.
- `--structured` requires native JSON-schema support and routing parameter
  support. Without it, models receive the same JSON instruction and responses
  are validated locally. Invalid, refused or truncated answers remain errors,
  never negative results. Provider errors are redacted.
- Model IDs are checked against the current OpenRouter image-input/text-output
  catalog, restricted to models released in 2026. Floating routers, batch variants
  and image-generation endpoints are excluded. Availability depends on the account and provider. `models` lists
  current options; the examples are starting points, not accuracy rankings.
  Optional temperature and reasoning settings follow each model’s advertised
  capabilities. Reasoning effort defaults to low; choose low, medium or high in
  **More settings** or pass `--reasoning-effort high`. Medium/high are rejected
  before inference when a selected model does not advertise support.
- A terminal positive is a **candidate**, not proof Waldo was found. Pruned
  negatives can be wrong. No accuracy is reported without independent human
  ground truth. A single image cannot establish general model performance.

## Results

Every run needs a new output directory. Existing runs are never overwritten.

```text
runs/grid/
  input.png                 # normalized original image
  reference.png             # exact appearance exemplar sent with every crop
  results.json              # settings, prompt, image hash, full search trace
  summary.csv               # per-model time, calls, errors, tokens and cost
  model-00/
    annotated.png           # region outlines and labels for review
    crops/                  # exact inputs: PNG, or root.jpg for direct boxes
```

Annotations use red for terminal candidates, amber for other present/uncertain
observations, green for negatives, and grey for errors. Results record original
and padded bounds, requested/returned model, provider, generation ID, latency,
usage (including reported reasoning-token counts), requested effort, early-stop
reason and untested regions. Provider-reported cost totals can
be incomplete; `cost_complete` distinguishes missing costs from real zero cost.
Search reports are checkpointed after each completed model. Interrupting a model
may leave its crops without a completed result. Raw API envelopes and image
base64 strings are not saved.

The supplied beach illustration is installed locally at `data/beach.png` and is
excluded from Git, along with all run images and secret configuration. See
[data/README.md](../data/README.md) for its provenance hash. Bring an image you have
permission to use when cloning the project.

The [initial experiment report](../reports/2026-10-20-initial-experiment.md) preserves
the older-model pilot as historical evidence. Current runs accept only 2026
models. See [dashboard verification](../reports/2026-10-20-dashboard-verification.md)
for the 2026-model browser tests. The [reference comparison](../reports/2026-10-20-reference-comparison.md)
records the matched before/after test with an exemplar and explicit occlusion
instructions. The [reasoning comparison](../reports/2026-10-20-reasoning-comparison.md)
tests low, medium and high effort at a matched response cap. Model candidates
still require visual review. The [crop-detail comparison](../reports/2026-10-20-crop-detail-comparison.md)
tests native and 4× enlarged target and distractor crops with both models. Its
scene-specific `experiments/crop_detail.py` prepares exact inputs offline, or makes
24 paid calls with `--live`, and writes a local HTML review sheet.
The [source-resolution comparison](../reports/2026-10-20-source-resolution-comparison.md)
tests a matched 3000 × 1926 copy against deliberately degraded crops at identical
input dimensions, separating source detail from simple enlargement.
The [higher-resolution full-grid run](../reports/2026-10-20-high-resolution-grid.md)
then searched every region of the complete scene in the app. Gemini selected only
the correct center region; GPT also selected five false positives. For the locally
downloaded clearer scene, use the Upload image control with
`data/beach-high-resolution.jpg`, or start `serve` with
`--image data/beach-high-resolution.jpg`.
The [binary-versus-grid comparison](../reports/2026-10-20-binary-vs-grid.md) uses the
same source and model settings. Default binary pruning lost Gemini's target
branch; GPT's binary run was slower and more expensive while retaining false
positives. The report includes request counts, elapsed times, costs and branch
reviews.
The [repeated-crop test](../reports/2026-10-20-repeated-crop.md) sends the exact
wrongly pruned crop ten times to each model with unchanged settings. Gemini
repeated its confident false negative in eight of ten calls. The
`experiments/repeat_crop.py` helper prepares repeats offline or makes paid calls
with `--live`; its expected label remains review metadata only. Live unchanged
repeats reject historical baselines whose image-detail setting differs from the
current provider default, before making any paid calls.
The [explicit image-detail test](../reports/2026-10-20-image-detail.md) then holds a
bounding-box prompt fixed while comparing `auto` with `original`. Across five
repetitions of the same positive crop, Gemini's correct localizations changed
from 0/5 to 5/5, with one false alarm in ten negative trials at `original`. GPT
localized Waldo at both settings but falsely detected him in every negative
trial. The standalone `experiments/image_detail.py` helper writes an interactive
box-overlay review; `--live` enables paid calls. That controlled crop experiment
kept app defaults unchanged at the time; new live searches now explicitly request
`original` search-image detail as documented above.
The [original-detail full-search comparison](../reports/2026-10-20-original-detail-searches.md)
repeats the entire grid and binary searches five times each with Gemini. Both
found the confirmed target in 5/5 runs; each returned an extra candidate in two
runs. Grid averaged 48.55 seconds and $0.16788; binary averaged 72.80 seconds and
$0.13383. The report separates first-candidate latency from full completion,
records individual runs, and explains the remaining close-lookalike errors.

## Development

```bash
uv --config-file uv.toml sync --locked
uv --config-file uv.toml run pytest
uv --config-file uv.toml run ruff check .
uv --config-file uv.toml run ruff format --check .
```

Dependencies are locked in `uv.lock`; uv excludes packages released within the
last seven days. Commands select `uv.toml` explicitly to avoid machine-wide configuration
overrides; keep its age policy aligned with `pyproject.toml`. Offline tests cover geometry, branch selection, request caps,
provider parsing and payloads, credential redaction, and result artifacts.

API references: [OpenRouter image inputs](https://openrouter.ai/docs/guides/overview/multimodal/image-understanding),
[structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs),
and [Infisical secrets CLI](https://infisical.com/docs/cli/commands/secrets).

## Brand assets

The [asset manifest](../image-assets/manifest.json) records the generated logo,
text-free icon, favicon frames, web icons, and 1200 × 630 social artwork.
Transparent originals and native Codex image-generation prompts are preserved in
[image-assets/sources](../image-assets/sources); [background previews](../image-assets/previews/backgrounds.png)
show the marks on light and dark surfaces. The README uses the cropped root
`logo.png` through its public raw-image URL.

The dashboard serves a bundled subset from `src/waldofinder/static/brand/`:
its header icon, favicon, touch and web icons, web manifest, and social image.
`/favicon.ico` and the explicitly listed `/brand/` assets are served with their
image or manifest content types; other paths remain unavailable. Keep these
runtime copies aligned with the matching exports in `image-assets/web-seo/` when
refreshing the branding. The runtime web manifest also sets `start_url` and
`scope` to `/`. Social metadata references the local image route; the dashboard
remains a loopback-only app rather than a publicly hosted social-preview page.

## Named distractor experiment

The [three-model distractor report](../reports/2026-10-21-distractor-references.md)
compares five repeats of the same positive and two negative crops, before and
after adding Wenda/Odlaw examples and explicit exclusion instructions. Local
artifacts are under `runs/distractor-references-2026-10-21/` (ignored by Git).
Prepare or inspect without paid calls:

```bash
uv --config-file uv.toml run python -m experiments.distractor_references \
  --output runs/distractor-references-2026-10-21
```

`--live` enables paid calls; `--probe` runs only positive replicate 1 per model.
Completed attempts, including failures, are never automatically retried. Existing
saved baseline folders are required and hash-checked. The saved prompt/schema,
Waldo example, crops and distractor bytes are checked before resuming. The older
image-detail prompt is frozen separately so historical baselines remain intact.

## Native OpenAI controls

The [direct-Sol and Image 2.5 report](../reports/2026-10-21-native-openai-controls.md)
compares native OpenAI calls with the saved OpenRouter condition. Sol keeps the
same Chat Completions inputs/settings to isolate routing. Sunburst edits each
crop to circle Waldo, with independent visual review for invented or altered
characters. Both use the same three appearance examples and exact crop files.

```bash
uv --config-file uv.toml run python -m experiments.openai_controls \
  --output runs/native-openai-controls-2026-10-21
```

Preparation/summarization is offline. `--live` enables paid calls and reads a
short-lived OpenAI key through a hidden terminal prompt; it does not save the key
or change the app's Infisical/OpenRouter authentication. Five repetitions per crop,
two arms, no automatic retries, 30 calls maximum per fresh experiment. Native
usage-based dollar estimates are distinguished from OpenRouter-reported cost.
`experiments.review_openai_controls FOLDER` proposes circle bounds and builds a
side-by-side input/output viewer. Proposals require visual review: a generated
Waldo in the wrong place is not evidence of a source-image detection.

## BSP across additional scenes

The [19-scene report](../reports/2026-10-21-gemini-bsp-scenes.md) records seven
visually confirmed finds, six model misses and six inconclusive target paths.

`experiments.bsp_scenes` runs the production binary-search engine on the frozen
19-scene collection described in [data provenance](../data/README.md). It uses
Gemini 4 Argon, `original` image detail, high reasoning, three appearance examples,
8% crop overlap, depth 4, and a 32-region cap per scene. A common prompt excludes
printed character examples from all scenes; target coordinates are never supplied.

```bash
uv --config-file uv.toml run python -m experiments.bsp_scenes \
  --output runs/gemini-bsp-scenes-new
```

Add `--live` for paid calls through the existing Infisical proxy. The first pending
scene runs before releasing the rest; if all its calls fail, submissions stop.
Up to eight scenes and 32 inference calls can overlap. A separate 5.8 MB budget
limits concurrent request bodies until response headers arrive, protecting the
proxy's 60-second upload deadline on slow connections.

The transport encodes search crops as JPEG quality 90, with 4:4:4 chroma and **no
resizing**. This adds lossy compression, so results are a separate condition from
earlier PNG experiments. Appearance-reference PNGs remain unchanged. Exact sent
JPEGs are saved by SHA-256 under `transport-inputs/`; each successful observation
records its transmitted crop, encoding, dimensions, wire size and upload queue
time. Timing includes encoding, upload, queueing and inference under shared load.
There are no automatic retries. Completed attempts are preserved on resume;
interrupted scene folders require review rather than silent resubmission.

`comparison.json` separates searches with transport errors from error-free
searches. Reported costs omit unreported charges and are marked incomplete when
usage is missing. Candidate containment of the target point is only coarse region
coverage: the model's explanation still needs visual verification against the
character, and one attempt per scene does not establish repeatability.

`python -m experiments.review_bsp_scenes OUTPUT` builds `review.html` from saved
results, with frozen ground-truth markers, candidate boxes and original target
context. Assistant visual judgments are saved separately in `visual-review.json`;
the 19-scene run's `evaluated-results.json` contains the checked final outcomes.
The source manifest is snapshotted so later catalog-label corrections do not
erase acquisition provenance. The department-store and musketeer scenes had
incorrect initial descriptive labels; image bytes and target coordinates did not change.
