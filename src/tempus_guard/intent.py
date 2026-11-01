"""Build the ``github.push_branch`` intent for a branch of the local repository."""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import gitfacts

SCHEMA_VERSION = "tempus.action-intent.v1"
ACTION_TYPE = "github.push_branch"
DEFAULT_BRANCH_PREFIX = "agent/"
MAX_PATHS = 1_000

_RESOURCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class IntentError(ValueError):
    """The branch or the arguments cannot become a valid push intent."""


@dataclass(frozen=True)
class PushFacts:
    """What the executor re-derives from the bundle; all of it goes into the signed intent."""

    branch: str
    base_sha: str
    tip_sha: str
    new_branch: bool
    bundle_path: str
    bundle_sha256: str
    paths: tuple[str, ...]
    diff_sha256: str

    def as_input(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "base_sha": self.base_sha,
            "tip_sha": self.tip_sha,
            "new_branch": self.new_branch,
            "bundle_sha256": self.bundle_sha256,
            "paths": list(self.paths),
            "diff_sha256": self.diff_sha256,
        }

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["paths"] = list(self.paths)
        return data


def action_id(tenant_id: str, agent_id: str, idempotency_key: str) -> str:
    """The action id the gate derives: sha256("tempus.action.v1" NUL tenant NUL agent NUL key)."""
    material = b"\0".join(
        part.encode("utf-8") for part in ("tempus.action.v1", tenant_id, agent_id, idempotency_key)
    )
    return hashlib.sha256(material).hexdigest()


def collect_push_facts(
    repo: Path,
    *,
    branch: str,
    base: str,
    bundle_out: Path,
    new_branch: bool | None = None,
    remote: str = "origin",
) -> PushFacts:
    """Read the branch and write the bundle. Nothing here touches the network."""
    if not branch or branch.startswith("-") or ".." in branch or branch.endswith(("/", ".")):
        raise IntentError(f"{branch!r} is not a usable branch name")
    tip_sha = gitfacts.resolve(repo, f"refs/heads/{branch}")
    base_sha = gitfacts.resolve(repo, base)
    if tip_sha == base_sha:
        raise IntentError(f"{branch} has no commits beyond {base}; nothing to publish")
    if not gitfacts.is_ancestor(repo, base_sha, tip_sha):
        raise IntentError(f"{base} is not an ancestor of {branch}; rebase first")
    paths = gitfacts.changed_paths(repo, base_sha, tip_sha)
    if not paths:
        raise IntentError("the branch changes no file")
    if len(paths) > MAX_PATHS:
        raise IntentError(
            f"the branch touches {len(paths)} paths; the executor accepts at most {MAX_PATHS}"
        )
    if new_branch is None:
        # The branch is new when the tracking remote does not have it yet.
        new_branch = not gitfacts.ref_exists(repo, f"refs/remotes/{remote}/{branch}")
    bundle_sha256 = gitfacts.create_bundle(repo, base_sha, f"refs/heads/{branch}", bundle_out)
    return PushFacts(
        branch=branch,
        base_sha=base_sha,
        tip_sha=tip_sha,
        new_branch=new_branch,
        bundle_path=str(bundle_out),
        bundle_sha256=bundle_sha256,
        paths=paths,
        diff_sha256=gitfacts.diff_digest(repo, base_sha, tip_sha),
    )


def build_push_intent(
    facts: PushFacts,
    *,
    tenant_id: str,
    agent_id: str,
    resource: str,
    idempotency_key: str | None = None,
    requested_at: int | None = None,
) -> dict[str, Any]:
    """The ``tempus.action-intent.v1`` document the agent signs.

    ``idempotency_key`` defaults to ``push:<branch>:<tip_sha>``, so asking twice for the
    same tip is the same action and a different tip is a new one. ``requested_at`` is in
    microseconds since the epoch, as the gate expects.
    """
    if not _IDENTIFIER.fullmatch(tenant_id):
        raise IntentError("tenant_id must be 1-128 letters, digits, '.', '_', ':' or '-'")
    if not _HEX64.fullmatch(agent_id):
        raise IntentError(
            "agent_id must be the agent's Ed25519 public key: 64 lowercase hex characters"
        )
    if not _RESOURCE.fullmatch(resource):
        raise IntentError("resource must be owner/repository")
    key = idempotency_key or f"push:{facts.branch}:{facts.tip_sha}"
    if not 1 <= len(key) <= 256:
        raise IntentError("idempotency_key must be 1-256 characters")
    stamp = requested_at if requested_at is not None else time.time_ns() // 1_000
    return {
        "schema_version": SCHEMA_VERSION,
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "idempotency_key": key,
        "action_type": ACTION_TYPE,
        "resource": resource,
        "requested_at": int(stamp),
        "input": facts.as_input(),
    }
