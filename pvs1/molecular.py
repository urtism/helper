"""Local sequence computations for HELPER; never PVS1 strength or NMD policy.

Requires HELPER's installed package (or PYTHONPATH=helper_next/src). Reuses
HELPER computations and FASTA reader; no provider, cache or client is instantiated.
All public functions return plain technical COMPLETE/INCOMPLETE dictionaries.
Reference input is the qualified, version-pinned TranscriptReferenceProvider
`data` payload, supplied by the caller. No network access occurs here. Intronic
inclusions additionally read an explicitly supplied, already-open genomic FASTA.
"""

import copy
import hashlib
import re

from helper_next.core.acmg_pvs1 import nonsense as task25_nonsense
from helper_next.core.acmg_transcripts import (
    VERSION as REFERENCE_VERSION, complement, genomic_to_mrna, mrna_to_genomic,
    translate,
)

from pvs1.models import PVS1Input
from helper_variants.indexer import IndexedFasta, sha256_file


VERSION = "helper-pvs1-molecular-1.0"


def _result(data=None, reason=None):
    return {"status": "INCOMPLETE" if reason else "COMPLETE", "data": data,
            "missing_data": [str(reason)] if reason else [], "warnings": []}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _dna(sequence, name, empty=False):
    _require(isinstance(sequence, str) and (bool(sequence) or empty)
             and not set(sequence) - set("ACGT"), name + ": unambiguous uppercase DNA required")
    return sequence


def _citation(source_ref):
    _require(isinstance(source_ref, str) and bool(source_ref.strip()), "source_ref: qualified reference required")


def _span(interval, length):
    _require(isinstance(interval, (tuple, list)) and len(interval) == 2
             and all(type(x) is int for x in interval)
             and 0 <= interval[0] <= interval[1] <= length,
             "edit_interval: expected CDS base-0 half-open endpoints within sequence")
    return interval


def _reference(sample, reference):
    _require(isinstance(sample, PVS1Input), "input: PVS1Input required")
    selected = (sample.transcript or {}).get("accession")
    _require(isinstance(selected, str) and re.fullmatch(r".+\.[0-9]+", selected),
             "transcript.accession: exact transcript version required")
    _require(isinstance(reference, dict), "reference: qualified transcript payload required")
    identity = reference["transcript"]
    _require(selected == identity["accession"] + "." + str(identity["version"]), "reference: transcript/version mismatch")
    variant = sample.variant
    _require(reference["assembly"] == variant["assembly"] and reference["chromosome"] == variant["contig"],
             "reference: assembly/contig mismatch")
    _require(sample.disease_context["gene"] in reference["gene_ids"], "reference: gene identity mismatch")
    _require(reference["strand"] in ("+", "-"), "reference.strand: explicit orientation required")
    _require(reference["chromosome"] in {str(i) for i in range(1, 23)} | {"X", "Y"},
             "reference: primary nuclear chromosome/standard genetic code required")
    _require(reference.get("annotation_release") and reference.get("coordinate_convention") ==
             "1-based inclusive; transcript 5-prime to 3-prime; CDS includes stop",
             "reference: release and qualified coordinate convention required")
    digest = reference.get("artifact_digest", {})
    _require(digest.get("algorithm") == "sha256" and isinstance(digest.get("value"), str)
             and re.fullmatch(r"[0-9a-f]{64}", digest["value"]), "reference: source artifact checksum required")
    cdna, cds = _dna(reference["cdna"], "reference.cdna"), _dna(reference["cds"], "reference.cds")
    start, end = reference["cds_start"], reference["cds_end"]
    _require(type(start) is int and type(end) is int and 1 <= start <= end <= len(cdna)
             and cdna[start - 1:end] == cds, "reference: CDS/cDNA coordinate disagreement")
    _require(len(cds) % 3 == 0 and cds.startswith("ATG") and "*" not in reference["protein"]
             and translate(cds) == reference["protein"] + "*"
             and len(reference["protein"]) == reference["protein_length"], "reference: complete standard-code CDS/protein required")
    cursor, previous = 1, None
    for exon in reference["exons"]:
        left, right = exon["genomic_start"], exon["genomic_end"]
        _require(type(left) is int and type(right) is int and 1 <= left <= right,
                 "reference.exons: invalid genomic endpoints")
        _require(exon["mrna_start"] == cursor and exon["mrna_end"] == cursor + right - left,
                 "reference.exons: inconsistent spliced coordinates")
        if previous:
            _require(left > previous["genomic_end"] if reference["strand"] == "+"
                     else right < previous["genomic_start"], "reference.exons: overlap/order mismatch")
        cursor, previous = exon["mrna_end"] + 1, exon
    _require(previous is not None and cursor - 1 == len(cdna), "reference.exons: incomplete cDNA coverage")
    expected_junctions = [exon["mrna_end"] for exon in reference["exons"][:-1]]
    _require([j["mrna_position"] for j in reference["junctions"]] == expected_junctions,
             "reference.junctions: disagreement with exon structure")
    provided = sample.transcript or {}
    for key, expected in (("strand", reference["strand"]), ("cds_interval", [start, end]),
                          ("exon_genomic_intervals", [[e["genomic_start"], e["genomic_end"]] for e in reference["exons"]]),
                          ("sequence", cdna)):
        value = provided.get(key)
        if value is not None:
            if key == "cds_interval":
                value = list(value)
            if key == "exon_genomic_intervals":
                value = [list(pair) for pair in value]
            _require(value == expected, "transcript." + key + ": input/reference disagreement")
    citation = "{}|{}|{}|release={}|sha256:{}".format(
        REFERENCE_VERSION, selected, reference["assembly"], reference["annotation_release"], digest["value"])
    return reference, citation


def transcript_facts(sample, reference):
    """Reuse qualified Task 25 geometry; derive coding phases, not relevance."""
    try:
        ref, citation = _reference(sample, reference)
        phases = []
        for exon in ref["exons"]:
            first = max(exon["mrna_start"], ref["cds_start"])
            last = min(exon["mrna_end"], ref["cds_end"])
            phases.append((-(first - ref["cds_start"])) % 3 if first <= last else None)
        result = copy.deepcopy(sample.transcript or {})
        result.update(strand=ref["strand"], coordinate_system="transcript_1_based_closed",
                      cds_interval=[ref["cds_start"], ref["cds_end"]],
                      exon_genomic_intervals=[[e["genomic_start"], e["genomic_end"]] for e in ref["exons"]],
                      exon_coordinate_system="genomic_1_based_closed", exon_phases=phases,
                      sequence=ref["cdna"])
        if (sample.transcript or {}).get("exon_phases") is not None:
            given = sample.transcript["exon_phases"]
            _require(len(given) == len(phases) and all(p is None or p == expected for p, expected in zip(given, phases)),
                     "transcript.exon_phases: input/reference disagreement")
        sources = dict(result.get("source_refs") or {})
        for key in ("accession", "strand", "cds_interval", "exon_genomic_intervals", "exon_phases", "sequence"):
            sources[key] = list(dict.fromkeys((sources.get(key) or []) + [citation, VERSION]))
        result["source_refs"] = sources
        return _result(result)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        return _result(reason=exc)


def map_variant_to_cds(sample, reference):
    """Map validated literal alleles to one contiguous CDS edit on either strand.

    The entire REF is validated, then the genomic VCF anchor is trimmed before
    strand orientation, preserving its placement even in minus-strand repeats.
    Junction-crossing or boundary insertions are incomplete, not splice effects.
    """
    try:
        ref, citation = _reference(sample, reference)
        variant = sample.variant
        original_ref = _dna(variant["reference_allele"], "variant.reference_allele")
        original_alt = _dna(variant["alternate_allele"], "variant.alternate_allele")
        _require(original_ref != original_alt, "variant: REF equals ALT")
        positions = [genomic_to_mrna(ref["exons"], ref["strand"], variant["position"] + i)
                     for i in range(len(original_ref))]
        _require(None not in positions and sorted(positions) == list(range(min(positions), max(positions) + 1)),
                 "variant: REF/anchor does not map contiguously to the spliced transcript")
        left, right = min(positions) - 1, max(positions)
        full_tx_ref = original_ref if ref["strand"] == "+" else complement(original_ref)
        _require(ref["cdna"][left:right] == full_tx_ref, "variant.reference_allele: disagrees with qualified transcript")
        genomic_ref, genomic_alt, prefix, suffix = original_ref, original_alt, 0, 0
        while genomic_ref and genomic_alt and genomic_ref[0] == genomic_alt[0]:
            prefix += 1
            genomic_ref, genomic_alt = genomic_ref[1:], genomic_alt[1:]
        while genomic_ref and genomic_alt and genomic_ref[-1] == genomic_alt[-1]:
            suffix += 1
            genomic_ref, genomic_alt = genomic_ref[:-1], genomic_alt[:-1]
        if ref["strand"] == "+":
            left, right = left + prefix, right - suffix
            tx_ref, tx_alt = genomic_ref, genomic_alt
        else:
            left, right = left + suffix, right - prefix
            tx_ref, tx_alt = complement(genomic_ref), complement(genomic_alt)
        _require(ref["cds_start"] - 1 <= left <= right <= ref["cds_end"], "variant: edited span lies outside CDS")
        if left == right:
            _require(ref["cds_start"] - 1 < left < ref["cds_end"], "variant: coding-boundary insertion is not qualified")
            before = mrna_to_genomic(ref["exons"], ref["strand"], left)
            after = mrna_to_genomic(ref["exons"], ref["strand"], left + 1)
            _require(before is not None and after is not None and abs(after - before) == 1,
                     "variant: exon-boundary insertion requires a qualified transcript event")
        if len(tx_ref) != len(tx_alt):
            _require(not any(left <= j["mrna_position"] <= right for j in ref["junctions"]),
                     "variant: indel touches an exon boundary; transcript event is unqualified")
        start = left - (ref["cds_start"] - 1)
        return _result({"cds_edit_interval": [start, start + len(tx_ref)],
                        "cds_coordinate_system": "cds_0_based_half_open",
                        "mrna_edit_interval": [left, right], "mrna_edit_coordinate_system": "transcript_0_based_half_open",
                        "reference_allele": tx_ref, "alternate_allele": tx_alt,
                        "source_ref": citation})
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        return _result(reason=exc)


def reconstruct_cds(reference_cds, edit_interval, reference_allele, alternate_allele, source_ref):
    """Apply one already-qualified edit; empty trimmed alleles are intentional."""
    try:
        _citation(source_ref)
        _dna(reference_cds, "reference_cds")
        _dna(reference_allele, "reference_allele", empty=True)
        _dna(alternate_allele, "alternate_allele", empty=True)
        start, end = _span(edit_interval, len(reference_cds))
        _require(reference_cds[start:end] == reference_allele, "reference_allele: does not match CDS edit span")
        _require(reference_allele != alternate_allele, "edit: no sequence change")
        return _result({"altered_cds": reference_cds[:start] + alternate_allele + reference_cds[end:],
                        "source_ref": source_ref})
    except (ValueError, TypeError) as exc:
        return _result(reason=exc)


def frame_effect(reference_cds, altered_cds, source_ref):
    """Length arithmetic only; does not assert residual function or pathogenicity."""
    try:
        _citation(source_ref)
        _dna(reference_cds, "reference_cds")
        _dna(altered_cds, "altered_cds", empty=True)
        delta = len(altered_cds) - len(reference_cds)
        return _result({"frame_effect": "IN_FRAME" if delta % 3 == 0 else "OUT_OF_FRAME", "length_delta_nt": delta})
    except (ValueError, TypeError) as exc:
        return _result(reason=exc)


def translate_altered_cds(reference_cds, altered_cds, edit_interval, cds_start, source_ref, downstream_sequence=""):
    """Standard-code indel product, stopping at the first complete stop codon.

    This is not the nonsense pathway: compute_molecular_evidence delegates that
    PTC to Task 25. A shifted but retained native stop is not a new PTC.
    Missing downstream sequence, changed initiation or edited native stop yields
    INCOMPLETE rather than an invented ORF. No automatic start re-initiation.
    """
    try:
        _citation(source_ref)
        _dna(reference_cds, "reference_cds")
        _dna(altered_cds, "altered_cds", empty=True)
        _dna(downstream_sequence, "downstream_sequence", empty=True)
        _require(type(cds_start) is int and cds_start >= 1, "cds_start: transcript base-1 coordinate required")
        reference_translation = translate(reference_cds)
        _require(len(reference_cds) % 3 == 0 and reference_cds.startswith("ATG")
                 and reference_translation.endswith("*") and "*" not in reference_translation[:-1],
                 "reference_cds: complete standard-code CDS required")
        start, end = _span(edit_interval, len(reference_cds))
        delta = len(altered_cds) - len(reference_cds)
        inserted_length = end - start + delta
        _require(inserted_length >= 0 and altered_cds[:start] == reference_cds[:start]
                 and altered_cds[start + inserted_length:] == reference_cds[end:], "edit: altered CDS flanks disagree")
        _require(start >= 3 and end <= len(reference_cds) - 3,
                 "edit: initiation/native stop affected; qualified initiation/termination evidence required")
        translated_sequence = altered_cds + downstream_sequence
        protein = translate(translated_sequence[:len(translated_sequence) // 3 * 3])
        stop = protein.find("*")
        if stop < 0:
            return _result({"translated_prefix": protein, "ptc_start": None},
                           "product: no stop in the supplied altered CDS; downstream sequence/termination unresolved")
        native_stop = len(reference_cds) - 3 + delta
        first_stop = stop * 3
        premature = first_stop < native_stop
        return _result({"protein": protein[:stop], "first_stop_cds_position": first_stop + 1,
                        "ptc_start": cds_start + first_stop if premature else None,
                        "termination_start": cds_start + first_stop,
                        "extends_into_utr": first_stop + 3 > len(altered_cds),
                        "stop_kind": "PREMATURE" if premature else "DOWNSTREAM_STOP" if delta % 3 else "REFERENCE_STOP_RETAINED"})
    except (ValueError, TypeError) as exc:
        return _result(reason=exc)


def junction_distances(ptc_start, junction_positions, transcript_ref):
    """Signed offsets from PTC's first base to resulting RNA exon-end positions."""
    try:
        _citation(transcript_ref)
        _require(type(ptc_start) is int and ptc_start >= 1, "ptc_start: determined product coordinate required")
        _require(isinstance(junction_positions, list) and all(type(p) is int and p >= 1 for p in junction_positions)
                 and junction_positions == sorted(set(junction_positions)), "junction_positions: ordered unique RNA base-1 coordinates required")
        pairs = [[p, p - ptc_start] for p in junction_positions]
        downstream = [pair for pair in pairs if pair[1] >= 0]
        return _result({"ptc_junction_distances": pairs,
                        "next_downstream_offset_nt": downstream[0][1] if downstream else None,
                        "last_downstream_offset_nt": downstream[-1][1] if downstream else None})
    except (ValueError, TypeError) as exc:
        return _result(reason=exc)


def protein_region_change(reference_protein, altered_protein, source_ref):
    """Minimal differing strings after shared prefix/nonoverlapping suffix.

    This is sequence comparison, not functional conservation/domain analysis.
    Only a pure deletion is reported as lost_protein_region.
    """
    try:
        _citation(source_ref)
        alphabet = set("ACDEFGHIKLMNPQRSTVWY")
        _require(isinstance(reference_protein, str) and reference_protein and not set(reference_protein) - alphabet
                 and isinstance(altered_protein, str) and not set(altered_protein) - alphabet,
                 "protein: complete unambiguous standard-code amino-acid strings required")
        prefix = 0
        while prefix < min(len(reference_protein), len(altered_protein)) and reference_protein[prefix] == altered_protein[prefix]:
            prefix += 1
        suffix = 0
        while suffix < min(len(reference_protein), len(altered_protein)) - prefix and reference_protein[-1 - suffix] == altered_protein[-1 - suffix]:
            suffix += 1
        reference_end, altered_end = len(reference_protein) - suffix, len(altered_protein) - suffix
        region = [prefix + 1, reference_end] if reference_end > prefix else None
        new_region = [prefix + 1, altered_end] if altered_end > prefix else None
        return _result({"altered_protein_region": region,
                        "lost_protein_region": region if new_region is None else None,
                        "product_difference_region": new_region,
                        "reference_changed_residues": reference_end - prefix,
                        "product_changed_residues": altered_end - prefix,
                        "reference_changed_fraction": (reference_end - prefix) / len(reference_protein)})
    except (ValueError, TypeError) as exc:
        return _result(reason=exc)


def _verified_intronic_sequence(ref, flanking_exons, interval, supplied, genome):
    """Compare optional caller sequence and flanking exons to an identified FASTA."""
    _require(isinstance(genome, dict), "genomic_reference: verifiable genomic FASTA required; provenance alone is insufficient")
    _require(genome.get("assembly") == ref["assembly"] and genome.get("chromosome") == ref["chromosome"],
             "genomic_reference: assembly/chromosome mismatch")
    for key in ("source_ref", "source_version"):
        _require(isinstance(genome.get(key), str) and bool(genome[key].strip()), "genomic_reference." + key + ": required")
    reader = genome.get("reader")
    _require(isinstance(reader, IndexedFasta), "genomic_reference.reader: existing IndexedFasta required")
    _require(ref["chromosome"] in reader.contigs, "genomic_reference: exact chromosome identity required")
    checksum = sha256_file(reader.path)
    _require(genome.get("artifact_digest") == {"algorithm": "sha256", "value": checksum},
             "genomic_reference: FASTA checksum missing/mismatch")
    for exon in flanking_exons:
        observed = _dna(reader.sequence(ref["chromosome"], exon["genomic_start"],
                                         exon["genomic_end"] - exon["genomic_start"] + 1), "genomic exon")
        observed = observed if ref["strand"] == "+" else complement(observed)
        _require(observed == ref["cdna"][exon["mrna_start"] - 1:exon["mrna_end"]],
                 "genomic_reference: flanking exon sequence disagrees with selected transcript")
    start, end = interval
    sequence = _dna(reader.sequence(ref["chromosome"], start, end - start + 1), "intronic reference")
    _require(len(sequence) == end - start + 1, "intronic reference: incomplete interval coverage")
    sequence = sequence if ref["strand"] == "+" else complement(sequence)
    sources = ["{}|version={}|sha256:{}".format(genome["source_ref"], genome["source_version"], checksum)]
    if supplied is not None:
        _require(isinstance(supplied, dict), "intronic_sequence: qualified sequence object required")
        _require(supplied.get("assembly") == ref["assembly"] and supplied.get("chromosome") == ref["chromosome"]
                 and supplied.get("strand") == ref["strand"]
                 and supplied.get("coordinate_system") == "genomic_1_based_closed",
                 "intronic_sequence: assembly/chromosome/strand/coordinate convention mismatch or missing")
        span = supplied.get("genomic_interval")
        _require(isinstance(span, (list, tuple)) and len(span) == 2 and all(type(p) is int for p in span)
                 and list(span) == interval, "intronic_sequence: genomic interval disagrees with explicit splice boundary")
        for key in ("source_ref", "source_version"):
            _require(isinstance(supplied.get(key), str) and bool(supplied[key].strip()), "intronic_sequence." + key + ": required")
        _require(_dna(supplied.get("sequence"), "intronic_sequence.sequence") == sequence,
                 "intronic_sequence: sequence disagrees with verified genomic reference")
        sources.append("{}|version={}".format(supplied["source_ref"], supplied["source_version"]))
    return {"assembly": ref["assembly"], "chromosome": ref["chromosome"], "genomic_interval": interval,
            "strand": ref["strand"], "coordinate_system": "genomic_1_based_closed", "sequence": sequence,
            "source_refs": sources}, sources


def reconstruct_splice_product(sample, reference, event=None, product_ref=None, *,
                               intronic_sequence=None, genomic_reference=None):
    """Reconstruct an explicit exon skip or exonic/intronic cryptic boundary.

    event is a MolecularProductData record with basis and involved_exons (base 1
    in the selected transcript). EXON_SKIPPING removes consecutive whole exons.
    CRYPTIC_SITE needs one exon and retained_exon_interval on reference RNA:
    move only its 3' end for donor or 5' start for acceptor, retaining the rest.
    Alternatively one explicit genomic_junctions pair extends that exon into
    its adjacent intron, using a verified caller-open IndexedFasta. Optional
    intronic_sequence must match that FASTA; source metadata alone cannot verify it.
    OBSERVED requires an original RNA citation on the event description.
    Other supplied consequences remain in calculation.input_event, not assertions
    adopted by this calculation. product_ref names the resulting RNA coordinate
    axis and must differ from the reference transcript accession.
    """
    input_event = copy.deepcopy(event)
    selected = (getattr(sample, "transcript", None) or {}).get("accession")
    try:
        _require(isinstance(event, dict), "event: explicit splicing event required")
        PVS1Input(variant=sample.variant, disease_context=sample.disease_context,
                  transcript=sample.transcript, molecular_effect={"products": [event]})
        _require(event.get("basis") != "UNKNOWN", "event: UNKNOWN basis; RNA event not determined")
        event_type = event.get("event_type")
        _require(event_type in ("EXON_SKIPPING", "CRYPTIC_SITE"), "event: explicit EXON_SKIPPING or CRYPTIC_SITE required")
        intronic = (event_type == "CRYPTIC_SITE" and event.get("retained_exon_interval") is None
                    and event.get("genomic_junctions") is not None)
        _require(intronic or (intronic_sequence is None and genomic_reference is None),
                 "event: intronic inputs require an explicit intronic CRYPTIC_SITE junction")
        involved = event.get("involved_exons")
        _require(isinstance(involved, list) and bool(involved), "event.involved_exons: explicit exon indices required")
        _require(all(b == a + 1 for a, b in zip(involved, involved[1:])),
                 "event.involved_exons: one ordered consecutive block without duplicates required")
        event_sources = event.get("source_refs") or {}
        evidence_keys = ("basis", "event_type", "involved_exons", "retained_exon_interval") + (("genomic_junctions",) if intronic else ())
        rna_sources = list(dict.fromkeys(source for key in evidence_keys
                                        for source in event_sources.get(key, [])))
        _require(event["basis"] != "OBSERVED" or bool(rna_sources),
                 "event: OBSERVED requires original RNA evidence in event description source_refs")
        if intronic:
            _require(bool(rna_sources) and bool(event_sources.get("method")),
                     "event: intronic splice source and method required in source_refs")
        _citation(product_ref)
        _require(product_ref != (sample.transcript or {}).get("accession"),
                 "product_ref: resulting RNA must have a distinct coordinate reference")
        ref, citation = _reference(sample, reference)
        facts = transcript_facts(sample, ref)
        _require(facts["status"] == "COMPLETE", "; ".join(facts["missing_data"]))
        exons = ref["exons"]
        _require(1 <= involved[0] <= involved[-1] <= len(exons),
                 "event.involved_exons: exon not belonging to selected transcript")
        inserted, sequence_sources, sequence_audit = "", [], None
        if event_type == "EXON_SKIPPING":
            _require(event.get("retained_exon_interval") is None,
                     "event: retained_exon_interval is only supported for CRYPTIC_SITE")
            skipped = involved
            _require(len(skipped) < len(exons), "event: skipping all exons leaves no representable RNA product")
            left, right = exons[skipped[0] - 1]["mrna_start"] - 1, exons[skipped[-1] - 1]["mrna_end"]
            retained = [(i, exon) for i, exon in enumerate(exons, 1) if i not in skipped]
        elif intronic:
            pairs = event["genomic_junctions"]
            _require(len(involved) == 1 and len(pairs) == 1, "event: one intronic boundary on exactly one exon required")
            index, (new_donor, new_acceptor) = involved[0], pairs[0]
            exon, direction = exons[index - 1], 1 if ref["strand"] == "+" else -1
            native_end = mrna_to_genomic(exons, ref["strand"], exon["mrna_end"])
            native_start = mrna_to_genomic(exons, ref["strand"], exon["mrna_start"])
            donor = (index < len(exons) and direction * (new_donor - native_end) > 0 and
                     new_acceptor == mrna_to_genomic(exons, ref["strand"], exons[index]["mrna_start"]))
            acceptor = (index > 1 and direction * (native_start - new_acceptor) > 0 and
                        new_donor == mrna_to_genomic(exons, ref["strand"], exons[index - 2]["mrna_end"]))
            _require(donor != acceptor, "event: exactly one intronic donor/acceptor boundary must extend the involved exon")
            upstream, downstream = (exon, exons[index]) if donor else (exons[index - 2], exon)
            gap = abs(mrna_to_genomic(exons, ref["strand"], downstream["mrna_start"]) -
                      mrna_to_genomic(exons, ref["strand"], upstream["mrna_end"])) - 1
            endpoints = [native_end + direction, new_donor] if donor else [new_acceptor, native_start - direction]
            span = sorted(endpoints)
            _require(0 < span[1] - span[0] + 1 < gap, "event: partial adjacent intron required; full retention/outside intron unsupported")
            sequence_audit, sequence_sources = _verified_intronic_sequence(
                ref, [upstream, downstream], span, intronic_sequence, genomic_reference)
            inserted = sequence_audit["sequence"]
            left = right = upstream["mrna_end"]
            retained = [(i, dict(e)) for i, e in enumerate(exons, 1)]
            extended = retained[index - 1][1]
            extended["included_length"] = len(inserted)
            boundary_key = "genomic_end" if donor == (ref["strand"] == "+") else "genomic_start"
            extended[boundary_key] = new_donor if donor else new_acceptor
        else:
            _require(len(involved) == 1, "event: CRYPTIC_SITE requires exactly one exon")
            interval = event.get("retained_exon_interval")
            _require(interval is not None, "event.retained_exon_interval: explicit reference RNA boundaries required")
            start, end = interval
            index = involved[0]
            exon = exons[index - 1]
            _require(exon["mrna_start"] <= start <= end <= exon["mrna_end"],
                     "event.retained_exon_interval: boundaries must lie within the involved exon")
            donor = start == exon["mrna_start"] and end < exon["mrna_end"]
            acceptor = start > exon["mrna_start"] and end == exon["mrna_end"]
            _require(donor or acceptor, "event: exactly one exonic boundary must move; unchanged/both ends unsupported")
            _require(index < len(exons) if donor else index > 1,
                     "event: cryptic donor requires a downstream exon; acceptor requires an upstream exon")
            left, right = (end, exon["mrna_end"]) if donor else (exon["mrna_start"] - 1, start - 1)
            retained = [(i, dict(e)) for i, e in enumerate(exons, 1)]
            endpoints = [mrna_to_genomic(exons, ref["strand"], p) for p in (start, end)]
            retained[index - 1][1].update(mrna_start=start, mrna_end=end,
                                         genomic_start=min(endpoints), genomic_end=max(endpoints))
        altered_rna = ref["cdna"][:left] + inserted + ref["cdna"][right:]
        junctions, genomic_junctions, cursor = [], [], 0
        for (up_index, upstream), (down_index, downstream) in zip(retained, retained[1:]):
            cursor += upstream["mrna_end"] - upstream["mrna_start"] + 1 + upstream.get("included_length", 0)
            pair = ([upstream["genomic_end"], downstream["genomic_start"]] if ref["strand"] == "+"
                    else [upstream["genomic_start"], downstream["genomic_end"]])
            genomic_junctions.append(pair)
            junctions.append({"upstream_exon": up_index, "downstream_exon": down_index,
                              "mrna_position": cursor, "genomic_junction": pair,
                              "new": down_index != up_index + 1 or pair != [
                                  mrna_to_genomic(exons, ref["strand"], exons[up_index - 1]["mrna_end"]),
                                  mrna_to_genomic(exons, ref["strand"], exons[down_index - 1]["mrna_start"])]})
        coding_start, coding_end = ref["cds_start"] - 1, ref["cds_end"]
        edit_start = max(0, min(len(ref["cds"]), left - coding_start))
        edit_end = max(0, min(len(ref["cds"]), right - coding_start))
        edit = [edit_start, edit_end]
        coding_inserted = inserted if coding_start < left < coding_end else ""
        coding_changed = edit_start < edit_end or bool(coding_inserted)
        if coding_changed:
            reconstructed = reconstruct_cds(ref["cds"], edit, ref["cds"][edit_start:edit_end], coding_inserted, citation)
            _require(reconstructed["status"] == "COMPLETE", "; ".join(reconstructed["missing_data"]))
            altered_cds = reconstructed["data"]["altered_cds"]
        else:
            altered_cds = ref["cds"]  # Noncoding skip: qualified reference translation is unchanged.
        frame = frame_effect(ref["cds"], altered_cds, citation)
        _require(frame["status"] == "COMPLETE", "; ".join(frame["missing_data"]))
        start_retained = not (left < coding_start + 3 and right > coding_start)
        stop_retained = not (left < coding_end and right > coding_end - 3)
        removed_before_cds = max(0, min(right, coding_start) - left)
        product_cds_start = (ref["cds_start"] - removed_before_cds + (len(inserted) if left <= coding_start else 0)
                             if start_retained else None)
        if not coding_changed:
            translated = _result({"protein": ref["protein"], "ptc_start": None,
                                  "first_stop_cds_position": len(ref["cds"]) - 2,
                                  "stop_kind": "REFERENCE_STOP_RETAINED"})
        else:
            # The shared translator rejects START/STOP loss before using cds_start.
            translated = translate_altered_cds(ref["cds"], altered_cds, edit,
                                                product_cds_start or 1, citation)
        metadata = ("basis", "event_type", "involved_exons", "retained_exon_interval", "functional_evidence", "evidence_quality")
        product = {key: copy.deepcopy(event[key]) for key in metadata if key in event}
        sources = {key: copy.deepcopy(value) for key, value in event_sources.items() if intronic or key in metadata}
        product.update(transcript_ref=product_ref, coordinate_system="transcript_1_based_closed",
                       sequence=altered_rna, genomic_junctions=genomic_junctions,
                       frame_effect=frame["data"]["frame_effect"],
                       ptc_start=(translated["data"] or {}).get("ptc_start"), source_refs=sources)
        calculated_sources = list(dict.fromkeys([citation, VERSION] + rna_sources + sequence_sources +
                                              ([source for refs in event_sources.values() for source in refs] if intronic else [])))
        for key in ("transcript_ref", "sequence", "genomic_junctions", "frame_effect", "ptc_start"):
            sources[key] = list(calculated_sources)
        audit = {"software_version": VERSION, "source_ref": citation, "input_event": input_event,
                 "reference_transcript": selected,
                 "mrna_edit_interval": [left, right], "mrna_edit_coordinate_system": "transcript_0_based_half_open",
                 "retained_exons": [i for i, _ in retained], "junctions": junctions,
                 "altered_cds": altered_cds, "product_cds_start": product_cds_start,
                 "original_start_retained": start_retained, "original_stop_retained": stop_retained,
                 "frame": frame["data"], "translation": translated["data"]}
        if event_type == "CRYPTIC_SITE":
            audit.update(cryptic_site_type="DONOR" if donor else "ACCEPTOR",
                         cryptic_site_position=(new_donor if donor else new_acceptor) if intronic else (end if donor else start))
        if intronic:
            audit.update(intronic_sequence=sequence_audit, input_intronic_sequence=copy.deepcopy(intronic_sequence),
                         cryptic_site_coordinate_system="genomic_1_based")
        if product["ptc_start"] is not None:
            geometry = junction_distances(product["ptc_start"], [j["mrna_position"] for j in junctions], product_ref)
            _require(geometry["status"] == "COMPLETE", "; ".join(geometry["missing_data"]))
            audit["ptc_geometry"] = geometry["data"]
            product["ptc_junction_distances"] = geometry["data"]["ptc_junction_distances"]
            sources["ptc_junction_distances"] = list(calculated_sources)
        if translated["status"] == "COMPLETE":
            change = protein_region_change(ref["protein"], translated["data"]["protein"], citation)
            _require(change["status"] == "COMPLETE", "; ".join(change["missing_data"]))
            audit["protein_change"] = change["data"]
            product.update(protein_accession=ref.get("protein_accession") or
                           "sha256:" + hashlib.sha256(ref["protein"].encode()).hexdigest(),
                           protein_coordinate_system="protein_1_based_closed",
                           altered_protein_region=change["data"]["altered_protein_region"],
                           lost_protein_region=change["data"]["lost_protein_region"])
            for key in ("protein_accession", "altered_protein_region", "lost_protein_region"):
                sources[key] = list(calculated_sources)
        effect = {"products": [product], "source_refs": {"products": list(calculated_sources)}}
        if coding_changed:
            effect.update(cds_edit_interval=edit, cds_coordinate_system="cds_0_based_half_open")
            effect["source_refs"]["cds_edit_interval"] = list(calculated_sources)
        data = {"transcript": facts["data"], "molecular_effect": effect, "calculation": audit}
        PVS1Input(variant=sample.variant, disease_context=sample.disease_context,
                  transcript=data["transcript"], molecular_effect=effect)
        result = _result(data, "; ".join(translated["missing_data"]) if translated["status"] != "COMPLETE" else None)
        result["warnings"].append("Sequence consequence is computationally reconstructed; it does not experimentally validate the RNA event.")
        if not start_retained or not stop_retained:
            result["warnings"].append("Original START/STOP affected; frame is length arithmetic only; initiation/termination unresolved.")
        return result
    except (ValueError, KeyError, TypeError, AttributeError, OSError, UnicodeError) as exc:
        return _result({"calculation": {"input_event": input_event, "reference_transcript": selected}}, reason=exc)


def compute_molecular_evidence(sample, reference, product_ref):
    """Compose common sequence facts into PVS1Input-compatible technical blocks.

    Does not mutate sample or merge/replace existing RNA evidence. The returned
    product is PREDICTED on the reference splicing pattern, never RNA proof.
    """
    try:
        _citation(product_ref)
        facts = transcript_facts(sample, reference)
        if facts["status"] != "COMPLETE":
            return facts
        mapped = map_variant_to_cds(sample, reference)
        if mapped["status"] != "COMPLETE":
            return mapped
        edit = mapped["data"]
        reconstructed = reconstruct_cds(reference["cds"], edit["cds_edit_interval"],
                                        edit["reference_allele"], edit["alternate_allele"], edit["source_ref"])
        if reconstructed["status"] != "COMPLETE":
            return reconstructed
        altered_cds = reconstructed["data"]["altered_cds"]
        frame = frame_effect(reference["cds"], altered_cds, edit["source_ref"])["data"]
        left, right = edit["mrna_edit_interval"]
        altered_rna = reference["cdna"][:left] + edit["alternate_allele"] + reference["cdna"][right:]
        variant = sample.variant
        terms = variant["consequence"].replace(",", "&").split("&")
        legacy = None
        if "stop_gained" in terms:
            legacy = task25_nonsense(
                {"assembly": variant["assembly"], "chromosome": variant["contig"], "position": variant["position"],
                 "reference": variant["reference_allele"], "alternate": variant["alternate_allele"]},
                {"transcript": sample.transcript["accession"]}, reference)
            offset = legacy["ptc_mrna_position"] - reference["cds_start"]
            translated = _result({"ptc_start": legacy["ptc_mrna_position"], "protein": translate(altered_cds[:offset]),
                                  "first_stop_cds_position": offset + 1, "stop_kind": "PREMATURE"})
        else:
            translated = translate_altered_cds(reference["cds"], altered_cds, edit["cds_edit_interval"],
                                                reference["cds_start"], edit["source_ref"],
                                                downstream_sequence=reference["cdna"][reference["cds_end"]:])
        product = {"basis": "PREDICTED", "transcript_ref": product_ref,
                   "coordinate_system": "transcript_1_based_closed", "sequence": altered_rna,
                   "frame_effect": frame["frame_effect"], "ptc_start": (translated["data"] or {}).get("ptc_start")}
        product_sources = {key: [edit["source_ref"], VERSION] for key in product if key != "basis"}
        if legacy:
            product_sources["ptc_start"].append(legacy["formula_version"])
        product["source_refs"] = product_sources
        effect = {"cds_edit_interval": edit["cds_edit_interval"], "cds_coordinate_system": "cds_0_based_half_open",
                  "products": [product], "source_refs": {"cds_edit_interval": [edit["source_ref"], VERSION]}}
        audit = {"software_version": VERSION, "mapping": edit, "altered_cds": altered_cds,
                 "frame": frame, "translation": translated["data"], "task25_nonsense": legacy}
        if product["ptc_start"] is not None:
            boundaries = [j["mrna_position"] + (frame["length_delta_nt"] if j["mrna_position"] >= right else 0)
                          for j in reference["junctions"]]
            geometry = junction_distances(product["ptc_start"], boundaries, product_ref)["data"]
            product["ptc_junction_distances"] = geometry["ptc_junction_distances"]
            product_sources["ptc_junction_distances"] = [edit["source_ref"], VERSION]
            audit["ptc_geometry"] = geometry
        if translated["status"] == "COMPLETE":
            change = protein_region_change(reference["protein"], translated["data"]["protein"], edit["source_ref"])
            _require(change["status"] == "COMPLETE", "product: protein comparison incomplete")
            audit["protein_change"] = change["data"]
            protein_ref = reference.get("protein_accession") or "sha256:" + hashlib.sha256(reference["protein"].encode()).hexdigest()
            product.update(protein_accession=protein_ref, protein_coordinate_system="protein_1_based_closed",
                           altered_protein_region=change["data"]["altered_protein_region"],
                           lost_protein_region=change["data"]["lost_protein_region"])
            for key in ("protein_accession", "altered_protein_region", "lost_protein_region"):
                product_sources[key] = [edit["source_ref"], VERSION]
        data = {"transcript": facts["data"], "molecular_effect": effect, "calculation": audit}
        # Validate compatibility with the sole input model, without changing the caller.
        PVS1Input(variant=sample.variant, disease_context=sample.disease_context,
                  transcript=data["transcript"], molecular_effect=effect)
        return _result(data, "; ".join(translated["missing_data"]) if translated["status"] != "COMPLETE" else None)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        return _result(reason=exc)
