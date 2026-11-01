# Contributing

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Test locally

```bash
ruff check .
python -m pytest
python -m build
python -m twine check dist/*
```

Install `tempus-ddb` (the `gate` extra) to also run the gate conformance tests; without it
they are skipped.

## Rules

- The CLI computes what the executor re-derives. A change to `changed_paths` or
  `diff_digest` semantics must land together with the matching change in
  `tempus-github-app` (`git_push.py`) or the executor will reject every intent.
- The contracts are the `.v1` documents of tempus-ddb; the CLI adds nothing to them. New
  fields go to the protocol first.
- No ledger, no policy language, no network calls other than `tempus guard request` against a
  local gate. The gate decides; the evidence bundle is the record.
- Every release-facing claim must be backed by implementation evidence and tests.
