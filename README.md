<p align="center">
  <img src="https://raw.githubusercontent.com/tsilva/waldofinder/main/logo.png" alt="waldofinder — a striped figure framed within a crowd" width="320">
  <br />
  <!-- repo-tagline:start -->
  <strong>🔎 Compare vision models searching for Waldo 🧩</strong>
  <!-- repo-tagline:end -->
</p>

<p align="center">
  <a href="https://github.com/tsilva/waldofinder/actions/workflows/ci.yml"><img src="https://github.com/tsilva/waldofinder/actions/workflows/ci.yml/badge.svg?branch=main" alt="Tests"></a>
  <a href="https://github.com/tsilva/waldofinder/blob/main/pyproject.toml"><img src="https://img.shields.io/badge/Python-3.11%2B-blue" alt="Python 3.11 or newer"></a>
</p>

Waldofinder is an experiment lab for people evaluating vision-language
models: AI models that answer questions about images. Compare how they search
for Waldo in the same crowded scene, inspect the exact crops they receive, and
save your own reviews alongside their predictions.

Use the browser dashboard to compare a fixed grid with recursive binary
partitioning, which repeatedly splits promising regions. The CLI can also
export crops offline or run repeatable comparisons.

Choose **Mode → Direct bounding box** to send the full image once to each model
and draw its proposed Waldo location. Each model has its own box colour; click a
box or model badge to inspect the coordinates and evidence.

## Hosted app

The Vercel deployment is configured for [waldofinder.tsilva.eu](https://waldofinder.tsilva.eu).
Production pushes pass secret scanning and exact-commit CI before key sync and
deployment; direct Vercel Git builds are disabled.
Visitors can run searches using the server's production OpenRouter key; keys
stay in Infisical and Vercel Functions. Images and results are saved in each
visitor's browser, with JSON export. Keep the tab open while a search runs.

Hosted limits: 3 MB / 40 megapixels per source image, 32 calls per model,
8,192 output tokens per call, and a three-minute scheduling window. In-flight
calls can finish after that window. Images are never automatically downscaled.
The local dashboard below retains its larger limits, filesystem artifacts and
reconnection support. See [hosting and delivery](docs/production-delivery.md).

## Quick start

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and a local PNG, JPEG,
or WebP scene you have permission to use. From the repository root:

```bash
uv --config-file uv.toml sync --locked
curl --fail --location https://waldo.candlewick.com/images/waldo-wave.jpg \
  --output data/waldo-reference.jpg
curl --fail --location https://waldo.candlewick.com/pdf/WaldoCharacterSheets20.pdf \
  --output /tmp/WaldoCharacterSheets20.pdf
# Requires Poppler's pdftoppm (for example: brew install poppler).
uv --config-file uv.toml run python -m experiments.extract_distractors /tmp/WaldoCharacterSheets20.pdf
uv --config-file uv.toml run waldofinder serve --port auto
```

Open the printed local URL, choose **Image**, and upload your scene
(up to 20 MB). You should see the image fit the viewport with search regions
overlaid. **Configure** changes the strategy, regions, and models; click a
region to inspect its crop. Loading images and previewing regions need no
credentials or paid inference.

Each call includes separate Waldo, Wenda and Odlaw appearance references. The
prompt explicitly excludes Wenda and Odlaw and accounts for partial occlusion.
These standalone examples reveal no scene locations and stay ignored by Git.
To supply your own, pass `--reference`, `--wenda-reference` and `--odlaw-reference`.
See [test-image provenance](data/README.md).

For live searches, first configure OpenRouter access through
[Infisical](docs/usage.md#quick-start). The default uses an existing Infisical
Agent Vault proxy; direct Infisical Secrets bindings are also supported.
Credentials stay on the Python server. Live searches send images to OpenRouter
and the selected provider and incur API charges.

## Compare and review

- **Watch models search together.** Each region shows every selected model's
  live state and decision, with yellow running masks, red discarded masks and
  green candidate masks; blue marks regions still under consideration.
  The catalog accepts 2026 image-input, text-output
  models; availability depends on the provider.
- **Inspect the evidence.** Open a crop to see the prediction and reason.
  **Present**, **Absent**, and **Unsure** save your judgment independently;
  **Mark Waldo** records a reference coordinate.
- **Keep reproducible results.** The local dashboard reconnects to an active run after a
  refresh; hosted history stores received observations in your browser. JSON exports and local run files preserve settings, prompts,
  reference provenance, predictions, and human reviews.
- **Compare reviewed results.** A post-run panel shows per-model TP/FP/TN/FN,
  recall (sensitivity/TPR), specificity (TNR), precision, accuracy and F1.
  Rates update with your crop reviews; coverage, abstentions and errors remain visible.

New live searches request `original` detail for search images and `auto` for the
separate appearance reference. History and crop review show the requested detail.

A positive region is a **candidate**, not proof Waldo was found. Negative
regions can be wrong too. Confidence is self-reported, and a request cap is
not a spending cap. **Stop** prevents new calls while those already in flight
finish. See [limits and compatibility](docs/usage.md#limits-and-model-compatibility).

For an offline CLI preview:

```bash
uv --config-file uv.toml run waldofinder preview /path/to/scene.png \
  --tiles 9 --output runs/preview
```

Success prints the output path. Open `regions.json` and `crops/` there;
choose a new output directory for every run.

## Further reading

- [Codex benchmark skill](.agents/skills/waldo-benchmark/SKILL.md): the project
  workflow for reproducible experiments and visual verification.
- [Usage and reference](docs/usage.md): authentication, grid and binary
  strategies, prompts, image detail, saved artifacts, and development checks.
- [Experiment reports](docs/usage.md#results): matched comparisons and their
  limitations, including cases where binary pruning missed the target.
- [19-scene Gemini BSP test](reports/2026-10-21-gemini-bsp-scenes.md): seven
  verified finds, six model misses and six searches inconclusive after gateway errors.
- [Brand assets](image-assets/manifest.json): logo, text-free icons, favicons,
  and social artwork. The dashboard bundles its header icon, browser icons,
  web manifest, and social-image metadata.
