"""Facts about a branch, read from git with plumbing commands.

Everything the executor re-derives from the bundle is computed here the same way, so the
intent the agent signs is exactly what the executor will accept:

* ``changed_paths`` is the union of the net diff ``base..tip`` and every path named by any
  commit in between (so a file added and then reverted still appears), sorted and unique.
* ``diff_digest`` is the sha256 of the raw bytes of
  ``git diff-tree -r -z --no-renames --no-commit-id --raw --abbrev=40 <base> <tip>``:
  plumbing output that does not depend on the user's git settings.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .canonical import sha256_hex

# The same arguments the executor uses (tempus_github_app.git_push.DIFF_DIGEST_ARGS).
DIFF_DIGEST_ARGS: tuple[str, ...] = (
    "diff-tree", "-r", "-z", "--no-renames", "--no-commit-id", "--raw", "--abbrev=40",
)

_SHA_LENGTH = 40
_HEX = set("0123456789abcdef")


class GitError(RuntimeError):
    """git could not answer; the message says which command and why."""


@dataclass(frozen=True)
class GitResult:
    returncode: int
    stdout: bytes
    stderr: bytes


def _env() -> dict[str, str]:
    # Reading only. Prompts are off; the user's configuration stays, because reading a
    # repository must respect its settings.
    env = dict(os.environ)
    env.update({"GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"})
    return env


def git(repo: Path, *args: str, check: bool = True) -> GitResult:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=repo, env=_env(), capture_output=True, check=False, timeout=120,
        )
    except FileNotFoundError:
        raise GitError("git executable not found on PATH") from None
    except subprocess.TimeoutExpired:
        raise GitError(f"git {args[0]} timed out") from None
    if check and completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise GitError(f"git {' '.join(args)} failed: {detail or completed.returncode}")
    return GitResult(completed.returncode, completed.stdout, completed.stderr)


def resolve(repo: Path, rev: str) -> str:
    """The full lowercase sha of ``rev`` as a commit."""
    out = git(repo, "rev-parse", "--verify", "--quiet", rev + "^{commit}", check=False).stdout
    sha = out.decode("ascii", "replace").strip().lower()
    if len(sha) != _SHA_LENGTH or set(sha) - _HEX:
        raise GitError(f"{rev!r} is not a commit in this repository")
    return sha


def current_branch(repo: Path) -> str | None:
    out = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).stdout
    name = out.decode("utf-8", "replace").strip()
    return name or None


def is_ancestor(repo: Path, base: str, tip: str) -> bool:
    return git(repo, "merge-base", "--is-ancestor", base, tip, check=False).returncode == 0


def ref_exists(repo: Path, ref: str) -> bool:
    return git(repo, "rev-parse", "--verify", "--quiet", ref, check=False).returncode == 0


def changed_paths(repo: Path, base: str, tip: str) -> tuple[str, ...]:
    """Every path touched between ``base`` and ``tip``, as the executor computes it."""
    net = git(repo, "diff", "--name-only", "--no-renames", "-z", base, tip).stdout
    per_commit = git(
        repo, "log", "-m", "--no-renames", "--name-only", "-z", "--format=", f"{base}..{tip}",
    ).stdout
    try:
        output = (net + b"\0" + per_commit).decode("utf-8")
    except UnicodeDecodeError:
        raise GitError("a changed path is not valid UTF-8; the permit cannot name it") from None
    return tuple(sorted({name.strip("\n") for name in output.split("\0")} - {""}))


def diff_digest(repo: Path, base: str, tip: str) -> str:
    """sha256 of the raw diff-tree listing between ``base`` and ``tip``."""
    return sha256_hex(git(repo, *DIFF_DIGEST_ARGS, base, tip).stdout)


def create_bundle(repo: Path, base: str, branch: str, out: Path) -> str:
    """Write ``git bundle create <out> <base>..<branch>`` and return its sha256.

    git refuses a bare sha as the bundle head, so ``branch`` must be a ref name.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    git(repo, "bundle", "create", "--quiet", str(out), f"{base}..{branch}")
    return sha256_hex(out.read_bytes())


def remote_resource(repo: Path, remote: str = "origin") -> str | None:
    """``owner/repository`` from a GitHub remote URL, or None when it is not GitHub."""
    out = git(repo, "remote", "get-url", remote, check=False).stdout
    url = out.decode("utf-8", "replace").strip()
    for prefix in ("https://github.com/", "ssh://git@github.com/", "git@github.com:"):
        if url.startswith(prefix):
            path = url[len(prefix):].removesuffix(".git").strip("/")
            parts = path.split("/")
            if len(parts) == 2 and all(parts):
                return "/".join(parts)
    return None
