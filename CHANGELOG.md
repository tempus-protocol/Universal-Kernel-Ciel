# Changelog

All notable changes to this project will be documented here.

## [Unreleased] — 2.0.0 "Guard client"

The Tempus Guard CLI (formerly Ciel) becomes the local client of Tempus Guard for GitHub. One protocol (the
`tempus.action-intent.v1` contract of tempus-ddb), one policy evaluator (the gate's), one
ledger (the gate's), one brand. The repository lives in the `tempus-protocol` GitHub organization.

### Added

- `tempus guard intent`: builds the `github.push_branch` intent for a branch (`branch`, `base_sha`,
  `tip_sha`, `new_branch`, `bundle_sha256`, sorted unique `paths` with the executor's
  semantics, `diff_sha256` over the raw `git diff-tree` listing), writes the git bundle,
  signs the intent with the agent's Ed25519 key over Tempus canonical JSON and prints
  `intent`, `agent_id`, `agent_signature`, the derived `action_id` and the bundle digest.
- `tempus guard request`: hands a signed intent to a local gate (`request_action_signed`) and prints
  the permit. Needs the optional `gate` extra (`tempus-ddb>=0.6`).
- `tempus guard hook install | uninstall | status`: a `pre-push` hook that refuses direct pushes
  unless `TEMPUS_GUARD_ALLOW_DIRECT_PUSH=1`, and never touches a hook it did not write.
- Configuration from the environment: `TEMPUS_TENANT_ID`, `TEMPUS_AGENT_KEYFILE`,
  `TEMPUS_RESOURCE`, `TEMPUS_BASE`, `TEMPUS_REMOTE`.
- Tests against a throwaway bare remote, and a gate conformance test (skipped when
  `tempus-ddb` is not installed) proving the gate accepts what the CLI signs.

### Changed

- Package rebuilt on the standard library plus `cryptography`; `typer`, `pydantic`,
  `pyyaml` and `rich` are gone. Build backend is hatchling. Console scripts: `tempus-guard`
  (and `tempus-guard-cli`, kept as an alias).
- README, CONTRIBUTING and SECURITY rewritten in English for the product surface.

### Removed

- The local decision ledger (`.ciel/decisions.log`), its hash chain and `ledger verify`.
- The YAML policy language (`policies/default.yaml`), `policy validate`, the evaluator and
  the `allow / deny / require_approval` verdicts: policy now lives in the gate.
- Interactive approval, the allowlisted command runner and the `CIEL_GATE_*` variables.
- `ciel-gate init` and `ciel-gate check`.

## 1.0.0 - 2026-10-26

Local policy firewall: diff parsing, YAML policies, approval, allowlisted checks and a
hash-chained ledger (superseded by 2.0.0).

## 0.9.0 - 2026-07-05

### Added

- Optional BYOK cloud inference adapters for OpenAI, Anthropic, and Gemini.
- Model routing modes for `auto`, `local`, `cloud`, and `deterministic` execution.
- Append-only decision ledger with hash-chain verification.
- Memory CLI commands: `memory init`, `memory status`, and `memory verify`.
- Multi-product boundary detection for mixed-language monorepositories.
- Versioned YAML policy rulesets and CLI ruleset selection.
- Auto-refactor planning with deterministic fallback plans.
- Safe patch proposal workflow with destructive-operation review and no automatic apply.
- Tag-triggered PyPI trusted-publishing workflow.

### Changed

- Consolidated CI into one test/build workflow with Python 3.10 and 3.11 coverage gates.
- Hardened cloud error handling so provider credentials cannot appear in returned errors.
- Aligned package and ledger metadata with the `0.9.0` Safe Patch Generation milestone.

### Removed

- Tracked local runtime decision ledger at `.ciel/decisions.log`.
