"""The intent the CLI signs is what the executor re-derives and what the gate verifies."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from tests.conftest import GIT_ENV, Repos, git

from tempus_guard import (
    DIFF_DIGEST_ARGS,
    IntentError,
    KeyfileError,
    action_id,
    build_push_intent,
    canonical_json,
    collect_push_facts,
    load_keyfile,
    sign_intent,
    verify_intent_signature,
)
from tempus_guard.gitfacts import remote_resource

TENANT = "tenant-tempus-guard"


def facts_for(repos: Repos, **kwargs):
    return collect_push_facts(
        repos.work, branch=repos.branch, base="origin/main",
        bundle_out=repos.root / "agent.bundle", **kwargs,
    )


def test_push_facts_name_the_tip_the_base_the_paths_and_the_digests(repos):
    repos.write("src/app.py", "print('fix')\n")
    tip = repos.commit("fix")
    facts = facts_for(repos)

    assert facts.branch == "agent/fix-123"
    assert facts.base_sha == repos.base and facts.tip_sha == tip
    assert facts.new_branch is True
    assert facts.paths == ("src/app.py",)
    raw = subprocess.run(
        ["git", *DIFF_DIGEST_ARGS, repos.base, tip], cwd=repos.work, env=GIT_ENV,
        capture_output=True, check=True,
    ).stdout
    assert facts.diff_sha256 == hashlib.sha256(raw).hexdigest()
    bundle = Path(facts.bundle_path)
    assert facts.bundle_sha256 == hashlib.sha256(bundle.read_bytes()).hexdigest()
    # The bundle is thin on base and heads at the branch, exactly what the executor unbundles.
    verify = subprocess.run(
        ["git", "bundle", "list-heads", str(bundle)], cwd=repos.work, env=GIT_ENV,
        capture_output=True, check=True,
    ).stdout.decode()
    assert f"{tip} refs/heads/agent/fix-123" in verify


def test_paths_include_files_a_later_commit_reverts(repos):
    repos.write("a.txt", "1\n")
    repos.write("tmp.txt", "scratch\n")
    repos.commit("add")
    repos.remove("tmp.txt")
    repos.commit("drop scratch")
    facts = facts_for(repos)
    # Net diff shows only a.txt; the per-commit union also names tmp.txt, as the executor does.
    assert facts.paths == ("a.txt", "tmp.txt")


def test_the_digest_follows_the_content_not_only_the_paths(repos):
    repos.write("a.txt", "one\n")
    repos.commit("one")
    first = facts_for(repos).diff_sha256
    repos.write("a.txt", "two\n")
    repos.commit("two")
    assert facts_for(repos).diff_sha256 != first


def test_an_existing_remote_branch_is_not_claimed_as_new(repos):
    repos.write("a.txt", "1\n")
    repos.commit("a")
    repos.push_remote(repos.branch, repos.base)
    assert facts_for(repos).new_branch is False
    assert facts_for(repos, new_branch=True).new_branch is True


def test_a_branch_without_new_commits_is_refused(repos):
    with pytest.raises(IntentError, match="no commits beyond"):
        facts_for(repos)


def test_a_branch_that_does_not_build_on_the_base_is_refused(repos):
    repos.write("y", "2\n")
    repos.commit("y")
    # main moved on GitHub to a commit the branch does not contain.
    git(repos.work, "switch", "--quiet", "main")
    repos.write("z", "3\n")
    moved = repos.commit("z")
    git(repos.work, "update-ref", "refs/remotes/origin/main", moved)
    git(repos.work, "switch", "--quiet", repos.branch)
    with pytest.raises(IntentError, match="not an ancestor"):
        facts_for(repos)


def test_the_intent_is_the_v1_contract_with_the_facts_as_input(repos, agent_keyfile):
    repos.write("src/app.py", "print('fix')\n")
    tip = repos.commit("fix")
    public, _ = load_keyfile(agent_keyfile)
    facts = facts_for(repos)
    intent = build_push_intent(
        facts, tenant_id=TENANT, agent_id=public, resource="acme/widget", requested_at=1_700_000_000_000_000,
    )
    assert intent == {
        "schema_version": "tempus.action-intent.v1",
        "tenant_id": TENANT,
        "agent_id": public,
        "idempotency_key": f"push:agent/fix-123:{tip}",
        "action_type": "github.push_branch",
        "resource": "acme/widget",
        "requested_at": 1_700_000_000_000_000,
        "input": {
            "branch": "agent/fix-123",
            "base_sha": repos.base,
            "tip_sha": tip,
            "new_branch": True,
            "bundle_sha256": facts.bundle_sha256,
            "paths": ["src/app.py"],
            "diff_sha256": facts.diff_sha256,
        },
    }
    assert action_id(TENANT, public, intent["idempotency_key"]) == hashlib.sha256(
        b"tempus.action.v1\0" + TENANT.encode() + b"\0" + public.encode() + b"\0"
        + intent["idempotency_key"].encode()
    ).hexdigest()


@pytest.mark.parametrize("field,value", [
    ("tenant_id", ""),
    ("tenant_id", "has space"),
    ("agent_id", "ABC"),
    ("resource", "acme"),
    ("resource", "acme/widget/extra"),
])
def test_intent_arguments_are_validated(repos, agent_keyfile, field, value):
    repos.write("a", "1\n")
    repos.commit("a")
    public, _ = load_keyfile(agent_keyfile)
    kwargs = {"tenant_id": TENANT, "agent_id": public, "resource": "acme/widget", field: value}
    with pytest.raises(IntentError):
        build_push_intent(facts_for(repos), **kwargs)


def test_canonical_json_matches_the_gate_rules():
    value = {"z": 1, "a": {"ñ": "é/\"\\\n", "b": [True, None, "x"]}, "m": "日本"}
    assert canonical_json(value) == '{"a":{"b":[true,null,"x"],"ñ":"é/\\"\\\\\\n"},"m":"日本","z":1}'
    with pytest.raises(ValueError):
        canonical_json({"amount": 1.5})


def test_signature_is_ed25519_over_the_canonical_intent(repos, agent_keyfile):
    repos.write("a", "1\n")
    repos.commit("a")
    public, private = load_keyfile(agent_keyfile)
    intent = build_push_intent(facts_for(repos), tenant_id=TENANT, agent_id=public, resource="acme/widget")
    signed = sign_intent(intent, private)
    assert signed["agent_id"] == public
    assert len(signed["agent_signature"]) == 128
    assert verify_intent_signature(intent, public, signed["agent_signature"])
    tampered = {**intent, "input": {**intent["input"], "paths": ["a", "b"]}}
    assert not verify_intent_signature(tampered, public, signed["agent_signature"])
    with pytest.raises(KeyfileError):
        sign_intent({**intent, "agent_id": "0" * 64}, private)


def test_keyfile_must_be_a_matching_pair(tmp_path, agent_keyfile):
    data = json.loads(agent_keyfile.read_text())
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({**data, "public_key": "0" * 64}))
    with pytest.raises(KeyfileError, match="belong"):
        load_keyfile(bad)
    with pytest.raises(KeyfileError, match="not found"):
        load_keyfile(tmp_path / "missing.json")
    bad.write_text("[]")
    with pytest.raises(KeyfileError):
        load_keyfile(bad)


def test_remote_resource_reads_github_urls_only(repos):
    git(repos.work, "remote", "set-url", "origin", "git@github.com:acme/widget.git")
    assert remote_resource(repos.work) == "acme/widget"
    git(repos.work, "remote", "set-url", "origin", "https://github.com/acme/widget")
    assert remote_resource(repos.work) == "acme/widget"
    git(repos.work, "remote", "set-url", "origin", "https://gitlab.example.com/acme/widget.git")
    assert remote_resource(repos.work) is None


tempus_ddb = pytest.importorskip("tempus_ddb", reason="the gate conformance check needs tempus-ddb")


def test_the_gate_accepts_what_the_cli_signs(repos, agent_keyfile, tmp_path):
    """request_action_signed verifies our canonical form and signature and issues the permit."""
    repos.write("src/app.py", "print('fix')\n")
    repos.commit("fix")
    public, private = load_keyfile(agent_keyfile)
    gate_keys = tmp_path / "gate.keys.json"
    tempus_ddb.gen_keys(str(gate_keys))
    gate = tempus_ddb.TempusDDB(str(tmp_path / "gate.db"), str(gate_keys))
    # The first registration bootstraps the gate's own key; then the agent.
    gate_id = json.loads(gate_keys.read_text(encoding="utf-8"))["public_key"]
    gate.register_agent(gate_id, "tempus-gate", '{"can_delegate":true}')
    gate.register_agent(public, "guard-agent", json.dumps({"tenant_id": TENANT}))
    with pytest.warns(UserWarning):
        gate.install_allow_all_dev_policy()

    intent = build_push_intent(facts_for(repos), tenant_id=TENANT, agent_id=public, resource="acme/widget")
    signed = sign_intent(intent, private)
    permit = json.loads(gate.request_action_signed(
        json.dumps(intent, ensure_ascii=False), signed["agent_id"], signed["agent_signature"], 60,
    ))
    assert permit["authorization"]["decision"] == "ALLOWED"
    assert permit["intent"]["input"]["diff_sha256"] == intent["input"]["diff_sha256"]
    assert permit["authorization"]["action_id"] == action_id(TENANT, public, intent["idempotency_key"])
