"""Transcript-specific molecular metrics. No disease mechanism or PVS1 strength.

All reconstruction uses molecular.py; percentages describe reference sequence,
never remaining function or the abundance of a predicted protein after NMD.
"""
import copy
import re
from urllib.parse import unquote

from helper_next.core.acmg_transcripts import genomic_to_mrna
from pvs1.models import PVS1Input
from pvs1.molecular import compute_molecular_evidence, map_variant_to_cds, transcript_facts


VERSION = "helper-transcript-impact-1.0"
FORMULAS = {
    "stop_gain": "100 * (N - stop_codon + 1) / N; N excludes the natural terminal stop",
    "frameshift": "100 * (N - first_affected_reference_codon + 1) / N",
    "physical_deletion": "100 * trimmed_reference_nt_removed / (3 * N)",
    "protein_nonconserved": "100 * (N - first_divergent_aa + 1) / N; positional reference tail, not functional loss",
    "shortening": "max(0, N - predicted_protein_length)",
    "nmd": "predicted if last resulting exon junction - termination_first_base > 50 nt",
}


def molecular_impact(variant, gene, transcript, reference, consequence="", annotation=None):
    """Analyze one exact allele/reference; unannotated effects are reconstructed.

    An absent VEP row is never proof that a transcript is unaffected. Coding
    alleles are tested against its own reference sequence independently.
    """
    row = {"transcript": transcript, "status": "INSUFFICIENT_DATA", "consequence": consequence or None,
           "cds_length_nt": None, "translated_cds_length_nt": None, "cds_position": None,
           "first_affected_reference_codon": None, "reference_protein_length": None,
           "reference_cds_untranslated_percent": None, "reference_cds_disrupted_percent": None,
           "physical_deleted_nt": None, "physical_inserted_nt": None, "physical_cds_deleted_percent": None,
           "protein_impact_percent": None, "reference_amino_acids_lost": None,
           "reference_amino_acids_replaced": None, "first_divergent_aa": None,
           "predicted_protein_length": None, "predicted_protein_shortening_aa": None,
           "termination_codon": None, "termination_mrna_position": None, "ptc_mrna_position": None,
           "nmd_predicted": None, "nmd_distance_nt": None, "extends_into_utr": None,
           "conditional": False, "warnings": [], "missing_data": [], "formulas": FORMULAS,
           "algorithm_version": VERSION, "provenance": {}, "pvs1_input": None, "calculation": None, "reference": None}
    if not reference:
        row["missing_data"].append("Qualified transcript reference unavailable")
        return row
    row.update(biotype=reference.get("biotype"), strand=reference.get("strand"),
               mane=reference.get("mane"), canonical=reference.get("canonical"), appris=reference.get("appris"))
    row["provenance"] = {key: copy.deepcopy(reference.get(key)) for key in
                         ("transcript", "assembly", "annotation_release", "gene_ids", "source_urls", "artifact_digest", "acquired_at")}
    try:
        sample = PVS1Input(variant=dict(variant, consequence=consequence or "UNKNOWN"),
                           disease_context={"gene": gene, "molecular_mechanism": "UNKNOWN"},
                           transcript={"accession": transcript})
        qualified = transcript_facts(sample, reference)
        if qualified["status"] != "COMPLETE":
            row["missing_data"].extend(qualified["missing_data"])
            return row
        row["reference"] = {key: reference[key] for key in ("cds", "protein", "exons", "junctions", "cds_start", "cds_end")}
        # Reference qualification and allele mapping are shared with PVS1.
        mapped = map_variant_to_cds(sample, reference)
        n = reference["protein_length"]
        row.update(cds_length_nt=len(reference["cds"]), translated_cds_length_nt=n * 3, reference_protein_length=n)
        if mapped["status"] != "COMPLETE":
            positions = [genomic_to_mrna(reference["exons"], reference["strand"], variant["position"] + i)
                         for i in range(len(variant["reference_allele"]))]
            coding_overlap = any(p is not None and reference["cds_start"] <= p <= reference["cds_end"] for p in positions)
            terms = set(consequence.replace(",", "&").split("&"))
            if not coding_overlap and not terms.intersection({"stop_gained", "frameshift_variant"}):
                span = [e["genomic_start"] for e in reference["exons"]] + [e["genomic_end"] for e in reference["exons"]]
                outside = variant["position"] > max(span) or variant["position"] + len(variant["reference_allele"]) - 1 < min(span)
                row.update(status="NOT_AFFECTED" if outside else "OTHER_CONSEQUENCE",
                           consequence=consequence or ("outside_transcript" if outside else "non_coding_transcript_region"))
                return row
            row["missing_data"].extend(mapped["missing_data"])
            return row
        edit = mapped["data"]
        start, end = edit["cds_edit_interval"]
        delta = len(edit["alternate_allele"]) - len(edit["reference_allele"])
        row.update(cds_position=start + 1, first_affected_reference_codon=start // 3 + 1,
                   physical_deleted_nt=len(edit["reference_allele"]) if delta else 0,
                   physical_inserted_nt=len(edit["alternate_allele"]) if delta else 0)
        row["physical_cds_deleted_percent"] = 100 * row["physical_deleted_nt"] / (3 * n)
        terms = set(consequence.replace(",", "&").split("&"))
        coding_terms = terms.intersection({"stop_gained", "frameshift_variant"})
        if len(coding_terms) > 1 or ("frameshift_variant" in terms and delta % 3 == 0) or ("stop_gained" in terms and delta != 0):
            row["missing_data"].append("VEP coding consequence conflicts with the transcript-specific allele/frame")
            return row
        if coding_terms:
            kind = next(iter(coding_terms))
        elif delta % 3:
            kind = "frameshift_variant"
        elif delta == 0:
            # Reuse the stop-gain reconstruction to verify an unannotated PTC.
            kind = "stop_gained"
        else:
            row.update(status="OTHER_CONSEQUENCE", consequence=consequence or "inframe_indel")
            return row
        if kind == "frameshift_variant" and start < n * 3:
            row["reference_cds_disrupted_percent"] = 100 * (n - start // 3) / n
        row["conditional"] = any(t.startswith("splice_") for t in terms)
        if row["conditional"]:
            row["warnings"].append("Conditional on reference splicing: an alternative splice product may change this result; no splice simulation")
        sample.variant["consequence"] = kind
        computed = compute_molecular_evidence(sample, reference, transcript + "|impact:" + VERSION)
        row["calculation"] = computed.get("data", {}).get("calculation") if computed.get("data") else None
        if not computed.get("data"):
            if not coding_terms and delta == 0 and any("does not introduce a premature" in message for message in computed["missing_data"]):
                row.update(status="OTHER_CONSEQUENCE", consequence=consequence or "coding_sequence_variant")
            else:
                row["missing_data"].extend(computed["missing_data"])
            return row
        data, audit = computed["data"], computed["data"]["calculation"]
        product = data["molecular_effect"]["products"][0]
        translation = audit["translation"] or {}
        stop_nt = translation.get("first_stop_cds_position")
        if stop_nt is not None:
            row.update(termination_codon=(stop_nt - 1) // 3 + 1,
                       termination_mrna_position=reference["cds_start"] + stop_nt - 1,
                       ptc_mrna_position=product.get("ptc_start"), extends_into_utr=translation.get("extends_into_utr", False))
        if kind == "stop_gained":
            k = row["termination_codon"]
            row.update(reference_amino_acids_lost=n - k + 1, reference_amino_acids_replaced=0,
                       reference_cds_untranslated_percent=100 * (n - k + 1) / n)
        predicted = translation.get("protein")
        if predicted is not None:
            length = len(predicted)
            prefix = 0
            while prefix < min(n, length) and reference["protein"][prefix] == predicted[prefix]:
                prefix += 1
            nonconserved = n - prefix
            lost = max(n - length, 0)
            row.update(first_divergent_aa=prefix + 1 if nonconserved or length != n else None,
                       predicted_protein_length=length, predicted_protein_shortening_aa=lost,
                       reference_amino_acids_lost=lost,
                       reference_amino_acids_replaced=max(nonconserved - lost, 0),
                       protein_impact_percent=100 * nonconserved / n)
        if row["termination_mrna_position"] is not None:
            right = edit["mrna_edit_interval"][1]
            junctions = [j["mrna_position"] + (delta if j["mrna_position"] >= right else 0) for j in reference["junctions"]]
            distance = junctions[-1] - row["termination_mrna_position"] if junctions else None
            row.update(nmd_distance_nt=distance, nmd_predicted=distance is not None and distance > 50)
            row["warnings"].append("NMD is predicted from geometry, not observed RNA degradation; protein sequence is a translation prediction")
        row["consequence"] = consequence or kind
        if consequence and not coding_terms:
            if not row["conditional"]:
                row["missing_data"].append("Reconstructed coding effect conflicts with the recorded VEP consequence")
        hgvs = unquote((annotation or {}).get("hgvsp") or "")
        annotated_stop = re.fullmatch(r"(?:[^:]+:)?p\.\(?[A-Z][a-z]{2}(\d+)(?:Ter|\*)\)?", hgvs)
        annotated_fs = re.fullmatch(r"(?:[^:]+:)?p\.\(?[A-Z][a-z]{2}(\d+)[A-Z][a-z]{2}fs(?:Ter|\*)(\d+)\)?", hgvs)
        expected_stop = int(annotated_stop[1]) if annotated_stop else (
            int(annotated_fs[1]) + int(annotated_fs[2]) - 1 if annotated_fs else None)
        if expected_stop is not None and row["termination_codon"] is not None and expected_stop != row["termination_codon"]:
            row["missing_data"].append("VEP HGVSp termination disagrees with the reconstructed sequence")
        # Numerical positions supplied by VEP must agree. Raw VEP is retained.
        fields = (annotation or {}).get("metadata", {}).get("fields", {})
        vep_position = str(fields.get("CDS_position") or "").split("/")[0]
        if vep_position and re.fullmatch(r"\d+(?:-\d+)?", vep_position):
            vep_start = int(vep_position.split("-")[0])
            if not start + 1 <= vep_start <= max(end, start + 1):
                row["warnings"].append("VEP CDS_position differs from the normalized genomic edit; sequence mapping is authoritative")
        row["missing_data"].extend(computed["missing_data"])
        row["status"] = "AFFECTED_CODING" if not row["missing_data"] else "INSUFFICIENT_DATA"
        if row["status"] == "AFFECTED_CODING":
            row["pvs1_input"] = {"transcript": data["transcript"], "molecular_effect": data["molecular_effect"]}
        return row
    except (ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        row["missing_data"].append(str(exc))
        return row
