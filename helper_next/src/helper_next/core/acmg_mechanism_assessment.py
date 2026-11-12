"""Task 28 biological interpretation of the existing mechanism matrix; no ACMG rules."""
import math
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field

from helper_next.core.acmg_mechanism_models import Model, MechanismEvidence, MechanismIdentity
from helper_next.core.acmg_digest import digest

VERSION = "helper-mechanism-assessment-1.0"
RULES_VERSION = "helper-mechanism-assessment-rules-1.3"
CURATED_SOURCES = {"g2p", "gencc", "clingen", "orphanet", "orphadata"}
PLI_THRESHOLD = 0.9
HI_INTERPRETATIONS = {0: "NO_EVIDENCE", 1: "LITTLE_EVIDENCE", 2: "SOME_EVIDENCE",
                      3: "SUFFICIENT_EVIDENCE", 30: "RECESSIVE_DISEASE", 40: "DOSAGE_UNLIKELY"}


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError, OverflowError):
        return None


def gene_level_indicators(identity, evidence):
    """Interpret dosage/constraint without assigning a target disease or voting.

    Prefer one MANE Select, then one canonical constraint transcript. Never pick
    the largest pLI among isoforms. Legacy values remain visible with their
    missing release/quality qualification, but cannot drive inference.
    """
    constraint = [e for e in evidence if e.source == "gnomad" and e.evidence_category == "POPULATION_CONSTRAINT"]
    qualified = [e for e in constraint if e.gene_id == identity.gene_id and e.applicability in {"GENE_LEVEL", "EXACT", "MAPPED"}]
    preferred = ([e for e in qualified if e.raw_assertion.get("mane_select") in (True, 1)]
                 or [e for e in qualified if e.raw_assertion.get("canonical") in (True, 1)] or qualified)
    selected = preferred[0].evidence_id if len(preferred) == 1 else None
    indicators = []
    for e in evidence:
        raw = e.raw_assertion
        hi = (e.source == "clingen_dosage" and e.evidence_category == "DOSAGE_SENSITIVITY"
              and raw.get("assessment") == "haploinsufficiency")
        if not hi and not (e.source == "gnomad" and e.evidence_category == "POPULATION_CONSTRAINT"):
            continue
        value = _number(raw.get("hi_score" if hi else "pli"))
        if value is not None and (value not in HI_INTERPRETATIONS if hi else not 0 <= value <= 1):
            value = None
        issues = []
        if e.gene_id != identity.gene_id or e.applicability not in {"GENE_LEVEL", "EXACT", "MAPPED"}:
            issues.append("UNRESOLVED_GENE_MAPPING")
        if value is None:
            issues.append("MISSING_OR_INVALID_VALUE")
        release = raw.get("release") or e.source_dataset_version
        if not hi:
            if not release:
                issues.append("UNVERIFIED_RELEASE")
            if raw.get("available") not in (True, 1):
                issues.append("UNAVAILABLE_CONSTRAINT")
            if not raw.get("transcript_id"):
                issues.append("MISSING_TRANSCRIPT")
            elif e.evidence_id != selected:
                issues.append("TRANSCRIPT_NOT_SELECTED" if selected else "AMBIGUOUS_TRANSCRIPT")
            if any(not isinstance(raw.get(key), list) for key in ("constraint_flags", "gene_flags")):
                issues.append("UNVERIFIED_QUALITY")
            elif raw["constraint_flags"] or raw["gene_flags"]:
                issues.append("QUALITY_FLAGS")
            expected = _number(raw.get("lof_expected"))
            if expected is None or expected <= 0:
                issues.append("MISSING_OR_ZERO_EXPECTED_LOF")
        interpretation = (HI_INTERPRETATIONS.get(value, "UNAVAILABLE") if hi else
                          "UNAVAILABLE" if value is None else "HIGH_LOF_INTOLERANCE" if value >= PLI_THRESHOLD else "NO_HIGH_LOF_INTOLERANCE")
        indicators.append({"source": e.source, "metric": "HI" if hi else "pLI", "value": value,
            "interpretation": interpretation, "scope": "GENE_LEVEL",
            "supports_lof": not issues and (value == 3 if hi else value >= PLI_THRESHOLD),
            "eligible_for_inference": not issues, "issues": issues, "evidence_id": e.evidence_id,
            "transcript": raw.get("transcript_id") if not hi else None,
            "selected_for_gene_assessment": hi or e.evidence_id == selected,
            "release": release, "source_url": raw.get("report_url" if hi else "source_url"),
            "threshold": None if hi else PLI_THRESHOLD,
            "source_record_ref": e.source_record_ref})
    return indicators


def disputed_validity(evidence):
    """Recognize GenCC validity labels while retaining the original source text."""
    classification = " ".join((evidence.source_classification or "").casefold().split())
    return (evidence.evidence_category == "GENE_DISEASE_VALIDITY"
            and classification in {"disputed", "disputed evidence", "refuted", "refuted evidence"})


def approved_vcep_assertion(evidence):
    """Qualify a retained biological assertion, never a classification profile.

    The existing source adapters do not currently supply these records. This
    boundary requires a normalized explicit statement and its archived official
    specification; profile IDs, PVS1 trees and applicability alone are insufficient.
    """
    try:
        url = urlparse(str(evidence.raw_assertion.get("source_url", "")))
    except ValueError:
        return False
    return (evidence.source == "clingen_vcep"
            and evidence.source_review_status == "APPROVED"
            and bool(evidence.source_record_id and evidence.source_record_version
                     and evidence.original_mechanism and evidence.source_record_ref
                     and evidence.raw_record_reference)
            and isinstance(evidence.raw_assertion.get("molecular_mechanism_statement"), str)
            and evidence.raw_assertion["molecular_mechanism_statement"].strip() == evidence.original_mechanism.strip()
            and url.scheme == "https"
            and (url.hostname == "clinicalgenome.org" or (url.hostname or "").endswith(".clinicalgenome.org"))
            and evidence.source_record_hash == digest(evidence.raw_assertion)["value"])


class MechanismAssertion(Model):
    mechanism: Literal["LOSS_OF_FUNCTION", "GAIN_OF_FUNCTION", "DOMINANT_NEGATIVE", "OTHER", "UNKNOWN"]
    confidence: Literal["DEFINITIVE", "INFERRED", "DISPUTED", "UNKNOWN"]
    scope: Literal["DISEASE_SPECIFIC", "GENE_LEVEL"]
    basis: str
    supporting_evidence_refs: list[str] = Field(default_factory=list)
    conflicting_evidence_refs: list[str] = Field(default_factory=list)


class MechanismAssessment(Model):
    schema_version: Literal["helper-mechanism-assessment-1.0"] = VERSION
    identity: MechanismIdentity
    gene_disease_association_status: Literal["CURATED", "INFERRED", "NOT_FOUND", "AMBIGUOUS", "DISPUTED", "SOURCE_UNAVAILABLE"]
    assertions: list[MechanismAssertion] = Field(default_factory=list)
    mechanism: str = "UNKNOWN"
    mechanism_confidence: Literal["DEFINITIVE", "INFERRED", "DISPUTED", "UNKNOWN"] = "UNKNOWN"
    mechanism_scope: Literal["DISEASE_SPECIFIC", "GENE_LEVEL"] = "DISEASE_SPECIFIC"
    mechanism_basis: str = "INSUFFICIENT_EVIDENCE"
    supporting_evidence: list[MechanismEvidence] = Field(default_factory=list)
    conflicting_evidence: list[MechanismEvidence] = Field(default_factory=list)
    gene_level_indicators: list[dict] = Field(default_factory=list)
    contextual_evidence: list[MechanismEvidence] = Field(default_factory=list)
    mapping_uncertainty: list[str] = Field(default_factory=list)
    provenance: dict = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


def assess(matrix):
    """Explicit statements outrank gene-level HI/pLI; no disease inference from constraint."""
    identity = matrix.identity
    # Preserve the original supporting record if the matrix also carries a
    # contradictory view of it. Never lose contradictory-only records.
    evidence = {e.evidence_id: e for e in (*matrix.contradictory_evidence, *matrix.contextual_evidence, *matrix.direct_evidence)}
    indicators = gene_level_indicators(identity, list(evidence.values()))
    scoped = [e for e in evidence.values() if e.gene_id == identity.gene_id
              and e.applicability in {"EXACT", "MAPPED"}
              and bool({identity.disease_id, *identity.disease_aliases}.intersection(e.disease_ids))
              and identity.allelic_requirement != "UNKNOWN"
              and e.allelic_requirement == identity.allelic_requirement]
    direct = [e for e in scoped if e.evidence_category == "DIRECT_MECHANISM_ASSERTION"
              and e.asserted_mechanism not in {"UNKNOWN", "MIXED"}
              and e.evidence_directness == "DIRECT" and e.evidence_direction == "SUPPORTING"
              and (e.source in CURATED_SOURCES or approved_vcep_assertion(e))]
    negative = [e for e in scoped if e.evidence_category == "DIRECT_MECHANISM_ASSERTION"
                and e.evidence_directness == "DIRECT" and e.evidence_direction == "CONTRADICTING"
                and (e.source in CURATED_SOURCES or approved_vcep_assertion(e))]
    vcep = [e for e in direct if approved_vcep_assertion(e)]
    validity = [e for e in scoped if e.evidence_category == "GENE_DISEASE_VALIDITY"]
    associations = [e for e in scoped if e.evidence_category in {"DIRECT_MECHANISM_ASSERTION", "GENE_DISEASE_VALIDITY"}]
    association = "CURATED" if associations else "NOT_FOUND"
    if any(disputed_validity(e) for e in validity):
        association = "DISPUTED"
    elif not associations:
        if any(e.applicability in {"AMBIGUOUS_DISEASE_MAPPING", "DIFFERENT_INHERITANCE"}
               for e in evidence.values()) or identity.allelic_requirement == "UNKNOWN":
            association = "AMBIGUOUS"
        elif any(s.status not in {"AVAILABLE", "NO_RECORDS"} for s in matrix.source_status if s.source in {"g2p", "gencc"}):
            association = "SOURCE_UNAVAILABLE"
    incompatible = {e.asserted_mechanism for e in direct}
    disputed = len(incompatible) > 1
    assertions = []
    for mechanism in sorted({e.asserted_mechanism for e in direct}):
        support = [e for e in direct if e.asserted_mechanism == mechanism]
        opposing = ([e for e in direct if e.asserted_mechanism != mechanism and e.asserted_mechanism in incompatible]
                    if disputed else []) + negative
        assertions.append(MechanismAssertion(mechanism=mechanism, confidence="DISPUTED" if opposing else "DEFINITIVE",
            scope="DISEASE_SPECIFIC", basis="EXPLICIT_CURATED_MOLECULAR_MECHANISM",
            supporting_evidence_refs=[e.evidence_id for e in support], conflicting_evidence_refs=[e.evidence_id for e in opposing]))
    scoped_dosage = [e for e in scoped if e.evidence_category == "DOSAGE_SENSITIVITY"
                     and e.raw_assertion.get("assessment") == "haploinsufficiency"
                     and str(e.raw_assertion.get("hi_score", "")).strip() == "3"]
    if scoped_dosage and not direct:
        assertions.append(MechanismAssertion(mechanism="LOSS_OF_FUNCTION", confidence="INFERRED", scope="DISEASE_SPECIFIC",
            basis="CLINGEN_HI_SUFFICIENT_EVIDENCE_3_WITH_QUALIFIED_DISEASE_AND_INHERITANCE",
            supporting_evidence_refs=[e.evidence_id for e in scoped_dosage]))
        if association == "NOT_FOUND":
            association = "INFERRED"
    # ClinGen score 3 explicitly means sufficient evidence for haploinsufficiency.
    # It supports a gene-level LoF hypothesis, never a target-disease assignment.
    dosage = [evidence[i["evidence_id"]] for i in indicators if i["metric"] == "HI" and i["supports_lof"]
              and evidence[i["evidence_id"]].applicability == "GENE_LEVEL"]
    if dosage:
        assertions.append(MechanismAssertion(mechanism="LOSS_OF_FUNCTION", confidence="INFERRED", scope="GENE_LEVEL",
            basis="GENE_LEVEL_INFERENCE:CLINGEN_HI_SUFFICIENT_EVIDENCE_3",
            supporting_evidence_refs=[e.evidence_id for e in dosage]))
    constraint_refs = [i["evidence_id"] for i in indicators if i["metric"] == "pLI" and i["supports_lof"]]
    if constraint_refs:
        assertions.append(MechanismAssertion(mechanism="LOSS_OF_FUNCTION", confidence="INFERRED", scope="GENE_LEVEL",
            basis="GENE_LEVEL_INFERENCE:GNOMAD_PLI_GE_0_9", supporting_evidence_refs=constraint_refs))
    # An explicit approved VCEP statement has priority even over curated generic
    # statements. Conflicts stay visible; conflicting VCEP statements stay disputed.
    vcep_mechanisms = {e.asserted_mechanism for e in vcep}
    assertions = [a.copy(update={"confidence": "DEFINITIVE" if len(vcep_mechanisms) == 1 else "DISPUTED",
                                "basis": "EXPLICIT_APPROVED_VCEP_MOLECULAR_MECHANISM"})
                  if a.scope == "DISEASE_SPECIFIC" and a.mechanism in vcep_mechanisms else a
                  for a in assertions]
    primary = next((a for a in assertions if a.scope == "DISEASE_SPECIFIC" and a.mechanism in vcep_mechanisms), None)
    primary = primary or next((a for a in assertions if a.scope == "DISEASE_SPECIFIC"), None)
    primary = primary or next(iter(assertions), None)
    used = {ref for a in assertions for ref in a.supporting_evidence_refs}
    conflicts = {ref for a in assertions for ref in a.conflicting_evidence_refs} | {e.evidence_id for e in negative}
    limits = list(matrix.missing_evidence) + [
        "DEFINITIVE describes an explicit curated mechanism, not independent clinical validation",
        "ClinVar LoF distributions qualified independently of PVS1 are not available in the existing adapter",
        "Constraint alone and isolated P/LP variants do not infer a disease mechanism",
        "Gene-level haploinsufficiency does not establish applicability to the target disease or inheritance",
        "pLI >= 0.9 supports predicted heterozygous LoF intolerance only; low pLI does not exclude recessive LoF disease",
        "Constraint flags, unverified releases and ambiguous transcripts cannot drive pLI inference",
    ]
    if not vcep:
        limits.append("No applicable approved VCEP molecular-mechanism assertion with archived official provenance is available; classification profiles do not establish a mechanism")
    if vcep and conflicts:
        limits.append("Conflicting source mechanisms are retained despite approved VCEP precedence; review is required")
    return MechanismAssessment(identity=identity, gene_disease_association_status=association, assertions=assertions,
        mechanism=primary.mechanism if primary else "UNKNOWN", mechanism_confidence=primary.confidence if primary else "UNKNOWN",
        mechanism_scope=primary.scope if primary else "DISEASE_SPECIFIC", mechanism_basis=primary.basis if primary else "INSUFFICIENT_EVIDENCE",
        supporting_evidence=[evidence[k] for k in sorted(used)], conflicting_evidence=[evidence[k] for k in sorted(conflicts)],
        gene_level_indicators=indicators,
        contextual_evidence=[evidence[k] for k in sorted({i["evidence_id"] for i in indicators})],
        mapping_uncertainty=matrix.mapping_uncertainty,
        provenance={**matrix.provenance, "assessment_version": VERSION, "snapshot_id": matrix.snapshot_id,
                    "assessment_rules_version": RULES_VERSION,
                    "selected_vcep_specifications": [{"id": e.source_record_id, "version": e.source_record_version,
                        "source": e.source, "source_url": e.raw_assertion["source_url"],
                        "source_record_ref": e.source_record_ref, "source_record_hash": e.source_record_hash,
                        "retrieved_at": e.retrieved_at} for e in vcep],
                    "source_status": [s.dict() for s in matrix.source_status],
                    "inference_rules": {"CLINGEN_HI_SUFFICIENT_EVIDENCE_3": {
                        "source": "https://www.clinicalgenome.org/tools/cnv-webinar/faq/",
                        "interpretation": "HI score 3 supports a gene-level LoF inference; disease and inheritance require separate qualified evidence"},
                        "GNOMAD_PLI_GE_0_9": {
                            "threshold": PLI_THRESHOLD,
                            "source": "https://www.clinicalgenome.org/site/assets/files/5747/use_of_the_genome_aggregation_database_gnomad_anne_odonnell_luria.pdf",
                            "interpretation": "Qualified pLI supports gene-level predicted LoF intolerance, never a disease-specific assertion; no LOEUF cutoff is applied"}}},
        limitations=list(dict.fromkeys(limits)))
