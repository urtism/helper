"""Prepare interpretation identifiers from HELPER's local structured annotations.

No remote lookup, phenotype inference or VCEP selection occurs here.
"""
import re

from helper_next.core.acmg_client import digest
from helper_variants import gene_phenotype


def identifier(curie, label=""):
    if not isinstance(curie, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*:[^\s:]+", curie):
        return None
    namespace = curie.split(":", 1)[0].upper()
    value = {"namespace": namespace, "identifier": curie}
    if label:
        value["label"] = label
    return value


def annotation_genes(annotation):
    fields = annotation.get("metadata", {}).get("fields", {})
    found = {}
    hgnc = str(fields.get("HGNC_ID") or fields.get("HGNC") or "").strip()
    if re.fullmatch(r"(?:HGNC:)?\d+", hgnc, re.I):
        found["HGNC:" + hgnc.split(":")[-1]] = "VCF HGNC annotation"
    for key in ("Gene", "Gene_ID", "Ensembl_Gene_ID"):
        value = str(fields.get(key) or "").strip()
        if re.fullmatch(r"ENSG\d+(?:\.\d+)?", value, re.I):
            found["ENSEMBL:" + value.split(".")[0]] = "VCF " + key
    return found


def inheritance_modes(association):
    # Vocabulary normalization only; no inference from genotype or gene symbol.
    aliases = {"ad": "AUTOSOMAL_DOMINANT", "autosomal dominant": "AUTOSOMAL_DOMINANT",
               "ar": "AUTOSOMAL_RECESSIVE", "autosomal recessive": "AUTOSOMAL_RECESSIVE",
               "x linked": "X_LINKED", "x linked dominant": "X_LINKED", "x linked recessive": "X_LINKED",
               "y linked": "Y_LINKED", "mitochondrial": "MITOCHONDRIAL"}
    modes = set()
    for assertion in association.get("assertions", []):
        normalized = str(assertion.get("inheritance") or "").strip().lower().replace("_", " ").replace("-", " ")
        mode = aliases.get(normalized)
        if mode:
            modes.add(mode)
    return sorted(modes)


def build(detail):
    """Immutable, source-linked choices for each exact transcript annotation."""
    annotations = []
    lookups = {}
    for annotation in detail.get("annotations", []):
        symbol = str(annotation.get("gene") or "").strip()
        raw_genes = annotation_genes(annotation)
        raw_hgnc = [key for key in raw_genes if key.startswith("HGNC:")]
        lookup_key = (symbol, raw_hgnc[0] if len(raw_hgnc) == 1 else "")
        if lookup_key not in lookups:
            lookups[lookup_key] = gene_phenotype.query_gene(*lookup_key)
        knowledge = lookups[lookup_key]
        cache = knowledge.get("cache", {})
        cache_genes = {g for g in knowledge.get("gene_identifiers", []) if identifier(g)}
        # The association's gene identifier must be the one actually curated.
        genes = set(raw_hgnc) if raw_hgnc else cache_genes
        if not genes:
            genes = set(raw_genes)
        gene = identifier(next(iter(genes)), symbol) if len(genes) == 1 else None
        choices = []
        if gene:
            for association in knowledge.get("associations", []):
                assertions = [a for a in association.get("assertions", []) if a.get("gene_id") == gene["identifier"]]
                disease = identifier(association.get("disease_id"), association.get("disease", ""))
                if not assertions or disease is None:
                    continue
                selected = dict(association, assertions=assertions)
                context = {"gene": gene, "disease": disease, "inheritance_modes": inheritance_modes(selected)}
                origin = {
                    "source": "HELPER local gene-disease cache", "source_version": cache.get("updated_at"),
                    "cache_schema_version": cache.get("schema_version"), "stale": cache.get("stale", False),
                    "gene_mapping": raw_genes.get(gene["identifier"], "Curated gene_curie matched to the VCF gene symbol"),
                    "assertions": assertions, "original_disease_ids": association.get("original_disease_ids", []),
                    "classification": association.get("strongest_classification", ""),
                }
                choice = {"id": "context-" + digest({"annotation_id": annotation.get("id"), "gene": gene["identifier"], "disease": disease["identifier"]})["value"][:24],
                          "context": context, "origin": origin}
                choice["fingerprint"] = digest(choice)
                choices.append(choice)
        conflict = bool(raw_hgnc and cache_genes and not set(raw_hgnc).intersection(cache_genes))
        status = "READY" if choices else "CONFLICTING_GENE_ID" if conflict else "AMBIGUOUS_GENE" if len(genes) > 1 else "MISSING_GENE_ID" if gene is None else "MISSING_DISEASE_CONTEXT"
        annotations.append({"annotation_id": annotation.get("id"), "transcript": annotation.get("transcript", ""),
                            "gene_symbol": symbol, "gene": gene, "gene_candidates": sorted(genes),
                            "status": status, "contexts": choices, "cache_status": cache.get("status", "missing"),
                            "cache_refreshing": cache.get("refreshing", False)})
    return {"schema_version": "helper-interpretation-context-v1", "annotations": annotations,
            "limitations": ["Identifiers and associations are imported from HELPER sources; they do not establish clinical approval",
                            "Multiple diseases require explicit context selection; no disease is inferred from the gene alone"]}


def select(catalog, annotation_id, transcript, context_id="", fingerprint="", inheritance=""):
    candidates = [c for a in catalog["annotations"]
                  if a["transcript"] == transcript and (annotation_id is None or a["annotation_id"] == annotation_id)
                  for c in a["contexts"] if not context_id or c["id"] == context_id]
    if len(candidates) != 1:
        raise ValueError("Select an available HELPER gene-disease context; missing identifiers require synchronization of HELPER knowledge sources")
    candidate = candidates[0]
    if fingerprint and candidate["fingerprint"]["value"] != fingerprint:
        raise ValueError("HELPER context changed after preview; reload the structured context")
    context = dict(candidate["context"])
    modes = context["inheritance_modes"]
    if inheritance:
        if inheritance not in modes:
            raise ValueError("Selected inheritance is not recorded for this HELPER gene-disease association")
        context["inheritance_modes"] = [inheritance]
    elif len(modes) > 1:
        context["inheritance_modes"] = []
    return context, candidate
