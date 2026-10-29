"""Conservative STANDARD PVS1 MVP. No engine, network, sequence fetch or inference.

decision_trace remains the model's list[str]: each string is a JSON requirement
record, allowing clients to inspect status/value/threshold/source independently.
Biological assertions are used only with field-specific citations; missing exon
relevance, LoF tolerance and rescue assertions produce non-blocking warnings.
"""
import json
import re
from dataclasses import asdict

from pvs1.models import PVS1Input, PVS1Result
from helper_next.core.acmg_transcripts import genomic_to_mrna


RULESET_ID = "PVS1_GENERAL"
RULESET_VERSION = "1.1.0"
_REQUIREMENTS = (
    ("policy", "Policy STANDARD", "STEP1"),
    ("input", "Validità strutturale dell'input PVS1", "STEP2"),
    ("context", "Associazione gene–malattia ed ereditarietà", "P01"),
    ("mechanism", "Meccanismo LoF documentato nel contesto", "P01–P05"),
    ("consequence", "Conseguenza supportata dal MVP", "P06"),
    ("transcript", "Trascritto selezionato con versione", "P06"),
    ("transcript_relevance", "Rilevanza biologica del trascritto (non bloccante)", "P06"),
    ("exon_relevance", "Rilevanza documentata dell'esone interessato", "P07"),
    ("tolerance", "Esone non tollerante a LoF frequenti", "P07/P12–P13"),
    ("rescue", "Assenza documentata di rescue funzionale", "P10/P37–P38"),
    ("splice_basis", "Base dell'evidenza splice", "P15/P34–P35"),
    ("splice_scenarios", "Scenari splice alternativi e motivi atipici", "P15/P36"),
    ("rna_quality", "Adeguatezza e completezza dell'evidenza RNA", "P40–P45"),
    ("product", "Prodotto molecolare e PTC determinati", "P08/P16–P18"),
    ("nmd", "Predizione NMD secondo il modello generale", "P08–P10"),
    ("region", "Regione proteica critica o quota realmente persa", "P11–P14"),
)


def _refs(block, *fields):
    sources = block.get("source_refs") or {}
    return list(dict.fromkeys(ref for field in fields for ref in sources.get(field, [])))


def calculate_pvs1(input, policy="STANDARD") -> PVS1Result:
    """Evaluate only documented, unambiguous branches of STEP0's general model.

    RNA assay weighting, alternative splice scenarios, inferred mechanisms,
    multiple products, start-loss and CNV remain explicit unevaluated checks.
    Neither a missing fact nor a negative NMD prediction excludes PVS1 by itself.
    """
    trace, missing, review, warnings = {}, [], [], []

    def record(key, status, value=None, source=None, reason="", threshold=None):
        trace[key] = dict(status=status, value=value, source=source or [], reason=reason, threshold=threshold)

    def unknown(key, reason, value=None, source=None):
        record(key, "UNKNOWN", value, source, reason)
        missing.append(reason)

    def finish(status, reason, strength=None):
        rows = []
        for key, description, rule in _REQUIREMENTS:
            row = dict(id=key, description=description, rule=rule if rule.startswith("STEP") else "STEP0:" + rule)
            row.update(trace.get(key, dict(status="NOT_EVALUATED", value=None, threshold=None, source=[],
                                           reason="Controllo non eseguito nel percorso raggiunto.")))
            rows.append(json.dumps(row, ensure_ascii=False))
        return PVS1Result(status=status, reason=reason, calculated_strength=strength, applied_strength=strength,
                          warnings=warnings, missing_data=list(dict.fromkeys(missing)), decision_trace=rows,
                          requires_review=status == "REQUIRES_REVIEW", ruleset_id=RULESET_ID, ruleset_version=RULESET_VERSION)

    if policy != "STANDARD":
        record("policy", "FAIL", policy, reason="È implementata soltanto la policy STANDARD.")
        return finish("NOT_EVALUABLE", "Policy non supportata.")
    record("policy", "PASS", policy, ["STEP1: modello generale, nessuna VCEP"])
    try:
        if not isinstance(input, PVS1Input):
            raise ValueError("È richiesto PVS1Input.")
        sample = PVS1Input(**asdict(input))  # Revalidate even if caller mutated its dictionaries.
    except (ValueError, TypeError) as exc:
        missing.append("Input non valido: " + str(exc))
        record("input", "FAIL", reason=missing[-1], source=["pvs1.models.PVS1Input: validazione strutturale"])
        return finish("NOT_EVALUABLE", missing[0])
    record("input", "PASS", source=["pvs1.models.PVS1Input: validazione strutturale"],
           reason="La validità strutturale non certifica la verità biologica delle asserzioni.")
    variant, context = sample.variant, sample.disease_context
    tx, effect = sample.transcript or {}, sample.molecular_effect or {}
    context_ready = bool(context.get("gene") != "UNKNOWN" and context.get("disease") and context.get("inheritance") and
                         context.get("scope") == "DISEASE_SPECIFIC" and _refs(context, "scope", "disease", "inheritance"))
    if context_ready:
        record("context", "PASS", {k: context.get(k) for k in ("gene", "disease", "inheritance", "scope")},
               _refs(context, "scope", "disease", "inheritance"))
    else:
        unknown("context", "Mancano associazione gene–malattia, ereditarietà o ambito disease-specific documentati.",
                {k: context.get(k) for k in ("gene", "disease", "inheritance", "scope")}, _refs(context, "scope", "disease", "inheritance"))
    mechanism, confidence = context.get("molecular_mechanism"), context.get("confidence")
    mechanism_ready = bool(context_ready and confidence == "DEFINITIVE" and _refs(context, "molecular_mechanism")
                           and _refs(context, "confidence"))
    if mechanism_ready and mechanism in ("GoF", "DN", "OTHER"):
        record("mechanism", "FAIL", mechanism, _refs(context, "molecular_mechanism", "confidence"),
               "Il meccanismo documentato in questo contesto non è LoF.")
        return finish("INACTIVE", "PVS1 non applicabile al meccanismo documentato.")
    if mechanism_ready and mechanism == "LoF":
        record("mechanism", "PASS", {"mechanism": mechanism, "confidence": confidence},
               _refs(context, "molecular_mechanism", "confidence"), "Curazione esplicita; nessuna inferenza da validità del gene o VEP.")
    elif mechanism == "LoF" and confidence in ("INFERRED", "DISPUTED"):
        record("mechanism", "NOT_EVALUATED", {"mechanism": mechanism, "confidence": confidence},
               _refs(context, "molecular_mechanism", "confidence"), "Riduzioni P02–P05 non implementate per questo contesto.")
        review.append("Meccanismo inferito/disputato: serve revisione, senza strength STANDARD automatica.")
    else:
        unknown("mechanism", "Meccanismo LoF disease-specific definitivo e relative fonti non disponibili.",
                {"mechanism": mechanism, "confidence": confidence}, _refs(context, "molecular_mechanism", "confidence"))

    terms = set(variant["consequence"].replace(",", "&").split("&"))
    unsupported = terms.intersection({"start_lost", "transcript_ablation", "transcript_amplification", "exon_loss_variant", "copy_number_change"})
    coding = terms.intersection({"stop_gained", "frameshift_variant"})
    conditional_splice = bool(coding) and any(term.startswith("splice_") for term in terms)
    splice = not coding and any(term.startswith("splice_") for term in terms)
    kind = "splice" if splice else "frameshift" if "frameshift_variant" in terms else "stop-gain" if "stop_gained" in terms else None
    if unsupported or kind is None or len(coding) > 1:
        record("consequence", "NOT_EVALUATED", variant["consequence"], _refs(variant, "consequence"),
               "Ramo non implementato o conseguenze concorrenti da rivedere.")
        return finish("NOT_EVALUABLE", "Start-loss, CNV e conseguenze non univoche non sono implementati nel MVP.")
    record("consequence", "PASS", kind, _refs(variant, "consequence"))
    if conditional_splice:
        reason = "Prodotto codificante condizionale sullo splicing reference: conseguenza splice concomitante da valutare prima di applicare PVS1."
        review.append(reason)
        warnings.append(reason)
    if re.fullmatch(r".+\.[0-9]+", tx.get("accession") or "") and _refs(tx, "accession"):
        record("transcript", "PASS", tx["accession"], _refs(tx, "accession"))
    else:
        unknown("transcript", "Mancano trascritto selezionato con versione esatta o fonte dell'identità.", tx.get("accession"), _refs(tx, "accession"))
    exclusions = []
    record("transcript_relevance", "NOT_EVALUATED", tx.get("biologically_relevant"), _refs(tx, "biologically_relevant"),
           "Si valuta il trascritto fornito da HELPER. La rilevanza biologica non è un requisito bloccante; nessun altro trascritto viene cercato.")
    warnings.append("Risultato riferito esclusivamente al trascritto fornito; la sua rilevanza biologica non è valutata dal Calculator.")
    for key, field, expected in (("exon_relevance", "affected_exon_relevant", True),
                                 ("tolerance", "affected_exon_lof_tolerant", False),
                                 ("rescue", "rescue_present", False)):
        value, source = tx.get(field), _refs(tx, field)
        if value is None or not source:
            reason = ("Manca il dato documentato transcript." + field
                      + ". Dato opzionale: PVS1 prosegue senza conferma di questo controllo biologico.")
            record(key, "UNKNOWN", value, source, reason)
            warnings.append(reason)
        else:
            passed = value is expected
            record(key, "PASS" if passed else "FAIL", value, source,
                   "Asserzione biologica fornita; non dedotta dalle annotazioni.")
            if not passed:
                exclusions.append(field)
    if exclusions and context_ready and mechanism_ready and mechanism == "LoF":
        return finish("INACTIVE", "Esclusione documentata nel contesto: " + ", ".join(exclusions) + ".")

    products = effect.get("products") or []
    if len(products) != 1:
        if not products:
            unknown("product", "Manca un evento splice completo esplicito e il relativo prodotto molecolare; conseguenza VEP e score/offset SpliceAI non determinano da soli l'evento."
                    if splice else "Manca un prodotto molecolare determinato.")
        else:
            record("product", "NOT_EVALUATED", len(products), reason="Aggregazione di prodotti multipli non implementata.")
            review.append("Prodotti multipli: non si seleziona automaticamente il più dannoso.")
        return finish("NOT_EVALUABLE" if missing else "REQUIRES_REVIEW", "; ".join(missing + review))
    product = products[0]
    basis = product.get("basis")
    frame_ready = True
    if splice:
        event_sources = _refs(product, "basis", "event_type", "involved_exons", "genomic_junctions", "retained_exon_interval")
        if basis == "UNKNOWN" or not event_sources or not product.get("event_type") or product.get("event_type") == "UNKNOWN":
            unknown("splice_basis", "Evento splice e base dell'evidenza non determinati con fonte originale.", basis, event_sources)
        else:
            record("splice_basis", "PASS", basis, event_sources, "L'evento conserva la propria base; il calcolo non conferma un esperimento.")
        if basis == "PREDICTED":
            offset, site = effect.get("splice_site_offset"), effect.get("splice_site_type")
            canonical = site in ("DONOR", "ACCEPTOR") and offset in (-2, -1, 1, 2)
            if not canonical:
                unknown("splice_scenarios", "Predizione splice non canonica o canonicità non documentata: PVS1 predittivo non assegnabile (P34).")
            else:
                record("splice_scenarios", "NOT_EVALUATED", {"offset": offset, "motif": effect.get("native_splice_motif")},
                       _refs(effect, "splice_site_offset", "native_splice_motif"), "Valutazione degli scenari alternativi e motivi atipici non implementata.")
                review.append("Splice predetta canonica: revisione degli scenari alternativi richiesta (P15/P36).")
            record("rna_quality", "NOT_APPLICABLE", reason="Il prodotto è predetto, non un'evidenza RNA osservata.")
        elif basis == "OBSERVED":
            record("splice_scenarios", "NOT_APPLICABLE", reason="Si esamina il prodotto RNA descritto, senza inventare altri eventi.")
            if not product.get("evidence_quality"):
                unknown("rna_quality", "Qualità, attribuzione allelica e completezza del saggio RNA non documentate.")
            else:
                record("rna_quality", "NOT_EVALUATED", product["evidence_quality"], event_sources,
                       "Ponderazione del saggio, profili misti e impatto completo/quasi completo non implementati.")
                review.append("Evidenza RNA conservata; adeguatezza e quantità richiedono revisione (P40–P45).")
        if product.get("frame_effect") not in ("IN_FRAME", "OUT_OF_FRAME") or not _refs(product, "frame_effect"):
            frame_ready = False
            unknown("product", "Frame del prodotto splice non determinato con fonte.")
    else:
        for key in ("splice_basis", "splice_scenarios", "rna_quality"):
            record(key, "NOT_APPLICABLE", reason="Non è un ramo splice.")
        if kind == "frameshift" and (product.get("frame_effect") != "OUT_OF_FRAME" or not _refs(product, "frame_effect")):
            frame_ready = False
            unknown("product", "Frameshift senza frame OUT_OF_FRAME documentato.")

    ptc, pairs = product.get("ptc_start"), product.get("ptc_junction_distances")
    in_frame_splice = (splice and frame_ready and product.get("frame_effect") == "IN_FRAME" and ptc is None
                      and product.get("protein_accession") and product.get("protein_coordinate_system") == "protein_1_based_closed"
                      and _refs(product, "protein_accession"))
    product_ready = (frame_ready and basis != "UNKNOWN" and product.get("transcript_ref") and product["transcript_ref"] != tx.get("accession") and
                     _refs(product, "ptc_start") and ptc is not None)
    if product_ready and not splice and tx.get("cds_interval"):
        cds_start, cds_end = tx["cds_interval"]
        delta = len(variant["alternate_allele"]) - len(variant["reference_allele"])
        product_ready = ptc >= cds_start and (ptc - cds_start) % 3 == 0 and ptc < cds_end - 2 + delta
        if kind == "frameshift" and effect.get("cds_edit_interval"):
            product_ready = product_ready and delta % 3 != 0 and ptc + 2 >= cds_start + effect["cds_edit_interval"][0]
        if kind == "stop-gain" and tx.get("exon_genomic_intervals") and tx.get("strand"):
            exons, cursor = [], 1
            for start, end in tx["exon_genomic_intervals"]:
                exons.append(dict(genomic_start=start, genomic_end=end, mrna_start=cursor, mrna_end=cursor + end - start))
                cursor += end - start + 1
            edited = [genomic_to_mrna(exons, tx["strand"], variant["position"] + offset)
                      for offset in range(len(variant["reference_allele"]))]
            product_ready = product_ready and delta == 0 and None not in edited and any(ptc <= p <= ptc + 2 for p in edited)
    sequence = product.get("sequence")
    if product_ready and sequence is not None:
        product_ready = ptc + 2 <= len(sequence) and sequence[ptc - 1:ptc + 2] in ("TAA", "TAG", "TGA")
    nmd = None
    if product_ready:
        record("product", "PASS", {"ptc_start": ptc, "transcript_ref": product["transcript_ref"]}, _refs(product, "ptc_start"))
    if in_frame_splice:
        record("product", "PASS", {"frame": "IN_FRAME", "ptc": None}, _refs(product, "frame_effect"), "Prodotto in-frame; esaminare la regione alterata.")
        record("nmd", "NOT_APPLICABLE", reason="Nessun PTC documentato nel prodotto in-frame.")
    elif not product_ready:
        unknown("product", "PTC sul prodotto risultante non determinato, non documentato o incoerente con la sequenza.")
    elif pairs is None or not _refs(product, "ptc_junction_distances"):
        record("product", "PASS", {"ptc_start": ptc, "transcript_ref": product["transcript_ref"]}, _refs(product, "ptc_start"))
        unknown("nmd", "Mancano tutte le giunzioni del prodotto e le distanze documentate dal PTC.")
    else:
        positions = [p for p, _ in pairs]
        expected_count = len(product["genomic_junctions"]) if product.get("genomic_junctions") is not None else (
            len(tx["exon_genomic_intervals"]) - 1 if tx.get("exon_genomic_intervals") else None)
        coherent = (positions == sorted(set(positions)) and all(distance == p - ptc for p, distance in pairs)
                    and expected_count is not None and len(pairs) == expected_count
                    and (sequence is None or all(p < len(sequence) for p in positions)))
        if not splice and tx.get("exon_genomic_intervals"):
            cursor, expected_positions = 0, []
            for left, right in tx["exon_genomic_intervals"][:-1]:
                cursor += right - left + 1
                expected_positions.append(cursor)
            if kind == "stop-gain":
                coherent = coherent and positions == expected_positions
            elif effect.get("cds_edit_interval") and tx.get("cds_interval"):
                edit_end = tx["cds_interval"][0] - 1 + effect["cds_edit_interval"][1]
                coherent = coherent and positions == [p + (delta if p >= edit_end else 0) for p in expected_positions]
        if not coherent:
            unknown("nmd", "Geometria PTC/giunzioni incoerente o completezza delle giunzioni non verificabile.")
        else:
            record("product", "PASS", {"ptc_start": ptc, "transcript_ref": product["transcript_ref"]}, _refs(product, "ptc_start"))
            last = pairs[-1][1] if pairs and pairs[-1][1] >= 0 else None
            nmd = last is not None and last > 50
            record("nmd", "PASS" if nmd else "FAIL", {"predicted_nmd": nmd, "last_downstream_offset_nt": last},
                   _refs(product, "ptc_junction_distances"), "Predizione generale; un esito negativo indirizza al ramo regione proteica, non esclude PVS1.",
                   {"operator": ">", "value": 50, "unit": "nt", "origin": "prima base PTC", "source": "A18 Fig.1 nota b; STEP0 P08"})
            warnings.append("NMD è una predizione geometrica del modello generale, non un'osservazione sperimentale; eccezioni specifiche richiedono revisione.")
    strength = None
    if nmd is True:
        strength = "VERY_STRONG"
        record("region", "NOT_APPLICABLE", reason="Ramo NMD previsto, subordinato ai prerequisiti biologici.")
    elif nmd is False or in_frame_splice:
        critical = product.get("lost_region_critical")
        if critical is True and _refs(product, "lost_region_critical") and product.get("functional_evidence"):
            strength = "STRONG"
            record("region", "PASS", {"critical": True}, _refs(product, "lost_region_critical"), "Regione documentata critica; nessuna inferenza da dominio annotato.")
            if splice:
                review.append("Regione critica splice: valutazione P39 e contesto RNA non implementati integralmente.")
        else:
            region, cds = product.get("lost_protein_region"), tx.get("cds_interval")
            length = (cds[1] - cds[0] + 1) // 3 - 1 if cds and (cds[1] - cds[0] + 1) % 3 == 0 else 0
            if region and length > 0 and region[1] <= length and _refs(product, "lost_protein_region") and _refs(tx, "cds_interval"):
                lost = region[1] - region[0] + 1
                if lost * 10 == length:
                    record("region", "NOT_EVALUATED", {"lost": lost, "reference_length": length, "fraction": 0.1},
                           _refs(product, "lost_protein_region"), "Il caso esattamente 10% non è risolto dalle disuguaglianze originali.")
                    review.append("Perdita esattamente 10%: revisione richiesta (P14).")
                else:
                    strength = "STRONG" if lost * 10 > length else "MODERATE"
                    record("region", "PASS", {"lost": lost, "reference_length": length, "fraction": lost / length},
                           _refs(product, "lost_protein_region") + _refs(tx, "cds_interval"), "Quota della proteina reference realmente persa, non percentuale di funzione.",
                           {"value": 0.1, "operators": [">", "<"], "source": "A18 Fig.1; STEP0 P12–P14"})
            else:
                unknown("region", "Mancano criticità documentata o regione realmente persa e lunghezza proteica qualificata.")
    if missing:
        return finish("NOT_EVALUABLE", "; ".join(dict.fromkeys(missing + review)))
    if review or strength is None:
        return finish("REQUIRES_REVIEW", "; ".join(review) or "Ramo scientifico non completamente valutato dal MVP.")
    return finish("ACTIVE", "Prerequisiti obbligatori e ramo generale soddisfatti; strength assegnata al solo criterio PVS1. Consultare i warning per i controlli biologici non documentati.", strength)
