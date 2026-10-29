"""Public-data cache models, separate from the ACMG Engine evidence contract."""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, StrictStr


SOURCES = ("g2p", "gencc", "clingen_dosage", "gnomad", "clinvar")
CachePolicy = Literal["CACHE_ONLY", "REFRESH_IF_STALE", "FORCE_REFRESH", "SNAPSHOT"]
Mechanism = Literal["LOSS_OF_FUNCTION", "GAIN_OF_FUNCTION", "DOMINANT_NEGATIVE", "MIXED", "OTHER", "UNKNOWN"]


class Model(BaseModel):
    class Config:
        extra = "forbid"
        allow_mutation = False


class MechanismIdentity(Model):
    gene_id: StrictStr
    gene_hgnc_id: Optional[StrictStr] = None
    gene_symbol: Optional[StrictStr] = None
    gene_aliases: list[str] = Field(default_factory=list)
    alternative_gene_ids: list[str] = Field(default_factory=list)
    disease_id: StrictStr
    disease_name: Optional[StrictStr] = None
    disease_aliases: list[str] = Field(default_factory=list)
    disease_alternative_names: list[str] = Field(default_factory=list)
    allelic_requirement: StrictStr = "UNKNOWN"


class SourcePacket(Model):
    source: Literal["g2p", "gencc", "clingen_dosage", "gnomad", "clinvar"]
    status: Literal["AVAILABLE", "NO_RECORDS", "CACHE_MISS", "UNREACHABLE", "ERROR", "NOT_SUPPORTED"]
    records: list[dict[str, Any]] = Field(default_factory=list)
    dataset_version: Optional[StrictStr] = None
    source_url: Optional[StrictStr] = None
    retrieved_at: StrictStr
    source_updated_at: Optional[StrictStr] = None
    etag: Optional[StrictStr] = None
    last_modified: Optional[StrictStr] = None
    stale: bool = False
    refresh_scope: Literal["LOCAL_INDEX", "TARGETED_REMOTE", "NOT_SUPPORTED"] = "LOCAL_INDEX"
    limitations: list[str] = Field(default_factory=list)
    remote_fetch_ms: Optional[float] = Field(default=None, ge=0)


class SourceState(Model):
    source: str
    status: str
    stale: bool = False
    checked_at: Optional[str] = None
    source_updated_at: Optional[str] = None
    dataset_version: Optional[str] = None
    source_url: Optional[str] = None
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    refresh_scope: str = "LOCAL_INDEX"
    error_code: Optional[str] = None
    limitations: list[str] = Field(default_factory=list)


class MechanismEvidence(Model):
    evidence_id: str
    source_record_ref: str
    source: str
    source_record_id: str
    source_record_version: Optional[str] = None
    source_dataset_version: Optional[str] = None
    gene_id: Optional[str] = None
    disease_ids: list[str] = Field(default_factory=list)
    allelic_requirement: str = "UNKNOWN"
    original_allelic_requirement: Optional[str] = None
    evidence_category: Literal["DIRECT_MECHANISM_ASSERTION", "GENE_DISEASE_VALIDITY", "DOSAGE_SENSITIVITY",
                               "POPULATION_CONSTRAINT", "VARIANT_CLASSIFICATION_CONTEXT", "OTHER"]
    asserted_mechanism: Mechanism = "UNKNOWN"
    original_mechanism: Optional[str] = None
    mechanism_detail: Optional[str] = None
    raw_assertion: dict[str, Any] = Field(default_factory=dict)
    evidence_direction: Literal["SUPPORTING", "CONTRADICTING", "CONTEXTUAL", "NOT_INFORMATIVE", "UNRESOLVED_APPLICABILITY"]
    evidence_directness: Literal["DIRECT", "INDIRECT", "CONTEXTUAL"]
    applicability: Literal["EXACT", "MAPPED", "GENE_LEVEL", "AMBIGUOUS_DISEASE_MAPPING", "UNRESOLVED_GENE_MAPPING", "DIFFERENT_INHERITANCE"]
    assertion_basis: str = "NOT_RECORDED"
    source_review_status: Optional[str] = None
    source_classification: Optional[str] = None
    references: list[str] = Field(default_factory=list)
    retrieved_at: str
    source_updated_at: Optional[str] = None
    source_record_hash: str
    raw_record_reference: str
    origin_group: str
    normalization_version: str


class MechanismHypothesis(Model):
    mechanism: Mechanism
    allelic_requirement: str
    supporting_evidence_refs: list[str] = Field(default_factory=list)
    contradictory_evidence_refs: list[str] = Field(default_factory=list)


class GeneDiseaseMechanismResult(Model):
    schema_version: Literal["helper-mechanism-matrix-1.0"] = "helper-mechanism-matrix-1.0"
    identity: MechanismIdentity
    candidate_mechanisms: list[Mechanism] = Field(default_factory=list)
    hypotheses: list[MechanismHypothesis] = Field(default_factory=list)
    resolution_status: Literal["SUPPORTED_BY_DIRECT_ASSERTION", "MULTIPLE_COMPATIBLE_ASSERTIONS", "CONFLICTING_ASSERTIONS", "INSUFFICIENT_EVIDENCE", "UNKNOWN"]
    reconciliation_status: Literal["UNRESOLVED", "CANDIDATE_ASSERTIONS_RECORDED"] = "UNRESOLVED"
    issues: list[str] = Field(default_factory=list)
    mapping_uncertainty: list[str] = Field(default_factory=list)
    direct_evidence: list[MechanismEvidence] = Field(default_factory=list)
    contextual_evidence: list[MechanismEvidence] = Field(default_factory=list)
    contradictory_evidence: list[MechanismEvidence] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    gene_disease_validity: list[dict[str, Any]] = Field(default_factory=list)
    mapping_evidence: list[dict[str, Any]] = Field(default_factory=list)
    source_status: list[SourceState] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    snapshot_id: Optional[str] = None
    review_status: Literal["NOT_REVIEWED"] = "NOT_REVIEWED"
    warnings: list[str] = Field(default_factory=list)
