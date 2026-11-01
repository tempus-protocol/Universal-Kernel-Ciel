"""`tempus guard intent` and `tempus guard hook` end to end, as an agent would call them."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
from tests.conftest import GIT_ENV, Repos, git

from tempus_guard import verify_intent_signature
from tempus_guard.cli import main


def run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tempus_guard", *args],
        env={**GIT_ENV, **(env or {})}, capture_output=True, text=True, encoding="utf-8",
    )


def test_version_and_help():
    assert run("--version").stdout.startswith("tempus-guard 2.")
    out = run("--help").stdout
    assert "intent" in out and "hook" in out and "request" in out


def test_intent_prints_a_signed_document_and_writes_the_bundle(repos: Repos, agent_keyfile, tmp_path):
    repos.write("src/app.py", "print('fix')\n")
    tip = repos.commit("fix")
    out_file = tmp_path / "signed.json"
    completed = run(
        "intent", "--repo", str(repos.work), "--tenant-id", "tenant-tempus-guard",
        "--agent-keyfile", str(agent_keyfile), "--out", str(out_file),
    )
    assert completed.returncode == 0, completed.stderr
    document = json.loads(completed.stdout)
    assert document == json.loads(out_file.read_text(encoding="utf-8"))
    assert document["schema_version"] == "tempus-guard-cli.signed-intent.v1"
    intent = document["intent"]
    assert intent["resource"] == "acme/widget"  # parsed from the GitHub remote URL
    assert intent["input"]["tip_sha"] == tip and intent["input"]["paths"] == ["src/app.py"]
    assert verify_intent_signature(intent, document["agent_id"], document["agent_signature"])
    bundle = document["bundle"]["path"]
    assert bundle.endswith("agent__fix-123.bundle") and os.path.exists(bundle)
    assert len(document["action_id"]) == 64
    assert "private_key" not in completed.stdout


def test_intent_takes_its_configuration_from_the_environment(repos: Repos, agent_keyfile):
    repos.write("a", "1\n")
    repos.commit("a")
    completed = run(
        "intent", "--repo", str(repos.work),
        env={
            "TEMPUS_TENANT_ID": "env-tenant",
            "TEMPUS_AGENT_KEYFILE": str(agent_keyfile),
            "TEMPUS_RESOURCE": "org/repo",
        },
    )
    assert completed.returncode == 0, completed.stderr
    intent = json.loads(completed.stdout)["intent"]
    assert intent["tenant_id"] == "env-tenant" and intent["resource"] == "org/repo"


def test_missing_configuration_is_a_usage_error(repos: Repos):
    repos.write("a", "1\n")
    repos.commit("a")
    completed = run("intent", "--repo", str(repos.work))
    assert completed.returncode == 2
    assert "tenant-id" in completed.stderr


def test_a_branch_without_commits_is_refused(repos: Repos, agent_keyfile):
    completed = run(
        "intent", "--repo", str(repos.work), "--tenant-id", "t", "--agent-keyfile", str(agent_keyfile),
    )
    assert completed.returncode == 1
    assert "no commits beyond" in completed.stderr


def test_hook_refuses_direct_pushes_until_allowed(repos: Repos, capsys):
    assert main(["hook", "--repo", str(repos.work), "status"]) == 0
    assert json.loads(capsys.readouterr().out)["installed"] is False
    assert main(["hook", "--repo", str(repos.work), "install"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "installed"
    repos.write("a", "1\n")
    repos.commit("a")

    refused = subprocess.run(
        ["git", "push", "--quiet", "origin", f"HEAD:refs/heads/{repos.branch}"],
        cwd=repos.work, env=GIT_ENV, capture_output=True, text=True,
    )
    assert refused.returncode != 0
    assert "direct push refused" in refused.stderr
    allowed = subprocess.run(
        ["git", "push", "--quiet", "origin", f"HEAD:refs/heads/{repos.branch}"],
        cwd=repos.work, env={**GIT_ENV, "TEMPUS_GUARD_ALLOW_DIRECT_PUSH": "1"},
        capture_output=True, text=True,
    )
    assert allowed.returncode == 0, allowed.stderr

    assert main(["hook", "--repo", str(repos.work), "uninstall"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "removed"


def test_hook_leaves_a_foreign_hook_alone(repos: Repos, capsys):
    hooks_dir = repos.work / ".git" / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "pre-push").write_text("#!/bin/sh\nexit 0\n")
    assert main(["hook", "--repo", str(repos.work), "install"]) == 1
    assert "not the CLI's" in capsys.readouterr().err
    assert main(["hook", "--repo", str(repos.work), "uninstall"]) == 1
    assert main(["hook", "--repo", str(repos.work), "install", "--force"]) == 0


def test_outside_a_repository_is_a_usage_error(tmp_path):
    assert main(["hook", "--repo", str(tmp_path), "status"]) == 2


@pytest.mark.skipif(
    subprocess.run([sys.executable, "-c", "import tempus_ddb"], capture_output=True).returncode != 0,
    reason="`tempus guard request` needs tempus-ddb",
)
def test_request_hands_the_signed_intent_to_a_local_gate(repos: Repos, agent_keyfile, tmp_path):
    import tempus_ddb

    repos.write("a", "1\n")
    repos.commit("a")
    public = json.loads(agent_keyfile.read_text())["public_key"]
    gate_keys = tmp_path / "gate.keys.json"
    tempus_ddb.gen_keys(str(gate_keys))
    gate_db = tmp_path / "gate.db"
    gate = tempus_ddb.TempusDDB(str(gate_db), str(gate_keys))
    gate_id = json.loads(gate_keys.read_text(encoding="utf-8"))["public_key"]
    gate.register_agent(gate_id, "tempus-gate", '{"can_delegate":true}')
    gate.register_agent(public, "guard-agent", json.dumps({"tenant_id": "tenant-tempus-guard"}))
    with pytest.warns(UserWarning):
        gate.install_allow_all_dev_policy()
    del gate

    signed = tmp_path / "signed.json"
    assert run(
        "intent", "--repo", str(repos.work), "--tenant-id", "tenant-tempus-guard",
        "--agent-keyfile", str(agent_keyfile), "--out", str(signed),
    ).returncode == 0
    completed = run(
        "request", "--signed", str(signed), "--gate-db", str(gate_db), "--gate-keyfile", str(gate_keys),
    )
    assert completed.returncode == 0, completed.stderr
    permit = json.loads(completed.stdout)
    assert permit["authorization"]["decision"] == "ALLOWED"
    assert permit["authorization"]["action_id"] == json.loads(signed.read_text())["action_id"]
    git(repos.work, "status")  # the repository is untouched
