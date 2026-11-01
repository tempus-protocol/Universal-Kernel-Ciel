# Security Policy

## Supported versions

Only the latest commit on `main` and the current 2.x release are supported.

## Reporting issues

Open a private security advisory or contact the maintainer directly. Do not publish exploit
details in a public issue before a fix is available.

## Current security posture

- The CLI holds the agent's Ed25519 key only to sign intents; it never holds a GitHub token,
  the GitHub App key or the gate key. The private key never appears in its output.
- The CLI pushes nothing. The executor pushes once, after re-deriving the bundle digest, the
  tip, the base, the changed paths and the diff digest from the bundle itself.
- `tempus guard request` talks only to a local gate database through the tempus-ddb library; there
  is no other network access.
- The pre-push hook refuses direct pushes unless `TEMPUS_GUARD_ALLOW_DIRECT_PUSH=1` is set for that
  command. It is a guard against habit, not against a determined operator: GitHub branch
  protection and the gate's policy are the real boundary.
- Bundles under `.tempus/` are local runtime files; keep `.tempus/` out of version control.
