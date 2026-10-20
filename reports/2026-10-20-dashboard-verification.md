# Dashboard verification — 2026-10-20

The browser UI was exercised through the native Codex in-app Browser and the
real Infisical Agent Vault → OpenRouter path, using only 2026 models.

| Strategy | Model | Requests | Errors | Candidates | Reported cost |
| --- | --- | ---: | ---: | ---: | ---: |
| binary | `google/gemini-4-argon` | 6 | 0 | 1 | $0.02233200 |
| grid | `google/gemini-4-argon` | 4 | 0 | 1 | $0.01502400 |
| grid | `openai/gpt-6.1-sol` | 4 | 0 | 4 | $0.01474000 |

The grid used four tiles per model. The binary test used Gemini 4 Argon at depth
2 with negative branches explored, producing six observations. These are model
claims for human inspection, not independently confirmed locations.

Verified browser interactions: grid and binary controls, live processing states
and completion events, per-model views, crop enlargement, human label and marker
persistence across reload, clearing test annotations, scene upload, saved-run
history, downloading an exported JSON run, and stopping a replay without
leaving the UI in a stale running state. Test annotations were cleared;
no verified ground-truth location has been recorded.

The model selector uses OpenRouter release metadata to admit 2026 vision models
only, excluding floating routers, batch variants and image-generation endpoints.
Defaults are Gemini 4 Argon (2026-10-13) and GPT-6.1 Sol (2026-09-29); Claude Sonnet
5.5 (2026-09-28) is an additional preset. Native JSON-schema outputs are supported
for these presets; optional request settings follow each model's advertised
capabilities. Their catalog pages are the release-date sources:
[Gemini 4 Argon](https://openrouter.ai/google/gemini-4-argon),
[GPT-6.1 Sol](https://openrouter.ai/openai/gpt-6.1-sol), and
[Claude Sonnet 5.5](https://openrouter.ai/anthropic/claude-sonnet-5.5).

52 offline tests passed on Python 3.11.15 and 3.14.5. They cover SSE cursors,
concurrent completion delivery, cancellation, replay cancellation without
inference, configuration limits, release-year enforcement, upload and artifact
boundaries, local request guards and independent review persistence, alongside
the original CLI tests. Ruff and JavaScript syntax checks passed. Built wheels
include the bundled UI. Credentials, scene images and generated runs stay ignored.

## Concurrent scheduler and compact interface

The updated UI removes the permanent sidebar, hero, statistic cards, activity feed
and result-card list. Configuration and exact-crop review use dialogs. The full
scene fits the available width and height, with no document scrolling. Browser
measurements confirmed this at 654 × 853 and 321 × 853 viewports. Every region
shows one status row per selected model. An upward arrow identifies a decision
from a larger binary ancestor; clicking that row opens that ancestor's exact crop.

The global pool defaults to 32 concurrent calls; the UI permits 1–64. Selected
models run together and binary children enter the same pool as soon as their
parent resolves. Per-model request caps, cancellation and candidate stopping still
apply; calls already in flight finish and retain their results.

| Strategy | Model | Requests | Errors | Candidates | Reported cost |
| --- | --- | ---: | ---: | ---: | ---: |
| 9-region grid | `google/gemini-4-argon` | 9 | 0 | 1 | $0.033458 |
| 9-region grid | `openai/gpt-6.1-sol` | 9 | 0 | 9 | $0.029566 |
| binary, depth 2 | `google/gemini-4-argon` | 2 | 0 | 0 | $0.008138 |
| binary, depth 2 | `openai/gpt-6.1-sol` | 6 | 0 | 4 | $0.021922 |

The grid event trace recorded **all 18 calls started before the first completion**
(peak 18 in flight). Model wall times overlapped: 9.18 seconds for Gemini and
18.24 seconds for GPT. Runs were `web-0199d9b9a2e14498a77623ce80106ff2`
and `web-6947eb0304df4387a173ee36a6ec6652`; generated files remain local.

The in-app Browser showed simultaneous running states on both initial binary
halves, then the divergent per-model partitions and parent-decision indicators.
Reviewing a parent row opened its saved parent crop. A test human label survived
reload and was cleared afterward. Closing configuration discarded unapplied
changes. The JSON export downloaded successfully. Stopping a live run with a two-call
pool retained exactly those two in-flight answers and launched no further calls;
the UI reached Cancelled and re-enabled Run. No browser console errors were
observed. These predictions remain
unverified model claims; no ground-truth location was added.

56 offline tests pass on Python 3.11.15 and 3.14.5. Added deterministic tests cover
cross-model concurrency, the global capacity limit, per-model caps, binary refill
while a sibling is blocked, draining cancellation, and correct artifact directories
when models finish out of order. Ruff and JavaScript syntax checks pass.

## Branding integration

The selected crowd-detective artwork is now wired into the compact dashboard:
a text-free header icon, browser favicon, Apple touch icon, web app icons and
manifest, and Open Graph image metadata. Static files are explicitly allowlisted;
unknown brand files and encoded traversal paths return 404. The ICO contains
16, 32 and 48 px frames, and the wheel includes all seven runtime brand files.
The local app remains loopback-only; social metadata does not create a hosted
public preview.

The native in-app Browser confirmed the header image loaded, configuration and
crop review still opened, and no console warnings or errors appeared. At
1280 × 720 and 390 × 844, the header and controls fit without horizontal document
scrolling. These checks used local image previews without paid inference.

The README is now a concise first-use guide; the detailed instructions and report
links are preserved in `docs/usage.md`. Its reference-image URL and both badge
URLs returned HTTP 200 with image content types. The offline CLI preview command
completed, local documentation links and anchors resolved, and the marked tagline
validated. Built wheel and source distributions passed an isolated Twine check;
the older system Twine could not parse their metadata version.
