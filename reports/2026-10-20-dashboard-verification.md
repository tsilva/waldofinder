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
