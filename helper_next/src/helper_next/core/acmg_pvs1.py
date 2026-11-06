"""Local nonsense sequence reconstruction reused by the PVS1 molecular library."""
from helper_next.core.acmg_digest import digest
from helper_next.core.acmg_transcripts import genomic_to_mrna, mrna_to_genomic, translate, complement


SOFTWARE = "helper-nonsense-1.0"


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
