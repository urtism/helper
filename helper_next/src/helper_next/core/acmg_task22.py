"""Task 22 REST contracts and annotation transport. No scientific evaluation."""
import copy
import json
import logging
import os
import time
from datetime import datetime, timezone
from urllib.parse import quote

from jsonschema import Draft202012Validator

from helper_next.core.acmg_client import ACMGClient, EngineError, digest
from helper_next.core.analysis_history import now


logger = logging.getLogger(__name__)
PROTOCOLS = ("ACMG_2015", "CLINGEN_GENERAL")


class Task22Client(ACMGClient):
    def __init__(self):
        super().__init__()
        self.openapi = None
        self.transport_requests = []

    def call(self, path, payload=None, allow_array=False):
        # Only reads are retried. Never repeat an evaluation or append operation.
        attempts = 2 if payload is None else 1
        for attempt in range(attempts):
            try:
                return super().call(path, payload, allow_array=allow_array)
            except EngineError as exc:
                logger.warning(json.dumps({"event": "acmg_transport_error", "correlation_id": self.correlation_id,
                                           "error_code": exc.code, "attempt": attempt + 1}))
                if exc.status not in (502, 503) or attempt + 1 == attempts:
                    raise
                time.sleep(0.1)

    def validate(self, value, schema):
        document = dict(schema, components=self.openapi.get("components", {}))
        error = next(Draft202012Validator(document, format_checker=Draft202012Validator.FORMAT_CHECKER).iter_errors(value), None)
        if error:
            # Do not log or echo clinical values from schema validation errors.
            raise EngineError("INVALID_TASK22_CONTRACT", "Task 22 schema validation failed", 422,
                              {"path": list(error.absolute_path), "validator": error.validator})

    def invoke(self, path, payload=None, template=None):
        if self.openapi is None:
            self.openapi = self.call("/openapi.json")
        method = "get" if payload is None else "post"
        operation = self.openapi.get("paths", {}).get(template or path, {}).get(method)
        if not operation:
            raise EngineError("UNSUPPORTED_TASK22_API", "Required Task 22 operation is unavailable", 409)
        if payload is not None:
            self.validate(payload, operation["requestBody"]["content"]["application/json"]["schema"])
        response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        result = self.call(path, payload, allow_array=response_schema.get("type") == "array")
        self.validate(result, response_schema)
        self.transport_requests.append({"operation": template or path, "method": method.upper(),
                                        "engine_request_id": self.last_request_id})
        logger.info(json.dumps({"event": "acmg_http_completed", "correlation_id": self.correlation_id,
                               "engine_request_id": self.last_request_id, "operation": template or path, "method": method.upper()}))
        return result

    def discover_task22(self):
        health = self.call("/health")
        capabilities = self.call("/v1/capabilities")
        if health.get("service") != "acmg-engine" or health.get("status") != "ok" or capabilities.get("api_version") != "v1" or capabilities.get("schema_version") != "1.0":
            raise EngineError("INCOMPATIBLE_API", "Task 22 requires a healthy ACMG Engine API v1", 409)
        self.openapi = self.call("/openapi.json")
        for path in ("/v1/evidence-contracts/schema", "/v1/evidence-contracts/validate",
                     "/v1/evidence/requirements", "/v1/criteria/evaluate"):
            if path not in self.openapi.get("paths", {}):
                raise EngineError("UNSUPPORTED_TASK22_API", "This engine does not implement Task 22", 409)
        # There is no protocol-list endpoint. Probe explicitly pinned manifests.
        version = os.environ.get("ACMG_CRITERIA_PROTOCOL_VERSION", "1.0.0")
        manifests = [self.invoke("/v1/criteria-protocols/{}/{}".format(p, quote(version, safe="")),
                                template="/v1/criteria-protocols/{protocol}/{version}") for p in PROTOCOLS]
        schema = self.invoke("/v1/evidence-contracts/schema")
        if schema.get("properties", {}).get("schema_version", {}).get("const") != "evidence-contract-1.0":
            raise EngineError("INCOMPATIBLE_SCHEMA", "Requires evidence-contract-1.0", 409)
        overrides, override_discovery = [], {"status": "AVAILABLE"}
        try:
            overrides = self.invoke("/v1/criteria/tree-overrides")
        except EngineError as exc:
            # Current engine includes a legacy /criteria/{code} route before
            # this static route. OpenAPI presence is not proof of reachability.
            override_discovery = {"status": "UNAVAILABLE", "code": exc.code, "message": str(exc)}
        return {"health": health, "capabilities": capabilities, "protocols": manifests,
                "contract_schema": schema, "schemas": self.openapi.get("components", {}).get("schemas", {}),
                "tree_overrides": [{"definition": override, "reference": {
                    "profile_id": override["profile_id"], "version": override["version"], "artifact_digest": digest(override)}}
                    for override in overrides], "tree_override_discovery": override_discovery,
                "correlation_id": self.correlation_id}

    def bundles(self, matrix):
        bundles = {}
        for criterion in matrix["criteria"]:
            identifier = criterion["execution"]["execution_id"]
            bundle = self.invoke("/v1/criteria/executions/{}/replay-bundle".format(quote(identifier, safe="")),
                                 template="/v1/criteria/executions/{execution_id}/replay-bundle")
            if bundle["trace"] != criterion["execution"]:
                raise EngineError("TRACE_MISMATCH", "Replay bundle differs from matrix execution")
            if digest(bundle["tree"]) != bundle["trace"]["tree_digest"]:
                raise EngineError("TREE_MISMATCH", "Replay tree checksum differs from recorded execution")
            bundles[criterion["criterion_id"]] = bundle
        return bundles


def canonical_import(item):
    """Pinned serialization of HELPER's two supported annotation evidence types.

    Defaults/omissions follow Task 22's Population/Computational serializers.
    The remote Pydantic contract remains authoritative, including semantic checks.
    """
    value = copy.deepcopy(item)
    value.setdefault("related_evidence_ids", [])
    value.setdefault("limitations", [])
    prov = value["provenance"]
    prov["acquired_at"] = datetime.fromisoformat(prov["acquired_at"].replace("Z", "+00:00")).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if prov.get("verification"):
        raw = prov["verification"]["verified_at"]
        prov["verification"]["verified_at"] = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    for key, default in (("source_url", None), ("references", []), ("artifact_digest", None),
                         ("limitations", []), ("verification", None)):
        prov.setdefault(key, default)
    observation = value["observation"]
    if value["kind"] == "POPULATION":
        observation.setdefault("aggregate", None)
        observation.setdefault("populations", [])
        observation.setdefault("coverage_notes", [])
        for row in [observation["aggregate"], *observation["populations"]]:
            if row is None:
                continue
            for key in ("allele_frequency", "allele_count", "allele_number", "homozygous_count"):
                row.setdefault(key, None)
            for key in ("hemizygous_count", "filtering_allele_frequency", "faf_confidence_level", "faf_definition",
                        "quality_status", "callable", "coverage_fraction", "mean_depth"):
                if row.get(key) is None:
                    row.pop(key, None)
            for key, default in (("filters", []), ("representation", "UNKNOWN"), ("population_kind", "UNKNOWN")):
                if row.get(key) == default:
                    row.pop(key, None)
        for key in ("dataset_id", "dataset_kind", "variant_identity", "variant_identifier"):
            if observation.get(key) is None:
                observation.pop(key, None)
        for key in ("exception_assessments", "clingen_applicability", "vcep_population_scope"):
            if not observation.get(key):
                observation.pop(key, None)
    elif value["kind"] == "COMPUTATIONAL":
        for key in ("predictor_version", "score", "interpretation", "transcript"):
            observation.setdefault(key, None)
        for key in list(observation):
            if key not in ("predictor", "predictor_version", "score", "interpretation", "transcript") and observation[key] in (None, []):
                observation.pop(key)
        if observation.get("spliceai"):
            # SpliceAIResult has no custom serializer; these are schema defaults.
            for key in ("acceptor_gain", "acceptor_loss", "donor_gain", "donor_loss", "maximum_delta",
                        "acceptor_gain_position", "acceptor_loss_position", "donor_gain_position", "donor_loss_position",
                        "canonical_dinucleotide", "mane_annotation", "masked", "maximum_distance", "reference_transcript",
                        "disease_relevant_splicing", "applicability_provenance"):
                observation["spliceai"].setdefault(key, None)
    else:
        raise ValueError("Unsupported automatic evidence mapping; use a validated provider envelope")
    return value


def provider_contract(workspace, additions=()):
    packet = workspace["normalized_evidence"]
    snapshot = packet["snapshot"]
    variant = snapshot["variant"]
    if variant["normalization"]["status"] != "NORMALIZED" or variant["normalization"].get("reference_validated") is not True:
        raise EngineError("REFERENCE_REQUIRED", "Task 22 requires a matching local FASTA and .fai. Configure HELPER_ACMG_REFERENCE_CONFIG and prepare the workspace again.", 409)
    if any(t.get("version") is None for t in snapshot["context"].get("transcripts", [])):
        raise EngineError("TRANSCRIPT_VERSION_REQUIRED", "Task 22 requires a versioned transcript from the annotation; no version is inferred.", 409)
    contract = {"schema_version": "evidence-contract-1.0", "variant": copy.deepcopy(variant),
                "context": copy.deepcopy(snapshot["context"]), "evidence": [],
                "dependencies": copy.deepcopy(snapshot.get("dependencies", []))}
    for item in snapshot["evidence"]:
        contract["evidence"].append(provider_envelope(item))
    for correction in additions:
        if set(correction) - {"evidence", "value", "replaces", "comment"} or not correction.get("comment", "").strip():
            raise ValueError("A provider correction requires evidence and a reason")
        if ("evidence" in correction) == ("value" in correction):
            raise ValueError("Supply either a full provider envelope or a supported structured evidence value")
        envelope = copy.deepcopy(correction["evidence"]) if "evidence" in correction else provider_envelope(correction["value"])
        if envelope["value"]["provenance"]["extraction_method"] != "MANUAL":
            raise ValueError("Manual corrections require MANUAL provenance")
        if not envelope["value"]["provenance"].get("source_version"):
            raise ValueError("Manual corrections require an explicit source version")
        replaces = correction.get("replaces")
        if replaces:
            if not any(e["value"]["id"] == replaces for e in contract["evidence"]):
                raise ValueError("Unknown replacement evidence ID")
            contract["evidence"] = [e for e in contract["evidence"] if e["value"]["id"] != replaces]
        contract["evidence"].append(envelope)
    return contract


def provider_envelope(item):
    normalized = canonical_import(item)
    original = json.dumps(item, ensure_ascii=False, allow_nan=False)
    output = json.dumps(normalized, ensure_ascii=False, allow_nan=False)
    transformations = [] if item == normalized else [{
        "method": "Task 22 serialization defaults", "software_version": "helper-task23-1.0",
        "formula": "Add declared null/empty defaults and apply documented serializer omissions; observation values unchanged",
        "input_json": original, "output_json": output, "performed_at": now(),
        "validation_checks": ["Original annotation evidence retained", "Engine contract validation required"]}]
    return {"schema_version": "provider-evidence-1.0", "value": normalized,
            "received_json": original, "quality_status": "UNKNOWN",
            "validation_status": normalized["provenance"]["verification_status"],
            "transformations": transformations, "af_consistency_tolerance": None}
