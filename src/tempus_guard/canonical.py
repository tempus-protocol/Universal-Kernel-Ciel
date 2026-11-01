"""Tempus canonical JSON, as the gate computes it before signing or verifying.

Mirrors ``canonicalize`` in tempus-ddb (``src/b2a.rs``): object keys sorted by code point
(which is UTF-8 byte order), no whitespace, strings escaped the way serde_json escapes them
(quote, backslash and control characters; everything else, non-ASCII included, written raw).
Python's ``json.dumps`` produces exactly that with ``sort_keys``, compact separators and
``ensure_ascii=False``. Intents carry only strings, booleans, integers, arrays and objects,
so no float spelling question arises here; a float is refused rather than guessed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _reject_floats(value: Any, path: str = "$") -> None:
    if isinstance(value, float):
        raise ValueError(f"{path}: floats have no single canonical spelling; use an integer or a string")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path}: object keys must be strings")
            _reject_floats(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_floats(item, f"{path}[{index}]")


def canonical_json(value: Any) -> str:
    """The canonical text whose bytes the agent signs and the gate verifies."""
    _reject_floats(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
