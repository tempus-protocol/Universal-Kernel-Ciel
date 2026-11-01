"""A throwaway GitHub-like setup: a bare remote with main, and an agent clone on a branch."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_AUTHOR_NAME": "Agent",
    "GIT_AUTHOR_EMAIL": "agent@example.test",
    "GIT_COMMITTER_NAME": "Agent",
    "GIT_COMMITTER_EMAIL": "agent@example.test",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
}


def git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "-c", "protocol.file.allow=always", *args],
        cwd=cwd, env=GIT_ENV, capture_output=True, check=True,
    )
    return completed.stdout.decode().strip()


class Repos:
    def __init__(self, root: Path, branch: str = "agent/fix-123"):
        self.root = root
        self.remote = root / "remote.git"
        self.work = root / "work"
        self.branch = branch
        git(root, "init", "--quiet", "--bare", str(self.remote))
        git(root, "init", "--quiet", str(self.work))
        # The remote URL names GitHub (the resource comes from it); pushes go to the bare
        # repo standing in for it, and remote-tracking refs are set by hand.
        git(self.work, "remote", "add", "origin", "https://github.com/acme/widget.git")
        git(self.work, "config", "remote.origin.pushurl", self.remote.as_uri())
        self.write("README.md", "hello\n")
        self.commit("base")
        self.push_remote("main", self.head())
        self.base = self.head()
        git(self.work, "switch", "--quiet", "-c", branch)

    def push_remote(self, branch: str, sha: str) -> None:
        """Put ``branch`` at ``sha`` on the stand-in GitHub and in origin's tracking refs."""
        git(self.work, "push", "--quiet", self.remote.as_uri(), f"{sha}:refs/heads/{branch}")
        git(self.work, "update-ref", f"refs/remotes/origin/{branch}", sha)

    def write(self, path: str, content: str) -> None:
        target = self.work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def remove(self, path: str) -> None:
        (self.work / path).unlink()

    def commit(self, message: str) -> str:
        git(self.work, "add", "-A")
        git(self.work, "commit", "--quiet", "--allow-empty", "-m", message)
        return self.head()

    def head(self) -> str:
        return git(self.work, "rev-parse", "HEAD")


@pytest.fixture
def repos(tmp_path: Path) -> Repos:
    return Repos(tmp_path)


@pytest.fixture
def agent_keyfile(tmp_path: Path) -> Path:
    key = Ed25519PrivateKey.generate()
    path = tmp_path / "agent.keys.json"
    public = key.public_key().public_bytes_raw().hex()
    private = key.private_bytes_raw().hex()
    path.write_text(f'{{"public_key": "{public}", "private_key": "{private}"}}', encoding="utf-8")
    return path
