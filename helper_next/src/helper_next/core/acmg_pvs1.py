"""Common PVS1 technical evidence builder; never NMD, applicability or strength.

Plain transport dictionaries use the existing engine contract. This module does
not define or import a second set of domain models.
"""
import copy
from datetime import datetime, timezone

from helper_next.core.acmg_client import digest
from helper_next.core.acmg_transcripts import VERSION, complement, genomic_to_mrna, mrna_to_genomic, translate
from helper_next.core.analysis_history import now


SOFTWARE = "helper-nonsense-1.0"
TECHNICAL_SOFTWARE = "helper-pvs1-technical-1.0"


def technical_consequence(annotation):
    """Select an annotated consequence, never predict a molecular outcome."""
    terms = set(annotation.get("consequence", "").replace(",", "&").split("&"))
    return next((term for term in (
        "transcript_ablation", "transcript_amplification", "exon_loss_variant", "copy_number_change",
        "frameshift_variant", "stop_gained", "splice_acceptor_variant", "splice_donor_variant",
        "start_lost", "splice_region_variant", "splice_donor_region_variant",
        "splice_donor_5th_base_variant", "splice_polypyrimidine_tract_variant") if term in terms), None)


def incomplete_reason(consequence):
    if consequence is None:
        return "No supported PVS1 technical consequence is recorded in the selected annotation"
    if consequence == "frameshift_variant":
        return "Validated indel-to-transcript mapping, altered CDS/frame and downstream stop reconstruction are not available; annotation/HGVS alone do not establish a PTC"
    if consequence and consequence.startswith("splice_"):
        return "A qualified splice event with transcript-specific RNA or other validated effect evidence is missing; splice annotation or prediction alone does not establish exon skipping, reading frame, PTC or NMD"
    if consequence == "start_lost":
        return "Validated initiation effect, alternative initiation/reinitiation and relevant transcript evidence are missing; start-loss annotation alone is insufficient"
    return "Exact exon event boundaries, affected copies, orientation and transcript-specific structural effect are not qualified; annotation alone does not establish exon deletion/duplication structure or frame"


def provenance(source, identifier, version, acquired_at, original, url=None):
    acquired_at = datetime.fromisoformat(acquired_at.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return {"source": source, "source_identifier": identifier, "source_version": version,
            "acquired_at": acquired_at, "extraction_method": "ALGORITHM", "software_version": SOFTWARE,
            "verification_status": "UNVERIFIED", "source_url": url, "references": [],
            "artifact_digest": digest(original), "limitations": ["Technical checks do not constitute clinical or human verification"],
            "verification": None}


def nonsense(identity, annotation, reference):
    """Reconstruct a premature stop for a contiguous equal-length substitution."""
    selected = reference["transcript"]["accession"] + "." + reference["transcript"]["version"]
    if (annotation["transcript"] != selected or identity["assembly"] != reference["assembly"]
            or identity["chromosome"] != reference["chromosome"]):
        raise ValueError("Selected variant assembly/chromosome/transcript does not match reference")
    ref, alt = identity["reference"], identity["alternate"]
    if len(ref) != len(alt) or not ref or set(ref + alt) - set("ACGT") or ref == alt:
        raise ValueError("Only unambiguous equal-length substitutions are supported for nonsense")
    positions = [genomic_to_mrna(reference["exons"], reference["strand"], identity["position"] + i)
                 for i in range(len(ref))]
    if None in positions or sorted(positions) != list(range(min(positions), max(positions) + 1)):
        raise ValueError("Variant cannot be mapped contiguously to the selected spliced transcript")
    start, end = min(positions), max(positions)
    if start < reference["cds_start"] or end > reference["cds_end"]:
        raise ValueError("Variant is outside the verified CDS")
    transcript_ref, transcript_alt = (ref, alt) if reference["strand"] == "+" else (complement(ref), complement(alt))
    if reference["cdna"][start - 1:end] != transcript_ref:
        raise ValueError("Genomic REF (strand adjusted) disagrees with transcript sequence")
    coding_position = start - reference["cds_start"] + 1
    offset = coding_position - 1
    altered_cds = reference["cds"][:offset] + transcript_alt + reference["cds"][offset + len(ref):]
    stop_index = translate(altered_cds).find("*")
    if stop_index < 0 or stop_index >= reference["protein_length"]:
        raise ValueError("Reconstructed allele does not introduce a premature in-frame stop")
    ptc = reference["cds_start"] + 3 * stop_index
    codon_offset = 3 * stop_index
    downstream = [j for j in reference["junctions"] if j["mrna_position"] >= ptc]
    # The last exon-exon boundary is supplied as a geometric fact. The engine
    # decides whether it is biologically relevant for NMD under its own policy.
    junction = reference["junctions"][-1] if downstream else None
    return {"coding_position": coding_position, "ptc_mrna_position": ptc,
            "ptc_genomic_position": mrna_to_genomic(reference["exons"], reference["strand"], ptc),
            "reference_codon": reference["cds"][codon_offset:codon_offset + 3],
            "altered_codon": altered_cds[codon_offset:codon_offset + 3], "protein_position": stop_index + 1,
            "transcript_ref": transcript_ref, "transcript_alt": transcript_alt,
            "junction": junction, "ptc_to_last_junction_nt": junction["mrna_position"] - ptc if junction else None,
            "ptc_to_last_junction_inclusive_nt": junction["mrna_position"] - ptc + 1 if junction else None,
            "ptc_to_next_junction_nt": downstream[0]["mrna_position"] - ptc if downstream else None,
            "formula_version": SOFTWARE,
            "formula": "coding_position = allele_mRNA_start - CDS_start + 1; PTC = CDS_start + 3 * first_stop_index; distance_nt = junction_upstream_exon_mRNA_end - PTC_first_base; inclusive_tail_nt = distance_nt + 1",
            "inputs": {"identity": identity, "cds_start": reference["cds_start"],
                       "cds_digest": digest(reference["cds"]), "junctions": reference["junctions"]}}


def transform(identity, annotation, context, source, candidates, mechanism_assessment=None):
    """One observation builder for all annotated PVS1 technical classes.

    The existing nonsense reconstruction is retained. Other classes carry an
    incomplete observation and original reference data, never invented effects.
    """
    selected_consequence = technical_consequence(annotation)
    is_nonsense = selected_consequence == "stop_gained"
    software = SOFTWARE if is_nonsense else TECHNICAL_SOFTWARE
    reference = source.get("data")
    timestamp = source.get("acquired_at") or now()
    missing = [{"path": "/observation/mechanism/lof_established", "reason": "Explicit gene-disease/inheritance mechanism review required; candidates do not establish LoF"},
               {"path": "/provenance/verification", "reason": "Human attestation and evidence quality review not recorded"}]
    warnings = ["MANE does not establish clinical relevance, affected exon relevance or absence of rescue",
                "HGVS strings retained from the selected annotation; not independently normalized"]
    original = {"identity": identity, "annotation": annotation, "transcript_reference": reference,
                "transcript_source": {k: v for k, v in source.items() if k != "data"},
                "gene_disease_candidates": candidates, "calculation": None}
    if not is_nonsense:
        original["technical_consequence"] = selected_consequence
        original["technical_context"] = None
    prov = provenance("HELPER nonsense evidence transformation", "helper-nonsense",
                      reference["annotation_release"] if reference else None, timestamp, original,
                      "https://rest.ensembl.org/" if reference else None)
    if not is_nonsense:
        prov.update(source="HELPER PVS1 technical evidence preparation", source_identifier="helper-pvs1-technical",
                    software_version=software)
    mechanism = None
    modes = context.get("gene_disease", {}).get("inheritance_modes", [])
    if len(modes) == 1 and context.get("gene") and context.get("disease"):
        mechanism = {"gene": context["gene"], "disease": context["disease"], "inheritance": modes[0],
                     "mechanisms": [], "lof_established": "UNKNOWN", "basis": "TABLE_1_2018", "validity": "UNKNOWN",
                     "pathogenic_lof_without_pvs1": None, "phenotype_lof_fraction": None, "across_exons": None,
                     "single_exon_gene": None, "null_mouse_recaptures_phenotype": None, "expert_strength_downgrade": None,
                     "dosage_information": None, "rationale": "Source candidates retained separately; explicit contextual review required",
                     "provenance": provenance("Unreviewed gene-disease source candidates", "helper-gene-disease-review",
                                              None, timestamp, candidates)}
    else:
        missing.append({"path": "/observation/mechanism", "reason": "One explicitly selected inheritance and stable gene-disease context are required"})
    if mechanism is not None and mechanism_assessment is not None:
        if not mechanism_assessment.matches_context(context):
            original["rejected_mechanism_assessment"] = mechanism_assessment.dict()
            missing.append({"path": "/observation/mechanism/confidence_assessment", "reason": "Mechanism assessment does not match the selected gene/disease/inheritance"})
            mechanism_assessment = None
    if mechanism is not None and mechanism_assessment is not None:
        assessment = mechanism_assessment.dict()
        mechanism["confidence_assessment"] = mechanism_assessment.confidence_contract()
        mechanism["mechanisms"] = list(dict.fromkeys(a["mechanism"] for a in assessment["assertions"]))
        mechanism["rationale"] = assessment["mechanism_basis"]
        original["mechanism_assessment"] = assessment
        missing = [m for m in missing if m["path"] != "/observation/mechanism/lof_established"]
        if assessment["mechanism_confidence"] == "UNKNOWN":
            missing.append({"path": "/observation/mechanism/confidence_assessment", "reason": "Supported molecular mechanism is unavailable"})
    effects = []
    if reference:
        gene_id = context.get("gene", {}).get("identifier")
        try:
            if gene_id not in reference["gene_ids"] and gene_id.removeprefix("ENSEMBL:") not in reference["gene_ids"]:
                raise ValueError("Transcript gene identity is not demonstrated for the selected stable gene")
            selected = reference["transcript"]["accession"] + "." + reference["transcript"]["version"]
            if (annotation["transcript"] != selected or identity["assembly"] != reference["assembly"]
                    or identity["chromosome"] != reference["chromosome"]):
                raise ValueError("Selected variant assembly/chromosome/transcript does not match reference")
            if not is_nonsense:
                original["technical_context"] = {k: copy.deepcopy(reference[k]) for k in (
                    "transcript", "assembly", "chromosome", "strand", "exons", "cds_start", "cds_end", "protein_length")}
                raise ValueError(incomplete_reason(selected_consequence))
            facts = nonsense(identity, annotation, reference)
            original["calculation"] = facts
            tx_prov = provenance("Ensembl targeted transcript reference", "ensembl_transcript", reference["annotation_release"],
                                 reference["acquired_at"], reference, reference["source_urls"].get("lookup"))
            transcript = {k: copy.deepcopy(reference[k]) for k in (
                "transcript", "assembly", "chromosome", "strand", "biotype", "mane", "exons", "cds_start", "cds_end", "protein_length")}
            transcript.update(gene=context["gene"], coordinate_model="REFERENCE", clinical_relevance="UNKNOWN",
                              affected_exon_relevant="UNKNOWN", alternative_rescue="UNKNOWN", reinitiation="UNKNOWN",
                              expression_evidence=[], alternative_isoforms=[], provenance=tx_prov)
            consequence = {"kind": "NONSENSE", "annotation_consequence": "stop_gained",
                           "coding_position": facts["coding_position"], "hgvs_coding": annotation.get("hgvsc") or None,
                           "hgvs_protein": annotation.get("hgvsp") or None, "ptc_mrna_position": facts["ptc_mrna_position"],
                           "ptc_genomic_position": facts["ptc_genomic_position"], "downstream_stop_validated": True,
                           "reading_frame": "IN_FRAME", "protein_region": None, "start_loss": None,
                           "experimental_protein_evidence": [], "experimental_rna_degradation": "UNKNOWN",
                           "provenance": provenance("Reference/alternate codon reconstruction", "helper-nonsense-codon",
                                                    reference["annotation_release"], timestamp, original, "https://rest.ensembl.org/")}
            effects.append({"transcript": transcript, "consequence": consequence, "splicing": None})
            for field in ("clinical_relevance", "affected_exon_relevant", "alternative_rescue"):
                missing.append({"path": "/observation/transcript_effects/0/transcript/" + field,
                                "reason": "Explicit contextual review not recorded"})
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            missing.append({"path": "/observation/transcript_effects", "reason": str(exc)})
    else:
        missing.append({"path": "/observation/transcript_effects", "reason": source.get("missing", "Qualified transcript/CDS unavailable")})
    if not is_nonsense:
        reason = incomplete_reason(selected_consequence)
        if not any(m["reason"] == reason for m in missing):
            missing.append({"path": "/observation/transcript_effects", "reason": reason})
    prov["artifact_digest"] = digest(original)
    item = {"id": "helper-pvs1-nonsense" if is_nonsense else "helper-pvs1-technical", "kind": "PVS1", "related_evidence_ids": [c["id"] for c in candidates],
            "limitations": [m["reason"] for m in missing], "provenance": prov,
            "observation": {"variant_identity": identity, "mechanism": mechanism,
                            "transcript_effects": effects, "structural": None, "used_by_criteria": []}}
    return {"evidence": item, "original": original, "missing_evidence": missing, "warnings": warnings,
            "status": "TECHNICALLY_VERIFIED" if effects else "INCOMPLETE",
            "transformer": "PVS1_NONSENSE" if is_nonsense else "PVS1_TECHNICAL",
            "software_version": software, "transcript_provider_version": VERSION}
