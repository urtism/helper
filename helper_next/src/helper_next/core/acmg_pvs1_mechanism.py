"""Small adapter from existing mechanism evidence/assessment to PVS1 context.

Only public local indexes are consulted. Association snapshots retain the
existing invalidation policy; assessment is reused until its inputs change.
This module neither reconstructs variants nor assigns an ACMG strength.
"""
import json
import os
import sqlite3
import threading
from functools import lru_cache

from helper_next.core.acmg_mechanism_assessment import RULES_VERSION, VERSION, assess, disputed_validity
from helper_next.core.acmg_mechanism_models import GeneDiseaseMechanismResult
from helper_next.core.acmg_mechanism_normalizer import allelic
from helper_next.core.acmg_mechanisms import MechanismEvidenceCache
from helper_next.core.acmg_mechanism_store import MechanismStore
from helper_next.core.acmg_sources import SourceManager
from helper_variants import gene_phenotype
from helper_variants.gene_phenotype import _G2P_ACCEPTED_CONFIDENCE


_MECHANISMS = {"LOSS_OF_FUNCTION": "LoF", "GAIN_OF_FUNCTION": "GoF", "DOMINANT_NEGATIVE": "DN", "OTHER": "OTHER"}
_resolver_lock = threading.Lock()


@lru_cache(maxsize=4)
def _resolver(database, gene_database, ttl_json, timeout):
    return MechanismEvidenceCache(database=database,
        sources=SourceManager(gene_database=gene_database, mechanism_fetch=False),
        ttl_seconds=json.loads(ttl_json), timeout=float(timeout))


def _shared_cache():
    """Keep one registry per configuration; its pin() still checks the active release.

    Only the resolver is reused. Every call retains the existing source revision,
    TTL, snapshot integrity and rule checks. Database write timestamps are not
    cache keys: publishing another association cannot reload the whole ontology.
    """
    key = (str(MechanismStore().path.expanduser().resolve()),
           str(gene_phenotype.cache_path().resolve()),
           os.environ.get("HELPER_MECHANISM_TTL_JSON", "{}"),
           os.environ.get("HELPER_MECHANISM_TIMEOUT", "15"))
    # functools' cache allows duplicate construction on concurrent cold misses.
    with _resolver_lock:
        return _resolver(*key)


@lru_cache(maxsize=128)
def _assessment(payload, version, rules_version):
    # Payload includes snapshot, evidence, source states and ontology versions.
    return assess(GeneDiseaseMechanismResult.parse_raw(payload))


def _qualified(evidence):
    if not (evidence.source_record_ref and evidence.source_record_hash and evidence.source_record_id):
        return False
    if evidence.source == "g2p":
        # Preserve the Calculator's existing source acceptance boundary.
        return (str(evidence.source_classification or "").strip().lower() in _G2P_ACCEPTED_CONFIDENCE
                and evidence.asserted_mechanism in {"LOSS_OF_FUNCTION", "GAIN_OF_FUNCTION", "DOMINANT_NEGATIVE"}
                and bool(evidence.raw_assertion.get("record_url")))
    return True


def resolve_pvs1_mechanism(choice, *, cache=None):
    """Return PVS1 fields, a source-preserving report and user-facing warnings.

    The selected stable gene ID is used for lookup, not the VCF display symbol.
    Ambiguous inheritance is left unknown; no alternative context is chosen.
    """
    selected = choice["context"]
    gene, disease = selected["gene"], selected["disease"]
    modes = selected.get("inheritance_modes", [])
    unknown = {"molecular_mechanism": "UNKNOWN", "confidence": "UNKNOWN"}
    if len(modes) != 1 or allelic(modes[0]) == "UNKNOWN":
        return unknown, {"status": "MISSING_INHERITANCE"}, ["Meccanismo non valutato: ereditarietà assente o ambigua nel contesto selezionato."]
    try:
        cache = cache or _shared_cache()
        matrix = cache.resolve_gene_disease_mechanism(
            gene["identifier"], disease["identifier"], modes[0],
            symbol=gene.get("label"), disease_name=disease.get("label"), cache_policy="REFRESH_IF_STALE")
        identity = matrix.identity
        if (identity.gene_id != gene["identifier"]
                or disease["identifier"] not in {identity.disease_id, *identity.disease_aliases}
                or identity.allelic_requirement != allelic(modes[0])):
            raise ValueError("Mechanism snapshot does not match the selected gene/disease/inheritance")
        assessment = _assessment(matrix.json(sort_keys=True), VERSION, RULES_VERSION)
    except (OSError, sqlite3.Error, ValueError, RuntimeError, TimeoutError) as exc:
        return unknown, {"status": "SOURCE_UNAVAILABLE", "reason": str(exc)}, [
            "Valutazione del meccanismo non disponibile dalle fonti locali: " + str(exc)]

    report = assessment.dict()
    report.update(status="ASSESSED", snapshot_id=matrix.snapshot_id, issues=list(matrix.issues))
    warnings = list(matrix.warnings)
    primary_refs = {ref for a in assessment.assertions
                    if a.mechanism == assessment.mechanism and a.scope == assessment.mechanism_scope
                    for ref in a.supporting_evidence_refs}
    supports = [e for e in assessment.supporting_evidence if e.evidence_id in primary_refs and _qualified(e)]
    conflicts = list(assessment.conflicting_evidence)
    # A disputed association also blocks an otherwise explicit mechanism.
    conflicts.extend(e for e in matrix.contextual_evidence
                     if disputed_validity(e) and e.applicability in {"EXACT", "MAPPED"}
                     and e.allelic_requirement == identity.allelic_requirement)
    conflicts = list({e.evidence_id: e for e in conflicts}.values())
    report["conflicting_evidence"] = [e.dict() for e in conflicts]
    fields = dict(unknown)
    if supports:
        fields.update(molecular_mechanism=_MECHANISMS.get(assessment.mechanism, "UNKNOWN"),
                      confidence=assessment.mechanism_confidence, scope=assessment.mechanism_scope)
        if conflicts or assessment.gene_disease_association_status == "DISPUTED":
            fields["confidence"] = "DISPUTED"
            if len({a.mechanism for a in assessment.assertions if a.scope == "DISEASE_SPECIFIC"}) > 1:
                fields["molecular_mechanism"] = "UNKNOWN"
        if assessment.mechanism_scope == "GENE_LEVEL":
            warnings.append("Il meccanismo disponibile riguarda il gene; non stabilisce il meccanismo della malattia selezionata.")
    else:
        warnings.append("Nessuna asserzione del meccanismo qualificata per il contesto selezionato nelle fonti locali.")
        if conflicts:
            fields.update(confidence="DISPUTED", scope=assessment.mechanism_scope)
    validity_conflicts = [e for e in conflicts if disputed_validity(e)]
    if validity_conflicts:
        warnings.append("Associazione gene–malattia contestata o confutata nelle fonti locali: "
                        + "; ".join(f"{e.source} {e.source_record_id}: {e.source_classification}" for e in validity_conflicts)
                        + ". PVS1 richiede revisione.")
    elif conflicts or assessment.gene_disease_association_status == "DISPUTED":
        warnings.append("Evidenze del meccanismo o dell'associazione in conflitto: PVS1 richiede revisione.")
    if supports or conflicts:
        citations = ["HELPER mechanism assessment " + json.dumps(
            {"snapshot_id": matrix.snapshot_id, "assessment_version": VERSION, "rules_version": RULES_VERSION,
             "evidence": e.dict()}, ensure_ascii=False, sort_keys=True)
            for e in {e.evidence_id: e for e in (*supports, *conflicts)}.values()]
        fields["source_refs"] = {key: list(citations) for key in ("molecular_mechanism", "confidence", "scope")}
    report["calculator_context"] = {k: v for k, v in fields.items() if k != "source_refs"}
    return fields, report, list(dict.fromkeys(warnings))
