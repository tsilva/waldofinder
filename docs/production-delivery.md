# Waldofinder production

- Domain: `waldofinder.tsilva.eu`; Cloudflare DNS-only CNAME
  `b3701aa7a29b126e.vercel-dns-017.com` (Auto TTL).
- Vercel project: `waldofinder`, `prj_9JcFTUe60qgFgxkAazfm01UcpXnA` in
  `team_eE2Iv7IMqPOx8ZVN2xNfR2f0`.
- Infisical: `waldofinder-production`, project
  `43228ca5-1edf-4c4c-bffe-e4c6194f4334`, `prod`, `/`.
  The sole runtime key is `OPENROUTER_API_KEY`; it is private, not Config.
- GitHub reader: `fa2d876f-5fa8-4ea8-8948-3b1a962f0128`, Viewer on only this
  production vault. OIDC pins repository ID `1427252678`, owner ID `26742`,
  `refs/heads/main`, the `Production` environment and this repository's exact
  `production-delivery.yml` workflow. Tokens expire after 900 seconds.
- GitHub `Production` allows deployments from `main`. Its `VERCEL_TOKEN` must
  be scoped to this Vercel project; never copy a general CLI login into Actions.

CI runs Python 3.11/3.14 tests and Ruff. Committed-secret scanning gates delivery.
The maintained installer generated the delivery runtime, tests, metadata and source
hashes. The workflow adds the same secret-scanning prerequisite used by the other
projects. Delivery waits for exact-commit CI, reads only the pinned Production key,
synchronizes it to Vercel as a Secret, then deploys that Git commit. Keep Require
Separate Values enabled. Disable parallel Vercel Git deployments only after the
ordered replacement succeeds; no Preview/Development keys are populated here.

The app is public. Uploaded sources and received results stay in the visitor's
browser history; the active Function temporarily processes the source and sends
crops to OpenRouter. [Hosted lifecycle and limits](usage.md#hosted-vercel-app)
explain interruption, browser storage, byte provenance and billing boundaries.
No historical experiment folders or private local uploads are deployed.

## Maintained template reference

# Production delivery template

This is the maintained source for ordered Vercel Production delivery in
`tsilva/private-skills`. It includes the separation-policy fix verified in all
18 Vercel delivery repositories on 20 October 2026. Source changes and fresh
repository setup are checked by the `Production delivery template` workflow.

## Install in a new Vercel repository

Use the maintained [new-repository setup command](https://github.com/tsilva/private-skills/blob/main/docs/new-repository-setup.md)
to install these files with a reviewed metadata manifest and provenance hashes:

| Source file | Repository destination |
| --- | --- |
| `production_delivery.py` | `.github/scripts/production_delivery.py` |
| `test_production_delivery.py` | `.github/scripts/test_production_delivery.py` |
| `production-delivery.json.example` | `.github/scripts/production-delivery.json` |
| `production-delivery.yml` | `.github/workflows/production-delivery.yml` |
| `README.md` | `docs/production-delivery.md` |

Replace every manifest placeholder with verified repository, Infisical vault,
OIDC reader, Vercel team and project identifiers. Customize `secretNames` to the
exact source-key allowlist. Despite its legacy name, this list contains both
configuration keys and credentials; it never contains their values.

Set `configNames` explicitly to the public subset of `secretNames`. An empty
list is valid for a repository containing only private credentials. Omitting
the field is rejected before any Vercel request. Supported public names are
listed in `config_names()`; recognized public prefixes are `NEXT_PUBLIC_`,
`PUBLIC_`, and `VITE_`. Never put a credential in that list or give it a public
prefix to work around the policy. Unknown configuration names require a
reviewed change to the source allowlist.

Keep Vercel's **Require Separate Values** policy enabled. Public settings use
Config visibility; private credentials remain write-only Secrets. Actual
Production credentials must differ from Preview, Development and custom
environments. Obtain equivalent Production credentials from their provider and
save them in the isolated Infisical `prod` environment; do not copy development
credentials into Production. Provider rejection holds delivery until the named
key is repaired at its source.

The script checks the pinned repository, main commit, source allowlist and
Vercel destination before writing. Existing Production variables are updated
by their exact IDs. A legacy Secret explicitly listed as public configuration
is replaced only in Production because Vercel cannot convert it to Config in
place. Preview and Development variables are preserved. Provider response
bodies and secret values are suppressed from logs.

The copied workflow expects an existing `ci.yml` workflow and waits for its
successful push run for the exact main commit. Before enabling delivery,
configure the repository's GitHub Production environment and project-scoped
`VERCEL_TOKEN`, authorize its exact repository/main/workflow claims in the
Infisical OIDC reader, and assign only the required source access. Keep the
repository's committed-secret scanning checks enabled. Disable automatic
Vercel Git deployments only once the ordered delivery replacement is verified,
so deployments cannot race secret synchronization. Copying these files does
not provision credentials, change policy, register webhooks, or deploy anything.

Run the credential-free regression suite in the new repository:

```sh
python3 -m unittest discover -s .github/scripts -p test_production_delivery.py
```

Then run **Actions → Production delivery → Run workflow → main**. Count delivery
as verified only when the workflow succeeds and logs `Production READY` for the
expected commit. Existing Production remains live if synchronization or the
build fails. A new repository's live delivery still requires this verification;
template fixture tests do not establish a live deployment.

## Verify the source template

From this template directory, run:

```sh
python3 -m unittest discover -p 'test*delivery*.py'
```

`test_delivery_template.py` assembles an isolated new-repository fixture from
these source files, runs the copied regression suite, and exercises sync followed
by deployment with a mocked provider that enforces secret separation. It makes
no real network requests and changes no provider settings.
