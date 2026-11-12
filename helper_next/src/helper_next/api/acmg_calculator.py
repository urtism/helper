"""Bridge from an exact HELPER annotation to the local PVS1 package.

No Task 22, Workbench or engine client. Molecular analysis uses release-qualified
public references; splice scenarios verify small intervals of the run's FASTA.
Selected-transcript sequence facts are shared with the optional gene-wide view.
"""
import json
import sqlite3
import uuid
from dataclasses import asdict, replace

from fastapi import APIRouter, Body, HTTPException

from helper_next.api.variants import _entry, _entry_database
from helper_next.core import acmg_context
from helper_next.core import acmg_pvs1_store as saved_pvs1
from helper_next.core import acmg_classification as classification
from helper_next.core import acmg_classification_store as saved_classification
from helper_next.core import acmg_automatic_store as automatic_store
from helper_next.core.acmg_digest import digest
from helper_next.core.acmg_sources import SourceManager
from helper_next.core.acmg_transcripts import primary_chromosome
from helper_next.core.acmg_pvs1_mechanism import resolve_pvs1_mechanism
from helper_next.core.acmg_molecular_impact import analyze_transcripts
from helper_variants import query, store as variant_store
from pvs1.calculator import calculate_pvs1, RULESET_VERSION
from pvs1.models import PVS1Input


router = APIRouter(prefix="/api/acmg-calculator", tags=["new ACMG Calculator"])
_MANUAL_STRENGTHS = {"VERY_STRONG", "STRONG", "MODERATE", "SUPPORTING", "NONE"}


def _saved_selection(payload, *, choice=None, entry=None):
    """Exact indexed selection, with no ClinVar enrichment or sequence analysis."""
    entry = entry or _entry(payload["run_id"])
    with variant_store.connect(_entry_database(entry)) as db:
        row = db.execute(
            "SELECT s.sample_key, v.reference_build, v.chromosome, v.position, v.reference, v.alternate, "
            "v.metadata_json AS variant_metadata, an.*, ar.resources_json "
            "FROM samples s JOIN analyses a ON a.sample_id=s.id JOIN calls c ON c.analysis_id=a.id "
            "JOIN variants v ON v.id=c.variant_id JOIN annotations an ON an.variant_id=v.id "
            "JOIN annotation_releases ar ON ar.id=an.release_id "
            "WHERE s.id=? AND v.id=? AND an.id=? AND an.transcript=? LIMIT 1",
            (int(payload["sample_id"]), int(payload["variant_id"]), int(payload["annotation_id"]), payload["transcript"]),
        ).fetchone()
    if row is None:
        raise ValueError("Selezione PVS1 non disponibile: ricarica la variante")
    annotation = {**dict(row), "metadata": json.loads(row["metadata_json"])}
    selected = {}
    if payload.get("context_id"):
        # Read-only lookup uses the already displayed context. Only the normal
        # evaluator can create save tickets, after validating the full catalog.
        selected = choice["context"] if choice else payload.get("interpretation_context")
        if not isinstance(selected, dict):
            raise ValueError("Contesto strutturato PVS1 mancante")
        if not isinstance(selected.get("gene"), dict) or not isinstance(selected.get("disease"), dict):
            raise ValueError("Identificativi del contesto PVS1 mancanti")
        gene, disease = selected.get("gene", {}).get("identifier"), selected.get("disease", {}).get("identifier")
        expected = "context-" + digest({"annotation_id": annotation["id"], "gene": gene, "disease": disease})["value"][:24]
        modes = selected.get("inheritance_modes", [])
        if (not acmg_context.identifier(gene) or not acmg_context.identifier(disease)
                or not isinstance(modes, list) or any(not isinstance(mode, str) for mode in modes)
                or expected != payload["context_id"]):
            raise ValueError("Il contesto PVS1 non corrisponde alla selezione")
    stored_context = annotation["metadata"].get("pvs1_input", {}).get("disease_context", {})
    genes = acmg_context.annotation_genes(annotation)
    hgnc = [gene for gene in genes if gene.startswith("HGNC:")]
    fields = annotation["metadata"].get("fields", {})
    assembly = {"hg19": "GRCh37", "hg38": "GRCh38", "grch37": "GRCh37", "grch38": "GRCh38"}.get(
        row["reference_build"].lower(), row["reference_build"])
    identity = dict(sample=row["sample_key"], assembly=assembly, chromosome=primary_chromosome(row["chromosome"]),
                    position=row["position"], reference=row["reference"], alternate=row["alternate"],
                    transcript=row["transcript"], gene=selected.get("gene", {}).get("identifier")
                    or (hgnc[0] if len(hgnc) == 1 else fields.get("Gene") or row["gene"]),
                    disease=selected.get("disease", {}).get("identifier") or stored_context.get("disease"),
                    inheritance=selected.get("inheritance_modes") or ([stored_context["inheritance"]] if stored_context.get("inheritance") else []))
    from pvs1.molecular import VERSION as molecular_version
    from pvs1.impact import VERSION as impact_version
    from helper_next.core.acmg_splice import VERSION as splice_version
    from helper_next.core.acmg_mechanism_assessment import RULES_VERSION as mechanism_version
    from helper_next.core.acmg_reference import reference_record
    reference, config = reference_record(assembly, entry.get("record"))
    candidates = [reference.get("run_config", {}).get("reference_fasta")]
    tools = reference.get("tools_config", {})
    if isinstance(tools.get(assembly), dict):
        candidates.append(tools[assembly].get("fasta"))
    reference_files = saved_pvs1.file_states([path for fasta in candidates if fasta for path in (str(fasta), str(fasta) + ".fai")])
    signature = digest([identity, annotation["metadata"], automatic_store.biological_metadata(row["variant_metadata"]), row["resources_json"],
                        row["consequence"], row["hgvsc"], row["hgvsp"],
                        selected, automatic_store.gene_revision(row["gene"], identity["gene"] or ""),
                        config, reference.get("run_config", {}).get("reference_version"), reference_files,
                        RULESET_VERSION, molecular_version, impact_version, splice_version, mechanism_version])["value"]
    return entry["record"]["run_dir"], identity, signature


@router.post("/pvs1/saved")
def saved_evaluation(payload: dict = Body(...)):
    try:
        run_dir = _entry(payload["run_id"])["record"]["run_dir"]
        if not saved_pvs1.path(run_dir).is_file():
            return {"saved": None}
        run_dir, identity, signature = _saved_selection(payload)
        record = saved_pvs1.latest(run_dir, identity)
        return {"saved": record, "needs_review": bool(record and saved_pvs1.needs_review(record, signature))}
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/pvs1/history")
def evaluation_history(payload: dict = Body(...)):
    try:
        run_dir, identity, _ = _saved_selection(payload)
        before = payload.get("before_revision")
        if before is not None and (type(before) is not int or before < 1):
            raise ValueError("Revisione dello storico non valida")
        records = saved_pvs1.history(run_dir, identity, before)
        return {"items": records, "next_before_revision": records[-1]["revision"] if len(records) == 20 else None}
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/pvs1/save")
def save_evaluation(payload: dict = Body(...)):
    try:
        run_dir = _entry(payload["run_id"])["record"]["run_dir"]
        pending = saved_pvs1.pending(payload["evaluation_id"], run_dir)
        _, identity, signature = _saved_selection(pending["selection"])
        if identity != pending["identity"] or saved_pvs1.needs_review(pending, signature):
            raise ValueError("Dati aggiornati: premi Valuta PVS1 prima di salvare")
        record = saved_pvs1.save(run_dir, identity, signature, pending["snapshot"], payload.get("note", ""))
        return {"saved": record, "needs_review": False}
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


def _classification_selection(payload):
    if not payload.get("context_id"):
        raise ValueError("Seleziona un contesto gene–malattia")
    run_dir, identity, signature = _saved_selection(payload)
    modes = identity.get("inheritance", [])
    if not identity.get("disease") or len(modes) != 1 or modes[0] not in {
        "AUTOSOMAL_DOMINANT", "AUTOSOMAL_RECESSIVE", "X_LINKED", "Y_LINKED", "MITOCHONDRIAL"
    }:
        raise ValueError("Seleziona una malattia e una modalità di ereditarietà")
    with variant_store.connect(_entry_database(_entry(payload["run_id"]))) as db:
        row = db.execute("SELECT consequence FROM annotations WHERE id=?", (int(payload["annotation_id"]),)).fetchone()
    splice = "splice" in (row["consequence"] or "").lower()
    return run_dir, identity, signature, splice


def _classification_pvs1(run_dir, identity, signature):
    record = saved_pvs1.latest(run_dir, identity)
    if not record:
        return None
    return dict(revision=record["revision"], strength=record["snapshot"]["result"].get("applied_strength"),
                status=record["snapshot"]["result"].get("status"),
                manual=bool(record["snapshot"].get("strength_override")),
                needs_review=saved_pvs1.needs_review(record, signature))


@router.post("/classification/load")
def load_classification(payload: dict = Body(...)):
    try:
        run_dir, identity, signature, splice = _classification_selection(payload)
        record = saved_classification.latest(run_dir, identity)
        pvs1 = _classification_pvs1(run_dir, identity, signature)
        stale = bool(record and (record["signature"] != signature or record["assessment"].get("version") != classification.VERSION))
        imported = next((row for row in record["assessment"]["criteria"] if row.get("origin") == "PVS1_SAVED"), None) if record else None
        stale = stale or bool(imported and (not pvs1 or pvs1["needs_review"] or imported["pvs1_revision"] != pvs1["revision"]))
        if record and record["assessment"].get("automatic_pvs1"):
            stale = stale or saved_pvs1.needs_review(dict(signature=record["signature"], snapshot=record["assessment"]["automatic_pvs1"]), signature)
        return dict(saved=record, needs_review=stale, catalog=classification.catalog(), pvs1=pvs1, splice=splice,
                    signature=signature, model=classification.MODEL, source_url=classification.SOURCE, pm2_source_url=classification.PM2_SOURCE)
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/classification/preview")
def preview_classification(payload: dict = Body(...)):
    try:
        return classification.combine(payload.get("criteria", []), splice=payload.get("splice") is True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/classification/save")
def save_classification(payload: dict = Body(...)):
    try:
        run_dir, identity, signature, splice = _classification_selection(payload)
        if payload.get("signature") != signature:
            raise ValueError("Dati aggiornati: riapri la scheda prima di salvare")
        assessment = classification.combine(payload.get("criteria", []), splice=splice)
        for row in assessment["criteria"]:
            if row["origin"] == "PVS1_SAVED":
                pvs1 = _classification_pvs1(run_dir, identity, signature)
                if not pvs1 or pvs1["needs_review"] or pvs1["revision"] != row["pvs1_revision"] or pvs1["strength"] != row["strength"]:
                    raise ValueError("Il PVS1 importato è cambiato: riapri la scheda e controlla il criterio")
            elif row["origin"] == "PVS1_AUTO":
                try:
                    evidence = saved_pvs1.pending(row["pvs1_evaluation_id"], run_dir)
                except ValueError:
                    previous = saved_classification.latest(run_dir, identity)
                    previous_row = next((item for item in (previous or {}).get("assessment", {}).get("criteria", [])
                                         if all(item.get(key) == row.get(key) for key in ("code", "strength", "origin", "pvs1_evaluation_id"))), None)
                    if not previous_row or not previous["assessment"].get("automatic_pvs1"):
                        raise ValueError("Valutazione automatica scaduta: ricarica la variante")
                    evidence = dict(identity=previous["identity"], signature=previous["signature"], snapshot=previous["assessment"]["automatic_pvs1"])
                if (evidence["identity"] != identity or saved_pvs1.needs_review(evidence, signature)
                        or evidence["snapshot"]["result"].get("applied_strength") != row["strength"]):
                    raise ValueError("Il PVS1 automatico è cambiato: ricarica la variante")
                assessment["automatic_pvs1"] = evidence["snapshot"]
        record = saved_classification.save(run_dir, identity, signature, assessment, payload.get("note", ""), payload.get("expected_revision", 0))
        return dict(saved=record, needs_review=False)
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/classification/summaries")
def classification_summaries(payload: dict = Body(...)):
    return _classification_summaries(payload)


def _classification_summaries(payload, entry=None):
    """One indexed read of current heads for the visible sample/allele."""
    try:
        entry = entry or _entry(payload["run_id"])
        with variant_store.connect(_entry_database(entry)) as db:
            row = db.execute("SELECT s.sample_key,v.* FROM samples s JOIN analyses a ON a.sample_id=s.id "
                             "JOIN calls c ON c.analysis_id=a.id JOIN variants v ON v.id=c.variant_id "
                             "WHERE s.id=? AND v.id=? LIMIT 1", (int(payload["sample_id"]), int(payload["variant_id"]))).fetchone()
        if row is None:
            raise ValueError("Variante non disponibile per questo campione")
        assembly = {"hg19": "GRCh37", "hg38": "GRCh38", "grch37": "GRCh37", "grch38": "GRCh38"}.get(row["reference_build"].lower(), row["reference_build"])
        identity = dict(sample=row["sample_key"], assembly=assembly, chromosome=primary_chromosome(row["chromosome"]),
                        position=row["position"], reference=row["reference"], alternate=row["alternate"])
        return {"items": saved_classification.summaries(entry["record"]["run_dir"], identity)}
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


def _automatic_classification(payload, entry, *, issue_tickets=True):
    """Reuse durable automatic results; user worksheets always take precedence."""
    try:
        database = _entry_database(entry)
        detail = query._variant_detail(database, int(payload["sample_id"]), int(payload["variant_id"]))
        if detail is None:
            raise ValueError("Variante non disponibile per questo campione")
        source = automatic_store.source_revision(detail["reference_build"], entry.get("record"),
                                                 [annotation["gene"] for annotation in detail["annotations"] if annotation.get("gene")])
        inputs = automatic_store.input_revisions(database, [int(payload["variant_id"])])[int(payload["variant_id"])]
        # Keep the same representative ordering as the Variants table.
        with variant_store.connect(database) as db:
            rows = db.execute("SELECT id,gene FROM annotations WHERE variant_id=? AND transcript<>'' "
                              "ORDER BY canonical DESC, CASE impact WHEN 'HIGH' THEN 0 WHEN 'MODERATE' THEN 1 "
                              "WHEN 'LOW' THEN 2 WHEN 'MODIFIER' THEN 3 ELSE 4 END,release_id DESC,id",
                              (int(payload["variant_id"]),)).fetchall()
        main_ids = {}
        for row in rows:
            if row["gene"]:
                main_ids.setdefault(row["gene"].upper(), row["id"])
        main = [annotation for annotation in detail["annotations"] if annotation["id"] in main_ids.values()]
        catalog = acmg_context.build({**detail, "annotations": main}, lookup_gene=automatic_store.gene_knowledge)
        items = _classification_summaries(payload, entry)["items"]
        automatic, mains = [], []
        ready = True
        for annotation in main:
            selected = next(item for item in catalog["annotations"] if item["annotation_id"] == annotation["id"])
            mains.append(dict(gene=annotation["gene"], annotation_id=annotation["id"], transcript=annotation["transcript"]))
            ready = ready and selected["cache_status"] == "ready" and not selected["cache_refreshing"]
            impact = None
            analyzed = False
            analysis_error = None
            for candidate in selected["contexts"]:
                context = candidate["context"]
                for mode in context.get("inheritance_modes") or [None]:
                    choice = {**candidate, "context": {**context, "inheritance_modes": [mode] if mode else []}}
                    selection = dict(run_id=payload["run_id"], sample_id=payload["sample_id"], variant_id=payload["variant_id"],
                                     annotation_id=annotation["id"], transcript=annotation["transcript"], context_id=choice["id"],
                                     interpretation_context=choice["context"])
                    identity = dict(gene=context["gene"]["identifier"], disease=context["disease"]["identifier"],
                                    transcript=annotation["transcript"], inheritance=[mode] if mode else [])
                    result = dict(identity=identity, annotation_id=annotation["id"], context_id=choice["id"], automatic=True,
                                  assessment=classification.combine([]))
                    try:
                        if mode is None:
                            raise ValueError("Ereditarietà non disponibile per questa associazione")
                        run_dir, identity, signature = _saved_selection(selection, choice=choice, entry=entry)
                        result["identity"] = identity
                        saved = saved_classification.latest(run_dir, identity)
                        if saved:
                            stale = saved["signature"] != signature or saved["assessment"].get("version") != classification.VERSION
                            snapshot = saved["assessment"].get("automatic_pvs1")
                            stale = stale or bool(snapshot and saved_pvs1.needs_review(dict(signature=saved["signature"], snapshot=snapshot), signature))
                            imported = next((row for row in saved["assessment"]["criteria"] if row.get("origin") == "PVS1_SAVED"), None)
                            if imported:
                                pvs1 = _classification_pvs1(run_dir, identity, signature)
                                stale = stale or not pvs1 or pvs1["needs_review"] or pvs1["revision"] != imported["pvs1_revision"]
                            for summary in items:
                                if summary["identity"] == identity:
                                    summary["needs_review"] = stale
                            if not stale:
                                continue  # A saved user worksheet always takes precedence.
                        previous_pvs1 = saved_pvs1.latest(run_dir, identity)
                        cache_signature = digest([signature, source, inputs, previous_pvs1])["value"]
                        cached = automatic_store.load(run_dir, identity, cache_signature)
                        if cached:
                            result, snapshot = cached
                            for criterion in result["assessment"]["criteria"]:
                                if issue_tickets and criterion.get("origin") == "PVS1_AUTO":
                                    criterion["pvs1_evaluation_id"] = saved_pvs1.remember(
                                        run_dir, selection, identity, signature, snapshot)
                            automatic.append(result)
                            continue
                        if previous_pvs1 and not saved_pvs1.needs_review(previous_pvs1, signature):
                            evaluated = previous_pvs1["snapshot"]["result"]
                            result["pvs1"] = {key: evaluated.get(key) for key in ("status", "reason", "applied_strength", "requires_review", "missing_data")}
                            result["pvs1"]["manual"] = bool(previous_pvs1["snapshot"].get("strength_override"))
                            criteria = []
                            if evaluated.get("applied_strength") and (evaluated["status"] == "ACTIVE" or result["pvs1"]["manual"]):
                                criteria.append(dict(code="PVS1", strength=evaluated["applied_strength"], origin="PVS1_SAVED",
                                                     pvs1_revision=previous_pvs1["revision"], source="HELPER PVS1 salvato"))
                            result["assessment"] = classification.combine(criteria, splice="splice" in (annotation.get("consequence") or "").lower())
                            result["assessment"]["requires_review"] |= bool(evaluated.get("requires_review"))
                            automatic_store.save(run_dir, identity, cache_signature, result, previous_pvs1["snapshot"], source, inputs)
                            automatic.append(result)
                            continue
                        sample, origin, warnings, assessment = prepare_pvs1_input(detail, annotation, choice)
                        fields = annotation.get("metadata", {}).get("fields", {})
                        needs_product = (bool(set((annotation.get("consequence") or "").replace(",", "&").split("&")) & {
                            "stop_gained", "frameshift_variant", "splice_donor_variant", "splice_acceptor_variant"
                        }) or any(str(key).lower().startswith("spliceai") for key in fields)) and sample.disease_context.get("molecular_mechanism") == "LoF"
                        if origin != "EXISTING_PVS1_INPUT" and needs_product and not analyzed:
                            analyzed = True
                            try:
                                impact = analyze_transcripts(detail, annotation, selected_only=True, record=entry.get("record"))
                            except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
                                analysis_error = str(exc)
                        if origin != "EXISTING_PVS1_INPUT" and needs_product and analysis_error:
                            raise ValueError(analysis_error)
                        response = _pvs1_response(sample, origin, warnings, assessment, impact if origin != "EXISTING_PVS1_INPUT" else None)
                        evaluated = response["result"]
                        result["pvs1"] = {key: evaluated.get(key) for key in ("status", "reason", "applied_strength", "requires_review", "missing_data")}
                        snapshot = saved_pvs1.compact_snapshot(response, annotation)
                        criteria = []
                        if evaluated["status"] == "ACTIVE" and evaluated["applied_strength"]:
                            token = (saved_pvs1.remember(run_dir, selection, identity, signature, snapshot)
                                     if issue_tickets else uuid.uuid4().hex)
                            criteria.append(dict(code="PVS1", strength=evaluated["applied_strength"], origin="PVS1_AUTO",
                                                 pvs1_evaluation_id=token, source="HELPER PVS1 automatico · " + annotation["transcript"]))
                        result["assessment"] = classification.combine(criteria, splice="splice" in (annotation.get("consequence") or "").lower())
                        result["assessment"]["requires_review"] = result["assessment"]["requires_review"] or bool(evaluated["requires_review"])
                        automatic_store.save(run_dir, identity, cache_signature, result, snapshot, source, inputs)
                    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
                        result["error"] = str(exc)
                        result["assessment"]["requires_review"] = True
                    automatic.append(result)
        return dict(items=items, automatic=automatic, mains=mains, contexts=catalog, context_ready=ready,
                    automatic_criteria=["PVS1"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/classification/automatic")
def automatic_classification(payload: dict = Body(...)):
    try:
        entry = _entry(payload["run_id"])
        with automatic_store.evaluation_lock(entry["record"]["run_dir"], int(payload["sample_id"]), int(payload["variant_id"])), \
                automatic_store.write_batch(entry["record"]["run_dir"]):
            return _automatic_classification(payload, entry)
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


def prepare_automatic_classification(payload, entry):
    """Run-local preparation reuses its entry and never allocates UI save tickets."""
    with automatic_store.evaluation_lock(entry["record"]["run_dir"], int(payload["sample_id"]), int(payload["variant_id"])), \
            automatic_store.write_batch(entry["record"]["run_dir"]):
        result = _automatic_classification(payload, entry, issue_tickets=False)
    return {"automatic": [{"error": item["error"]} for item in result["automatic"] if item.get("error")]}


def _strength_override(result, strength):
    """Apply a user selection without rewriting the automatic assessment."""
    if strength is None:
        return result, None
    if not isinstance(strength, str) or strength not in _MANUAL_STRENGTHS:
        raise ValueError("Strength manuale non valida")
    applied = None if strength == "NONE" else strength
    selection = {"strength": strength, "automatic_status": result.status,
                 "automatic_applied_strength": result.applied_strength}
    trace = json.dumps({"id": "manual_strength", "description": "Strength scelta manualmente",
                        "rule": "USER_OVERRIDE", "status": "MANUAL",
                        "value": {"calculated_strength": result.calculated_strength,
                                  "automatic_applied_strength": result.applied_strength, "applied_strength": applied},
                        "source": ["HELPER Calculator: selezione manuale dell'utente"],
                        "reason": "La scelta manuale modifica soltanto la strength applicata; la valutazione automatica è conservata."},
                       ensure_ascii=False)
    warning = "Strength scelta manualmente: " + ("PVS1 non applicato." if applied is None else applied + ".")
    return replace(result, applied_strength=applied, warnings=[*result.warnings, warning],
                   decision_trace=[*result.decision_trace, trace]), selection


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
    tx = {"accession": annotation["transcript"], "source_refs": {"accession": [source]}}
    stored = annotation.get("metadata", {}).get("pvs1_input")
    sample = None
    if stored is not None:
        sample = PVS1Input(**stored)
        identity = ("assembly", "contig", "position", "reference_allele", "alternate_allele", "consequence")
        if any(sample.variant[k] != variant[k] for k in identity) or (sample.transcript or {}).get("accession") != tx["accession"]:
            raise ValueError("Existing PVS1 input does not match the selected allele/transcript")
        if sample.disease_context["gene"] != gene or (choice and sample.disease_context.get("disease") != context["disease"]):
            raise ValueError("Existing PVS1 input does not match the selected gene/disease")
        if choice and context.get("inheritance") and sample.disease_context.get("inheritance") != context["inheritance"]:
            raise ValueError("Existing PVS1 input does not match the selected inheritance")
        if not choice:
            return sample, "EXISTING_PVS1_INPUT", [], None
    assessment = None
    warnings = ["VEP non documenta automaticamente meccanismo LoF, rilevanza dell'esone, tolleranza o rescue; il meccanismo è valutato dalle fonti locali nel contesto selezionato."]
    if choice:
        mechanism_fields, assessment, mechanism_warnings = resolve_pvs1_mechanism(choice)
        sources = mechanism_fields.pop("source_refs", {})
        # The mechanism's scope does not replace the selected association's scope.
        if "scope" in mechanism_fields:
            mechanism_fields["mechanism_scope"] = mechanism_fields.pop("scope")
        if "scope" in sources:
            sources["mechanism_scope"] = sources.pop("scope")
        context.update(mechanism_fields)
        for key, citations in sources.items():
            context["source_refs"].setdefault(key, []).extend(citations)
        warnings.extend(mechanism_warnings)
    if sample is None:
        sample = PVS1Input(variant=variant, disease_context=context, transcript=tx)
    else:
        # Preserve the supplied molecular evidence, while assessing the newly
        # selected context rather than reusing a stored biological conclusion.
        sample.disease_context = context
    if choice and context["molecular_mechanism"] == "UNKNOWN":
        unscoped = choice.get("origin", {}).get("unscoped_g2p_records", [])
        if unscoped:
            warnings.append("Record G2P " + ", ".join(r["id"] for r in unscoped)
                            + " privi di identificativo di malattia nella cache: non attribuiti automaticamente al contesto selezionato.")
    return sample, "EXISTING_PVS1_INPUT" if stored is not None else "ANNOTATION_ONLY", warnings, assessment


def _selected_annotation(payload):
    entry = _entry(payload["run_id"])
    detail = query.variant_detail(_entry_database(entry), int(payload["sample_id"]), int(payload["variant_id"]))
    if detail is None:
        raise HTTPException(status_code=404, detail="Variant not found for this sample")
    annotations = [a for a in detail["annotations"] if a.get("id") == payload.get("annotation_id")
                   and a.get("transcript") == payload.get("transcript")]
    if len(annotations) != 1:
        raise ValueError("Select one exact HELPER transcript annotation for this allele")
    return detail, annotations[0]


def _public_impact(impact):
    if impact:
        for row in impact["transcripts"]:
            row.pop("pvs1_input", None)
    return impact


def _explain_unresolved_product(result, impact, row):
    """Carry the reconstruction failure into the requirement shown by the UI."""
    generic = next((reason for reason in result.missing_data if reason.startswith(
        ("Manca un prodotto molecolare determinato.", "Manca un evento splice completo esplicito"))), None)
    if not generic or not row:
        return
    reasons = list(row["missing_data"])
    if not impact["release_verified"]:
        reasons.append("Release dell'annotazione non verificata: il prodotto non può essere trasferito a PVS1.")
    if not reasons:
        return
    reason = generic + " " + "; ".join(dict.fromkeys(reasons))
    result.missing_data = [reason if item == generic else item for item in result.missing_data]
    result.reason = result.reason.replace(generic, reason)
    for index, raw in enumerate(result.decision_trace):
        requirement = json.loads(raw)
        if requirement["id"] == "product":
            requirement.update(reason=reason, value=row["product_resolution"])
            result.decision_trace[index] = json.dumps(requirement, ensure_ascii=False)


@router.post("/molecular-impact")
def evaluate_molecular_impact(payload: dict = Body(...)):
    """Optional gene-wide comparison, independent of disease and PVS1 strength."""
    try:
        detail, annotation = _selected_annotation(payload)
        return _public_impact(analyze_transcripts(detail, annotation, record=_entry(payload["run_id"]).get("record")))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


def _pvs1_response(sample, origin, warnings, assessment, impact, *, policy="STANDARD", strength=None):
    selected_impact = next((row for row in (impact or {}).get("transcripts", []) if row.get("selected")), None)
    if impact:
        warnings.extend(impact["warnings"])
    if selected_impact:
        warnings.extend(selected_impact["warnings"] + selected_impact["missing_data"])
    if selected_impact and selected_impact.get("pvs1_input") and impact["release_verified"]:
        technical = selected_impact["pvs1_input"]
        sources = {**(sample.transcript.get("source_refs") or {}), **technical["transcript"]["source_refs"]}
        sample.transcript = {**sample.transcript, **technical["transcript"], "source_refs": sources}
        sample.molecular_effect = technical["molecular_effect"]
        if (selected_impact.get("splice_analysis", {}).get("site") or {}).get("prediction_only"):
            # Keep the indexed annotation intact; the derived RNA hypothesis
            # supplies its own consequence and source on this calculation.
            sample.variant["consequence"] = selected_impact["consequence"]
            references = sample.variant.setdefault("source_refs", {})
            references["consequence"] = [*references.get("consequence", []),
                selected_impact["provenance"]["splice_scenario"]]
        origin = "TRANSCRIPT_MOLECULAR_ANALYSIS"
    result = calculate_pvs1(sample, policy=policy)
    _explain_unresolved_product(result, impact, selected_impact)
    result.warnings.extend(warnings)
    result, override = _strength_override(result, strength)
    response = {"criterion": "PVS1", "input": asdict(sample), "result": asdict(result), "molecular_origin": origin,
                "molecular_impact": impact, "mechanism_assessment": assessment}
    if override is not None:
        response["strength_override"] = override
    return response


@router.post("/pvs1")
def evaluate_pvs1(payload: dict = Body(...)):
    try:
        strength = payload.get("strength_override")
        if strength is not None and (not isinstance(strength, str) or strength not in _MANUAL_STRENGTHS):
            raise ValueError("Strength manuale non valida")
        detail, annotation = _selected_annotation(payload)
        save_context = None
        persistence_error = None
        choice = None
        if payload.get("context_id"):
            selected, choice = acmg_context.select(acmg_context.build(detail), annotation["id"], annotation["transcript"], payload["context_id"],
                                                  inheritance=payload.get("inheritance", ""))
            if payload.get("inheritance"):
                choice = {**choice, "context": selected}
        if payload.get("prepare_save") is True:
            try:
                save_context = _saved_selection(payload, choice=choice)
            except (OSError, sqlite3.Error, ValueError, KeyError) as exc:
                persistence_error = str(exc)
        sample, origin, warnings, assessment = prepare_pvs1_input(detail, annotation, choice)
        # A supplied RNA/product input is already explicit evidence; do not
        # fetch references or overwrite it with a reference-splicing prediction.
        impact = None if origin == "EXISTING_PVS1_INPUT" else analyze_transcripts(
            detail, annotation, selected_only=True,
            record=_entry(payload["run_id"]).get("record") if payload.get("run_id") else None)
        response = _pvs1_response(sample, origin, warnings, assessment, impact, policy=payload.get("policy", "STANDARD"), strength=strength)
        response["molecular_impact"] = _public_impact(impact)
        if save_context:
            try:
                run_dir, identity, signature = save_context
                snapshot = saved_pvs1.compact_snapshot(response, annotation)
                selection = {key: payload.get(key) for key in ("run_id", "sample_id", "variant_id", "annotation_id", "transcript", "context_id")}
                selection["interpretation_context"] = choice["context"] if choice else None
                response["evaluation_id"] = saved_pvs1.remember(run_dir, selection, identity, signature, snapshot)
                response["evaluation_signature"] = signature
            except ValueError as exc:
                persistence_error = str(exc)
        if persistence_error:
            response["persistence_error"] = persistence_error
        return response
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
