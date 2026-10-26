"""Versioned REST boundary. No engine imports or scientific calculations."""
import errno
import hashlib
import json
import logging
import math
import os
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
from uuid import uuid4


MAX_RESPONSE = 16 * 1024 * 1024
logger = logging.getLogger(__name__)


def strict_json(raw):
    def reject_constant(value):
        raise ValueError("Nonfinite JSON")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique)


def digest(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {"algorithm": "sha256", "value": hashlib.sha256(payload.encode()).hexdigest()}


class EngineError(Exception):
    def __init__(self, code, message, status=502, details=None):
        super().__init__(message)
        self.code, self.status, self.details = code, status, details


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ACMGClient:
    def __init__(self):
        self.url = os.environ.get("ACMG_ENGINE_URL", "http://127.0.0.1:8000").rstrip("/")
        parsed = urlsplit(self.url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise EngineError("CONFIGURATION_ERROR", "Invalid ACMG_ENGINE_URL", 503)
        self.timeout = float(os.environ.get("ACMG_ENGINE_TIMEOUT", "15"))
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise EngineError("CONFIGURATION_ERROR", "ACMG_ENGINE_TIMEOUT must be a positive finite number", 503)
        self.correlation_id = uuid4().hex
        self.last_request_id = None

    def call(self, path, payload=None, allow_array=False):
        data = json.dumps(payload, allow_nan=False).encode() if payload is not None else None
        headers = {"Content-Type": "application/json", "Accept": "application/json", "X-Correlation-ID": self.correlation_id}
        token = os.environ.get("ACMG_ENGINE_TOKEN")
        if token:
            headers["Authorization"] = "Bearer " + token
        request = Request(self.url + path, data=data, headers=headers)
        try:
            with build_opener(NoRedirect).open(request, timeout=self.timeout) as response:
                self.last_request_id = getattr(response, "headers", {}).get("X-Request-ID")
                raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise EngineError("RESPONSE_TOO_LARGE", "ACMG response exceeds local limit")
                document = strict_json(raw)
                if not isinstance(document, dict) and not (allow_array and isinstance(document, list)):
                    raise EngineError("INVALID_RESPONSE", "ACMG Engine response must be a JSON object")
                return document
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read(MAX_RESPONSE))
            except (ValueError, OSError):
                detail = {}
            error = detail.get("error", {}) if isinstance(detail, dict) else {}
            raise EngineError(error.get("code", "ENGINE_HTTP_ERROR"), error.get("message", "ACMG request failed"),
                              422 if exc.code in (400, 404, 409, 422) else 502, detail) from None
        except (URLError, OSError) as exc:
            cause = exc.reason if isinstance(exc, URLError) else exc
            if isinstance(cause, TimeoutError):
                reason, explanation = "TIMEOUT", f"request timed out after {self.timeout:g}s"
            elif isinstance(cause, ConnectionRefusedError) or getattr(cause, "errno", None) == errno.ECONNREFUSED:
                reason, explanation = "CONNECTION_REFUSED", "connection refused; the service is not listening"
            elif isinstance(cause, socket.gaierror):
                reason, explanation = "HOST_NOT_FOUND", "host could not be resolved"
            else:
                reason, explanation = "CONNECTION_FAILED", "connection failed"
            raise EngineError(
                "ENGINE_UNAVAILABLE",
                f"ACMG Engine unavailable at {self.url}: {explanation}. "
                "Start ACMG Engine or check ACMG_ENGINE_URL in the HELPER server environment.",
                503, {"engine_url": self.url, "reason": reason, "timeout_seconds": self.timeout},
            ) from None
        except (ValueError, UnicodeError):
            raise EngineError("INVALID_RESPONSE", "ACMG Engine returned invalid JSON") from None

    def discover(self):
        health = self.call("/health")
        cap = self.call("/v1/capabilities")
        if health.get("service") != "acmg-engine" or health.get("status") != "ok" or cap.get("api_version") != "v1" or cap.get("schema_version") != "1.0":
            raise EngineError("INCOMPATIBLE_API", "Requires ACMG Engine API v1 / schema 1.0", 409)
        schema = self.call("/openapi.json")
        required = ("/v1/evidence-packets/interpret", "/v1/interpretations/compare", "/v1/profiles/applicable")
        if any(p not in schema.get("paths", {}) for p in required):
            raise EngineError("INCOMPATIBLE_API", "Required ACMG endpoints are absent", 409)
        return {"health": health, "capabilities": cap, "criteria": self.call("/v1/criteria"),
                "schemas": schema.get("components", {}).get("schemas", {})}

    def profiles(self, context):
        params = {}
        for kind in ("gene", "disease"):
            if context.get(kind):
                params[kind + "_namespace"] = context[kind]["namespace"]
                params[kind + "_id"] = context[kind]["identifier"]
        return self.call("/v1/profiles/applicable?" + urlencode(params))["profiles"]


def profile_reference(profile):
    """API v1 RuleProfile.reference canonicalization, verified against real service tests.

    A transport checksum only: this does not resolve any scientific profile rules.
    """
    declaration = dict(profile)
    if not declaration.get("overridable_criteria"):
        declaration.pop("overridable_criteria", None)
    return {"profile_id": profile["profile_id"], "version": profile["version"], "artifact_digest": digest(declaration)}


def configuration(profiles, selected):
    lookup = {(p["profile_id"], p["version"]): p for p in profiles}
    try:
        chain = [lookup[(r["profile_id"], r["version"])] for r in selected]
    except (KeyError, TypeError):
        raise ValueError("Profile/version is unavailable for this exact gene-disease context")
    if not chain or len(chain) > 2:
        raise ValueError("Select a generic profile and optionally one specialization")
    base = chain[0]
    if base["applicability"]["specificity"] != "NONE":
        raise ValueError("Base profile must be generic")
    if any(p["strategy"] != base["strategy"] or p["release_status"] in ("DRAFT", "DEPRECATED") for p in chain):
        raise ValueError("Unsupported profile/strategy combination")
    if len(chain) == 2 and chain[1]["applicability"]["specificity"] == "NONE":
        raise ValueError("Second profile must be a specialization")
    return {"configuration_id": "helper-" + digest(selected)["value"][:24],
            "strategy": base["strategy"], "specificity": chain[-1]["applicability"]["specificity"],
            "base_profile": profile_reference(base), "specializations": [profile_reference(p) for p in chain[1:]],
            "modifications": [], "profile_usage": "RESEARCH",
            "incomplete_evidence_policy": "REPORT_WITHOUT_CLASSIFICATION"}
