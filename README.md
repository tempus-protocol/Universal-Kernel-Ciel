# Tempus Guard CLI

**The local client of [Tempus Guard for GitHub](https://github.com/Julio-Patron/tempus-ddb).**

Coding agents commit locally and never hold a GitHub credential. The Tempus Guard CLI runs where the agent
runs and does one thing: it turns the commits on a branch into a signed
`tempus.action-intent.v1` for `github.push_branch`, so the Tempus gate can decide, the
mediated executor can push, and the pull request gets its **Verified by Tempus** check with
the evidence bundle anyone can verify in a browser.

The CLI keeps no ledger and no policy language. The gate holds the policy (one evaluator,
`jsonlogic-fast`), the gate's ledger holds the decision, and the evidence bundle linked from
the check is the record. Everything the CLI computes locally is re-derived by the executor
from the bundle before the single push: if they disagree, nothing is pushed.

## What `tempus guard intent` signs

For a branch built on top of `origin/main`:

| Field | Meaning |
| --- | --- |
| `branch`, `base_sha`, `tip_sha`, `new_branch` | Where the commits go and the exact state they start from |
| `bundle_sha256` | sha256 of `git bundle create <base_sha>..<branch>`, the only thing the executor unbundles |
| `paths` | Every path touched between base and tip, including files a later commit reverts, sorted and unique |
| `diff_sha256` | sha256 of the raw `git diff-tree -r -z --no-renames --no-commit-id --raw --abbrev=40 <base> <tip>` listing |

The signature is Ed25519 over the canonical JSON of the intent (sorted keys, no whitespace,
non-ASCII raw), with the agent key from `tempus keygen`. The output is exactly what the
gate's `request_action_signed` takes: `intent`, `agent_id`, `agent_signature`.

## Install

```bash
pip install -e .
# also talk to a local gate from the CLI (`tempus guard request`):
pip install -e ".[gate]"
```

Python 3.10+ and `git` on `PATH`. The only runtime dependency is `cryptography`.

## Use

```bash
# once per clone: a direct push from this machine is refused from now on
tempus guard hook install

# the agent commits on agent/fix-123, then asks for a permit
tempus guard intent --branch agent/fix-123 --base origin/main \
  --tenant-id acme --agent-keyfile agent.keys.json --out signed.json
# -> signed.json: intent + agent_id + agent_signature, action_id, bundle path and sha256

# hand the signed intent to the gate: locally,
tempus guard request --signed signed.json --gate-db gate.db --gate-keyfile gate.keys.json > permit.json
# or through the Tempus MCP tool `tempus_request_action_signed`, or your own transport.

# the executor (tempus-github-app) consumes the permit, pushes the bundle once and
# publishes the "Verified by Tempus" check on the pushed commit:
tempus-github-app-executor --permit permit.json --bundle .tempus/bundles/agent__fix-123.bundle
```

`--tenant-id`, `--agent-keyfile`, `--resource`, `--base` and `--remote` also read
`TEMPUS_TENANT_ID`, `TEMPUS_AGENT_KEYFILE`, `TEMPUS_RESOURCE`, `TEMPUS_BASE` and `TEMPUS_REMOTE`.
`--resource` defaults to the `owner/repository` of the GitHub remote. The bundle goes to
`.tempus/bundles/` inside the repository unless `--bundle-out` says otherwise; add `.tempus/`
to your `.gitignore`.

`tempus guard ...` in the core CLI (`tempus-ddb`) runs these same commands once this package is installed; `tempus-guard ...` is the standalone entry point.

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Done; the JSON on stdout is the result |
| 1 | The branch, the keys, git or the gate refused; stderr says why |
| 2 | Usage: missing arguments, not a repository, library not installed |

### The pre-push hook

`tempus guard hook install` writes a `pre-push` hook that exits 1 with a message pointing at
`tempus guard intent`. A human who means to push directly sets `TEMPUS_GUARD_ALLOW_DIRECT_PUSH=1` for that
command. The hook never replaces a hook it did not write unless `--force` is given, and
`tempus guard hook uninstall` removes only its own.

## What the CLI does not do

* It does not decide. The gate evaluates the tenant's policy and issues or refuses the permit.
* It does not push. The executor does, once, with a short-lived installation token, after
  re-deriving every field above from the bundle.
* It does not keep a ledger. The gate's ledger and the exported evidence bundle do; verify
  them at <https://julio-patron.github.io/tempus-ddb/verify.html> with the gate's public key.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

The gate conformance tests (`request_action_signed` accepting what the CLI signs) run when
`tempus-ddb` is importable and are skipped otherwise.

## License

MIT. See [CHANGELOG.md](CHANGELOG.md) for what changed in 2.0.
