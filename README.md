<p align="center">
  <!-- repo-tagline:start -->
  <strong>🔎 Compare vision models searching for Waldo 🧩</strong>
  <!-- repo-tagline:end -->
</p>

# waldofinder

Test whether dividing a crowded image helps vision-language models find Waldo.
Run the same image through different OpenRouter models, compare a fixed grid with
recursive binary partitioning, and inspect every crop and decision.

## Quick start

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and access to OpenRouter
through [Infisical](https://infisical.com/docs/cli/overview).

```bash
uv --config-file uv.toml sync --locked
uv --config-file uv.toml run waldofinder models
# Put your own test image at data/beach.png, or pass another local image path.
uv --config-file uv.toml run waldofinder preview data/beach.png --tiles 9 --output runs/preview
uv --config-file uv.toml run waldofinder run data/beach.png --tiles 9 \
  --model google/gemini-2.5-flash \
  --model openai/gpt-4.1-mini --output runs/grid
uv --config-file uv.toml run waldofinder run data/beach.png --strategy binary --max-depth 5 \
  --model google/gemini-2.5-flash --max-requests 32 --output runs/binary
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
  --model google/gemini-2.5-flash --auth infisical \
  --infisical-project YOUR_PROJECT_UUID --infisical-env dev \
  --infisical-path / --infisical-secret OPENROUTER_API_KEY
```

Use `--infisical-domain https://eu.infisical.com` for EU Cloud. Only the named
secret is fetched, with expansion, imports and personal overrides disabled. Keys
are never exported to files. Live runs send cropped images to OpenRouter and its
selected model provider and incur API charges. Offline `preview` needs no login.

## Search strategies

**Grid:** `--tiles N` creates exactly N regions covering the whole image. Each
selected model evaluates every region independently with up to `--concurrency 4`
calls in flight. With M models, a complete grid costs N × M requests. Models run
sequentially to keep their wall times separate. `--columns 3 --tiles 12` forces a
regular 3-column, 4-row grid. Square tile counts use square grids. Other counts use balanced rows and may be ragged.

**Binary:** split the longest side into two and classify both halves; split
positive or uncertain branches again. A confident negative prunes its branch.
The default stops after the first confident positive terminal region, at
`--max-depth 4`, `--min-size 64` (longest side), or an indivisible region. Use
`--all-candidates` to continue through all promising branches, or
`--explore-negatives` to split negative branches too. The latter checks whether
coarse-scale false negatives hide the target. Depth one means the initial halves;
an exhaustive depth D uses at most 2^(D+1) − 2 requests before size limits.

Both strategies use 8% padding on each side (`--overlap 0.08`) to help with boundary
cuts. Boxes use original, EXIF-corrected image pixels and half-open coordinates
`[left, top, right, bottom]`. Crops are neither rescaled nor annotated before
inference. A candidate applies to its padded crop; Waldo may be just outside the
unpadded region. Adjacent positive crops may describe the same character.

`--threshold 0.7` applies to the model's self-reported decision confidence.
Uncertain and low-confidence decisions continue through binary search; they do
not count as detections. This score is not a calibrated probability.

## Limits and model compatibility

- `--max-requests 64` caps HTTP attempts **per model**, including failed attempts.
  There are no automatic retries or cross-model fallbacks. This is a call cap,
  not a dollar cap; control provider spending limits separately.
- `--max-tokens 512` bounds each response; `--timeout 90` bounds each HTTP timeout
  phase. A transport timeout may still have incurred a charge.
- `--structured` requires native JSON-schema support and routing parameter
  support. Without it, models receive the same JSON instruction and responses
  are validated locally. Invalid, refused or truncated answers remain errors,
  never negative results. Provider errors are redacted.
- Model IDs are checked against the current OpenRouter image-input/text-output
  catalog. Availability depends on the account and provider. `models` lists
  current options; the examples are starting points, not accuracy rankings.
- A terminal positive is a **candidate**, not proof Waldo was found. Pruned
  negatives can be wrong. No accuracy is reported without independent human
  ground truth. A single image cannot establish general model performance.

## Results

Every run needs a new output directory. Existing runs are never overwritten.

```text
runs/grid/
  input.png                 # normalized original image
  results.json              # settings, prompt, image hash, full search trace
  summary.csv               # per-model time, calls, errors, tokens and cost
  model-00/
    annotated.png           # region outlines and labels for review
    crops/                  # exact PNG inputs sent to the model
```

Annotations use red for terminal candidates, amber for other present/uncertain
observations, green for negatives, and grey for errors. Results record original
and padded bounds, requested/returned model, provider, generation ID, latency,
usage, early-stop reason and untested regions. Provider-reported cost totals can
be incomplete; `cost_complete` distinguishes missing costs from real zero cost.
Search reports are checkpointed after each completed model. Interrupting a model
may leave its crops without a completed result. Raw API envelopes and image
base64 strings are not saved.

The supplied beach illustration is installed locally at `data/beach.png` and is
excluded from Git, along with all run images and secret configuration. See
[data/README.md](data/README.md) for its provenance hash. Bring an image you have
permission to use when cloning the project.

See the [initial experiment report](reports/2026-10-20-initial-experiment.md) for
live results on the supplied image. No verified localization was established.

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
