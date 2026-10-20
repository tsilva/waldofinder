<p align="center">
  <img src="https://raw.githubusercontent.com/tsilva/waldofinder/main/logo.png" alt="waldofinder — a striped figure framed within a crowd" width="320">
  <br />
  <!-- repo-tagline:start -->
  <strong>🔎 Compare vision models searching for Waldo 🧩</strong>
  <!-- repo-tagline:end -->
</p>

<p align="center">
  <a href="https://github.com/tsilva/waldofinder/actions/workflows/tests.yml"><img src="https://github.com/tsilva/waldofinder/actions/workflows/tests.yml/badge.svg?branch=main" alt="Tests"></a>
  <a href="https://github.com/tsilva/waldofinder/blob/main/pyproject.toml"><img src="https://img.shields.io/badge/Python-3.11%2B-blue" alt="Python 3.11 or newer"></a>
</p>

Waldofinder is a local experiment lab for people evaluating vision-language
models: AI models that answer questions about images. Compare how they search
for Waldo in the same crowded scene, inspect the exact crops they receive, and
save your own reviews alongside their predictions.

Use the browser dashboard to compare a fixed grid with recursive binary
partitioning, which repeatedly splits promising regions. The CLI can also
export crops offline or run repeatable comparisons.

## Quick start

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and a local PNG, JPEG,
or WebP scene you have permission to use. From the repository root:

```bash
uv --config-file uv.toml sync --locked
curl --fail --location https://waldo.candlewick.com/images/waldo-wave.jpg \
  --output data/waldo-reference.jpg
uv --config-file uv.toml run waldofinder serve --port auto
```

Open the printed local URL, choose **Image**, and upload your scene
(up to 20 MB). You should see the image fit the viewport with search regions
overlaid. **Configure** changes the strategy, regions, and models; click a
region to inspect its crop. Loading images and previewing regions need no
credentials or paid inference.

The downloaded character illustration is a separate appearance reference;
it does not reveal Waldo's location in your scene. It stays ignored by Git.
To supply your own, pass `--reference /path/to/waldo.png`.
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
- **Keep reproducible results.** History reconnects to an active run after a
  refresh. JSON exports and local run files preserve settings, prompts,
  reference provenance, predictions, and human reviews.

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

- [Usage and reference](docs/usage.md): authentication, grid and binary
  strategies, prompts, image detail, saved artifacts, and development checks.
- [Experiment reports](docs/usage.md#results): matched comparisons and their
  limitations, including cases where binary pruning missed the target.
- [Brand assets](image-assets/manifest.json): logo, text-free icons, favicons,
  and social artwork. The dashboard bundles its header icon, browser icons,
  web manifest, and social-image metadata.
