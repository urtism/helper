"""Global Evidence Builder over existing HELPER adapters and the Task 22 REST API.

No engine models, criteria, strengths or clinical caches are implemented here.
"""
import copy
import json
import math
from decimal import Decimal

from helper_next.core import acmg_population
from helper_next.core import acmg_pvs1
from helper_next.core.acmg_mechanism_assessment import assess, context_curie
from helper_next.core.acmg_client import EngineError, digest
from helper_next.core.acmg_sources import SourceManager
from helper_next.core.acmg_task22 import provider_contract
from helper_next.core.analysis_history import now


def json_text(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def population_rounding_tolerance(raw):
    """Bound binary64 division roundoff, never the observed AC/AN/AF discrepancy.

    The existing gnomAD adapter computes AF from integer counts as a float. Two
    ULPs cover its serialization roundoff; a genuinely inconsistent AF is retained
    and still reported by the engine. No tolerance is inferred for VCF annotations.
    """
    bounds = []
    for row in [raw, *raw.get("populations", [])]:
        ac, an = row.get("ac"), row.get("an")
        if (type(ac) is int and type(an) is int and 0 <= ac <= an and an > 0
                and isinstance(row.get("af"), (float, int))):
            expected = ac / an
            if expected:
                bounds.append(Decimal(str(math.ulp(expected))) * 2)
    return str(max(bounds)) if bounds else None


class EvidenceAssembler:
    """Reuse HELPER's serializers and the authoritative remote semantic validator."""

    def __init__(self, engine):
        self.engine = engine

    def draft(self, workspace, additions=()):
        return provider_contract(workspace, additions)

    def assemble(self, workspace, additions=(), originals=None, preserved_envelopes=()):
        try:
            contract = self.draft(workspace, additions)
            preserved = {e["value"]["id"]: e for e in preserved_envelopes}
            # Revalidation after packet corrections must retain the original
            # provider audit for every unchanged automatic observation.
            contract["evidence"] = [copy.deepcopy(preserved[e["value"]["id"]])
                                    if e["value"]["id"] in preserved and preserved[e["value"]["id"]]["value"] == e["value"]
                                    else e for e in contract["evidence"]]
            known_dependencies = {d["id"] for d in contract["dependencies"]}
            contract["dependencies"].extend(d for d in source_dependencies({
                "evidence": [e["value"] for e in contract["evidence"]]}) if d["id"] not in known_dependencies)
            for envelope in contract["evidence"]:
                original = (originals or {}).get(envelope["value"]["id"])
                if original is None:
                    continue
                # A manual replacement has its own original and attestation.
                if envelope["value"]["provenance"]["extraction_method"] == "MANUAL":
                    continue
                normalized = envelope["value"]
                envelope["received_json"] = json_text(original)
                is_pvs1 = normalized["kind"] == "PVS1"
                envelope["transformations"] = [{
                    "method": "HELPER existing source adapter and Task 22 serialization",
                    "software_version": normalized["provenance"]["software_version"] if is_pvs1 else "helper-evidence-builder-1.0",
                    "formula": ((original.get("calculation") or {}).get("formula", "Incomplete technical evidence; no PTC, splice outcome or NMD inferred")
                                if is_pvs1 else "Select exact allele/transcript or gene-disease candidates; map existing adapter fields; apply Task 22 serialization defaults"),
                    "input_json": envelope["received_json"], "output_json": json_text(normalized),
                    "performed_at": normalized["provenance"]["acquired_at"],
                    "validation_checks": ["Original source record retained", "No automatic human verification",
                                          "Missing scientific release is not replaced by artifact checksum"]}]
                if normalized["id"] == "helper-gnomad-genomes":
                    envelope["af_consistency_tolerance"] = population_rounding_tolerance(original["record"])
            validated = self.engine.invoke("/v1/evidence-contracts/validate", contract)
            return {"contract": validated["contract"], "validated": validated, "errors": []}
        except EngineError as exc:
            return {"contract": None, "validated": None, "errors": [
                {"code": exc.code, "message": str(exc), "status": exc.status, "details": exc.details}]}
        except (ValueError, KeyError, TypeError) as exc:
            return {"contract": None, "validated": None, "errors": [
                {"code": "INVALID_BUILDER_INPUT", "message": "Evidence could not be assembled",
                 "status": 422, "details": {"error_type": type(exc).__name__}}]}


def gene_disease_candidates(knowledge, context, acquired_at):
    """Retain original contexts; do not map candidates to a curated PVS1 mechanism."""
    gene = context["gene"]["identifier"]
    disease = context["disease"]["identifier"]
    associations = [a for a in knowledge.get("associations", []) if a.get("disease_id") == disease]
    records = {"gencc": [], "g2p": [], "clingen_dosage": []}
    aliases = {disease}
    for association in associations:
        assertions = [a for a in association.get("assertions", []) if a.get("gene_id") == gene]
        if not assertions:
            continue
        aliases.update(association.get("original_disease_ids", []))
        records["gencc"].extend(dict(a, disease_id=disease) for a in assertions)
        for row in association.get("molecular_mechanism", {}).get("records", []):
            # The old adapter could fall back to a symbol. Never adopt that as identity proof.
            if row.get("gene_id") == gene and aliases.intersection({row.get("disease_id"), row.get("disease_mim")}):
                records["g2p"].append(row)
    for row in knowledge.get("g2p_records", []):
        if (row.get("gene_id") == gene
                and aliases.intersection({row.get("disease_id"), row.get("disease_mim")})
                and row not in records["g2p"]):
            records["g2p"].append(row)
    dosage = knowledge.get("dosage_sensitivity", {})
    if dosage.get("status") == "ready":
        for name in ("haploinsufficiency", "triplosensitivity"):
            row = dosage.get(name, {})
            if row.get("disease_id") in aliases:
                records["clingen_dosage"].append({"assessment": name, **row,
                    "gene_id": dosage.get("gene_id"), "gene_symbol": knowledge.get("gene"),
                    "gene_identity_match": "UNVERIFIED",  # NCBI ID/symbol is not an HGNC equivalence proof.
                    "last_evaluated": dosage.get("last_evaluated"), "source_url": dosage.get("source_url")})
    cache = knowledge.get("cache", {})
    urls = {"gencc": cache.get("source_url") or "https://thegencc.org/",
            "g2p": cache.get("g2p_source_url") or "https://www.ebi.ac.uk/gene2phenotype/",
            "clingen_dosage": cache.get("clingen_dosage_source_url") or "https://search.clinicalgenome.org/kb/gene-dosage"}
    result, originals = [], {}
    for source_id, rows in records.items():
        if not rows:
            continue
        original = {"context": context, "records": rows, "snapshot_acquired_at": cache.get("updated_at"),
                    "cache_stale": cache.get("stale"), "source_url": urls[source_id]}
        # Retain disagreements as recorded vocabulary; do not resolve mechanism
        # or inheritance compatibility in HELPER.
        if source_id == "g2p":
            original["recorded_mechanisms"] = sorted({r.get("original_mechanism", "") for r in rows} - {""})
            original["recorded_inheritance"] = sorted({r.get("allelic_requirement", "") for r in rows} - {""})
            original["divergent_records_require_review"] = (len(original["recorded_mechanisms"]) > 1
                                                            or len(original["recorded_inheritance"]) > 1)
        limitations = ["Candidate records only; mechanism and inheritance compatibility require explicit review",
                        "Individual record versions/review dates are retained; global scientific release not recorded"]
        item = {"id": "helper-" + source_id + "-candidates", "kind": "EXTENSION",
                "provenance": {"source": source_id, "source_identifier": source_id, "source_version": None,
                    "acquired_at": cache.get("updated_at") or acquired_at, "extraction_method": "DIRECT_IMPORT",
                    "software_version": "helper-evidence-builder-1.0", "verification_status": "UNVERIFIED",
                    "source_url": urls[source_id], "artifact_digest": digest(original), "limitations": limitations},
                "limitations": limitations,
                "observation": {"schema_id": "helper-gene-disease-candidates", "schema_version": "1.0",
                    "fields": [{"name": "records_json", "value": json_text(original), "unit": None},
                               {"name": "mechanism_compatibility", "value": "NOT_VERIFIED", "unit": None}]}}
        result.append(item)
        originals[item["id"]] = original
    return result, originals


def deferred_pvs1(workspace, requirements):
    """Compatibility audit when no selected annotation reaches the builder."""
    return {"transformer": "PVS1", "status": "DEFERRED",
            "annotation_id": workspace.get("selected_annotation_id"),
            "candidate_evidence_ids": [e["id"] for e in workspace["normalized_evidence"]["snapshot"]["evidence"]
                                       if e["kind"] == "EXTENSION"],
            "requirements": [r for r in requirements.get("node_requirements", []) if r["criterion"] == "PVS1"],
            "limitations": ["No selected annotation with a supported PVS1 technical consequence",
                            "No technical consequence inferred from other annotation classes"]}


def mechanism_matrix_evidence(result):
    """Existing EXTENSION boundary; no matrix values become PVS1 assessments."""
    original = result.dict()
    limits = ["Unreviewed mechanism candidates only; no automatic PVS1 applicability",
              "Scientific releases are retained per source record; no single global release is asserted"]
    item = {"id": "helper-mechanism-matrix", "kind": "EXTENSION", "limitations": limits,
            "provenance": {"source": "HELPER persistent Mechanism Evidence Cache",
                "source_identifier": "helper-mechanism-cache", "source_version": None,
                "acquired_at": result.provenance["created_at"], "extraction_method": "ALGORITHM",
                "software_version": "helper-mechanism-cache-1.0", "verification_status": "UNVERIFIED",
                "artifact_digest": digest(original), "limitations": limits},
            "observation": {"schema_id": "helper-mechanism-evidence-matrix", "schema_version": "1.0",
                "fields": [{"name": "matrix_json", "value": json_text(original), "unit": None},
                           {"name": "snapshot_id", "value": result.snapshot_id, "unit": None},
                           {"name": "review_status", "value": result.review_status, "unit": None}]}}
    return item, original


def mechanism_assessment_evidence(assessment, annotation, variant, acquired_at):
    """Retain biology and the selected consequence even without nonsense facts.

    This extension is transport/audit evidence. It does not establish a PVS1
    technical consequence or substitute for the Engine's specialized evaluator.
    """
    original = {"assessment": assessment.dict(), "selected_annotation": annotation,
                "variant_identity": variant}
    limits = list(assessment.limitations)
    item = {"id": "helper-mechanism-assessment", "kind": "EXTENSION", "limitations": limits,
            "provenance": {"source": "HELPER Evidence Coordinator", "source_identifier": "helper-mechanism-assessment",
                "source_version": assessment.schema_version, "acquired_at": acquired_at,
                "extraction_method": "ALGORITHM", "software_version": assessment.schema_version,
                "verification_status": "UNVERIFIED", "artifact_digest": digest(original), "limitations": limits},
            "observation": {"schema_id": "helper-mechanism-assessment", "schema_version": "1.0",
                "fields": [{"name": "assessment_json", "value": json_text(original), "unit": None}]}}
    return item, original


def source_dependencies(snapshot):
    """Record only demonstrable shared input artifacts, never predictor assumptions."""
    groups = {}
    for item in snapshot["evidence"]:
        provenance = item["provenance"]
        checksum = provenance.get("artifact_digest")
        if checksum:
            key = (provenance["source_identifier"], checksum["value"])
            groups.setdefault(key, []).append(item)
    for group in groups.values():
        if len(group) > 1:
            ids = sorted(e["id"] for e in group)
            yield {"id": "helper-shared-" + digest(ids)["value"][:20], "kind": "CORRELATED",
                   "evidence_ids": ids, "dependent_evidence_id": None,
                   "explanation": "Observations share the same recorded source artifact; scientific independence is not established",
                   "provenance": group[0]["provenance"]}


class EvidenceCoordinator:
    """The sole orchestrator: requirements -> requested sources -> assembly."""

    def __init__(self, engine, sources=None):
        self.engine = engine
        self.sources = sources or SourceManager()
        self.assembler = EvidenceAssembler(engine)

    def build(self, workspace, protocol, additions=(), mechanism_request=None):
        working = copy.deepcopy(workspace)
        packet = working["normalized_evidence"]
        snapshot = packet["snapshot"]
        # Existing reference/transcript guards remain in force before any source access.
        try:
            seed = self.assembler.draft(working, additions)
            requirements = self.engine.invoke("/v1/evidence/requirements", {
                "variant": seed["variant"], "context": seed["context"], "protocol": protocol})
        except EngineError as exc:
            return {"contract": None, "validated": None, "errors": [
                {"code": exc.code, "message": str(exc), "status": exc.status, "details": exc.details}]}
        except (ValueError, KeyError, TypeError) as exc:
            return {"contract": None, "validated": None, "errors": [
                {"code": "INVALID_BUILDER_INPUT", "message": "Evidence could not be assembled",
                 "status": 422, "details": {"error_type": type(exc).__name__}}]}
        kinds = {b["evidence_type"] for r in requirements["requirements"] for b in r["alternatives"]}
        sources, originals = [], {}
        transformers = []
        mechanism_result = None
        mechanism_assessment = None
        detail = working["original_vcf_evidence"]
        if "POPULATION" in kinds:
            source = self.sources.population(snapshot["variant"]["identity"], detail.get("gnomad_frequency"))
            sources.append({k: v for k, v in source.items() if k != "data"})
            raw = source["data"]
            if raw:
                imported, snapshots, versions, quality, missing = acmg_population.import_cached(
                    {"gnomad_frequency": raw}, snapshot["variant"]["identity"], now())
                if imported:
                    item = imported[0]
                    existing = next((e for e in snapshot["evidence"] if e["id"] == item["id"]), None)
                    if existing is None:
                        snapshot["evidence"].append(item)
                        packet["source_snapshots"].extend(snapshots)
                        packet["annotation_versions"].extend(versions)
                        packet["quality_information"].extend(quality)
                        packet["missing_evidence"] = [m for m in packet["missing_evidence"]
                                                      if m["path"] != "/snapshot/evidence/population"]
                        packet["missing_evidence"].extend(missing)
                    # Do not relabel an older observation with a changed cache record.
                    if existing is None or existing["provenance"]["artifact_digest"] == digest(raw):
                        originals[item["id"]] = {"record": raw, "annotation_versions": versions, "quality": quality}
                else:
                    packet["missing_evidence"].extend(missing)
        needs_gene = "PVS1" in kinds or any("gene_disease" in r.get("context_requirements", [])
                                             for r in requirements["requirements"])
        if needs_gene and snapshot["context"].get("gene") and snapshot["context"].get("disease"):
            annotation = next(a for a in detail["annotations"] if a.get("id") == working.get("selected_annotation_id")
                              and a["transcript"].split(".")[0] == snapshot["context"]["transcripts"][0]["accession"])
            gene_id = snapshot["context"]["gene"]["identifier"]
            # query_gene's stable-ID argument is specifically HGNC, not a generic CURIE.
            source = self.sources.gene_disease(annotation.get("gene", ""), gene_id if gene_id.startswith("HGNC:") else "")
            sources.append({k: v for k, v in source.items() if k != "data"})
            candidates, raw_candidates = gene_disease_candidates(source["data"] or {}, snapshot["context"], now())
            known = {e["id"] for e in snapshot["evidence"]}
            snapshot["evidence"].extend(e for e in candidates if e["id"] not in known)
            originals.update({k: v for k, v in raw_candidates.items() if k not in known})
            available = {e["provenance"]["source_identifier"] for e in candidates}
            for source_id in ("gencc", "g2p", "clingen_dosage"):
                if source_id not in available:
                    packet["missing_evidence"].append({"path": "/snapshot/context/gene_disease/candidates/" + source_id,
                        "reason": "No source candidates with demonstrable selected gene-disease context"})
        if mechanism_request is not None or "PVS1" in kinds and snapshot["context"].get("gene") and snapshot["context"].get("disease"):
            from helper_next.core.acmg_mechanisms import MechanismEvidenceCache
            context = snapshot["context"]
            selected = next(a for a in detail["annotations"] if a.get("id") == working.get("selected_annotation_id"))
            modes = context.get("gene_disease", {}).get("inheritance_modes", [])
            request = dict(mechanism_request or {"cache_policy": "CACHE_ONLY"})
            request.setdefault("allelic_requirement", modes[0] if len(modes) == 1 else None)
            mechanism_result = MechanismEvidenceCache(self.sources).resolve_gene_disease_mechanism(
                context_curie(context["gene"]), context_curie(context["disease"]), symbol=selected.get("gene"), **request)
            mechanism_assessment = assess(mechanism_result)
            item, original = mechanism_assessment_evidence(mechanism_assessment, selected,
                                                         snapshot["variant"]["identity"], now())
            if not any(e["id"] == item["id"] for e in snapshot["evidence"]):
                snapshot["evidence"].append(item)
                originals[item["id"]] = original
            if mechanism_request is not None:
                item, original = mechanism_matrix_evidence(mechanism_result)
                if not any(e["id"] == item["id"] for e in snapshot["evidence"]):
                    snapshot["evidence"].append(item)
                    originals[item["id"]] = original
        if "PVS1" in kinds:
            tx = snapshot["context"]["transcripts"][0]
            transcript = tx["accession"] + "." + tx["version"]
            annotation = next((a for a in detail["annotations"]
                               if a.get("id") == working.get("selected_annotation_id") and a["transcript"] == transcript), None)
            if annotation and acmg_pvs1.technical_consequence(annotation):
                source = self.sources.transcript(transcript, snapshot["variant"]["identity"]["assembly"])
                sources.append({k: v for k, v in source.items() if k != "data"})
                candidates = [e for e in snapshot["evidence"] if e["kind"] == "EXTENSION"
                              and e["observation"].get("schema_id") == "helper-gene-disease-candidates"]
                transformed = acmg_pvs1.transform(snapshot["variant"]["identity"], annotation,
                                                snapshot["context"], source, candidates,
                                                mechanism_assessment)
                if not any(e["id"] == transformed["evidence"]["id"] for e in snapshot["evidence"]):
                    snapshot["evidence"].append(transformed["evidence"])
                    originals[transformed["evidence"]["id"]] = transformed["original"]
                packet["missing_evidence"].extend({**m, "path": "/snapshot/evidence/" + transformed["evidence"]["id"] + m["path"]}
                                                  for m in transformed["missing_evidence"])
                transformers.append({k: v for k, v in transformed.items() if k not in ("evidence", "original")})
        for item in snapshot["evidence"]:
            if item["id"].startswith("imported-"):
                tx = snapshot["context"]["transcripts"][0]
                selected_transcript = tx["accession"] + ("." + tx["version"] if tx.get("version") else "")
                annotations = [a for a in detail["annotations"] if a.get("id") == working.get("selected_annotation_id")
                               and a["transcript"] == selected_transcript]
                raw_vcf = detail.get("metadata", {}).get("original_vcf", {})
                originals[item["id"]] = {"annotations": annotations,
                    "original_vcf": {k: raw_vcf[k] for k in ("info", "alternates", "alt_index", "filter") if k in raw_vcf},
                    "source_snapshots": packet["source_snapshots"], "annotation_versions": packet["annotation_versions"]}
        result = self.assembler.assemble(working, additions, originals)
        if result["contract"] is not None:
            contract = result["contract"]
            try:
                result["requirements"] = self.engine.invoke("/v1/evidence/requirements", {
                    "variant": contract["variant"], "context": contract["context"],
                    "protocol": protocol, "supplied": contract})
            except EngineError as exc:
                result["errors"].append({"code": exc.code, "message": str(exc),
                                         "status": exc.status, "details": exc.details})
        result.update(sources=sources, missing_evidence=packet["missing_evidence"],
                      packet=packet,
                      transformers=transformers,
                      deferred_transformers=[deferred_pvs1(working, requirements)] if "PVS1" in kinds and not transformers else [])
        if mechanism_result is not None:
            result["mechanism_evidence"] = mechanism_result.dict()
            result["mechanism_assessment"] = mechanism_assessment.dict()
        return result


def contract_packet(packet, contract):
    """Thin adapter to the existing Engine packet; values are never interpreted."""
    result = copy.deepcopy(packet)
    result["snapshot"].update(variant=copy.deepcopy(contract["variant"]), context=copy.deepcopy(contract["context"]),
                              evidence=[copy.deepcopy(e["value"]) for e in contract["evidence"]],
                              dependencies=copy.deepcopy(contract["dependencies"]))
    return result


def prepare_evidence(engine, workspace, protocol, additions=(), mechanism_request=None, packet_corrections=()):
    """Shared application entry point for criteria evaluation and classification.

    The two existing correction formats remain compatibility boundaries. Sources,
    assessment and technical facts are prepared exactly once by the Coordinator.
    """
    built = EvidenceCoordinator(engine).build(workspace, protocol, additions, mechanism_request=mechanism_request)
    if not built["errors"]:
        if not additions:
            built["automatic_contract"] = copy.deepcopy(built["contract"])
        built["packet"] = contract_packet(built["packet"], built["contract"])
        if packet_corrections:
            from helper_next.core.acmg_workbench import corrected_packet
            packet = corrected_packet(built["packet"], packet_corrections)
            assembled = EvidenceAssembler(engine).assemble(dict(workspace, normalized_evidence=packet),
                                                          preserved_envelopes=built["contract"]["evidence"])
            built.update(assembled)
            if not built["errors"]:
                built["packet"] = contract_packet(packet, built["contract"])
                built["requirements"] = engine.invoke("/v1/evidence/requirements", {
                    "variant": built["contract"]["variant"], "context": built["contract"]["context"],
                    "protocol": protocol, "supplied": built["contract"]})
    if built["errors"]:
        error = built["errors"][0]
        raise EngineError(error["code"], error["message"], error["status"], error.get("details"))
    return built
