"""Shared PVS1 input/result containers with structural validation only.

Unknown scientific values may be omitted or None (or an explicit UNKNOWN enum).
No consequence, RNA event, PTC, NMD, review status or strength is inferred.
TypedDicts describe blocks and one shared product record, not runtime models.
Source references map field names to essential versioned citations/locators.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple, TypedDict


Interval = Tuple[int, int]
SourceReferences = Dict[str, List[str]]
PVS1Status = Literal[
    "ACTIVE", "INACTIVE", "NOT_EVALUABLE", "REQUIRES_REVIEW", "EXPLORATORY"
]
PVS1Strength = Literal["VERY_STRONG", "STRONG", "MODERATE", "SUPPORTING"]


class VariantData(TypedDict, total=False):
    """Normalized genomic identity; coordinate is a point, not an interval."""

    assembly: str
    contig: str
    position: int
    reference_allele: str
    alternate_allele: str
    consequence: str
    coordinate_system: Literal["genomic_1_based"]
    source_refs: Optional[SourceReferences]


class DiseaseContextData(TypedDict, total=False):
    gene: str
    disease: Optional[str]
    inheritance: Optional[str]
    molecular_mechanism: Optional[Literal["LoF", "GoF", "DN", "OTHER", "UNKNOWN"]]
    confidence: Optional[Literal["DEFINITIVE", "INFERRED", "DISPUTED", "UNKNOWN"]]
    scope: Optional[Literal["DISEASE_SPECIFIC", "GENE_LEVEL"]]
    source_refs: Optional[SourceReferences]


class TranscriptData(TypedDict, total=False):
    """Reference transcript and its genomic exons, including UTRs.

    CDS: spliced RNA, base 1, closed interval including the normal stop codon.
    Genomic exons: variant contig/assembly, base 1, closed intervals, listed in
    transcript 5'-to-3' order. Junctions follow from adjacent exons and strand.
    Phases: 0/1/2 bases to the next full codon at each coding segment's 5' edge;
    list aligned with exons, with None for unavailable/noncoding entries.
    sequence is the full spliced reference sequence in transcript orientation;
    sequence_ref identifies a qualified/versioned sequence without fetching it.
    affected_exon_lof_tolerant and rescue_present are externally curated facts
    about frequent LoF tolerance and pertinent functional rescue, not inferred
    from frequency annotations/isoform catalogs; absent remains unknown.
    """

    accession: Optional[str]
    strand: Optional[Literal["+", "-"]]
    coordinate_system: Optional[Literal["transcript_1_based_closed"]]
    cds_interval: Optional[Interval]
    exon_genomic_intervals: Optional[List[Interval]]
    exon_coordinate_system: Optional[Literal["genomic_1_based_closed"]]
    exon_phases: Optional[List[Optional[int]]]
    biologically_relevant: Optional[bool]
    affected_exon_relevant: Optional[bool]
    affected_exon_lof_tolerant: Optional[bool]
    rescue_present: Optional[bool]
    sequence: Optional[str]
    sequence_ref: Optional[str]
    source_refs: Optional[SourceReferences]


class MolecularProductData(TypedDict, total=False):
    """One record reused for all consequences and evidence bases.

    basis labels the RNA event/product evidence, not clinical pathogenicity.
    ptc_start is the first stop-codon base on transcript_ref (the resulting,
    possibly altered RNA), base 1. Never substitute the reference transcript.
    involved_exons are reference exon indices, base 1, in transcript order.
    retained_exon_interval is the retained part of one CRYPTIC_SITE exon on
    the selected reference transcript RNA, base 1, closed, in 5'-to-3' order.
    Only one boundary may move: 3' for donor, 5' for acceptor; not product RNA.
    genomic_junctions are (last upstream exonic base, first downstream exonic
    base) on the variant contig/assembly, base 1, in transcript direction;
    they are oriented pairs, not intervals (descending pairs on minus strand).
    Protein intervals are base 1, closed, on protein_accession.
    Frame/PTC assertions can have their own sources even for OBSERVED RNA.
    """

    basis: Literal["PREDICTED", "OBSERVED", "UNKNOWN"]
    event_type: Optional[Literal[
        "EXON_SKIPPING", "CRYPTIC_SITE", "INTRON_RETENTION", "OTHER", "UNKNOWN"
    ]]
    involved_exons: Optional[List[int]]
    retained_exon_interval: Optional[Interval]
    genomic_junctions: Optional[List[Tuple[int, int]]]
    transcript_ref: Optional[str]
    coordinate_system: Optional[Literal["transcript_1_based_closed"]]
    sequence: Optional[str]
    frame_effect: Optional[Literal["IN_FRAME", "OUT_OF_FRAME", "UNKNOWN"]]
    ptc_start: Optional[int]
    ptc_junction_distances: Optional[List[Tuple[int, int]]]
    protein_accession: Optional[str]
    protein_coordinate_system: Optional[Literal["protein_1_based_closed"]]
    lost_protein_region: Optional[Interval]
    altered_protein_region: Optional[Interval]
    lost_region_critical: Optional[bool]
    functional_evidence: Optional[List[str]]
    evidence_quality: Optional[str]
    source_refs: Optional[SourceReferences]


class MolecularEffectData(TypedDict, total=False):
    """Conditional data shared by stop-gain, frameshift and splice inputs.

    The normalized indel is stored only in variant. cds_edit_interval describes
    the affected reference CDS span without a VCF anchor: base 0, half-open;
    an insertion uses an empty span [k, k). Its reference is transcript's CDS.
    A splice site's genomic anchor is the last exonic donor base or first exonic
    acceptor base; offset is signed in transcript direction, no zero omission.
    Distinct predicted and observed products remain distinct list entries.
    """

    cds_edit_interval: Optional[Interval]
    cds_coordinate_system: Optional[Literal["cds_0_based_half_open"]]
    splice_site_type: Optional[Literal["DONOR", "ACCEPTOR", "OTHER", "UNKNOWN"]]
    splice_site_genomic_position: Optional[int]
    splice_site_offset: Optional[int]
    native_splice_motif: Optional[str]
    products: Optional[List[MolecularProductData]]
    source_refs: Optional[SourceReferences]


def _block(value, shape, path):
    if not isinstance(value, dict):
        raise ValueError("{} must be an object".format(path))
    unknown = set(value) - set(shape.__annotations__)
    if unknown:
        raise ValueError("{} contains unsupported fields: {}".format(path, unknown))
    return value


def _scalar(value, expected, path, required=False):
    if value is None and not required:
        return
    if type(value) is not expected or (expected is str and not value.strip()):
        raise ValueError("{} must be a nonempty {}".format(path, expected.__name__))


def _choice(value, choices, path, required=False):
    if value is None and not required:
        return
    if not isinstance(value, str) or value not in choices:
        raise ValueError("{} must be one of {}".format(path, choices))


def _integer(value, path, minimum=None):
    _scalar(value, int, path, required=True)
    if minimum is not None and value < minimum:
        raise ValueError("{} must be >= {}".format(path, minimum))


def _interval(value, path, base=1, oriented=False):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("{} must contain two endpoints".format(path))
    for endpoint in value:
        _integer(endpoint, path, minimum=base)
    if not oriented and value[1] < value[0]:
        raise ValueError("{} has reversed endpoints".format(path))


def _list(value, path):
    if not isinstance(value, list):
        raise ValueError("{} must be a list".format(path))


def _sources(value, path):
    if value is None:
        return
    if not isinstance(value, dict):
        raise ValueError("{} must map fields to source lists".format(path))
    for name, references in value.items():
        _scalar(name, str, path, required=True)
        _list(references, path)
        if not references:
            raise ValueError("{} source lists must not be empty".format(path))
        for reference in references:
            _scalar(reference, str, path, required=True)


@dataclass
class PVS1Input:
    """One common input; validation checks shape, types and coordinate labels only.

    Scientific fields may be omitted/None. Provenance may be unavailable, but
    present citations must be nonempty strings. No completeness or truth verdict.
    Use json.dumps(dataclasses.asdict(instance)) for standard serialization.
    """

    variant: VariantData
    disease_context: DiseaseContextData
    transcript: Optional[TranscriptData] = None
    molecular_effect: Optional[MolecularEffectData] = None

    def __post_init__(self):
        variant = _block(self.variant, VariantData, "variant")
        for name in ("assembly", "contig", "reference_allele", "alternate_allele", "consequence"):
            _scalar(variant.get(name), str, "variant." + name, required=True)
        _integer(variant.get("position"), "variant.position", minimum=1)
        _choice(variant.get("coordinate_system"), ("genomic_1_based",), "variant.coordinate_system", True)
        _sources(variant.get("source_refs"), "variant.source_refs")
        context = _block(self.disease_context, DiseaseContextData, "disease_context")
        _scalar(context.get("gene"), str, "disease_context.gene", required=True)
        for name in ("disease", "inheritance"):
            _scalar(context.get(name), str, "disease_context." + name)
        _choice(context.get("molecular_mechanism"), ("LoF", "GoF", "DN", "OTHER", "UNKNOWN"), "molecular_mechanism")
        _choice(context.get("confidence"), ("DEFINITIVE", "INFERRED", "DISPUTED", "UNKNOWN"), "confidence")
        _choice(context.get("scope"), ("DISEASE_SPECIFIC", "GENE_LEVEL"), "scope")
        _sources(context.get("source_refs"), "disease_context.source_refs")
        if self.transcript is not None:
            self._validate_transcript()
        if self.molecular_effect is not None:
            self._validate_effect()

    def _validate_transcript(self):
        data = _block(self.transcript, TranscriptData, "transcript")
        for name in ("accession", "sequence", "sequence_ref"):
            _scalar(data.get(name), str, "transcript." + name)
        _choice(data.get("strand"), ("+", "-"), "transcript.strand")
        _choice(data.get("coordinate_system"), ("transcript_1_based_closed",), "transcript.coordinate_system")
        _choice(data.get("exon_coordinate_system"), ("genomic_1_based_closed",), "transcript.exon_coordinate_system")
        if data.get("cds_interval") is not None:
            _interval(data["cds_interval"], "transcript.cds_interval")
            _scalar(data.get("accession"), str, "transcript.accession", required=True)
            _choice(data.get("coordinate_system"), ("transcript_1_based_closed",), "transcript.coordinate_system", True)
        exons = data.get("exon_genomic_intervals")
        if exons is not None:
            _list(exons, "transcript.exon_genomic_intervals")
            _choice(data.get("exon_coordinate_system"), ("genomic_1_based_closed",), "transcript.exon_coordinate_system", True)
            for interval in exons:
                _interval(interval, "transcript.exon_genomic_intervals")
        phases = data.get("exon_phases")
        if phases is not None:
            _list(phases, "transcript.exon_phases")
            if exons is None or len(phases) != len(exons):
                raise ValueError("exon_phases must align with exon_genomic_intervals")
            for phase in phases:
                if phase is not None:
                    _integer(phase, "transcript.exon_phases", minimum=0)
                    if phase > 2:
                        raise ValueError("exon phases must be 0, 1, 2 or None")
        for name in ("biologically_relevant", "affected_exon_relevant", "affected_exon_lof_tolerant", "rescue_present"):
            _scalar(data.get(name), bool, "transcript." + name)
        _sources(data.get("source_refs"), "transcript.source_refs")

    def _validate_effect(self):
        data = _block(self.molecular_effect, MolecularEffectData, "molecular_effect")
        _choice(data.get("cds_coordinate_system"), ("cds_0_based_half_open",), "cds_coordinate_system")
        if data.get("cds_edit_interval") is not None:
            _interval(data["cds_edit_interval"], "cds_edit_interval", base=0)
            _choice(data.get("cds_coordinate_system"), ("cds_0_based_half_open",), "cds_coordinate_system", True)
            _scalar((self.transcript or {}).get("accession"), str, "transcript.accession", required=True)
        _choice(data.get("splice_site_type"), ("DONOR", "ACCEPTOR", "OTHER", "UNKNOWN"), "splice_site_type")
        if data.get("splice_site_genomic_position") is not None:
            _integer(data["splice_site_genomic_position"], "splice_site_genomic_position", minimum=1)
        if data.get("splice_site_offset") is not None:
            _integer(data["splice_site_offset"], "splice_site_offset")
        _scalar(data.get("native_splice_motif"), str, "native_splice_motif")
        _sources(data.get("source_refs"), "molecular_effect.source_refs")
        products = data.get("products")
        if products is not None:
            _list(products, "products")
            for product in products:
                self._validate_product(product)

    @staticmethod
    def _validate_product(product):
        data = _block(product, MolecularProductData, "product")
        _choice(data.get("basis"), ("PREDICTED", "OBSERVED", "UNKNOWN"), "product.basis", True)
        _choice(data.get("event_type"), ("EXON_SKIPPING", "CRYPTIC_SITE", "INTRON_RETENTION", "OTHER", "UNKNOWN"), "product.event_type")
        _choice(data.get("frame_effect"), ("IN_FRAME", "OUT_OF_FRAME", "UNKNOWN"), "product.frame_effect")
        _choice(data.get("coordinate_system"), ("transcript_1_based_closed",), "product.coordinate_system")
        _choice(data.get("protein_coordinate_system"), ("protein_1_based_closed",), "product.protein_coordinate_system")
        if data.get("retained_exon_interval") is not None:
            _interval(data["retained_exon_interval"], "product.retained_exon_interval")
        for name in ("transcript_ref", "sequence", "protein_accession", "evidence_quality"):
            _scalar(data.get(name), str, "product." + name)
        if data.get("ptc_start") is not None:
            _integer(data["ptc_start"], "product.ptc_start", minimum=1)
            _scalar(data.get("transcript_ref"), str, "product.transcript_ref", required=True)
            _choice(data.get("coordinate_system"), ("transcript_1_based_closed",), "product.coordinate_system", True)
        distances = data.get("ptc_junction_distances")
        if distances is not None:
            _integer(data.get("ptc_start"), "product.ptc_start", minimum=1)
            _list(distances, "product.ptc_junction_distances")
            for pair in distances:
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    raise ValueError("ptc_junction_distances requires position/offset pairs")
                _integer(pair[0], "product.junction_position", minimum=1)
                _integer(pair[1], "product.junction_offset")
        for name in ("lost_protein_region", "altered_protein_region"):
            if data.get(name) is not None:
                _interval(data[name], "product." + name)
                _scalar(data.get("protein_accession"), str, "product.protein_accession", required=True)
                _choice(data.get("protein_coordinate_system"), ("protein_1_based_closed",), "product.protein_coordinate_system", True)
        _scalar(data.get("lost_region_critical"), bool, "product.lost_region_critical")
        for name in ("involved_exons", "genomic_junctions", "functional_evidence"):
            if data.get(name) is not None:
                _list(data[name], "product." + name)
                for value in data[name]:
                    if name == "involved_exons":
                        _integer(value, "product.involved_exons", minimum=1)
                    elif name == "genomic_junctions":
                        _interval(value, "product.genomic_junctions", oriented=True)
                    else:
                        _scalar(value, str, "product.functional_evidence", required=True)
        _sources(data.get("source_refs"), "product.source_refs")


@dataclass
class PVS1Result:
    """Caller-supplied values; validation does not reconcile or compute results."""

    status: PVS1Status
    reason: str
    calculated_strength: Optional[PVS1Strength] = None
    applied_strength: Optional[PVS1Strength] = None
    warnings: List[str] = field(default_factory=list)
    missing_data: List[str] = field(default_factory=list)
    decision_trace: List[str] = field(default_factory=list)
    requires_review: Optional[bool] = None
    ruleset_id: Optional[str] = None
    ruleset_version: Optional[str] = None

    def __post_init__(self):
        _choice(self.status, ("ACTIVE", "INACTIVE", "NOT_EVALUABLE", "REQUIRES_REVIEW", "EXPLORATORY"), "status", True)
        _scalar(self.reason, str, "reason", required=True)
        for name in ("calculated_strength", "applied_strength"):
            _choice(getattr(self, name), ("VERY_STRONG", "STRONG", "MODERATE", "SUPPORTING"), name)
        _scalar(self.requires_review, bool, "requires_review")
        for name in ("ruleset_id", "ruleset_version"):
            _scalar(getattr(self, name), str, name)
        for name in ("warnings", "missing_data", "decision_trace"):
            values = getattr(self, name)
            _list(values, name)
            for value in values:
                _scalar(value, str, name, required=True)
