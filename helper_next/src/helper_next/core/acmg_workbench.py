"""Evidence mapping and audit projections. All scientific decisions remain remote."""
import copy
import math
import re

from helper_next.core.analysis_history import now
from helper_next.core.acmg_client import digest
from helper_next.core import acmg_population, acmg_reference


CRITERIA = ("PVS1 PS1 PS2 PS3 PS4 PM1 PM2 PM3 PM4 PM5 PM6 PP1 PP2 PP3 PP4 PP5 "
            "BA1 BS1 BS2 BS3 BS4 BP1 BP2 BP3 BP4 BP5 BP6 BP7").split()
DISCREPANCIES = ("EVIDENCE_MAPPING_ERROR WRONG_THRESHOLD WRONG_CALCULATION WRONG_RULE_PROFILE "
                 "INCORRECT_APPLICABILITY INCORRECT_STRENGTH MISSING_EVIDENCE "
                 "SCIENTIFIC_RULE_DISAGREEMENT DEPENDENCY_ERROR OTHER").split()


def provenance(source_id, checksum, acquired_at, method="DIRECT_IMPORT"):
    return {"source": "HELPER selected VCF record", "source_identifier": source_id,
            "source_version": "sha256-" + checksum["value"], "artifact_digest": checksum,
            "acquired_at": acquired_at, "extraction_method": method,
            "software_version": "helper-task22-v1", "verification_status": "UNVERIFIED",
            "limitations": ["Annotation dataset and predictor release versions are not verified"]}


def transcript_reference(value):
    if not value or not re.fullmatch(r"[A-Za-z0-9_]+(?:\.[0-9]+)?", value):
        raise ValueError("Select an explicit transcript accession")
    accession, _, version = value.partition(".")
    namespace = "Ensembl" if accession.startswith("ENS") else "RefSeq" if re.match(r"[NX][MR]_", accession) else "VCF"
    return {"namespace": namespace,
            "accession": accession, "version": version or None}


def prepare(detail, locator, context, transcript, assembly, reference_record=None, annotation_id=None, context_resolution=None):
    if assembly not in ("GRCh37", "GRCh38"):
        raise ValueError("Explicit GRCh37 or GRCh38 assembly confirmation required")
    recorded = detail["reference_build"]
    aliases = {"hg19": "GRCh37", "hg38": "GRCh38", "grch37": "GRCh37", "grch38": "GRCh38"}
    if recorded.lower() in aliases and aliases[recorded.lower()] != assembly:
        raise ValueError("Assembly conflicts with indexed coordinates; use the correct source")
    if not context.get("gene") or not context.get("disease"):
        raise ValueError("Select stable gene and disease identifiers explicitly")
    for name in ("gene", "disease"):
        identifier = context[name]
        if not isinstance(identifier, dict) or any(not isinstance(identifier.get(k), str) or not re.fullmatch(r"\S+", identifier[k]) for k in ("namespace", "identifier")):
            raise ValueError("Gene and disease require explicit namespace and stable identifier tokens")
    if context["gene"].get("namespace", "").upper() in ("SYMBOL", "GENE_SYMBOL", "HGNC_SYMBOL"):
        raise ValueError("Gene symbol alone is not a stable gene identifier")
    ref, alt = detail["reference"], detail["alternate"]
    if not re.fullmatch("[ACGTN]+", ref) or not re.fullmatch("[ACGTN]+", alt) or ref == alt:
        raise ValueError("Unsupported symbolic, spanning-deletion or breakend variant")
    annotations = [a for a in detail["annotations"] if a["transcript"] == transcript]
    if annotation_id is not None:
        annotations = [a for a in annotations if a.get("id") == annotation_id]
    if not annotations:
        raise ValueError("Selected transcript is not an annotation of this ALT allele")
    if len(annotations) > 1:
        raise ValueError("Multiple annotation records for this transcript; select an explicit annotation ID")
    tx = transcript_reference(transcript)
    stamp = now()
    checksum = digest({"locator": locator, "variant": detail})
    source_id = "vcf-record-" + checksum["value"][:20]
    prov = provenance(source_id, checksum, stamp)
    selection_checksum = digest({"context": context, "transcript": transcript, "annotation_id": annotation_id})
    selection_id = "user-selection-" + selection_checksum["value"][:20]
    selection_provenance = dict(provenance(selection_id, selection_checksum, stamp, "MANUAL"),
                                source="HELPER explicit interpretation context and transcript selection",
                                limitations=["User-declared stable gene mapping and clinical context are unverified",
                                             "Original VCF annotation source: " + source_id])
    if context_resolution:
        selection_checksum = digest({"context": context, "resolution": context_resolution, "transcript": transcript, "annotation_id": annotation_id})
        selection_id = "helper-context-" + selection_checksum["value"][:20]
        selection_provenance = dict(provenance(selection_id, selection_checksum, stamp),
                                    source="HELPER structured gene-disease interpretation context",
                                    limitations=["Source-linked gene-disease association; not scientific approval",
                                                 "Dataset snapshot: " + str(context_resolution["origin"].get("source_version") or "NOT_RECORDED")])
    normalized_context = {"gene": context["gene"], "disease": context["disease"], "transcripts": [tx]}
    modes = context.get("inheritance_modes", [])
    if modes:
        normalized_context["gene_disease"] = {
            "gene": context["gene"], "disease": context["disease"],
            "inheritance_modes": modes, "relevant_transcripts": [tx],
            "provenance": selection_provenance}
    kind = "SNV" if len(ref) == len(alt) == 1 else (
        "MNV" if len(ref) == len(alt) else "INSERTION" if len(ref) == 1 else "DELETION" if len(alt) == 1 else "DELINS")
    identity = {"assembly": assembly, "chromosome": detail["chromosome"], "position": detail["position"],
                "reference": ref, "alternate": alt}
    reference_resource = acmg_reference.verify(identity, reference_record)
    evidence = []
    missing = [{"path": "/snapshot/variant/normalization", "reason": "VCF alleles trimmed by HELPER; reference/left alignment not verified for engine"},
               {"path": "/annotation_versions", "reason": "VCF dataset and predictor release versions require explicit provenance"}]
    if not modes:
        missing.append({"path": "/snapshot/context/gene_disease/inheritance_modes", "reason": "Inheritance not supplied; no inference from genotype"})
    if tx["version"] is None:
        missing.append({"path": "/snapshot/context/transcripts/version", "reason": "Selected VCF transcript has no version; none inferred"})
    if tx["namespace"] == "VCF":
        missing.append({"path": "/snapshot/context/transcripts/namespace", "reason": "Transcript is a VCF-local identifier with no established external namespace"})
    a = annotations[0]
    fields = a.get("metadata", {}).get("fields", {})
    hgnc_id = str(fields.get("HGNC_ID") or "")
    if context["gene"]["namespace"].upper() == "HGNC" and hgnc_id:
        expected_hgnc = "HGNC:" + hgnc_id if hgnc_id.isdigit() else hgnc_id
        if context["gene"]["identifier"] != expected_hgnc:
            raise ValueError("Selected stable gene ID conflicts with the transcript's HGNC annotation")
    # Only exact REVEL annotation, on the explicitly selected transcript. No impact/ClinVar mapping.
    raw_revel = fields.get("REVEL") or fields.get("REVEL_score")
    if raw_revel not in (None, "", "."):
        try:
            score = float(raw_revel)
            if not math.isfinite(score):
                raise ValueError()
            evidence.append({"id": "imported-revel", "kind": "COMPUTATIONAL", "provenance": prov,
                             "observation": {"predictor": "REVEL", "predictor_version": None,
                                             "score": score, "transcript": tx, "variant_identity": identity}})
            missing.append({"path": "/snapshot/evidence/imported-revel/predictor_version", "reason": "Predictor release not present in selected annotation"})
        except (ValueError, TypeError):
            missing.append({"path": "/snapshot/evidence/imported-revel", "reason": "REVEL is not a single finite score; raw annotation retained"})
    splice_fields = {"acceptor_gain": "SpliceAI_pred_DS_AG", "acceptor_loss": "SpliceAI_pred_DS_AL",
                     "donor_gain": "SpliceAI_pred_DS_DG", "donor_loss": "SpliceAI_pred_DS_DL"}
    if any(fields.get(key) not in (None, "", ".") for key in splice_fields.values()):
        vector = {}
        for name, key in splice_fields.items():
            raw = fields.get(key)
            if raw not in (None, "", "."):
                try:
                    value = float(raw)
                    if not math.isfinite(value) or not 0 <= value <= 1:
                        raise ValueError()
                    vector[name] = value
                except (ValueError, TypeError):
                    missing.append({"path": "/snapshot/evidence/imported-spliceai/" + name, "reason": "Invalid raw SpliceAI delta; original value retained locally"})
        if vector:
            evidence.append({"id": "imported-spliceai", "kind": "COMPUTATIONAL", "provenance": prov,
                             "observation": {"predictor": "SpliceAI", "predictor_version": None,
                                             "score": None, "transcript": tx, "variant_identity": identity,
                                             "spliceai": dict(vector, reference_transcript=tx)}})
            missing.append({"path": "/snapshot/evidence/imported-spliceai/predictor_version", "reason": "Predictor release and complete applicability require explicit evidence; no maximum delta calculated by HELPER"})
    if not any(e["kind"] == "COMPUTATIONAL" for e in evidence):
        missing.append({"path": "/snapshot/evidence/computational", "reason": "No supported transcript-specific numeric REVEL annotation"})
    # Dataset-tagged annotations are observations, not proof of population quality
    # or release compatibility. Unprefixed cohort AC/AN are deliberately not used.
    original_vcf = detail.get("metadata", {}).get("original_vcf", {})
    info = original_vcf.get("info", {})
    definitions = a.get("release_resources", {}).get("info_definitions", {})
    for prefix, dataset_kind in (("gnomAD", None), ("gnomADe", "EXOME"), ("gnomADg", "GENOME")):
        observed = {}
        for suffix, target, conversion in (("AC", "allele_count", int), ("AN", "allele_number", int), ("AF", "allele_frequency", float)):
            key = prefix + "_" + suffix
            raw = fields.get(key)
            if raw in (None, "", ".") and key in info:
                number = definitions.get(key, {}).get("number")
                parts = str(info[key]).split(",")
                if number in ("A", "R"):
                    offset = int(original_vcf.get("alt_index", 1)) - (1 if number == "A" else 0)
                    raw = parts[offset] if offset < len(parts) else None
                elif number == "1" or len(original_vcf.get("alternates", [])) <= 1:
                    raw = info[key]
            if raw not in (None, "", "."):
                try:
                    value = conversion(raw)
                    if value < 0 or (conversion is float and (not math.isfinite(value) or value > 1)):
                        raise ValueError()
                    observed[target] = value
                except (ValueError, TypeError):
                    missing.append({"path": "/snapshot/evidence/imported-" + prefix + "/" + target, "reason": "Annotation cannot be mapped to a single valid allele-specific value"})
        if observed:
            observation = {"aggregate": dict(observed, population="UNSPECIFIED"), "populations": [],
                           "coverage_notes": ["Population, dataset release, callable status and quality are not established by this annotation"]}
            if dataset_kind:
                observation["dataset_kind"] = dataset_kind
            evidence.append({"id": "imported-" + prefix, "kind": "POPULATION", "provenance": prov,
                             "limitations": ["Provenance pins the VCF record; it does not assert the population dataset release"],
                             "observation": observation})
    population, population_sources, population_versions, population_quality, population_missing = acmg_population.import_cached(detail, identity, stamp)
    evidence.extend(population)
    missing.extend(population_missing)
    packet = {"schema_version": "evidence-packet-v1", "packet_id": "helper-" + checksum["value"],
              "snapshot": {"schema_version": "1.0", "variant": {
                  "identity": identity, "variant_type": kind,
                  "normalization": {"status": "UNVERIFIED", "reference_validated": None, "provenance": prov},
                  "annotations": [{"gene": context["gene"], "transcript": tx, "provenance": selection_provenance,
                                   "consequence": a["consequence"] or None, "hgvs_coding": a["hgvsc"] or None,
                                   "hgvs_protein": a["hgvsp"] or None}],
                  "transcript_selection": {"transcript": tx, "rationale": "Explicit user selection", "provenance": selection_provenance}},
                  "context": normalized_context, "evidence": evidence, "dependencies": []},
              "source_snapshots": [{"source_id": source_id, "version": prov["source_version"], "checksum": checksum,
                                    "url": None, "limitations": ["Checksum identifies local selected-record snapshot, not a population dataset release"]},
                                   {"source_id": selection_id, "version": selection_provenance["source_version"], "checksum": selection_checksum,
                                    "url": None, "limitations": ["HELPER source-linked context, no scientific verification" if context_resolution else "Explicit user-declared context, no scientific verification"]}],
              "transcript_designations": ([{"transcript": tx, "designation": "RELEVANT_TRANSCRIPT", "source_id": source_id,
                                           "source_version": prov["source_version"]}] if tx["version"] else []),
              "annotation_versions": population_versions, "quality_information": [{"name": "VCF_FILTER", "value": str(detail.get("metadata", {}).get("original_vcf", {}).get("filter", "NOT_RECORDED"))}, *population_quality],
              "missing_evidence": missing}
    packet["source_snapshots"].extend(population_sources)
    if reference_resource:
        reference_provenance = dict(prov, source="HELPER existing indexed FASTA verification",
                                    source_identifier=reference_resource["identifier"], source_version=reference_resource["version"],
                                    artifact_digest=reference_resource["digest"], extraction_method="ALGORITHM",
                                    limitations=["Technical reference and existing allele normalization check; no clinical validation"])
        packet["snapshot"]["variant"]["normalization"] = {"status": "NORMALIZED", "reference_validated": True, "provenance": reference_provenance}
        packet["snapshot"]["variant"]["reference_resource"] = reference_resource
        packet["source_snapshots"].append({"source_id": reference_resource["identifier"], "version": reference_resource["version"], "checksum": reference_resource["digest"], "url": None})
        packet["missing_evidence"] = [m for m in packet["missing_evidence"] if m["path"] != "/snapshot/variant/normalization"]
    return {"locator": locator, "selected_annotation_id": annotations[0].get("id"),
            "context_resolution": context_resolution,
            "original_vcf_evidence": detail, "normalized_evidence": packet,
            "research_only": True}


def corrected_packet(original, corrections):
    """Corrections are full structured evidence items, never scientific rules."""
    packet = copy.deepcopy(original)
    if not corrections:
        return packet
    known = {e["id"]: e for e in packet["snapshot"]["evidence"]}
    for change in corrections:
        if set(change) - {"evidence", "source", "replaces", "comment"}:
            raise ValueError("Evidence corrections cannot contain rule or threshold settings")
        item, source = change["evidence"], change["source"]
        prov = item["provenance"]
        if not change.get("comment", "").strip() or prov.get("extraction_method") != "MANUAL":
            raise ValueError("Manual evidence requires provenance and a correction comment")
        if not prov.get("source_version") or not source.get("version") or not source.get("checksum"):
            raise ValueError("Manual evidence requires a versioned source checksum")
        if (prov["source_identifier"], prov["source_version"], prov.get("artifact_digest")) != (source["source_id"], source["version"], source["checksum"]):
            raise ValueError("Manual evidence provenance must match its source checksum")
        replaces = change.get("replaces")
        if replaces:
            if replaces not in known:
                raise ValueError("Correction refers to an unknown evidence ID")
            del known[replaces]
        if item["id"] in known:
            raise ValueError("Evidence ID already exists; use explicit replaces")
        known[item["id"]] = item
        if source not in packet["source_snapshots"]:
            packet["source_snapshots"].append(source)
    packet["snapshot"]["evidence"] = list(known.values())
    packet["packet_id"] = "helper-corrected-" + digest(packet)["value"]
    return packet


def criterion_rows(result):
    found = {c["code"]: c for c in result.get("criterion_results", [])}
    classification = result.get("classification", {})
    strengths = {s["code"]: s["strength"] for s in classification.get("effective_strengths", [])}
    excluded = {s["code"]: s for s in classification.get("excluded_criteria", [])}
    dependency_exclusions = {code for d in classification.get("dependencies", []) if d.get("disposition") == "EXCLUDE"
                             for code in d.get("criterion_codes", []) if code in excluded}
    recorded_effective = "included_criteria" in classification
    rows = []
    for code in CRITERIA:
        c = found.get(code)
        deprecated = code in ("PP5", "BP6")
        status = c.get("status", "NOT_RECORDED") if c else "NOT_RECORDED"
        display = "DEPRECATED" if deprecated else "EXCLUDED_BY_DEPENDENCY" if code in dependency_exclusions else "UNSUPPORTED" if c and c.get("activation") == "UNSUPPORTED" else status if c else "NOT_EVALUATED"
        rows.append({"code": code, "engine_status": status, "display_status": display,
                     "candidate_active": {"MET": True, "NOT_MET": False}.get(status),
                     "effective_active": (code in classification["included_criteria"]) if recorded_effective else None,
                     "candidate_strength": c.get("strength") if c else None,
                     "effective_strength": strengths.get(code), "excluded": excluded.get(code),
                     "deprecated": deprecated, "explanation": c.get("explanation") if c else "Criterion absent from engine response",
                     "raw": c})
    return rows


def compare_results(before, after):
    left, right = criterion_rows(before), criterion_rows(after)
    return [{"code": a["code"], "before": a, "after": b, "changed": a != b} for a, b in zip(left, right)]
