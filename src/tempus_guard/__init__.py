"""Tempus Guard CLI: the local client of Tempus Guard for GitHub.

The Tempus Guard CLI runs on the agent's machine. It turns the commits an agent made on a branch into a
``tempus.action-intent.v1`` for ``github.push_branch`` (with the git bundle, the bundle
digest, the changed paths and the diff digest the executor re-derives), signs that intent
with the agent's Ed25519 key, and installs a pre-push hook so the branch can only reach
GitHub through a Tempus permit. It keeps no ledger and no policy: the gate decides, the
executor pushes, and the evidence bundle linked from the "Verified by Tempus" check is the
record.
"""

from __future__ import annotations

from .canonical import canonical_json, sha256_hex
from .gitfacts import DIFF_DIGEST_ARGS, GitError, changed_paths, create_bundle, diff_digest
from .intent import (
    ACTION_TYPE,
    SCHEMA_VERSION,
    IntentError,
    PushFacts,
    action_id,
    build_push_intent,
    collect_push_facts,
)
from .signing import KeyfileError, load_keyfile, sign_intent, verify_intent_signature

__version__ = "2.0.0"

__all__ = [
    "ACTION_TYPE",
    "DIFF_DIGEST_ARGS",
    "SCHEMA_VERSION",
    "GitError",
    "IntentError",
    "KeyfileError",
    "PushFacts",
    "__version__",
    "action_id",
    "build_push_intent",
    "canonical_json",
    "changed_paths",
    "collect_push_facts",
    "create_bundle",
    "diff_digest",
    "load_keyfile",
    "sha256_hex",
    "sign_intent",
    "verify_intent_signature",
]
