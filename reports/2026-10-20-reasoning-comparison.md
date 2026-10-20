# Reasoning-effort comparison — 2026-10-20

Higher reasoning did not fix the localization failure in this test. Gemini missed
the user-confirmed center region at low, medium and high effort. High effort used
9,032 reported reasoning tokens, yet selected the same wrong middle-left region
and rejected the center at 97% confidence. GPT marked every region positive at low
and medium effort, and eight of nine at high effort; its explanations in the
confirmed center crop still pointed to inconsistent locations.

## Setup

Each condition used the same 1080 × 675 beach image, 3 × 3 grid, 8% crop padding,
0.7 confidence threshold, character exemplar and `waldo-reference-occlusion-v2`
prompt. All 54 search-crop files, normalized image bytes and reference bytes were
identical across levels. The ground-truth point and reviews stayed separate from
the inference images and prompts.

A fresh low-effort control used the same **8,192-token response cap** as medium and
high effort. This avoids comparing higher effort at a larger token cap against
only the earlier 2,048-token baseline. Reasoning tokens share the response cap with
the final JSON even when their text is excluded; see
[OpenRouter's reasoning documentation](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).
The supported effort levels were checked against the current model catalog.
Google and OpenAI remained the reported providers respectively.

Requests ran concurrently within each condition; conditions ran in order. The
low control used the existing 90-second transport timeout. Medium/high used 180
seconds to allow longer generation. This changes the client timeout, not the model
input or token allowance. No image-detail or prompt changes were introduced.

| Model | Effort | Confirmed center decision | Positive crops / valid responses | Reported reasoning tokens | Reported cost | Errors |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| Gemini 4 Argon | low | Absent, 90% | 1 / 8 | 0 | $0.050486 | 1 |
| Gemini 4 Argon | medium | Absent, 90% | 0 / 9 | 0 | $0.057508 | 0 |
| Gemini 4 Argon | high | Absent, 97% | 1 / 9 | 9,032 | $0.148078 | 0 |
| GPT-6.1 Sol | low | Present, 90% | 9 / 9 | 1,948 | $0.0261387 | 0 |
| GPT-6.1 Sol | medium | Present, 88% | 9 / 9 | 4,229 | $0.0761815 | 0 |
| GPT-6.1 Sol | high | Present, 91% | 8 / 9 | 13,048 | $0.1644015 | 0 |

These are requested effort levels and provider-reported usage. Zero is the value
Google reported at low/medium; it is not an independent measurement of internal
computation. High effort clearly increased reported reasoning for both models.
Self-reported confidence is not an accuracy score.

The center is independently labeled present. Gemini's medium condition removed
its previous false positive by answering absent everywhere, but still missed
Waldo. High effort restored that false positive (`r1c0`). GPT's high condition
changed `r0c1` to absent; that padded top-center crop overlaps Waldo's upper area,
so this change alone cannot be called a correction without reviewing partial
visibility. No whole-grid accuracy is inferred from point containment.

The main sweep made 54 attempts, with **$0.5227937 in reported cost**. The one
failed low-control request (`r0c1`) was manually retried once with a 180-second
timeout. The retry returned an unusable answer (invalid, refused or truncated),
without usage or a usable finish reason. It is preserved separately as
`manual-retry-r0c1.json`; the original run was not overwritten. Including this
retry there were 55 attempts. Neither failed attempt provided usage, and either
may have incurred an unreported charge. All six center-region responses were usable. Caching and
variable generated token counts also affect costs, so these totals should not be
interpreted as stable per-effort prices. This is a single image and one request per
model/region/effort, not a repeated estimate of general model performance.

## Run records and review

- Low: `web-5f1ba7ffa8c44063a80dcebe23606ac8`
- Medium: `web-0b6f1028bd8442ada5bbb555f35d27a5`
- High: `web-414636ec448e41b6b8f6f36576f7035c`

All three runs have the confirmed (668, 253) marker and independent reviews for
the center region and Gemini's previously selected negative crop. Predictions
remain unchanged. The local dashboard is left on the high-effort run. History
identifies each run's effort and response cap, and **More settings** now exposes
reasoning effort, response cap and request timeout. CLI runs accept
`--reasoning-effort low|medium|high`.

Local `runs/reasoning-comparison-2026-10-20.json` holds the comparison and input
checks. Images, run records and ground-truth files remain ignored by Git.

73 offline tests pass on Python 3.11.15 and 3.14.5. Added checks verify that selected
effort reaches both supported request forms, unsupported efforts are rejected
before inference, higher-effort configuration survives launch and reload, and
truncation retains its finish reason. Browser tests exercised all three effort
settings, live runs, saved configuration and ground-truth review.
