"""Canonical checksums shared by local ACMG data and provenance."""
import hashlib
import json


def digest(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {"algorithm": "sha256", "value": hashlib.sha256(payload.encode()).hexdigest()}
