"""The pre-push hook: a branch leaves this machine only through a Tempus permit."""

from __future__ import annotations

from pathlib import Path

from . import gitfacts

HOOK_MARKER = "# tempus-guard-pre-push"

HOOK_SCRIPT = (
    "#!/bin/sh\n"
    f"{HOOK_MARKER}\n"
    "# Installed by `tempus guard hook install`. Agents publish through Tempus Guard for GitHub:\n"
    "#   tempus guard intent --branch <branch> --base origin/main ...   -> signed intent + bundle\n"
    "# and the mediated executor pushes once it holds the permit. A direct push from here\n"
    "# skips the gate, the permit and the \"Verified by Tempus\" check, so it is refused.\n"
    "# Set TEMPUS_GUARD_ALLOW_DIRECT_PUSH=1 to push directly on purpose (humans, hotfixes).\n"
    'if [ "$TEMPUS_GUARD_ALLOW_DIRECT_PUSH" = "1" ]; then\n'
    "  exit 0\n"
    "fi\n"
    'echo "tempus-guard: direct push refused; publish this branch through Tempus Guard" >&2\n'
    'echo "tempus-guard: run \'tempus guard intent --branch <branch> --base origin/main\'" >&2\n'
    'echo "tempus-guard: and hand the signed intent to the gate" >&2\n'
    'echo "tempus-guard: or set TEMPUS_GUARD_ALLOW_DIRECT_PUSH=1 for a deliberate direct push" >&2\n'
    "exit 1\n"
)


def hook_path(repo: Path) -> Path:
    out = gitfacts.git(repo, "rev-parse", "--git-path", "hooks/pre-push").stdout
    path = Path(out.decode("utf-8", "replace").strip())
    return path if path.is_absolute() else repo / path


def is_installed(repo: Path) -> bool:
    path = hook_path(repo)
    return path.exists() and HOOK_MARKER in path.read_text(encoding="utf-8", errors="replace")


def install(repo: Path, *, force: bool = False) -> Path:
    path = hook_path(repo)
    if path.exists() and not force:
        existing = path.read_text(encoding="utf-8", errors="replace")
        if HOOK_MARKER not in existing:
            raise FileExistsError(f"{path} exists and is not the CLI's; use --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HOOK_SCRIPT, encoding="utf-8", newline="\n")
    path.chmod(0o755)
    return path


def uninstall(repo: Path) -> Path | None:
    path = hook_path(repo)
    if not path.exists():
        return None
    if HOOK_MARKER not in path.read_text(encoding="utf-8", errors="replace"):
        raise FileExistsError(f"{path} is not the Tempus Guard hook; leaving it alone")
    path.unlink()
    return path
