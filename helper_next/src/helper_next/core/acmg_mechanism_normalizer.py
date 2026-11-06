"""Deterministic vocabulary mapping and assertion reconciliation, not clinical inference."""
import re
from collections import defaultdict

from helper_variants.gene_phenotype import _normalize_disease_id, _is_exact_mapping
from helper_next.core.acmg_digest import digest
from helper_next.core.acmg_mechanism_models import (
    GeneDiseaseMechanismResult, MechanismEvidence, MechanismHypothesis, MechanismIdentity,
)


NORMALIZATION_VERSION = "mechanism-normalizer-1.1"
RECONCILIATION_VERSION = "mechanism-reconciliation-1.0"
MAPPING_VERSION = "registry-qualified-association-2.0"
INHERITANCE_CROSSWALK = "Roberts et al. 2024, Table 2; doi:10.1016/j.gim.2023.101029"


def curie(value, gene=False):
    value = str(value).strip()
    if gene and re.fullmatch(r"(?:HGNC:)?[0-9]+", value, re.I):
        return "HGNC:" + value.split(":")[-1]
    value = _normalize_disease_id(value) if not gene else value
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*:[A-Za-z0-9_.-]+", value):
        raise ValueError("A stable gene/disease CURIE is required; names are not identifiers")
    namespace, identifier = value.split(":", 1)
    return namespace.upper() + ":" + identifier


def allelic(value):
    """Lexical aliases plus the published, fully qualified G2P/HPO crosswalk.

    Generic mono/biallelic and unspecified X-linked remain distinct. Original
    source terms are preserved on each evidence record.
    """
    word = re.sub(r"[\s_-]+", " ", str(value or "").strip().lower())
    aliases = {"ad": "AUTOSOMAL_DOMINANT", "autosomal dominant": "AUTOSOMAL_DOMINANT",
               "ar": "AUTOSOMAL_RECESSIVE", "autosomal recessive": "AUTOSOMAL_RECESSIVE",
               "x linked": "X_LINKED", "x linked dominant": "X_LINKED_DOMINANT",
               "x linked recessive": "X_LINKED_RECESSIVE", "mitochondrial": "MITOCHONDRIAL",
               "monoallelic": "MONOALLELIC", "biallelic": "BIALLELIC",
               "monoallelic autosomal": "AUTOSOMAL_DOMINANT", "biallelic autosomal": "AUTOSOMAL_RECESSIVE",
               "monoallelic x hemizygous": "X_LINKED_RECESSIVE",
               "monoallelic x heterozygous": "X_LINKED_DOMINANT",
               "monoallelic y hemizygous": "Y_LINKED", "y linked inheritance": "Y_LINKED",
               "monoallelic x hem": "MONOALLELIC_X_HEM",
               "monoallelic x het": "MONOALLELIC_X_HET", "y linked": "Y_LINKED",
               "unknown": "UNKNOWN", "": "UNKNOWN", "other": "OTHER_COMPLEX", "complex": "OTHER_COMPLEX"}
    return aliases.get(word, "OTHER:" + word)


def identity(gene, disease, requirement=None, symbol=None, disease_name=None):
    gene_id, disease_id = curie(gene, gene=True), curie(disease)
    return MechanismIdentity(gene_id=gene_id, gene_hgnc_id=gene_id if gene_id.startswith("HGNC:") else None,
                             gene_symbol=symbol or None, disease_id=disease_id, disease_name=disease_name or None,
                             allelic_requirement=allelic(requirement))


def association_key(request):
    return digest({"gene": request.gene_id, "disease": request.disease_id,
                   "allelic_requirement": request.allelic_requirement, "association_policy": MAPPING_VERSION})["value"]


def text(row, key):
    value = row.get(key)
    if value is None:
        return ""
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ValueError("Invalid public source field: " + key)
    return str(value).strip()


def describe(source, row):
    """Read existing adapter/SQLite columns; no new remote parsers."""
    if source == "g2p":
        record_id = text(row, "g2p_id")
        gene = text(row, "gene_curie")
        diseases = [text(row, "disease_curie"), text(row, "disease_mim")]
        original_inheritance = text(row, "allelic_requirement")
        mechanism = text(row, "mechanism")
        version = text(row, "record_version") or None
        url = text(row, "record_url")
    elif source == "gencc":
        record_id = text(row, "sgc_id")
        version = text(row, "version_number") or None
        if not record_id or version is None:
            raise ValueError("GenCC requires sgc_id/version_number; legacy assertions are unsupported")
        if not version.isdigit() or int(version) < 1:
            raise ValueError("GenCC record version must be a positive integer")
        gene = text(row, "gene_curie")
        diseases = [text(row, "disease_curie"), text(row, "disease_original_curie")]
        original_inheritance, mechanism, url = text(row, "moi_title"), "", text(row, "public_report_url")
    elif source == "clingen_dosage":
        base_id = text(row, "gene_id") or text(row, "gene_symbol")
        if not base_id or text(row, "assessment") not in ("haploinsufficiency", "triplosensitivity"):
            raise ValueError("Dosage source record requires identity and a specific HI/TS assessment")
        record_id = base_id + ":" + text(row, "assessment")
        gene = "NCBI_GENE:" + text(row, "gene_id") if text(row, "gene_id") else None
        diseases = [text(row, "hi_disease_id") if text(row, "assessment") == "haploinsufficiency" else text(row, "ts_disease_id")]
        original_inheritance, mechanism, version, url = "", "", None, text(row, "report_url")
    elif source == "gnomad":
        record_id = text(row, "gene_id") or text(row, "gene_symbol")
        gene = "ENSEMBL:" + text(row, "gene_id") if text(row, "gene_id") else None
        diseases, original_inheritance, mechanism, version, url = [], "", "", None, text(row, "source_url")
    elif source == "clinvar":
        # Existing aggregate adapter result: VCV/RCV/SCV stay in ONE origin group.
        identifiers = row.get("identifiers", [])
        if not isinstance(identifiers, list) or not all(isinstance(i, str) for i in identifiers):
            raise ValueError("Invalid ClinVar aggregate identifiers")
        record_id = next((i for i in identifiers if i.startswith("VCV")), None) or next(iter(identifiers), "")
        gene, diseases = text(row, "gene_id") or None, row.get("condition_ids", [])
        original_inheritance, mechanism, version, url = "", "", record_id.rsplit(".", 1)[-1] if "." in record_id else None, text(row, "source_url")
    else:
        raise ValueError("Unsupported mechanism source")
    if not record_id:
        raise ValueError("Stable source record identifier missing: " + source)
    if not isinstance(diseases, list) or not all(isinstance(d, str) for d in diseases):
        raise ValueError("Invalid disease identifiers")
    diseases = sorted({curie(d) for d in diseases if d})
    return {"source_record_id": record_id, "version": version, "gene_id": gene,
            "disease_ids": diseases, "original_inheritance": original_inheritance,
            "inheritance": allelic(original_inheritance), "mechanism": mechanism, "url": url or None}


def molecular_mechanism(original):
    word = re.sub(r"[\s_-]+", " ", original.strip().lower())
    return {"loss of function": "LOSS_OF_FUNCTION", "gain of function": "GAIN_OF_FUNCTION",
            "dominant negative": "DOMINANT_NEGATIVE", "mixed": "MIXED", "mixed mechanism": "MIXED",
            "unknown": "UNKNOWN", "undetermined": "UNKNOWN", "undetermined non loss of function": "UNKNOWN",
            "not known": "UNKNOWN", "": "UNKNOWN"}.get(word, "OTHER")


def mapping(request, records, registry=None):
    from helper_next.core.acmg_ontology import OntologyMappingRegistry, cardinality_conflict
    registry = (registry or OntologyMappingRegistry()).pin()
    scoped = [(p, r, ref) for p, r, ref in records if p.source in ("g2p", "gencc")
              and describe(p.source, r)["gene_id"] == request.gene_id]
    aliases = registry.aliases(request.disease_id)
    edges = registry.observations(request.disease_id, scoped)
    ambiguous = cardinality_conflict(registry.component(request.disease_id))
    return aliases, edges, ambiguous


def normalize(request, records, registry=None):
    aliases, mapping_evidence, ambiguous = mapping(request, records, registry)
    evidence = []
    names, symbols = set(), set()
    for packet, row, ref in records:
        info = describe(packet.source, row)
        source = packet.source
        gene_matches = info["gene_id"] == request.gene_id
        primary_disease = text(row, "disease_curie") or text(row, "disease_mim") or text(row, "disease_original_curie")
        primary_matches = bool(primary_disease and curie(primary_disease) in aliases)
        disease_matches = bool(aliases.intersection(info["disease_ids"]))
        if source in ("g2p", "gencc") and info["disease_ids"] and not (primary_matches or disease_matches):
            continue  # Lack of mapping is not a biological difference assertion.
        applicability = "EXACT" if primary_disease and curie(primary_disease) == request.disease_id else "MAPPED" if primary_matches else "GENE_LEVEL"
        if source in ("g2p", "gencc") and info["disease_ids"] and not primary_matches:
            applicability = "AMBIGUOUS_DISEASE_MAPPING"
        if source in ("g2p", "gencc") and not info["disease_ids"]:
            applicability = "AMBIGUOUS_DISEASE_MAPPING"
        if not gene_matches:
            applicability = "UNRESOLVED_GENE_MAPPING"
        if (request.allelic_requirement != "UNKNOWN" and source in ("g2p", "gencc")
                and request.allelic_requirement != info["inheritance"]):
            applicability = "DIFFERENT_INHERITANCE"
        category = {"g2p": "DIRECT_MECHANISM_ASSERTION", "gencc": "GENE_DISEASE_VALIDITY",
                    "clingen_dosage": "DOSAGE_SENSITIVITY", "gnomad": "POPULATION_CONSTRAINT",
                    "clinvar": "VARIANT_CLASSIFICATION_CONTEXT"}[source]
        mechanism = molecular_mechanism(info["mechanism"]) if source == "g2p" else "UNKNOWN"
        if source == "g2p" and (info["mechanism"].endswith("_variant") or info["mechanism"].lower() in ("missense", "frameshift", "nonsense")):
            mechanism, category = "UNKNOWN", "OTHER"
        direction = "SUPPORTING" if source == "g2p" and mechanism != "UNKNOWN" else "CONTEXTUAL"
        if source == "g2p" and mechanism == "UNKNOWN":
            direction = "NOT_INFORMATIVE"
        if applicability in ("AMBIGUOUS_DISEASE_MAPPING", "UNRESOLVED_GENE_MAPPING", "DIFFERENT_INHERITANCE"):
            direction = "UNRESOLVED_APPLICABILITY"
        record_hash = digest(row)["value"]
        origin = text(row, "upstream_record_id") or info["url"] or source + ":" + info["source_record_id"]
        dosage_pmids = text(row, "hi_pmids") if text(row, "assessment") == "haploinsufficiency" else text(row, "ts_pmids")
        references = [r for r in re.split(r"[;,|]", text(row, "publications") or text(row, "pmids") or dosage_pmids) if r]
        basis = text(row, "mechanism_support") or "NOT_RECORDED"
        evidence.append(MechanismEvidence(
            evidence_id="me-" + digest({"ref": ref, "normalizer": NORMALIZATION_VERSION})["value"],
            source_record_ref=ref, source=source, source_record_id=info["source_record_id"],
            source_record_version=info["version"], source_dataset_version=packet.dataset_version,
            gene_id=info["gene_id"], disease_ids=info["disease_ids"], allelic_requirement=info["inheritance"],
            original_allelic_requirement=info["original_inheritance"] or None,
            evidence_category=category, asserted_mechanism=mechanism, original_mechanism=info["mechanism"] or None,
            mechanism_detail=text(row, "mechanism_category") or None, raw_assertion=row, evidence_direction=direction,
            evidence_directness="DIRECT" if source == "g2p" else "INDIRECT" if source in ("gnomad", "clingen_dosage") else "CONTEXTUAL",
            applicability=applicability, assertion_basis=basis, source_review_status=text(row, "review_status") or None,
            source_classification=text(row, "confidence") or text(row, "classification_title") or None,
            references=references, retrieved_at=packet.retrieved_at,
            source_updated_at=text(row, "last_reviewed") or text(row, "submitted_run_date") or text(row, "last_evaluated") or packet.source_updated_at,
            source_record_hash=record_hash, raw_record_reference=ref, origin_group=origin,
            normalization_version=NORMALIZATION_VERSION))
        if gene_matches:
            if text(row, "gene_symbol"):
                symbols.add(text(row, "gene_symbol"))
            name = text(row, "disease_name") or text(row, "disease_title")
            if name:
                names.add(name)
    updated = request.copy(update={"disease_aliases": sorted(aliases - {request.disease_id}),
                                   "disease_alternative_names": sorted(names),
                                   "gene_symbol": next(iter(symbols)) if len(symbols) == 1 else request.gene_symbol})
    return updated, sorted(evidence, key=lambda e: e.evidence_id), mapping_evidence, ambiguous


def analyze(request, records, states, registry=None):
    request, evidence, mappings, ambiguous = normalize(request, records, registry)
    direct = [e for e in evidence if e.evidence_direction == "SUPPORTING"]
    contextual = [e for e in evidence if e not in direct]
    groups = defaultdict(list)
    for e in direct:
        groups[(e.allelic_requirement, e.asserted_mechanism)].append(e)
    contradictory, hypotheses = {}, []
    for (requirement, mechanism), items in sorted(groups.items()):
        # MIXED and OTHER preserve detail; they are not treated as assertions
        # negating every specific mechanism. No numeric voting or weighting.
        opposite = [e for e in direct if e.allelic_requirement == requirement
                    and e.asserted_mechanism != mechanism
                    and {mechanism, e.asserted_mechanism} <= {"LOSS_OF_FUNCTION", "GAIN_OF_FUNCTION", "DOMINANT_NEGATIVE"}]
        contradictory.update({e.evidence_id: e for e in opposite})
        hypotheses.append(MechanismHypothesis(mechanism=mechanism, allelic_requirement=requirement,
                                             supporting_evidence_refs=sorted(e.evidence_id for e in items),
                                             contradictory_evidence_refs=sorted(e.evidence_id for e in opposite)))
    source_failure = any(s.status in ("CACHE_MISS", "UNREACHABLE", "ERROR", "NORMALIZATION_ERROR") for s in states)
    status = ("CONFLICTING_ASSERTIONS" if contradictory else "MULTIPLE_COMPATIBLE_ASSERTIONS" if len(direct) > 1
              else "SUPPORTED_BY_DIRECT_ASSERTION" if direct else "INSUFFICIENT_EVIDENCE" if evidence or source_failure else "UNKNOWN")
    issues = []
    if contradictory:
        issues.append("CONTRADICTORY_ASSERTIONS")
    if contextual and direct:
        issues.append("DIFFERENT_EVIDENCE_LEVELS")
    if ambiguous or any(e.applicability == "AMBIGUOUS_DISEASE_MAPPING" for e in evidence):
        issues.append("AMBIGUOUS_DISEASE_MAPPING")
    if any(s.status not in ("AVAILABLE", "NO_RECORDS") for s in states):
        issues.append("SOURCE_UNAVAILABLE")
    mapping_states = {m["verification_status"] for m in mappings}
    if "CONFLICTING_MAPPING" in mapping_states:
        issues.append("CONFLICTING_DISEASE_MAPPING")
    if mapping_states.intersection({"UNVERIFIED_CROSS_REFERENCE", "NO_VERIFIED_MAPPING"}):
        issues.append("UNVERIFIED_DISEASE_MAPPING")
    if registry is not None and len(registry.aliases(request.disease_id)) == 1:
        issues.append("NO_VERIFIED_DISEASE_MAPPING")
    uncertainty = mapping_states - {"VERIFIED_EXACT", "IDENTITY"}
    if "NO_VERIFIED_DISEASE_MAPPING" in issues and not ambiguous:
        uncertainty.add("NO_VERIFIED_MAPPING")
    missing = ["Explicit contextual mechanism review and human attestation are not recorded"]
    if not direct:
        issues.append("MISSING_INFORMATION")
        missing.append("No applicable explicit gene-disease/allelic-requirement mechanism assertion")
    if any(e.source_record_version is None and e.source_dataset_version is None for e in evidence):
        missing.append("Some upstream record/dataset versions are not recorded; content hashes preserve acquired data")
    validity = [{"evidence_id": e.evidence_id, "classification": e.source_classification,
                 "allelic_requirement": e.allelic_requirement, "applicability": e.applicability}
                for e in evidence if e.evidence_category == "GENE_DISEASE_VALIDITY"]
    return GeneDiseaseMechanismResult(
        identity=request, candidate_mechanisms=sorted({e.asserted_mechanism for e in direct}), hypotheses=hypotheses,
        resolution_status=status, reconciliation_status="CANDIDATE_ASSERTIONS_RECORDED" if direct and not contradictory and not ambiguous and "CONFLICTING_DISEASE_MAPPING" not in issues else "UNRESOLVED",
        issues=sorted(set(issues)), mapping_uncertainty=sorted(uncertainty), direct_evidence=direct, contextual_evidence=contextual,
        contradictory_evidence=[contradictory[k].copy(update={"evidence_direction": "CONTRADICTING"}) for k in sorted(contradictory)],
        missing_evidence=missing, gene_disease_validity=validity, mapping_evidence=mappings, source_status=states,
        warnings=["Candidate assertions are not clinical validation or PVS1 applicability",
                  "Inheritance groups remain separate; only the published qualified G2P/HPO crosswalk is applied; generic mono/biallelic remain distinct",
                  "Dosage and constraint are context; no LOEUF thresholds, source majority or variant-class inference applied",
                  "Shared origin groups do not establish independent observations; no evidence counts are used"])
