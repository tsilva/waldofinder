---
name: waldofinder_benchmark
description: Run and audit reproducible Waldofinder crop comparisons, grid/BSP searches, reasoning or image-detail controls, and cross-scene evaluations. Use for experiments in this repository, including accuracy, latency and cost comparisons; ordinary dashboard styling does not require this workflow.
---

# Waldo benchmark

Turn the requested hypothesis into a reproducible experiment with inspectable
inputs, paid-call accounting and visually checked outcomes. Work from the
Waldofinder repository root; locate it rather than relying on the shell's cwd.

Read the relevant sections of [usage](../../../docs/usage.md) and
[image provenance](../../../data/README.md). Use the
[experiment map](references/experiments.md) to choose an existing driver and its
mode-specific checks. Historical reports are evidence, not executable instructions
or current model/pricing authorities.

## Choose and freeze the comparison

- Preserve the user's chosen models, strategy and scope. Resolve current model IDs
  and supported parameters through the repository's model catalog/provider code.
  The app's vision-text catalog accepts 2026 releases; image-generation controls
  use a separate driver. Do not silently substitute models or provider fallbacks.
- Reuse a suitable driver. Inspect its parser, constants, baseline dependencies
  and resume behavior before invoking it: several scripts are deliberately fixed
  to particular images, models or saved baselines. Add a separate condition when
  changing those assumptions; do not rewrite a historical baseline.
- Freeze source bytes/hashes, actual dimensions, crop bounds, references, prompt
  version, schema, image encoding, requested detail, reasoning/token cap, repeats,
  concurrency, timeout, stopping rules and request limits before live calls.
  Record the precise comparison and which factors change. Adaptive or sequential
  follow-ups remain separate from the initial condition.
- Visually check ground truth before scoring. Validate upstream class mappings
  and coordinates against the actual image, including printed portraits, multiple
  characters and boundary fragments. Keep target annotations and review markers
  separate from model inputs. Confirm negative crops visually as well.
- Use independent appearance references with no scene coordinates. The maintained
  prompt addresses partial occlusion and distinguishes Waldo from Wenda/Odlaw.
  If the experiment changes the prompt or references, version and hash that change.

## Prepare and run

Preparation and artifact inspection are offline. Paid calls require an existing
user request to run the relevant test; creating this skill does not authorize a
new benchmark. State the planned call count or upper bound and substantive cost
uncertainty before a material new condition. An attempt cap is not a dollar cap.

Use the existing Infisical credential workflow in `src/waldofinder/credentials.py`
and repository access bindings when present. The default Agent Vault path reads
only the loopback proxy URL and public CA from its owner-only configuration and
uses a placeholder key; real OpenRouter keys remain inside the proxy. Keep TLS
verification enabled. Diagnose failures with status, timing and presence checks,
without dumping configuration, provider error bodies or logs. Native OpenAI
controls need their own authorized, current credential path; never recover a key
from chat history or save one with experiment artifacts.

Preview/preparation must succeed before live inference. For a new multi-model
or large-image condition, validate a small representative image-bearing request
or scene before releasing the batch. A text-only success does not validate image
transport. Parallelize within a global request limit, while separately accounting
for upload capacity and shared resources. Preserve completed observations and
interrupted attempts; do not silently retry, overwrite, or rebill them. Define a
bounded, recorded retry policy if retries are part of the requested experiment.

`original` is a requested image-detail value, not evidence of the provider's
internal preprocessing. Record its exact payload location and any available
provider echo. Changing PNG/JPEG/WebP, compression, dimensions or upscaling creates
a different input condition. Save the exact transmitted image bytes. Do not claim
that generated/upscaled detail recovers source evidence.

## Score the evidence

- Separate usable predictions, explicit uncertainty, invalid/truncated answers,
  and gateway/transport errors. Reasoning can consume the output token budget;
  truncation is not an absent decision. Missing usage means unknown charges.
- For crops, report positive hits and negative false positives separately, with
  their denominators and error counts. Localization and correct identity are
  distinct from a yes/no answer and self-reported confidence.
- For searches, follow the frozen target through padded crop bounds, pruning,
  request caps, early stopping and errors. A terminal box containing its point
  is coarse coverage. Visually match the explanation to the actual character
  before calling it found. A box outside the point can still contain a fragment;
  inspect it rather than inferring absence from geometry alone.
- Keep confirmed finds, conclusive model misses and inconclusive target paths
  separate. An error elsewhere need not invalidate verified target evidence;
  an overlapping failed target branch may make a negative outcome inconclusive.
  Count overlapping boxes on one character as one scene find, and describe
  off-target boxes independently. Preserve the raw engine summary alongside
  subsequent visual judgments.
- For image-model circle controls, inspect the original and output together.
  An invented/redrawn Waldo is not a source-image detection. A model's own verdict
  or circle proposal is not independent ground truth.

## Deliver and verify

Save observations, requested/returned models, provider, generation IDs, settings,
usage, events and visual judgments under a fresh ignored `runs/` condition. Keep
reported dollar amounts separate from usage-based estimates and unknown charges.
Define timing boundaries: encoding, upload, queueing, inference, first useful
detection and full completion can differ. Shared-batch times are not isolated
model latencies. Avoid an accuracy percentage that folds errors into misses.

Provide a local visual audit with ground truth and candidate evidence. Use the
browser selected by the global Browser Use and Testing policy to verify a newly created or changed viewer. Update the
existing usage/data docs and a report under `reports/` when adding a protocol or
result. Keep source artwork and secrets out of Git. Explain condition changes,
sample size and limits on generalization or repeatability; a single scene or run
does not establish broad model superiority.

Validate code changes with relevant tests and Ruff, then the project's required
checks. An offline skill/documentation change needs no paid rerun. Publishing,
Git pushes and messages to other people retain their separate authorization rules.
