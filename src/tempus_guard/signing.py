"""Sign an intent with the agent's Ed25519 key, the way the gate verifies it.

The gate's ``request_action_signed(intent, agent_id, agent_signature)`` checks the
signature over the canonical bytes of the intent; ``agent_id`` is the hex public key. Key
files are the ones ``tempus keygen`` writes:
``{"public_key": <hex32>, "private_key": <hex32>}``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .canonical import canonical_json

_HEX32 = re.compile(r"^[0-9a-f]{64}$")


class KeyfileError(ValueError):
    """The key file is missing, malformed or does not hold an Ed25519 key pair."""


def load_keyfile(path: Path) -> tuple[str, str]:
    """``(public_key_hex, private_key_hex)`` after checking the pair belongs together."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise KeyfileError(f"key file not found: {path}") from None
    except (OSError, ValueError) as exc:
        raise KeyfileError(f"key file {path} is not readable JSON: {exc}") from None
    if not isinstance(data, dict):
        raise KeyfileError("key file must be a JSON object")
    public = str(data.get("public_key", "")).lower()
    private = str(data.get("private_key", "")).lower()
    if not _HEX32.fullmatch(public) or not _HEX32.fullmatch(private):
        raise KeyfileError("key file needs 'public_key' and 'private_key' as 64 hex characters")
    derived = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private)).public_key()
    if derived.public_bytes_raw().hex() != public:
        raise KeyfileError("public_key does not belong to private_key")
    return public, private


def sign_intent(intent: dict[str, Any], private_key_hex: str) -> dict[str, Any]:
    """The arguments of ``request_action_signed``: intent, agent_id and agent_signature."""
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    agent_id = key.public_key().public_bytes_raw().hex()
    if intent.get("agent_id") != agent_id:
        raise KeyfileError("intent.agent_id is not the public key of the signing key")
    canonical = canonical_json(intent)
    signature = key.sign(canonical.encode("utf-8")).hex()
    return {"intent": intent, "agent_id": agent_id, "agent_signature": signature}


def verify_intent_signature(intent: dict[str, Any], agent_id: str, signature: str) -> bool:
    try:
        public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(agent_id))
        public.verify(bytes.fromhex(signature), canonical_json(intent).encode("utf-8"))
    except (InvalidSignature, ValueError):
        return False
    return True
