"""Task 28 biological interpretation of the existing mechanism matrix; no ACMG rules."""
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field

from helper_next.core.acmg_mechanism_models import Model, MechanismEvidence, MechanismIdentity
from helper_next.core.acmg_digest import digest

VERSION = "helper-mechanism-assessment-1.0"
RULES_VERSION = "helper-mechanism-assessment-rules-1.1"
CURATED_SOURCES = {"g2p", "gencc", "clingen", "orphanet", "orphadata"}


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
    mapping_uncertainty: list[str] = Field(default_factory=list)
    provenance: dict = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


def assess(matrix):
    """Explicit source statements outrank gene-level dosage; never infer from validity/LOEUF."""
    identity = matrix.identity
    # Preserve the original supporting record if the matrix also carries a
    # contradictory view of it. Never lose contradictory-only records.
    evidence = {e.evidence_id: e for e in (*matrix.contradictory_evidence, *matrix.contextual_evidence, *matrix.direct_evidence)}
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
    if validity and any((e.source_classification or "").casefold() in {"disputed", "refuted"} for e in validity):
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
    dosage = [e for e in evidence.values() if e.gene_id == identity.gene_id
              and e.evidence_category == "DOSAGE_SENSITIVITY"
              and e.raw_assertion.get("assessment") == "haploinsufficiency"
              and str(e.raw_assertion.get("hi_score", "")).strip() == "3"
              and e.applicability == "GENE_LEVEL"]
    if dosage:
        assertions.append(MechanismAssertion(mechanism="LOSS_OF_FUNCTION", confidence="INFERRED", scope="GENE_LEVEL",
            basis="GENE_LEVEL_INFERENCE:CLINGEN_HI_SUFFICIENT_EVIDENCE_3",
            supporting_evidence_refs=[e.evidence_id for e in dosage]))
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
    ]
    if not vcep:
        limits.append("No applicable approved VCEP molecular-mechanism assertion with archived official provenance is available; classification profiles do not establish a mechanism")
    if vcep and conflicts:
        limits.append("Conflicting source mechanisms are retained despite approved VCEP precedence; review is required")
    return MechanismAssessment(identity=identity, gene_disease_association_status=association, assertions=assertions,
        mechanism=primary.mechanism if primary else "UNKNOWN", mechanism_confidence=primary.confidence if primary else "UNKNOWN",
        mechanism_scope=primary.scope if primary else "DISEASE_SPECIFIC", mechanism_basis=primary.basis if primary else "INSUFFICIENT_EVIDENCE",
        supporting_evidence=[evidence[k] for k in sorted(used)], conflicting_evidence=[evidence[k] for k in sorted(conflicts)],
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
                        "interpretation": "HI score 3 supports a gene-level LoF inference; disease and inheritance require separate qualified evidence"}}},
        limitations=list(dict.fromkeys(limits)))
