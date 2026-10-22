# Existing experiment entry points

All paths below are relative to the Waldofinder Git root. Use
`uv --config-file uv.toml run ...` to retain the repository's dependency policy.
Check the current driver source or `--help` before a live invocation; constants
and local artifact prerequisites matter as much as CLI flags.

## General grid and binary searches

`src/waldofinder/search.py` implements the shared production engine;
`src/waldofinder/provider.py` constructs the prompt and OpenRouter payload.
`src/waldofinder/geometry.py` defines splitting and padded bounds.

```sh
uv --config-file uv.toml run waldofinder preview IMAGE \
  --strategy grid --tiles 9 --output NEW_PREVIEW_DIRECTORY
uv --config-file uv.toml run waldofinder run --help
uv --config-file uv.toml run waldofinder models
```

The `run` command is paid; `preview` and the public model catalog are not inference
calls. Repeat `--model` for comparisons. Match explicit settings instead of
assuming CLI defaults equal earlier experiments. In particular, the reasoning
default is low, the output-token cap may include reasoning, and `--structured`
requires provider support. The provider currently requests crop
`image_url.detail = "original"` and separate reference detail `auto`.

BSP starts with two halves, not a full-image classification. A confident absent
answer prunes a branch unless `--explore-negatives` changes that policy. Depth and
request caps are different constraints. First-candidate stopping does not cancel
calls already in flight, so a run can return additional boxes. Grid and BSP must
use matched input/prompt settings for a strategy comparison.

## Controlled crops and native-provider comparisons

| Driver | Purpose | Couplings to check |
| --- | --- | --- |
| `experiments/repeat_crop.py` | Repeat identical crops to assess variability | Fixed crop definitions, model list and defaults in source |
| `experiments/image_detail.py` | Requested-detail and localization comparison | Frozen box prompt/schema, target and negative crops, saved baseline files; `--repeats`, `--probe`, `--live` |
| `experiments/compare_claude.py` | Extend the matched crop comparison to Claude | Fixed model/settings and image-detail baseline dependency |
| `experiments/distractor_references.py` | Before/after Wenda and Odlaw examples | Existing baseline folders and reference hashes; `--probe` gates a first positive per model |
| `experiments/openai_controls.py` | Direct OpenAI text-model and image-circle controls | Exact saved OpenRouter baseline, two fixed arms, native credential input and pricing assumptions |
| `experiments/review_openai_controls.py` | Review proposed circles against originals | Circle proposals require independent visual confirmation; no inference rerun |

These modules are controlled experiment fixtures, not a generic benchmark runner.
Read their `main()` and preparation checks before treating a new `--output` path
as sufficient to run a new comparison. In particular, historical model IDs and
native pricing constants need verification before a newly requested live run.
Offline CLI preparation may require local baseline artifacts omitted from Git.

Reports under `reports/` document the prior image-detail, source-resolution,
original-detail search, distractor-reference and native-OpenAI controls. Use their
saved inputs and settings to identify what can legitimately be compared.

## Frozen 19-scene BSP collection

`experiments/bsp_scenes.py` uses the production BSP engine on the locally stored
`data/online-waldo-scenes/` collection. Its preparation expects exactly 19 scenes,
their manifest and separate annotations. Its model, prompt, depth and other
settings are constants; `--source` does not make it a generic arbitrary-dataset
runner. `--output` prepares or summarizes; `--live` enables paid calls.

The current condition uses full-size JPEG quality 90, 4:4:4, without resizing,
while the general app provider sends PNG crops. Its streaming adapter has a
separate **5.8 MB upload budget**, released when response headers arrive, alongside
up to eight scenes and 32 inference calls. These are measured-workaround settings,
not universal proxy limits or benchmark defaults. Some gateway errors remained.
Inspect current transport evidence before changing this budget or encoding.

The first pending scene gates the batch only when **all** its requests fail.
It can proceed after a mixture of valid responses and errors. Resume preserves
completed attempts and refuses interrupted scene folders; inspect them rather
than deleting them to trigger another paid attempt.

Raw `comparison.json` aggregates treat only wholly error-free searches as
evaluable. Target-path visual review can resolve a find/miss despite an unrelated
error, so preserve both the raw summary and the rationale for any refined score.

```sh
uv --config-file uv.toml run python -m experiments.review_bsp_scenes RUN_DIRECTORY
```

This builds `review.html` from saved results. `visual-review.json` holds separate
manual judgments; the existing run's `evaluated-results.json` was generated in a
separate audit and is **not** produced automatically by this viewer command.
If adding automated evaluation, validate those semantics rather than assuming the
HTML builder establishes correct identity.

Specific provenance pitfalls: class 0 is Charlie/Waldo, class 2 Wenda. The
dinosaurs/aliens scene (`4-9-0`) uses the third line of the separate head labels;
the body labels list only a printed portrait. Initial descriptive labels for the
department-store and musketeer scenes were corrected after acquisition. Preserve
the original manifest snapshot/hashes and verify labels visually; do not infer
ground truth or scene identity from a caption alone.
