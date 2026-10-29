"""Minimal bridge from an existing HELPER annotation to the new PVS1 package.

No Task 22, Workbench, engine client or genomic FASTA access. Gene-wide
molecular analysis uses release-qualified public references via SourceManager.
"""
import hashlib
import json
import re
import sqlite3
from dataclasses import asdict
from urllib.parse import unquote

from fastapi import APIRouter, Body, HTTPException

from helper_next.api.variants import _entry, _entry_database
from helper_next.core import acmg_context
from helper_next.core.acmg_mechanism_normalizer import allelic, molecular_mechanism
from helper_next.core.acmg_transcripts import TranscriptReferenceProvider
from helper_next.core.acmg_molecular_impact import analyze_transcripts
from helper_variants import query
from pvs1.calculator import calculate_pvs1
from pvs1.models import PVS1Input
from pvs1.molecular import compute_molecular_evidence, junction_distances, map_variant_to_cds, transcript_facts


router = APIRouter(prefix="/api/acmg-calculator", tags=["new ACMG Calculator"])


def _import_g2p_context(context, choice):
    """Reuse explicit local assertions only in the selected gene/disease/MOI scope."""
    selected, origin = choice["context"], choice.get("origin", {})
    mechanisms, sources = set(), []
    for record in origin.get("g2p_records", []):
        if (record.get("gene_id") != selected["gene"]["identifier"]
                or context.get("disease") not in {record.get("disease_id"), record.get("disease_mim")}
                or allelic(record.get("allelic_requirement")) != context.get("inheritance")
                or not record.get("id") or not record.get("url")):
            continue
        # Source association confidence is retained separately from the fact
        # that the molecular mechanism is explicitly stated by the curator.
        if not record.get("accepted"):
            continue
        mechanism = molecular_mechanism(record.get("original_mechanism") or record.get("mechanism") or "")
        if mechanism not in {"LOSS_OF_FUNCTION", "GAIN_OF_FUNCTION", "DOMINANT_NEGATIVE"}:
            continue
        mechanisms.add(mechanism)
        sources.append("Gene2Phenotype " + json.dumps(
            {"record": record, "local_cache_version": origin.get("source_version")}, ensure_ascii=False, sort_keys=True))
    if sources:
        mapping = {
            "LOSS_OF_FUNCTION": "LoF", "GAIN_OF_FUNCTION": "GoF", "DOMINANT_NEGATIVE": "DN",
        }
        context["molecular_mechanism"] = mapping[next(iter(mechanisms))] if len(mechanisms) == 1 else "UNKNOWN"
        context["confidence"] = "DEFINITIVE" if len(mechanisms) == 1 else "DISPUTED"
        context["source_refs"].update({key: sources for key in ("molecular_mechanism", "confidence")})
        for key in ("disease", "inheritance", "scope"):
            context["source_refs"][key].extend(sources)


def _annotated_product(sample, reference, annotation, source):
    """Use only an explicit numerical VEP stop, with the existing REF/CDS mapping."""
    terms = set(sample.variant["consequence"].split("&"))
    hgvs = unquote(annotation.get("hgvsp") or "")
    stop = re.fullmatch(r"(?:[^:]+:)?p\.\(?[A-Z][a-z]{2}(\d+)(?:Ter|\*)\)?", hgvs)
    fs = re.fullmatch(r"(?:[^:]+:)?p\.\(?[A-Z][a-z]{2}(\d+)[A-Z][a-z]{2}fs(?:Ter|\*)(\d+)\)?", hgvs)
    amino_position = None
    if "stop_gained" in terms:
        position = (annotation.get("metadata", {}).get("fields", {}).get("Protein_position") or "")
        amino_position = int(stop[1]) if stop else int(position) if re.fullmatch(r"[1-9][0-9]*", str(position)) else None
    elif "frameshift_variant" in terms and fs and int(fs[2]) > 0:
        amino_position = int(fs[1]) + int(fs[2]) - 1
    if amino_position is None:
        return None
    mapped = map_variant_to_cds(sample, reference)
    if mapped["status"] != "COMPLETE":
        return None
    edit = mapped["data"]
    delta = len(edit["alternate_allele"]) - len(edit["reference_allele"])
    if ("frameshift_variant" in terms and delta % 3 == 0) or ("stop_gained" in terms and delta != 0):
        return None
    ptc = reference["cds_start"] + 3 * (amino_position - 1)
    if not reference["cds_start"] <= ptc < reference["cds_end"] - 2 + delta:
        return None
    identifier = sample.transcript["accession"] + "|VEP-product:" + hashlib.sha256(repr(sample.variant).encode()).hexdigest()[:16]
    positions = [j["mrna_position"] + (delta if j["mrna_position"] >= edit["mrna_edit_interval"][1] else 0)
                 for j in reference["junctions"]]
    product = {"basis": "PREDICTED", "transcript_ref": identifier, "coordinate_system": "transcript_1_based_closed",
               "frame_effect": "OUT_OF_FRAME" if delta % 3 else "IN_FRAME", "ptc_start": ptc,
               "ptc_junction_distances": junction_distances(ptc, positions, identifier)["data"]["ptc_junction_distances"]}
    if "stop_gained" in terms:
        product.update(protein_accession=reference.get("protein_accession") or
                       "sha256:" + hashlib.sha256(reference["protein"].encode()).hexdigest(),
                       protein_coordinate_system="protein_1_based_closed",
                       lost_protein_region=[amino_position, reference["protein_length"]])
    product["source_refs"] = {key: [source, edit["source_ref"], "VEP stop annotation; no independent PTC translation"]
                              for key in product if key != "basis"}
    return {"products": [product], "cds_edit_interval": edit["cds_edit_interval"],
            "cds_coordinate_system": "cds_0_based_half_open"}


def prepare_pvs1_input(detail, annotation, choice=None):
    """Adapt raw indexed fields; preserve unknown biology and exact selection."""
    fields = annotation.get("metadata", {}).get("fields", {})
    source = "HELPER indexed annotation {}:{}; {}".format(
        annotation.get("release_id", ""), annotation.get("id", ""), annotation.get("release_key", annotation.get("annotator", "ANN/CSQ")))
    assembly = {"hg19": "GRCh37", "grch37": "GRCh37", "hg38": "GRCh38", "grch38": "GRCh38"}.get(
        str(detail["reference_build"]).lower(), detail["reference_build"])
    gene = fields.get("Gene") or annotation.get("gene") or "UNKNOWN"
    variant = dict(assembly=assembly, contig=detail["chromosome"], position=detail["position"],
                   reference_allele=detail["reference"], alternate_allele=detail["alternate"],
                   consequence=annotation.get("consequence") or "UNKNOWN", coordinate_system="genomic_1_based",
                   source_refs={"consequence": [source], "position": [source]})
    context = {"gene": gene, "molecular_mechanism": "UNKNOWN", "confidence": "UNKNOWN"}
    if choice:
        selected = choice["context"]
        origin = choice.get("origin", {})
        citation = "HELPER association {}|{}|{}".format(choice["id"], origin.get("source"), origin.get("source_version"))
        modes = selected.get("inheritance_modes", [])
        context.update(disease=selected["disease"]["identifier"], inheritance=modes[0] if len(modes) == 1 else None,
                       scope="DISEASE_SPECIFIC", source_refs={key: [citation] for key in ("disease", "inheritance", "scope")})
        _import_g2p_context(context, choice)
    tx = {"accession": annotation["transcript"], "source_refs": {"accession": [source]}}
    stored = annotation.get("metadata", {}).get("pvs1_input")
    if stored is not None:
        sample = PVS1Input(**stored)
        identity = ("assembly", "contig", "position", "reference_allele", "alternate_allele", "consequence")
        if any(sample.variant[k] != variant[k] for k in identity) or (sample.transcript or {}).get("accession") != tx["accession"]:
            raise ValueError("Existing PVS1 input does not match the selected allele/transcript")
        if sample.disease_context["gene"] != gene or (choice and sample.disease_context.get("disease") != context["disease"]):
            raise ValueError("Existing PVS1 input does not match the selected gene/disease")
        return sample, "EXISTING_PVS1_INPUT", []
    sample = PVS1Input(variant=variant, disease_context=context, transcript=tx)
    warnings = ["VEP non documenta automaticamente meccanismo LoF, rilevanza dell'esone, tolleranza o rescue; le asserzioni G2P disponibili sono importate nel contesto selezionato."]
    if choice and context["molecular_mechanism"] == "UNKNOWN":
        unscoped = choice.get("origin", {}).get("unscoped_g2p_records", [])
        if unscoped:
            warnings.append("Record G2P " + ", ".join(r["id"] for r in unscoped)
                            + " privi di identificativo di malattia nella cache: non attribuiti automaticamente al contesto selezionato.")
    origin = "ANNOTATION_ONLY"
    if re.fullmatch(r"ENST[0-9]+\.[0-9]+", tx["accession"]):
        cached = TranscriptReferenceProvider().get(tx["accession"], assembly, fetch=False)
        reference = cached.get("data")
        if reference:
            facts = transcript_facts(sample, reference)
            if facts["status"] == "COMPLETE":
                sample.transcript = facts["data"]
                terms = set(variant["consequence"].split("&"))
                if terms.intersection({"stop_gained", "frameshift_variant"}) and not any(t.startswith("splice_") for t in terms):
                    sample.molecular_effect = _annotated_product(sample, reference, annotation, source)
                    origin = "VEP_STOP_ANNOTATION" if sample.molecular_effect else "TRANSCRIPT_CACHE"
                    if sample.molecular_effect is None:
                        calculated = compute_molecular_evidence(sample, reference, tx["accession"] + "|HELPER-product:" + str(annotation.get("id")))
                        if calculated.get("data"):
                            sample.molecular_effect = calculated["data"]["molecular_effect"]
                        warnings.extend(calculated["warnings"] + calculated["missing_data"])
                    elif "frameshift_variant" in terms:
                        product = sample.molecular_effect["products"][0]
                        if not any(distance > 50 for _, distance in product["ptc_junction_distances"]):
                            calculated = compute_molecular_evidence(sample, reference, product["transcript_ref"])
                            if calculated.get("data"):
                                sample.molecular_effect = calculated["data"]["molecular_effect"]
                                origin = "TRANSCRIPT_CACHE_FOR_PROTEIN_REGION"
                            warnings.extend(calculated["warnings"] + calculated["missing_data"])
            else:
                warnings.extend(facts["missing_data"])
        else:
            warnings.append("Riferimento trascrizionale esatto non disponibile nella cache: nessun download o FASTA eseguito.")
    return sample, origin, warnings


@router.post("/pvs1")
def evaluate_pvs1(payload: dict = Body(...)):
    try:
        entry = _entry(payload["run_id"])
        detail = query.variant_detail(_entry_database(entry), int(payload["sample_id"]), int(payload["variant_id"]))
        if detail is None:
            raise HTTPException(status_code=404, detail="Variant not found for this sample")
        annotations = [a for a in detail["annotations"] if a.get("id") == payload.get("annotation_id")
                       and a.get("transcript") == payload.get("transcript")]
        if len(annotations) != 1:
            raise ValueError("Select one exact HELPER transcript annotation for this allele")
        annotation = annotations[0]
        choice = None
        if payload.get("context_id"):
            _, choice = acmg_context.select(acmg_context.build(detail), annotation["id"], annotation["transcript"], payload["context_id"])
        impact = analyze_transcripts(detail, annotation)
        sample, origin, warnings = prepare_pvs1_input(detail, annotation, choice)
        selected_impact = next((row for row in impact["transcripts"] if row.get("selected")), None)
        if (selected_impact and selected_impact.get("pvs1_input") and impact["release_verified"]
                and origin != "EXISTING_PVS1_INPUT"):
            technical = selected_impact["pvs1_input"]
            sources = {**(sample.transcript.get("source_refs") or {}), **technical["transcript"]["source_refs"]}
            sample.transcript = {**sample.transcript, **technical["transcript"], "source_refs": sources}
            sample.molecular_effect = technical["molecular_effect"]
            origin = "TRANSCRIPT_MOLECULAR_ANALYSIS"
            warnings.extend(selected_impact["warnings"])
        elif (selected_impact and selected_impact.get("status") == "INSUFFICIENT_DATA"
              and impact["release_verified"] and origin != "EXISTING_PVS1_INPUT"):
            # Do not use an unchecked numerical HGVS stop over a failed sequence reconstruction.
            sample.molecular_effect = None
            warnings.extend(selected_impact["missing_data"])
        result = calculate_pvs1(sample, policy=payload.get("policy", "STANDARD"))
        result.warnings.extend(warnings)
        for row in impact["transcripts"]:
            row.pop("pvs1_input", None)
        return {"criterion": "PVS1", "input": asdict(sample), "result": asdict(result), "molecular_origin": origin,
                "molecular_impact": impact}
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
