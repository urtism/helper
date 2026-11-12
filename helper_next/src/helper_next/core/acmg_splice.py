"""Conditional canonical-splice scenarios; never evidence of an observed RNA.

Reuse the declared local FASTA and the existing splice-product reconstructor.
Read only the allele/site window and the involved exon, without hashing or
scanning the genome. Alternative products remain explicitly unassessed.
"""
import copy

from helper_next.core import acmg_reference, reference_validation
from helper_next.core.acmg_digest import digest
from helper_next.core.acmg_transcripts import complement, genomic_to_mrna, mrna_to_genomic
from helper_next.core.acmg_splice_prediction import THRESHOLD, spliceai_prediction
from helper_variants import indexer
from pvs1.models import PVS1Input
from pvs1.molecular import reconstruct_splice_product


VERSION = "helper-canonical-splice-scenario-1.1"
ALTERNATIVES = ["CRYPTIC_SITE", "INTRON_RETENTION", "RESIDUAL_REFERENCE_SPLICING"]


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _edit(variant):
    position = variant["position"]
    ref, alt = variant["reference_allele"], variant["alternate_allele"]
    _require(ref and alt and not set(ref + alt) - set("ACGT") and ref != alt, "Unambiguous distinct REF/ALT required")
    while ref and alt and ref[0] == alt[0]:
        position, ref, alt = position + 1, ref[1:], alt[1:]
    while ref and alt and ref[-1] == alt[-1]:
        ref, alt = ref[:-1], alt[:-1]
    return position, ref, alt


def _site(variant, reference):
    """Use the edited bases, excluding the unchanged VCF anchor."""
    position, ref, alt = _edit(variant)
    end = position + len(ref) - 1
    exons, direction = reference["exons"], 1 if reference["strand"] == "+" else -1
    # This first automatic scenario handles intronic edits only. Mixed coding
    # and splice edits need the allele applied to the resulting RNA as well.
    for exon in exons:
        overlap = (position <= exon["genomic_end"] and end >= exon["genomic_start"]) if ref else (
            exon["genomic_start"] < position <= exon["genomic_end"])
        _require(not overlap, "The edited allele also changes exonic sequence; an explicit combined RNA event is required")
    sites = []
    for index, exon in enumerate(exons, 1):
        for kind, rna, offsets in (("DONOR", exon["mrna_end"], [1, 2]),
                                   ("ACCEPTOR", exon["mrna_start"], [-2, -1])):
            if (kind == "DONOR" and index == len(exons)) or (kind == "ACCEPTOR" and index == 1):
                continue
            anchor = mrna_to_genomic(exons, reference["strand"], rna)
            bases = [anchor + direction * offset for offset in offsets]
            affected = [offset for offset, base in zip(offsets, bases) if position <= base <= end] if ref else (
                offsets if position == max(bases) else [])
            if affected:
                sites.append(dict(type=kind, exon=index, genomic_anchor=anchor, affected_offsets=affected))
    _require(len(sites) == 1, "Exactly one canonical donor/acceptor site must be affected; no unique site is determined")
    return sites[0], (position, ref, alt)


def _verify_site(variant, reference, site, edit, record):
    selected, config = acmg_reference.reference_record(variant["assembly"], record)
    fasta = indexer.open_reference(selected, variant["assembly"])
    _require(fasta is not None, "A configured local FASTA with .fai is required to verify intronic REF and the splice motif")
    try:
        state = reference_validation.reference_state(fasta)
        if config.get("sha256"):
            _require(acmg_reference.reference_checksum(fasta, variant["assembly"], selected, config) == config["sha256"],
                     "Configured reference FASTA checksum mismatch")
        chromosome = variant["contig"]
        # Ambiguous aliases must not select a different sequence accidentally.
        names = {reference["chromosome"], "chr" + reference["chromosome"]}.intersection(fasta.contigs)
        _require(len(names) == 1, "Reference FASTA chromosome is absent or ambiguous")
        chromosome = next(iter(names))
        original = fasta.sequence(chromosome, variant["position"], len(variant["reference_allele"]))
        _require(original == variant["reference_allele"], "Intronic variant REF disagrees with the declared reference FASTA")
        exon = reference["exons"][site["exon"] - 1]
        observed = fasta.sequence(chromosome, exon["genomic_start"], exon["genomic_end"] - exon["genomic_start"] + 1)
        if reference["strand"] == "-":
            observed = complement(observed)
        _require(observed == reference["cdna"][exon["mrna_start"] - 1:exon["mrna_end"]],
                 "Reference FASTA exon disagrees with the selected transcript")
        anchor = site["genomic_anchor"]
        start = min(anchor, variant["position"]) - 2
        stop = max(anchor, variant["position"] + len(original) - 1) + 2
        window = fasta.sequence(chromosome, start, stop - start + 1)
        _require(not set(window) - set("ACGT"), "Unambiguous reference splice window required")
        offset = variant["position"] - start
        changed = window[:offset] + variant["alternate_allele"] + window[offset + len(original):]
        delta = len(variant["alternate_allele"]) - len(original)
        shifted_anchor = anchor - start + (delta if variant["position"] + len(original) - 1 < anchor else 0)
        downstream = (site["type"] == "DONOR") == (reference["strand"] == "+")

        def motif(sequence, boundary):
            value = sequence[boundary + 1:boundary + 3] if downstream else sequence[boundary - 2:boundary]
            return value if reference["strand"] == "+" else complement(value)

        native, altered = motif(window, anchor - start), motif(changed, shifted_anchor)
        _require(len(native) == len(altered) == 2, "Complete native and altered splice motifs required")
        _require(reference_validation.reference_state(fasta) == state, "Reference FASTA or .fai changed during splice analysis")
        return dict(native_motif=native, altered_motif=altered,
                    genomic_edit=dict(position=edit[0], reference=edit[1], alternate=edit[2]),
                    reference_window=dict(start=start, end=stop, sequence=window, altered_sequence=changed,
                                          digest=digest(window)),
                    reference_source=dict(assembly=variant["assembly"], version=reference_validation.reference_version(
                        variant["assembly"], selected, config), files=state,
                        validation="ALLELE_AND_EXON_AND_SPLICE_WINDOW_VERIFIED"))
    finally:
        fasta.close()


def _cryptic_event(variant, reference, site, prediction, source, record):
    """One predicted loss/gain pair must identify a boundary of this transcript."""
    if not prediction or prediction["status"] == "NOT_APPLICABLE":
        return None, None
    _require(prediction["status"] == "AVAILABLE", "; ".join(prediction["issues"]))
    row, = prediction["records"]
    kind = "D" if site["type"] == "DONOR" else "A"
    other = "A" if kind == "D" else "D"
    exploratory = site.get("prediction_only", False)
    if row["DS_" + kind + "G"] < THRESHOLD and not exploratory:
        _require(row["DS_" + other + "G"] < THRESHOLD,
                 "SpliceAI predicts a different boundary type; combined RNA event is unresolved")
        return None, None
    _require(row["DS_" + kind + "L"] >= THRESHOLD or (exploratory and row["DS_" + kind + "L"] > 0),
             "SpliceAI cryptic gain lacks a qualified matching splice-site loss")
    _require(row["position"] + row["DP_" + kind + "L"] == site["genomic_anchor"],
             "SpliceAI lost site does not match the selected transcript boundary")
    _require(row["DS_" + other + "G"] < THRESHOLD and row["DS_" + other + "L"] < THRESHOLD,
             "SpliceAI predicts multiple boundary changes; no unique simple RNA event")
    gained = row["position"] + row["DP_" + kind + "G"]
    _require(gained > 0 and gained != site["genomic_anchor"], "SpliceAI cryptic boundary must differ from the native site")
    exons, strand = reference["exons"], reference["strand"]
    exon = exons[site["exon"] - 1]
    event = dict(basis="PREDICTED", event_type="CRYPTIC_SITE", involved_exons=[site["exon"]])
    rna = genomic_to_mrna(exons, strand, gained)
    if rna is not None:
        _require(exon["mrna_start"] <= rna <= exon["mrna_end"],
                 "SpliceAI gained site belongs to another exon; combined event is unresolved")
        interval = [exon["mrna_start"], rna] if kind == "D" else [rna, exon["mrna_end"]]
        _require(interval != [exon["mrna_start"], exon["mrna_end"]], "SpliceAI gained site leaves the reference exon unchanged")
        event["retained_exon_interval"] = interval
    else:
        if kind == "D":
            event["genomic_junctions"] = [[gained, mrna_to_genomic(exons, strand, exons[site["exon"]]["mrna_start"])]]
        else:
            event["genomic_junctions"] = [[mrna_to_genomic(exons, strand, exons[site["exon"] - 2]["mrna_end"]), gained]]
        direction = 1 if strand == "+" else -1
        _require(direction * (gained - site["genomic_anchor"]) * (1 if kind == "D" else -1) > 0,
                 "SpliceAI gained site is outside the adjacent donor/acceptor intron")
        # Bound reads to the affected intron, before opening/reading its sequence.
        pair = event["genomic_junctions"][0]
        _require(direction * (pair[1] - pair[0]) > 1, "SpliceAI gained site crosses the adjacent exon")
    selected, config = acmg_reference.reference_record(variant["assembly"], record)
    fasta = indexer.open_reference(selected, variant["assembly"])
    _require(fasta is not None, "A configured local FASTA is required for the cryptic splice site")
    genome = None
    try:
        state = reference_validation.reference_state(fasta)
        _require(state == site["reference_source"]["files"], "Reference FASTA/FAI changed after native-site verification")
        names = {reference["chromosome"], "chr" + reference["chromosome"]}.intersection(fasta.contigs)
        _require(len(names) == 1, "Cryptic FASTA chromosome is absent or ambiguous")
        chromosome = next(iter(names))
        start = min(variant["position"], gained) - 2
        end = max(variant["position"] + len(variant["reference_allele"]) - 1, gained) + 2
        window = fasta.sequence(chromosome, start, end - start + 1)
        offset = variant["position"] - start
        _require(window[offset:offset + len(variant["reference_allele"])] == variant["reference_allele"],
                 "Cryptic window variant REF mismatch")
        edit_position, edit_ref, edit_alt = _edit(variant)
        if len(edit_ref) != len(edit_alt):
            _require(not (edit_position <= gained < edit_position + len(edit_ref))
                     and not (not edit_ref and gained == edit_position - 1),
                     "SpliceAI gained coordinate lies in a deleted/inserted allele span; boundary is ambiguous")
        changed = window[:offset] + variant["alternate_allele"] + window[offset + len(variant["reference_allele"]):]
        boundary = gained - start + (len(variant["alternate_allele"]) - len(variant["reference_allele"])
                                     if variant["position"] + len(variant["reference_allele"]) - 1 < gained else 0)
        downstream = (kind == "D") == (strand == "+")
        motif = changed[boundary + 1:boundary + 3] if downstream else changed[boundary - 2:boundary]
        motif = motif if strand == "+" else complement(motif)
        _require(motif == ("GT" if kind == "D" else "AG"), "SpliceAI gained site lacks a compatible GT/AG motif in the altered sequence")
        _require(reference_validation.reference_state(fasta) == state, "Reference FASTA/FAI changed during cryptic-site verification")
        prediction.update(gained_site=dict(type=site["type"], genomic_position=gained, motif=motif,
            coordinate_system="genomic_1_based", window_digest=digest(window), altered_window_digest=digest(changed)))
        event["source_refs"] = {key: [source] for key in event}
        event["source_refs"].update(method=["SpliceAI loss/gain; allele and motif verified; hypothetical RNA"],
                                    method_version=[VERSION])
        if "genomic_junctions" in event:
            genome = dict(assembly=variant["assembly"], chromosome=reference["chromosome"], fasta_chromosome=chromosome,
                reader=fasta, source_ref=source, source_version=VERSION, verified_file_state=state)
        return event, genome
    finally:
        if genome is None:
            fasta.close()


def _predicted_exonic_site(variant, reference, prediction):
    """An exonic allele may be removed by one predicted cryptic truncation.

    Positions define an exploratory RNA hypothesis even for low delta scores;
    they do not qualify noncanonical variants for predictive PVS1 (P34).
    Retained coding edits, multiple boundaries and complete exon loss are excluded.
    """
    _require(prediction and prediction["status"] == "AVAILABLE", "No unique SpliceAI prediction for an exonic cryptic event")
    predicted, = prediction["records"]
    position, ref, _ = _edit(variant)
    _require(ref, "Exonic insertion requires an explicit combined RNA event")
    exons, strand = reference["exons"], reference["strand"]
    direction = 1 if strand == "+" else -1
    candidates = []
    for index, exon in enumerate(exons, 1):
        if not (exon["genomic_start"] <= position and position + len(ref) - 1 <= exon["genomic_end"]):
            continue
        first = genomic_to_mrna(exons, strand, position)
        last = genomic_to_mrna(exons, strand, position + len(ref) - 1)
        for kind, code, native_rna in (("DONOR", "D", exon["mrna_end"]), ("ACCEPTOR", "A", exon["mrna_start"])):
            if (kind == "DONOR" and index == len(exons)) or (kind == "ACCEPTOR" and index == 1):
                continue
            if predicted["DS_" + code + "G"] <= 0 or predicted["DS_" + code + "L"] <= 0:
                continue
            anchor = mrna_to_genomic(exons, strand, native_rna)
            gained = predicted["position"] + predicted["DP_" + code + "G"]
            rna = genomic_to_mrna(exons, strand, gained)
            if predicted["position"] + predicted["DP_" + code + "L"] != anchor or rna is None:
                continue
            if not exon["mrna_start"] <= rna <= exon["mrna_end"]:
                continue
            excised = (rna < min(first, last) and rna < exon["mrna_end"]) if kind == "DONOR" else (
                rna > max(first, last) and rna > exon["mrna_start"])
            if excised:
                candidates.append(dict(type=kind, exon=index, genomic_anchor=anchor, prediction_only=True,
                                       affected_offsets=[direction * (position - anchor)]))
    _require(len(candidates) == 1, "No unique cryptic truncation fully removes the edited exonic allele")
    site = candidates[0]
    code = "D" if site["type"] == "DONOR" else "A"
    prediction["selection_status"] = ("EXPLORATORY_LOW_DELTA" if min(predicted["DS_" + code + "G"],
        predicted["DS_" + code + "L"]) < THRESHOLD else "PREDICTED_EXONIC_EVENT")
    prediction["automatic_pvs1_eligible"] = False
    return site


def splice_impact(row, variant, gene, reference, *, record=None, annotation=None, original=None, prediction=None):
    """Return a hypothetical skip/cryptic product, or the exact unresolved cause."""
    row = copy.deepcopy(row)
    if row.get("pvs1_input"):
        # A reference-splicing product cannot stand in for a failed alternative
        # RNA reconstruction, even if the coding allele alone was interpretable.
        row.update(pvs1_input=None, calculation=None, status="INSUFFICIENT_DATA", conditional=True)
        for key in ("predicted_protein_length", "predicted_protein_shortening_aa", "termination_codon",
                    "termination_mrna_position", "ptc_mrna_position", "nmd_predicted", "nmd_distance_nt",
                    "protein_impact_percent", "reference_amino_acids_lost", "reference_amino_acids_replaced", "first_divergent_aa"):
            row[key] = None
        row["product_resolution"] = dict(status="UNRESOLVED", method=None, reason_codes=[])
    row["splice_analysis"] = dict(algorithm_version=VERSION, status="UNRESOLVED", site=None,
                                  scenarios=[], alternatives_not_assessed=list(ALTERNATIVES))
    analysis = row["splice_analysis"]
    genome = None
    try:
        prediction = prediction if prediction is not None else spliceai_prediction(annotation, variant, original)
        if prediction:
            analysis["prediction"] = prediction
        try:
            site, edit = _site(variant, reference)
        except ValueError:
            if not prediction:
                raise
            site = _predicted_exonic_site(variant, reference, prediction)
            edit = _edit(variant)
        analysis["site"] = site
        terms = set((row["consequence"] or "").replace(",", "&").split("&"))
        _require(not ("splice_donor_variant" in terms and site["type"] != "DONOR")
                 and not ("splice_acceptor_variant" in terms and site["type"] != "ACCEPTOR"),
                 "Annotated splice consequence conflicts with the transcript-specific splice site")
        verification = _verify_site(variant, reference, site, edit, record)
        site.update(verification)
        expected = "GT" if site["type"] == "DONOR" else "AG"
        _require(site["native_motif"] == expected, "Non-GT/AG native splice motif requires a specific assessment")
        _require(site.get("prediction_only") or site["altered_motif"] not in ({"GT", "GC"} if site["type"] == "DONOR" else {"AG"}),
                 "A potentially functional splice dinucleotide is retained; exon skipping cannot be assumed")
        source = VERSION + "|" + row["transcript"] + "|sha256:" + digest({"site": site, "prediction": prediction})["value"]
        event, genome = _cryptic_event(variant, reference, site, prediction, source, record)
        cryptic = event is not None
        if not cryptic:
            event = dict(basis="PREDICTED", event_type="EXON_SKIPPING", involved_exons=[site["exon"]],
                     source_refs={key: [source] for key in ("basis", "event_type", "involved_exons")})
        else:
            analysis["alternatives_not_assessed"] = ["EXON_SKIPPING", *ALTERNATIVES[1:]]
        scenario = dict(event=event, assumption="SpliceAI loss/gain at a transcript-matched cryptic site; not observed RNA" if cryptic
                        else "Exon skipping after canonical splice-site disruption; not observed RNA",
                        status="UNRESOLVED")
        analysis["scenarios"].append(scenario)
        consequence = row["consequence"]
        if site.get("prediction_only"):
            consequence = "&".join(dict.fromkeys([*(consequence or "").split("&"), "splice_region_variant"]))
            row["provenance"]["original_consequence"] = row["consequence"]
            row["consequence"] = consequence
        sample = PVS1Input(variant=dict(variant, consequence=consequence),
                           disease_context=dict(gene=gene, molecular_mechanism="UNKNOWN"),
                           transcript=dict(accession=row["transcript"]))
        computed = reconstruct_splice_product(sample, reference, event, row["transcript"] + "|splice:" + VERSION,
                                               genomic_reference=genome, apply_retained_variant=cryptic)
        scenario.update(status=computed["status"], missing_data=computed["missing_data"])
        _require(computed["status"] == "COMPLETE", "; ".join(computed["missing_data"]))
        data = computed["data"]
        audit, effect = data["calculation"], data["molecular_effect"]
        product, translated = effect["products"][0], audit["translation"]
        effect.update(splice_site_type=site["type"], splice_site_genomic_position=site["genomic_anchor"],
                      splice_site_offset=min(site["affected_offsets"], key=abs), native_splice_motif=site["native_motif"])
        effect["source_refs"].update({key: [source] for key in
                                     ("splice_site_type", "splice_site_genomic_position", "splice_site_offset", "native_splice_motif")})
        coding_edit = effect.get("cds_edit_interval", [0, 0])
        n, predicted = reference["protein_length"], translated["protein"]
        change = audit["protein_change"]
        first = change["altered_protein_region"][0] if change["altered_protein_region"] else None
        pairs = product.get("ptc_junction_distances") or []
        distance = pairs[-1][1] if pairs else None
        stop_cds = translated.get("first_stop_cds_position")
        row.update(status="SPLICE_SCENARIO", conditional=True, missing_data=[], calculation=audit,
                   cds_position=coding_edit[0] + 1 if coding_edit[1] > coding_edit[0] else None,
                   first_affected_reference_codon=coding_edit[0] // 3 + 1 if coding_edit[1] > coding_edit[0] else None,
                   physical_deleted_nt=len(edit[1]) if len(edit[1]) != len(edit[2]) else 0,
                   physical_inserted_nt=len(edit[2]) if len(edit[1]) != len(edit[2]) else 0, physical_cds_deleted_percent=0,
                   predicted_protein_length=len(predicted), predicted_protein_shortening_aa=max(0, n - len(predicted)),
                   first_divergent_aa=first, reference_amino_acids_lost=max(0, n - len(predicted)),
                   reference_amino_acids_replaced=max(0, change["reference_changed_residues"] - max(0, n - len(predicted))),
                   protein_impact_percent=100 * change["reference_changed_fraction"],
                   termination_codon=(stop_cds - 1) // 3 + 1 if stop_cds else None,
                   termination_mrna_position=translated.get("termination_start"), ptc_mrna_position=product.get("ptc_start"),
                   nmd_distance_nt=distance, nmd_predicted=distance is not None and distance > 50,
                   product_resolution=dict(status="CONDITIONAL", method="SPLICEAI_CRYPTIC_SCENARIO" if cryptic else "CANONICAL_SPLICE_SCENARIO",
                                           reason_codes=["ALTERNATIVE_SPLICE_PRODUCTS_UNASSESSED"]),
                   pvs1_input=dict(transcript=data["transcript"], molecular_effect=effect))
        if product["frame_effect"] == "OUT_OF_FRAME" and coding_edit[1] > coding_edit[0]:
            row["reference_cds_disrupted_percent"] = 100 * (n - coding_edit[0] // 3) / n
        scenario.update(frame_effect=product["frame_effect"], rna_deleted_nt=audit["mrna_edit_interval"][1] - audit["mrna_edit_interval"][0],
                        rna_inserted_nt=len(audit.get("inserted_rna_sequence", "")),
                        coding_deleted_nt=coding_edit[1] - coding_edit[0],
                        coding_inserted_nt=len(audit["altered_cds"]) - len(reference["cds"]) + coding_edit[1] - coding_edit[0],
                        genomic_junctions=product["genomic_junctions"], ptc_start=product.get("ptc_start"),
                        nmd_predicted=row["nmd_predicted"], nmd_distance_nt=distance)
        analysis["status"] = "CONDITIONAL"
        row["provenance"]["splice_scenario"] = source
        if prediction and prediction.get("selection_status") == "EXPLORATORY_LOW_DELTA":
            row["warnings"].append("Scenario esplorativo da posizioni SpliceAI con delta score sotto soglia: non è una predizione forte né dimostra il prodotto prevalente; PVS1 predittivo non canonico resta non assegnabile.")
        row["warnings"].extend(["Scenario splice condizionale: " + ("sito criptico nell'esone " if cryptic else "salto dell'esone ") + str(site["exon"])
                                + "; il prodotto RNA non è osservato.",
                                ("Exon skipping, ritenzione intronica e splicing residuo non valutati; " if cryptic else
                                 "Siti criptici, ritenzione intronica e splicing residuo non valutati; ") + "l'esito PVS1 è riferito allo scenario predetto.",
                                "NMD predetto dalla geometria del prodotto ipotizzato; non osservato sperimentalmente."])
    except (ValueError, KeyError, TypeError, OSError) as exc:
        row["missing_data"].append("Splice reconstruction unavailable: " + str(exc))
        row["product_resolution"]["reason_codes"].append("SPLICE_SCENARIO_UNRESOLVED")
    finally:
        if genome is not None:
            genome["reader"].close()
    return row
