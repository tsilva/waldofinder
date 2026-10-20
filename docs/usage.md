# Usage and reference

[Back to the README](../README.md). Run all commands from the repository root.

## Visual experiment lab

```bash
uv --config-file uv.toml run waldofinder serve --port auto
```

Open the printed local URL. The dashboard uses your existing Infisical connection;
credentials stay on the Python server. Every live call receives a separate Waldo
appearance reference and the search crop, with explicit instructions for partial
occlusion. Search crops explicitly request `original` image detail; the reference
uses `auto`. It includes:

- A supplied beach scene or an uploaded PNG, JPEG or WebP (20 MB maximum).
- Fixed grids or binary partitioning, overlap, depth, confidence and request caps.
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

**Stop** prevents new calls and lets calls already in flight finish. Results
and events are saved under `runs/web-*/`; human labels and the target marker are in
`review.json`. Refreshing the page resumes the current run. A server restart marks
unfinished sessions interrupted and preserves completed observations. The server
binds to `127.0.0.1`, validates request origin and requires a per-session token for
writes. It is a local tool, with no hosted authentication or remote access.

For another image, pass `--image /path/to/scene.png`. The `serve` command accepts
the same Infisical binding options as `run`, plus `--runs-dir` for a different local
experiment folder. `--reference /path/to/waldo.png` selects the appearance exemplar
(default `data/waldo-reference.jpg`); its preview and the full prompt are available
under **Reference & prompt for new searches** in configuration. The UI uses bundled HTML, CSS and JavaScript with no npm build
or external frontend dependencies.

## Quick start

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and access to OpenRouter
through [Infisical](https://infisical.com/docs/cli/overview).

```bash
uv --config-file uv.toml sync --locked
# Download the publisher's standalone character illustration for local testing.
curl --fail --location https://waldo.candlewick.com/images/waldo-wave.jpg \
  --output data/waldo-reference.jpg
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

## Prompt and visual reference

Each request contains the same text instruction, a labeled **REFERENCE** image,
then a labeled **SEARCH CROP** image. Only the search crop counts as evidence of
presence. The reference is a separate full-figure illustration, never a target
crop extracted from the test scene. The prompt explains that Waldo is often
partially occluded or cut off at the crop edge, and does not require his whole
body or every identifying feature to be visible together. Stripes alone are
insufficient; weak or ambiguous evidence should produce `uncertain`.

The reference is required for live inference. Both `run` and `serve` accept
`--reference PATH`; offline `preview` does not need it. The default local image
comes from [Candlewick's Waldo site](https://waldo.candlewick.com/). Artwork stays
ignored by Git. Supply your own appropriate reference when cloning the repo.
The server normalizes it to RGB PNG once and copies the exact exemplar into each
run as `reference.png`. Results and session exports record the prompt version,
full prompt, reference dimensions, source hash and normalized PNG hash. Each
observation records its reference hash and prompt version. Historical runs and
replays retain their original provenance rather than adopting the current prompt.

New live searches in both the app and CLI use OpenRouter's `original` detail for
the search image and `auto` for the reference. Exact image detail is
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
    crops/                  # exact PNG inputs sent to the model
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
