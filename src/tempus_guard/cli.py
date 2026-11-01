"""``tempus-guard``: build and sign the push intent, request the permit, guard the branch.

Exit codes: 0 done; 1 the branch, keys or gate refused (the message says why); 2 usage.
Everything prints JSON on stdout so agents can consume it; messages go to stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__, gitfacts, hooks
from .intent import ACTION_TYPE, IntentError, action_id, build_push_intent, collect_push_facts
from .signing import KeyfileError, load_keyfile, sign_intent

_ENV = {
    "tenant_id": "TEMPUS_TENANT_ID",
    "agent_keyfile": "TEMPUS_AGENT_KEYFILE",
    "resource": "TEMPUS_RESOURCE",
    "base": "TEMPUS_BASE",
    "remote": "TEMPUS_REMOTE",
}


class CliError(Exception):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def _repo(value: str) -> Path:
    repo = Path(value).resolve()
    if not repo.is_dir():
        raise CliError(f"{repo} is not a directory", 2)
    out = gitfacts.git(repo, "rev-parse", "--show-toplevel", check=False)
    if out.returncode != 0:
        raise CliError(f"{repo} is not inside a git repository", 2)
    return Path(out.stdout.decode("utf-8", "replace").strip())


def _print(document: Any, out: Path | None = None) -> None:
    text = json.dumps(document, indent=2, ensure_ascii=False)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)


def cmd_intent(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    branch = args.branch or gitfacts.current_branch(repo)
    if not branch:
        raise CliError("--branch is required when HEAD is detached", 2)
    resource = args.resource or gitfacts.remote_resource(repo, args.remote)
    if not resource:
        raise CliError(
            f"--resource owner/repository is required; remote {args.remote!r} is not a GitHub URL", 2
        )
    if not args.tenant_id:
        raise CliError("--tenant-id (or TEMPUS_TENANT_ID) is required", 2)
    if not args.agent_keyfile:
        raise CliError("--agent-keyfile (or TEMPUS_AGENT_KEYFILE) is required", 2)
    public_key, private_key = load_keyfile(Path(args.agent_keyfile))

    if args.bundle_out:
        bundle_out = Path(args.bundle_out)
    else:
        safe = branch.replace("/", "__")
        bundle_out = repo / ".tempus" / "bundles" / f"{safe}.bundle"
    new_branch = None
    if args.new_branch:
        new_branch = True
    elif args.existing_branch:
        new_branch = False

    facts = collect_push_facts(
        repo, branch=branch, base=args.base, bundle_out=bundle_out, new_branch=new_branch,
        remote=args.remote,
    )
    intent = build_push_intent(
        facts, tenant_id=args.tenant_id, agent_id=public_key, resource=resource,
        idempotency_key=args.idempotency_key,
    )
    signed = sign_intent(intent, private_key)
    document = {
        "schema_version": "tempus-guard-cli.signed-intent.v1",
        "action_type": ACTION_TYPE,
        "action_id": action_id(args.tenant_id, public_key, intent["idempotency_key"]),
        "intent": signed["intent"],
        "agent_id": signed["agent_id"],
        "agent_signature": signed["agent_signature"],
        "bundle": {"path": str(bundle_out.resolve()), "sha256": facts.bundle_sha256},
        "next": (
            "hand intent, agent_id and agent_signature to the gate (request_action_signed, "
            "`tempus guard request`, or the Tempus MCP tool tempus_request_action_signed); the executor "
            "needs the permit and the bundle"
        ),
    }
    _print(document, Path(args.out) if args.out else None)
    print(
        f"tempus-guard: intent for {branch} -> {resource} ({len(facts.paths)} paths, "
        f"diff {facts.diff_sha256[:12]}..., bundle {facts.bundle_sha256[:12]}...)",
        file=sys.stderr,
    )
    return 0


def cmd_request(args: argparse.Namespace) -> int:
    try:
        from tempus_ddb import TempusDDB
    except ImportError:
        raise CliError(
            "`tempus guard request` needs the gate library: pip install 'tempus-guard-cli[gate]' "
            "(tempus-ddb >= 0.6)", 2
        ) from None
    try:
        document = json.loads(Path(args.signed).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CliError(f"cannot read the signed intent: {exc}", 2) from None
    for field in ("intent", "agent_id", "agent_signature"):
        if field not in document:
            raise CliError(f"signed intent is missing {field!r}", 2)
    gate = TempusDDB(args.gate_db, args.gate_keyfile)
    permit = gate.request_action_signed(
        json.dumps(document["intent"], ensure_ascii=False),
        document["agent_id"],
        document["agent_signature"],
        args.ttl_seconds,
    )
    _print(json.loads(permit), Path(args.out) if args.out else None)
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    if args.hook_command == "install":
        try:
            path = hooks.install(repo, force=args.force)
        except FileExistsError as exc:
            raise CliError(str(exc), 1) from None
        _print({"status": "installed", "hook": str(path)})
    elif args.hook_command == "uninstall":
        try:
            path = hooks.uninstall(repo)
        except FileExistsError as exc:
            raise CliError(str(exc), 1) from None
        _print({"status": "removed" if path else "absent", "hook": str(path) if path else None})
    else:
        _print({"installed": hooks.is_installed(repo), "hook": str(hooks.hook_path(repo))})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tempus-guard",
        description=(
            "Tempus Guard CLI, the local client of Tempus Guard for GitHub: turn a branch into a signed "
            "tempus.action-intent.v1 for github.push_branch, request the permit, and keep "
            "direct pushes out."
        ),
    )
    parser.add_argument("--version", action="version", version=f"tempus-guard {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    intent = sub.add_parser(
        "intent", help="Build and sign the push intent for a branch (writes the git bundle)"
    )
    intent.add_argument("--repo", default=".", help="Path inside the repository (default: .)")
    intent.add_argument("--branch", help="Branch to publish (default: the checked-out branch)")
    intent.add_argument(
        "--base", default=os.environ.get(_ENV["base"], "origin/main"),
        help="Commit the branch builds on, as GitHub has it (env: TEMPUS_BASE, default: origin/main)",
    )
    intent.add_argument(
        "--remote", default=os.environ.get(_ENV["remote"], "origin"),
        help="Remote that names the GitHub repository (env: TEMPUS_REMOTE, default: origin)",
    )
    intent.add_argument(
        "--tenant-id", default=os.environ.get(_ENV["tenant_id"]), help="Tempus tenant (env: TEMPUS_TENANT_ID)"
    )
    intent.add_argument(
        "--agent-keyfile", default=os.environ.get(_ENV["agent_keyfile"]),
        help="Agent Ed25519 key file from `tempus keygen` (env: TEMPUS_AGENT_KEYFILE)",
    )
    intent.add_argument(
        "--resource", default=os.environ.get(_ENV["resource"]),
        help="owner/repository (env: TEMPUS_RESOURCE, default: parsed from the remote URL)",
    )
    intent.add_argument(
        "--idempotency-key", help="Default: push:<branch>:<tip_sha> (same tip, same action)"
    )
    intent.add_argument("--bundle-out", help="Where to write the git bundle (default: .tempus/bundles/)")
    intent.add_argument("--out", help="Also write the signed intent to this file")
    claim = intent.add_mutually_exclusive_group()
    claim.add_argument("--new-branch", action="store_true", help="Claim the branch does not exist on GitHub")
    claim.add_argument(
        "--existing-branch", action="store_true",
        help="Claim the branch exists on GitHub at --base (default: inferred from the remote-tracking ref)",
    )
    intent.set_defaults(func=cmd_intent)

    request = sub.add_parser(
        "request", help="Hand a signed intent to a local gate and print the permit (needs tempus-ddb)"
    )
    request.add_argument("--signed", required=True, help="Output of `tempus guard intent`")
    request.add_argument("--gate-db", required=True, help="Gate SQLite database")
    request.add_argument("--gate-keyfile", required=True, help="Gate key file")
    request.add_argument("--ttl-seconds", type=int, default=60, help="Permit lifetime (default: 60)")
    request.add_argument("--out", help="Also write the permit to this file")
    request.set_defaults(func=cmd_request)

    hook = sub.add_parser("hook", help="Manage the pre-push hook that refuses direct pushes")
    hook.add_argument("--repo", default=".", help="Path inside the repository (default: .)")
    hook_sub = hook.add_subparsers(dest="hook_command", required=True)
    install = hook_sub.add_parser("install", help="Install the hook")
    install.add_argument("--force", action="store_true", help="Replace a foreign pre-push hook")
    hook_sub.add_parser("uninstall", help="Remove the Tempus Guard hook (a foreign hook is left alone)")
    hook_sub.add_parser("status", help="Say whether the Tempus Guard hook is installed")
    hook.set_defaults(func=cmd_hook)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except CliError as exc:
        print(f"tempus-guard: {exc}", file=sys.stderr)
        return exc.code
    except (IntentError, KeyfileError, gitfacts.GitError) as exc:
        print(f"tempus-guard: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        # The gate refused (request_action_signed raises RuntimeError with its reason).
        print(f"tempus-guard: gate refused: {exc}", file=sys.stderr)
        return 1


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
