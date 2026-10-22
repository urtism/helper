"""Read-only, keyset-paginated queries for a run-local variant database."""
import base64
import binascii
from collections import OrderedDict
import json
import os
import re
import threading

from helper_prioritization import RULESET_VERSION, score_variant
from helper_variants import gene_phenotype, gnomad_frequency, store


DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500
DEFAULT_FILTER_STATUSES = (
    "LOW_DEPTH", "LOW_VAF", "LOW_ALTERNATE_DEPTH", "LOW_QUAL", "LOW_MAPQ",
    "LOW_CALLER_SUPP", "LOW_GQ", "LOW_QD", "STRAND_BIAS", "READ_POSITION_BIAS",
    "GT_CONFLICT", "LOW_CALLER_SUPPORT",
)
FILTER_STATUS_ALIASES = {
    "LOW_DEPTH": ("LOW_DEPTH", "LOW_DP"),
    "LOW_ALTERNATE_DEPTH": ("LOW_ALTERNATE_DEPTH", "LOW_AD"),
    "LOW_QUAL": ("LOW_QUAL", "LOWQUAL"),
}
_PRIORITY_ORDER_CACHE = OrderedDict()
_PRIORITY_ORDER_CACHE_LOCK = threading.Lock()
_PRIORITY_ORDER_CACHE_SIZE = 4


class VariantQueryError(ValueError):
    pass


def run_summary(database):
    with store.connect(database) as db:
        run = db.execute("SELECT * FROM runs ORDER BY id LIMIT 1").fetchone()
        if run is None:
            raise VariantQueryError("variant database has no run record")
        sources = [dict(row) for row in db.execute(
            "SELECT relative_path, stage, status, records_processed, error, updated_at "
            "FROM index_sources WHERE run_id = ? ORDER BY relative_path", (run["id"],)
        )]
        counts = db.execute(
            "SELECT COUNT(DISTINCT a.sample_id) AS samples, "
            "COUNT(DISTINCT c.variant_id) AS variants, COUNT(c.id) AS calls "
            "FROM analyses a LEFT JOIN calls c ON c.analysis_id = a.id WHERE a.run_id = ?",
            (run["id"],),
        ).fetchone()
        releases = db.execute(
            "SELECT COUNT(*) FROM annotation_releases WHERE reference_build = ?",
            (run["reference_build"],),
        ).fetchone()[0]
        sample_names = [row[0] for row in db.execute(
            "SELECT DISTINCT s.display_name FROM samples s JOIN analyses a ON a.sample_id = s.id "
            "WHERE a.run_id = ? ORDER BY s.display_name COLLATE NOCASE", (run["id"],)
        )]
        metadata = _json_value(run["metadata_json"])
        public_metadata = {key: metadata.get(key) for key in (
            "run_id", "history_id", "reference_fasta", "reference_validated"
        ) if key in metadata}
        return {
            "run_key": run["run_key"], "reference_build": run["reference_build"],
            "source_path": run["source_path"], "imported_at": run["imported_at"],
            "metadata": public_metadata,
            "sample_count": counts["samples"], "variant_count": counts["variants"],
            "call_count": counts["calls"], "annotation_release_count": releases,
            "sample_names": sample_names,
            "sources": sources,
        }


def list_samples(database):
    with store.connect(database) as db:
        rows = db.execute(
            "SELECT s.id AS sample_id, s.sample_key, s.display_name, s.specimen_type, "
            "s.metadata_json, a.id AS analysis_id, a.analysis_key, a.role, a.qc_json, "
            "COUNT(DISTINCT c.variant_id) AS variant_count, COUNT(DISTINCT c.id) AS call_count, "
            "(SELECT COUNT(DISTINCT annotated_calls.variant_id) FROM calls annotated_calls "
            " JOIN annotations an ON an.variant_id = annotated_calls.variant_id "
            " WHERE annotated_calls.analysis_id = a.id) AS annotated_variant_count "
            "FROM samples s JOIN analyses a ON a.sample_id = s.id "
            "LEFT JOIN calls c ON c.analysis_id = a.id "
            "GROUP BY s.id, a.id ORDER BY s.display_name COLLATE NOCASE, s.id, a.id"
        ).fetchall()
        return [{
            "sample_id": row["sample_id"], "sample_key": row["sample_key"],
            "display_name": row["display_name"], "specimen_type": row["specimen_type"],
            "metadata": _json_value(row["metadata_json"]),
            "analysis_id": row["analysis_id"], "analysis_key": row["analysis_key"],
            "role": row["role"], "qc": _json_value(row["qc_json"]),
            "variant_count": row["variant_count"], "call_count": row["call_count"],
            "annotated_variant_count": row["annotated_variant_count"],
        } for row in rows]


def list_variants(database, sample_id, cursor=None, limit=DEFAULT_PAGE_SIZE, gene="",
                  variant_id=None,
                  genes="", max_af=None, population_frequency="MAX_AF",
                  include_missing_af=True, consequences="",
                  clinical_significances="", inheritance_candidates="", family_evidence="",
                  family_pattern="",
                  priority_classes="", min_priority=None, max_priority=None,
                  filter_mode="all", filter_statuses="", zygosities="", min_depth=None,
                  min_vaf=None, min_quality=None, possible_compound=False,
                  sort_by="priority", sort_direction=""):
    limit = _page_size(limit)
    gene = str(gene or "").strip()
    if len(gene) > 100:
        raise VariantQueryError("gene filter must be at most 100 characters")
    filters = _variant_filters(
        gene=gene, genes=genes, max_af=max_af, population_frequency=population_frequency,
        include_missing_af=include_missing_af,
        consequences=consequences, clinical_significances=clinical_significances,
        inheritance_candidates=inheritance_candidates, family_evidence=family_evidence,
        family_pattern=family_pattern,
        priority_classes=priority_classes, min_priority=min_priority,
        max_priority=max_priority,
        filter_mode=filter_mode,
        filter_statuses=filter_statuses, zygosities=zygosities, min_depth=min_depth,
        min_vaf=min_vaf, min_quality=min_quality, possible_compound=possible_compound,
    )
    sort_by, sort_direction = _variant_sort(sort_by, sort_direction)
    if variant_id not in (None, ""):
        try:
            variant_id = int(variant_id)
        except (TypeError, ValueError):
            raise VariantQueryError("variant id must be an integer")
        if variant_id < 1:
            raise VariantQueryError("variant id must be positive")
    else:
        variant_id = None
    signature = json.dumps(
        {
            "filters": filters, "variant_id": variant_id,
            "sort_by": sort_by, "sort_direction": sort_direction,
        },
        sort_keys=True, separators=(",", ":"),
    )
    if sort_by:
        page_offset = _decode_offset_cursor(cursor, int(sample_id), signature) if cursor else 0
        after_variant_id = 0
    else:
        page_offset = 0
        after_variant_id = _decode_cursor(cursor, int(sample_id), signature) if cursor else 0
    computed_priority = sort_by == "priority" or bool(
        filters["priority_classes"] or filters["min_priority"] is not None
        or filters["max_priority"] is not None
    )
    priority_cache_key = _priority_order_cache_key(
        database, sample_id, signature
    ) if computed_priority else None
    cached_priority_ids = (
        _priority_order_cache_get(priority_cache_key) if priority_cache_key else None
    )
    cached_page_ids = (
        cached_priority_ids[page_offset:page_offset + limit]
        if cached_priority_ids is not None else None
    )

    annotation_clauses = []
    annotation_parameters = []
    requires_annotation = False
    if filters["genes"]:
        annotation_clauses.append(
            "selected.gene COLLATE NOCASE IN (SELECT value FROM json_each(?))"
        )
        annotation_parameters.append(json.dumps(filters["genes"]))
        requires_annotation = True
    if filters["consequences"]:
        matches = []
        for consequence in filters["consequences"]:
            matches.append("instr('&' || lower(selected.consequence) || '&', ?) > 0")
            annotation_parameters.append("&{}&".format(consequence.lower()))
        annotation_clauses.append("(" + " OR ".join(matches) + ")")
        requires_annotation = True
    if filters["clinical_significances"]:
        matches = []
        for significance in filters["clinical_significances"]:
            if significance == "__not_reported__":
                matches.append(
                    "(trim(COALESCE(selected.clinical_significance, '')) IN ('', '.') "
                    "AND NOT EXISTS (SELECT 1 FROM annotations clinical_reported "
                    "WHERE clinical_reported.variant_id = selected.variant_id "
                    "AND trim(COALESCE(clinical_reported.clinical_significance, '')) NOT IN ('', '.')))"
                )
                continue
            matches.append(
                "instr('&' || replace(replace(lower(selected.clinical_significance), ',', '&'), '|', '&') || '&', ?) > 0"
            )
            annotation_parameters.append("&{}&".format(significance.lower()))
        annotation_clauses.append("(" + " OR ".join(matches) + ")")
        if "__not_reported__" not in filters["clinical_significances"]:
            requires_annotation = True
    annotation_filter = "".join(" AND " + clause for clause in annotation_clauses)
    result_clauses = ["an.id IS NOT NULL"] if requires_annotation else []
    if "__not_reported__" in filters["clinical_significances"] and not requires_annotation:
        result_clauses.append(
            "(an.id IS NOT NULL OR NOT EXISTS (SELECT 1 FROM annotations clinical_any "
            "WHERE clinical_any.variant_id = v.id "
            "AND trim(COALESCE(clinical_any.clinical_significance, '')) NOT IN ('', '.')))"
        )
    result_parameters = []
    if variant_id is not None:
        result_clauses.append("v.id = ?")
        result_parameters.append(variant_id)
    if filters["max_af"] is not None:
        if filters["population_frequency"] == "MAX_AF":
            expression = "an.population_af"
            expression_parameters = []
        else:
            expression = "CAST(NULLIF(NULLIF(json_extract(an.metadata_json, ?), ''), '.') AS REAL)"
            expression_parameters = ["$.fields.{}".format(filters["population_frequency"])]
        if filters["include_missing_af"]:
            result_clauses.append("({0} IS NULL OR {0} <= ?)".format(expression))
            result_parameters.extend(expression_parameters * 2)
        else:
            result_clauses.append("({} <= ?)".format(expression))
            result_parameters.extend(expression_parameters)
        result_parameters.append(filters["max_af"])
    if cached_page_ids is not None:
        if cached_page_ids:
            result_clauses.append("v.id IN (SELECT value FROM json_each(?))")
            result_parameters.append(json.dumps(cached_page_ids))
        else:
            result_clauses.append("0")
    inheritance_clauses = []
    for candidate in filters["inheritance_candidates"]:
        if candidate == "compound":
            inheritance_clauses.append(
                "(an.gene != '' AND EXISTS (SELECT 1 FROM calls compound_current "
                "JOIN analyses compound_current_analysis ON compound_current_analysis.id = compound_current.analysis_id "
                "WHERE compound_current.variant_id = v.id AND compound_current_analysis.sample_id = a.sample_id "
                "AND lower(compound_current.zygosity) = 'het') "
                "AND an.gene COLLATE NOCASE IN (SELECT compound_annotation.gene "
                "FROM calls compound_call JOIN analyses compound_analysis "
                "ON compound_analysis.id = compound_call.analysis_id "
                "JOIN annotations compound_annotation ON compound_annotation.variant_id = compound_call.variant_id "
                "WHERE compound_analysis.sample_id = ? AND lower(compound_call.zygosity) = 'het' "
                "AND compound_annotation.gene != '' GROUP BY compound_annotation.gene COLLATE NOCASE "
                "HAVING COUNT(DISTINCT compound_call.variant_id) >= 2))"
            )
            result_parameters.append(int(sample_id))
        elif candidate in ("dominant", "recessive"):
            zygosity = "het" if candidate == "dominant" else "hom_alt"
            inheritance_clauses.append(
                "EXISTS (SELECT 1 FROM calls inheritance_call JOIN analyses inheritance_analysis "
                "ON inheritance_analysis.id = inheritance_call.analysis_id "
                "WHERE inheritance_call.variant_id = v.id AND inheritance_analysis.sample_id = a.sample_id "
                "AND lower(inheritance_call.zygosity) = ?)"
            )
            result_parameters.append(zygosity)
        elif candidate in ("x_linked", "y_linked"):
            chromosome = "X" if candidate == "x_linked" else "Y"
            inheritance_clauses.append("replace(upper(v.chromosome), 'CHR', '') = ?")
            result_parameters.append(chromosome)
        elif candidate == "mitochondrial":
            inheritance_clauses.append(
                "replace(upper(v.chromosome), 'CHR', '') IN ('M', 'MT')"
            )
    if inheritance_clauses:
        result_clauses.append("(" + " OR ".join(inheritance_clauses) + ")")
    if filters["family_evidence"]:
        father_id, mother_id = _family_parent_ids(database, sample_id)
        family_clauses = []
        family_parameters = []
        if father_id is not None and mother_id is not None:
            for evidence in filters["family_evidence"]:
                clause, parameters = _family_evidence_clause(
                    evidence, int(sample_id), father_id, mother_id
                )
                family_clauses.append(clause)
                family_parameters.extend(parameters)
        result_clauses.append(
            "(" + " OR ".join(family_clauses) + ")" if family_clauses else "0"
        )
        result_parameters.extend(family_parameters)
    if filters["family_pattern"]:
        available_members = _family_member_ids(database, sample_id)
        requested_members = {member_id for member_id, _ in filters["family_pattern"]}
        if not requested_members.issubset(available_members):
            raise VariantQueryError("family pattern contains a sample outside the current family")
        pattern_clauses = []
        for index, (member_id, state) in enumerate(filters["family_pattern"]):
            carried = _family_call_exists("family_pattern_{}".format(index), "v.id")
            pattern_clauses.append(carried if state == "present" else "NOT " + carried)
            result_parameters.append(member_id)
        result_clauses.append("(" + " AND ".join(pattern_clauses) + ")")
    result_filter = "".join(" AND " + clause for clause in result_clauses)

    call_clauses = []
    call_parameters = []
    pass_expression = "upper(trim(COALESCE(filtered.filter_status, ''))) NOT IN ('', '.', 'PASS')"
    if filters["filter_mode"] == "pass":
        call_clauses.append(
            "NOT EXISTS (SELECT 1 FROM calls filtered JOIN analyses filtered_analysis "
            "ON filtered_analysis.id = filtered.analysis_id WHERE filtered.variant_id = v.id "
            "AND filtered_analysis.sample_id = a.sample_id AND " + pass_expression + ")"
        )
    elif filters["filter_mode"] in {"selected", "exclude"}:
        status_matches = []
        for status in filters["filter_statuses"]:
            aliases = FILTER_STATUS_ALIASES.get(status.upper(), (status,))
            for alias in aliases:
                status_matches.append(
                    "instr(',' || replace(upper(filtered.filter_status), ';', ',') || ',', ?) > 0"
                )
                call_parameters.append(",{},".format(alias.upper()))
        existence = "EXISTS" if filters["filter_mode"] == "selected" else "NOT EXISTS"
        call_clauses.append(
            existence + " (SELECT 1 FROM calls filtered JOIN analyses filtered_analysis "
            "ON filtered_analysis.id = filtered.analysis_id WHERE filtered.variant_id = v.id "
            "AND filtered_analysis.sample_id = a.sample_id AND (" + " OR ".join(status_matches) + "))"
        )
    if filters["zygosities"]:
        placeholders = ",".join("?" for _ in filters["zygosities"])
        call_clauses.append(
            "EXISTS (SELECT 1 FROM calls zygosity_call JOIN analyses zygosity_analysis "
            "ON zygosity_analysis.id = zygosity_call.analysis_id "
            "WHERE zygosity_call.variant_id = v.id AND zygosity_analysis.sample_id = a.sample_id "
            "AND lower(zygosity_call.zygosity) IN ({}))".format(placeholders)
        )
        call_parameters.extend(filters["zygosities"])
    call_filter = "".join(" AND " + clause for clause in call_clauses)

    having_clauses = []
    having_parameters = []
    for key, column in (("min_depth", "c.depth"), ("min_vaf", "c.allele_fraction"),
                        ("min_quality", "c.quality")):
        if filters[key] is not None:
            having_clauses.append("MAX({}) >= ?".format(column))
            having_parameters.append(filters[key])
    having_filter = " HAVING " + " AND ".join(having_clauses) if having_clauses else ""
    variant_cursor_filter = "" if sort_by or computed_priority else " AND v.id > ?"
    order_by = _variant_order(sort_by, sort_direction)
    pagination = "" if computed_priority else " LIMIT ? OFFSET ?" if sort_by else " LIMIT ?"
    cursor_parameters = [] if sort_by or computed_priority else [after_variant_id]
    pagination_parameters = [] if computed_priority else (
        [limit + 1, page_offset] if sort_by else [limit + 1]
    )
    parameters = (annotation_parameters + [int(sample_id)] + cursor_parameters
                  + result_parameters + call_parameters + having_parameters
                  + pagination_parameters)
    with store.connect(database) as db:
        _require_sample(db, sample_id)
        rows = db.execute(
            "SELECT v.id AS variant_id, v.reference_build, v.chromosome, v.position, v.reference, "
            "v.alternate, v.variant_type, GROUP_CONCAT(DISTINCT NULLIF(c.caller, '')) AS callers, "
            "GROUP_CONCAT(DISTINCT NULLIF(c.genotype, '')) AS genotypes, MAX(c.depth) AS depth, "
            "GROUP_CONCAT(DISTINCT NULLIF(c.zygosity, '')) AS zygosities, "
            "MAX(c.alternate_depth) AS alternate_depth, MAX(c.allele_fraction) AS allele_fraction, "
            "MAX(c.genotype_quality) AS genotype_quality, MAX(c.quality) AS quality, "
            "GROUP_CONCAT(DISTINCT NULLIF(c.filter_status, '')) AS filter_status, "
            "an.gene, an.transcript, an.consequence, an.impact, an.hgvsc, an.hgvsp, "
            "an.clinical_significance, an.population_af, an.canonical, an.metadata_json "
            "FROM variants v JOIN calls c ON c.variant_id = v.id "
            "JOIN analyses a ON a.id = c.analysis_id "
            "LEFT JOIN annotations an ON an.id = ("
            "  SELECT selected.id FROM annotations selected WHERE selected.variant_id = v.id "
            + annotation_filter +
            "  ORDER BY selected.canonical DESC, "
            "  CASE selected.impact WHEN 'HIGH' THEN 0 WHEN 'MODERATE' THEN 1 "
            "       WHEN 'LOW' THEN 2 WHEN 'MODIFIER' THEN 3 ELSE 4 END, "
            "  selected.release_id DESC, selected.id LIMIT 1"
            ") WHERE a.sample_id = ?" + variant_cursor_filter + " " + result_filter + call_filter +
            " GROUP BY v.id" + having_filter + " ORDER BY " + order_by + pagination,
            parameters,
        ).fetchall()
        score_rows = rows if computed_priority else rows[:limit]
        gene_context = gene_phenotype.priority_contexts(row["gene"] for row in score_rows)
        frequency_contexts = gnomad_frequency.cached_contexts((
            (
                row["reference_build"], row["chromosome"], row["position"],
                row["reference"], row["alternate"],
            )
            for row in score_rows
        ))
        compound_genes = _possible_compound_genes(db, sample_id)
        parental_evidence = _parental_evidence(
            database, db, sample_id, [row["variant_id"] for row in score_rows]
        )
        scored_items = [
            _compact_variant(
                row,
                gene_context.get(str(row["gene"] or "").strip().upper(), {}),
                str(row["gene"] or "").strip().upper() in compound_genes
                and _compound_eligible(row),
                parental_evidence.get(row["variant_id"], {}),
                frequency_contexts[index],
            )
            for index, row in enumerate(score_rows)
        ]
        if cached_priority_ids is not None:
            position = {variant_id: index for index, variant_id in enumerate(cached_page_ids)}
            items = sorted(scored_items, key=lambda item: position[item["variant_id"]])
            has_more = len(cached_priority_ids) > page_offset + limit
        elif computed_priority:
            scored_items = _filter_priority(scored_items, filters)
            if sort_by == "priority":
                scored_items = _sort_priority(scored_items, sort_direction)
            _priority_order_cache_put(
                priority_cache_key, [item["variant_id"] for item in scored_items]
            )
            has_more = len(scored_items) > page_offset + limit
            items = scored_items[page_offset:page_offset + limit]
        else:
            has_more = len(rows) > limit
            items = scored_items
        if has_more and (sort_by or computed_priority):
            next_cursor = _encode_offset_cursor(
                int(sample_id), page_offset + limit, signature
            )
        elif has_more:
            next_cursor = _encode_cursor(int(sample_id), items[-1]["variant_id"], signature)
        else:
            next_cursor = None
        return {
            "items": items, "next_cursor": next_cursor, "limit": limit,
            "sort_by": sort_by, "sort_direction": sort_direction,
        }


def variant_filter_options(database, sample_id):
    """Return compact, data-driven choices for the sample filter drawer."""
    with store.connect(database) as db:
        _require_sample(db, sample_id)
        consequences = set()
        for row in db.execute(
            "SELECT DISTINCT an.consequence FROM annotations an JOIN calls c ON c.variant_id = an.variant_id "
            "JOIN analyses a ON a.id = c.analysis_id WHERE a.sample_id = ? AND an.consequence != ''",
            (int(sample_id),),
        ):
            consequences.update(part for part in row[0].split("&") if part)
        clinical_significances = set()
        for row in db.execute(
            "SELECT DISTINCT an.clinical_significance FROM annotations an "
            "JOIN calls c ON c.variant_id = an.variant_id JOIN analyses a ON a.id = c.analysis_id "
            "WHERE a.sample_id = ? AND an.clinical_significance != ''", (int(sample_id),),
        ):
            clinical_significances.update(
                part.strip().lower() for part in re.split(r"[&,|]", row[0]) if part.strip()
            )
        population_frequencies = {"MAX_AF"}
        for row in db.execute(
            "SELECT DISTINCT fields.key FROM annotations an "
            "JOIN calls c ON c.variant_id = an.variant_id JOIN analyses a ON a.id = c.analysis_id "
            "JOIN json_each(an.metadata_json, '$.fields') fields "
            "WHERE a.sample_id = ? AND (upper(fields.key) = 'AF' OR upper(fields.key) LIKE '%_AF')",
            (int(sample_id),),
        ):
            population_frequencies.add(row[0])
        statuses = set(DEFAULT_FILTER_STATUSES)
        zygosities = [row[0] for row in db.execute(
            "SELECT DISTINCT lower(c.zygosity) FROM calls c JOIN analyses a ON a.id = c.analysis_id "
            "WHERE a.sample_id = ? AND c.zygosity != '' ORDER BY c.zygosity", (int(sample_id),),
        )]
        standard_clinical = [
            "pathogenic", "likely_pathogenic", "uncertain_significance",
            "likely_benign", "benign",
        ]
        clinical_order = {value: position for position, value in enumerate(standard_clinical)}
        clinical_significances.update(standard_clinical)
        return {"consequences": sorted(consequences),
                "clinical_significances": sorted(
                    clinical_significances,
                    key=lambda item: (clinical_order.get(item.casefold(), len(standard_clinical)), item.casefold()),
                ) + ["__not_reported__"],
                "population_frequencies": sorted(
                    population_frequencies,
                    key=lambda item: (0 if item == "MAX_AF" else 1 if item.upper() == "AF" else 2, item.casefold()),
                ),
                "filter_statuses": sorted(
                    statuses,
                    key=lambda item: (
                        DEFAULT_FILTER_STATUSES.index(item)
                        if item in DEFAULT_FILTER_STATUSES else len(DEFAULT_FILTER_STATUSES),
                        item.casefold(),
                    ),
                ), "zygosities": zygosities}


def variant_detail(database, sample_id, variant_id):
    with store.connect(database) as db:
        _require_sample(db, sample_id)
        variant = db.execute(
            "SELECT v.* FROM variants v WHERE v.id = ? AND EXISTS ("
            "SELECT 1 FROM calls c JOIN analyses a ON a.id = c.analysis_id "
            "WHERE c.variant_id = v.id AND a.sample_id = ?)",
            (int(variant_id), int(sample_id)),
        ).fetchone()
        if variant is None:
            return None
        calls = [dict(row) for row in db.execute(
            "SELECT c.id, c.caller, c.genotype, c.phased, c.zygosity, c.depth, "
            "c.reference_depth, c.alternate_depth, c.allele_fraction, c.genotype_quality, "
            "c.quality, c.filter_status, c.metadata_json "
            "FROM calls c JOIN analyses a ON a.id = c.analysis_id "
            "WHERE c.variant_id = ? AND a.sample_id = ? ORDER BY c.id",
            (int(variant_id), int(sample_id)),
        )]
        annotations = [dict(row) for row in db.execute(
            "SELECT an.id, ar.release_key, ar.annotator, ar.annotator_version, ar.created_at, "
            "an.allele, an.gene, an.transcript, an.consequence, an.impact, an.hgvsc, an.hgvsp, "
            "an.clinical_significance, an.population_af, an.canonical, an.metadata_json, ar.resources_json "
            "FROM annotations an JOIN annotation_releases ar ON ar.id = an.release_id "
            "WHERE an.variant_id = ? ORDER BY ar.id DESC, an.canonical DESC, an.id",
            (int(variant_id),),
        )]
        result = dict(variant)
        result["metadata"] = _json_value(result.pop("metadata_json"))
        for call in calls:
            call["phased"] = bool(call["phased"])
            call["metadata"] = _json_value(call.pop("metadata_json"))
        for annotation in annotations:
            annotation["canonical"] = bool(annotation["canonical"])
            annotation["release_resources"] = _json_value(annotation.pop("resources_json"))
            annotation["metadata"] = _json_value(annotation.pop("metadata_json"))
            annotation["exon_intron"] = _annotation_exon_intron(
                annotation["metadata"], annotation["consequence"]
            )
        result.update({
            "calls": calls,
            "annotations": annotations,
            "database_ids": _database_ids(result["metadata"], annotations),
        })
        result["clinvar_evidence"] = _clinvar_evidence(
            result["metadata"], annotations, result["database_ids"].get("clinvar", [])
        )
        result["gnomad_frequency"] = gnomad_frequency.cached_variant(
            result["reference_build"], result["chromosome"], result["position"],
            result["reference"], result["alternate"],
        )
        return result


def variant_carriers(database, reference_build, chromosome, position, reference, alternate):
    """Return samples carrying one exact normalized allele in a run store."""
    with store.connect(database) as db:
        rows = db.execute(
            "SELECT v.id AS variant_id, s.id AS sample_id, s.sample_key, s.display_name, s.specimen_type, "
            "s.metadata_json, GROUP_CONCAT(DISTINCT NULLIF(a.role, '')) AS roles, "
            "GROUP_CONCAT(DISTINCT NULLIF(c.genotype, '')) AS genotypes, "
            "MAX(c.depth) AS depth, MAX(c.allele_fraction) AS allele_fraction "
            "FROM variants v JOIN calls c ON c.variant_id = v.id "
            "JOIN analyses a ON a.id = c.analysis_id JOIN samples s ON s.id = a.sample_id "
            "WHERE v.reference_build = ? AND v.chromosome = ? AND v.position = ? "
            "AND v.reference = ? AND v.alternate = ? "
            "GROUP BY s.id ORDER BY s.display_name COLLATE NOCASE, s.id",
            (
                str(reference_build), str(chromosome), int(position),
                str(reference).upper(), str(alternate).upper(),
            ),
        ).fetchall()
        return [{
            "variant_id": row["variant_id"],
            "sample_id": row["sample_id"], "sample_key": row["sample_key"],
            "display_name": row["display_name"], "specimen_type": row["specimen_type"],
            "metadata": _json_value(row["metadata_json"]), "roles": _csv(row["roles"]),
            "genotypes": _csv(row["genotypes"]), "depth": row["depth"],
            "allele_fraction": row["allele_fraction"],
        } for row in rows]


def _compact_variant(row, gene_context=None, compound_candidate=False, family_context=None,
                     population_context=None):
    metadata = _json_value(row["metadata_json"])
    fields = (metadata or {}).get("fields") or {}
    zygosities = _csv(row["zygosities"])
    review_values = _metadata_values(fields, "CLNREVSTAT", "ClinVar_CLNREVSTAT")
    conflict_values = _metadata_values(fields, "CLNSIGCONF", "ClinVar_CLNSIGCONF")
    population_context = dict(population_context or {})
    population_values = [row["population_af"], population_context.get("population_af")]
    population_af = max(
        (float(value) for value in population_values if value is not None), default=None
    )
    item = {
        "variant_id": row["variant_id"], "reference_build": row["reference_build"],
        "chromosome": row["chromosome"], "position": row["position"],
        "reference": row["reference"], "alternate": row["alternate"],
        "variant_type": row["variant_type"], "callers": _csv(row["callers"]),
        "genotypes": _csv(row["genotypes"]), "zygosities": zygosities,
        "depth": row["depth"],
        "alternate_depth": row["alternate_depth"], "allele_fraction": row["allele_fraction"],
        "genotype_quality": row["genotype_quality"], "quality": row["quality"],
        "filter_status": _csv(row["filter_status"]), "gene": row["gene"] or "",
        "transcript": row["transcript"] or "", "consequence": row["consequence"] or "",
        "exon_intron": _annotation_exon_intron(metadata, row["consequence"]),
        "impact": row["impact"] or "", "hgvsc": row["hgvsc"] or "",
        "hgvsp": row["hgvsp"] or "", "clinical_significance": row["clinical_significance"] or "",
        "population_af": population_af, "canonical": bool(row["canonical"] or 0),
        "population_frequency_status": population_context.get("population_frequency_status", ""),
        "population_frequency_source": population_context.get("population_frequency_source", ""),
    }
    context = dict(gene_context or {})
    family_context = dict(family_context or {})
    item["priority"] = score_variant({
        "chromosome": row["chromosome"],
        "population_af": population_af,
        "consequence": row["consequence"] or "",
        "clinical_significance": row["clinical_significance"] or "",
        "clinvar_stars": max(
            [_clinvar_review_stars(review) for review in review_values] or [0]
        ),
        "clinvar_conflict": bool(conflict_values) or any(
            _clinvar_has_conflict_text(value)
            for value in review_values + [row["clinical_significance"] or ""]
        ),
        "clinvar_condition_match": "unknown",
        "prediction_fields": fields,
        "zygosities": zygosities,
        "compound_status": "phase_unknown" if compound_candidate else "",
        "de_novo_status": family_context.get("de_novo_status", ""),
        "filter_status": item["filter_status"],
        "depth": row["depth"],
        "quality": row["quality"],
        **context,
        **population_context,
    })
    return item


def _metadata_values(fields, *names):
    wanted = {_clinvar_field_key(name) for name in names}
    return [
        value for key, raw in (fields or {}).items()
        if _clinvar_field_key(key) in wanted
        for value in _clinvar_display_values([raw])
    ]


def _possible_compound_genes(db, sample_id):
    rows = db.execute(
        "SELECT upper(an.gene) AS gene FROM calls c "
        "JOIN analyses a ON a.id = c.analysis_id "
        "JOIN annotations an ON an.variant_id = c.variant_id "
        "WHERE a.sample_id = ? AND lower(c.zygosity) IN ('het', 'heterozygous') "
        "AND an.gene != '' AND (an.population_af IS NULL OR an.population_af <= 0.01) "
        "AND lower(an.consequence) NOT IN ('', 'intergenic_variant', 'intron_variant', "
        "'upstream_gene_variant', 'downstream_gene_variant', 'synonymous_variant') "
        "GROUP BY upper(an.gene) "
        "HAVING COUNT(DISTINCT c.variant_id) >= 2",
        (int(sample_id),),
    ).fetchall()
    return {row["gene"] for row in rows if row["gene"]}


def _compound_eligible(row):
    af = row["population_af"]
    if af is not None and float(af) > 0.01:
        return False
    excluded = {
        "", "intergenic_variant", "intron_variant", "upstream_gene_variant",
        "downstream_gene_variant", "synonymous_variant",
    }
    consequences = {
        value.strip().casefold() for value in re.split(r"[&,|]", row["consequence"] or "")
    }
    return bool(consequences - excluded)


def _parental_evidence(database, db, sample_id, variant_ids):
    if not variant_ids:
        return {}
    father_id, mother_id = _family_parent_ids(database, sample_id)
    if father_id is None or mother_id is None:
        return {}
    rows = []
    for offset in range(0, len(variant_ids), 500):
        batch = variant_ids[offset:offset + 500]
        placeholders = ",".join("?" for _ in batch)
        rows.extend(db.execute(
            "SELECT c.variant_id, a.sample_id, c.genotype, c.zygosity FROM calls c "
            "JOIN analyses a ON a.id = c.analysis_id "
            "WHERE a.sample_id IN (?, ?) AND c.variant_id IN ({})".format(placeholders),
            [father_id, mother_id] + list(batch),
        ).fetchall())
    carried = {}
    for row in rows:
        if _call_carries_alternate(row["genotype"], row["zygosity"]):
            carried.setdefault(row["variant_id"], set()).add(row["sample_id"])
    result = {}
    for variant_id in variant_ids:
        parents = carried.get(variant_id, set())
        if not parents:
            result[variant_id] = {
                "de_novo_status": "candidate", "parental_origin": "neither",
            }
        elif parents == {father_id}:
            result[variant_id] = {"parental_origin": "father"}
        elif parents == {mother_id}:
            result[variant_id] = {"parental_origin": "mother"}
        else:
            result[variant_id] = {"parental_origin": "both"}
    return result


def _call_carries_alternate(genotype, zygosity):
    normalized = str(zygosity or "").strip().casefold()
    if normalized in {"het", "heterozygous", "hom_alt", "homozygous", "hemizygous", "hemi"}:
        return True
    alleles = str(genotype or "").replace("|", "/").split("/")
    return any(allele.strip() not in {"", ".", "0"} for allele in alleles)


def _annotation_exon_intron(metadata, consequence=""):
    fields = (metadata or {}).get("fields") or {}
    normalized = {str(key).upper(): value for key, value in fields.items()}
    locations = []
    for key, label in (("EXON", "Exon"), ("INTRON", "Intron")):
        field_value = str(normalized.get(key) or "").strip()
        if field_value and field_value != ".":
            locations.append("{} {}".format(label, field_value))
    if locations:
        return " · ".join(locations)
    rank = str(normalized.get("RANK") or "").strip()
    if not rank or rank == ".":
        return ""
    label = "Intron" if "intron" in str(consequence or "").lower() else "Exon"
    return "{} {}".format(label, rank)


def _database_ids(variant_metadata, annotations):
    """Collect stable public identifiers already present in source annotations."""
    identifiers = {"dbsnp": [], "clinvar": [], "clingen": []}
    seen = {database: set() for database in identifiers}

    def add(database, identifier):
        normalized = str(identifier).strip()
        folded = normalized.casefold()
        if normalized and folded not in seen[database]:
            seen[database].add(folded)
            identifiers[database].append(normalized)

    sources = [("VCF_ID", (variant_metadata or {}).get("vcf_id", ""))]
    sources.extend(
        (str(key), field_value)
        for key, field_value in ((variant_metadata or {}).get("clinvar") or {}).items()
    )
    for annotation in annotations:
        fields = annotation.get("metadata", {}).get("fields", {})
        sources.extend((str(key), field_value) for key, field_value in fields.items())

    for field_name, field_value in sources:
        if field_value in (None, "", "."):
            continue
        key = field_name.upper().replace("-", "_")
        text = str(field_value).replace("%3D", "=")
        is_identifier_field = any(token in key for token in (
            "VCF_ID", "EXISTING_VARIATION", "VAR_SYNONYM", "DBSNP",
            "CLINVAR", "CLNVID", "CLINGEN", "CAID",
        ))
        if not is_identifier_field:
            continue
        for match in re.findall(r"(?i)(?<![A-Z0-9])rs\d+", text):
            add("dbsnp", match.lower())
        for match in re.findall(r"(?i)(?<![A-Z0-9])(?:VCV|RCV|SCV)\d+(?:\.\d+)?", text):
            add("clinvar", match.upper())
        clinvar_numeric_id = (
            "CLNVID" in key or "CLINVARVARIATIONID" in key
            or key in {"CLINVAR", "CLINVAR_ID", "CLINVARID"}
        )
        if clinvar_numeric_id:
            for match in re.findall(r"(?<![A-Z0-9])\d+(?![A-Z0-9])", text, re.IGNORECASE):
                add("clinvar", match)
        for match in re.findall(r"(?i)(?<![A-Z0-9])CA\d+", text):
            add("clingen", match.upper())
    return identifiers


def _clinvar_evidence(variant_metadata, annotations, identifiers):
    fields = []
    fields.extend(((variant_metadata or {}).get("clinvar") or {}).items())
    classifications = []
    for annotation in annotations:
        if annotation.get("clinical_significance") not in (None, "", "."):
            classifications.append(annotation["clinical_significance"])
        fields.extend((annotation.get("metadata", {}).get("fields") or {}).items())
    normalized = {}
    for key, value in fields:
        if value in (None, "", "."):
            continue
        normalized.setdefault(_clinvar_field_key(key), []).append(value)

    def values(*keys):
        raw = []
        for key in keys:
            raw.extend(normalized.get(_clinvar_field_key(key), []))
        return _clinvar_display_values(raw)

    classifications.extend(values(
        "CLNSIG", "CLIN_SIG", "CLINICAL_SIGNIFICANCE", "ClinVar_CLNSIG"
    ))
    classifications = _clinvar_display_values(classifications)
    review_values = values("CLNREVSTAT", "ClinVar_CLNREVSTAT")
    review_statuses = [
        {"label": value, "stars": _clinvar_review_stars(value)}
        for value in review_values
    ]
    conflicts = values("CLNSIGCONF", "ClinVar_CLNSIGCONF")
    conflict = bool(conflicts) or any(
        _clinvar_has_conflict_text(value) for value in classifications + review_values
    )
    evidence = {
        "status": "not_reported",
        "identifiers": list(identifiers), "classifications": classifications,
        "review_statuses": review_statuses,
        "conditions": values("CLNDN", "ClinVar_CLNDN"),
        "condition_ids": values("CLNDISDB", "ClinVar_CLNDISDB"),
        "conflicts": conflicts, "has_conflict": conflict,
        "origins": values("CLNORIGIN", "ClinVar_CLNORIGIN"),
        "last_evaluated": values(
            "CLNDATE", "LAST_EVALUATED", "LASTEVALUATED", "ClinVar_LAST_EVALUATED"
        ),
        "oncogenicity": values("ONC", "ONCSIG", "ClinVar_ONC"),
        "oncogenicity_review_statuses": [
            {"label": value, "stars": _clinvar_review_stars(value)}
            for value in values("ONCREVSTAT", "ClinVar_ONCREVSTAT")
        ],
        "somatic_clinical_impact": values("SCI", "SCISIG", "ClinVar_SCI"),
        "somatic_review_statuses": [
            {"label": value, "stars": _clinvar_review_stars(value)}
            for value in values("SCIREVSTAT", "ClinVar_SCIREVSTAT")
        ],
    }
    detail_keys = (
        "classifications", "review_statuses", "conditions", "condition_ids", "conflicts",
        "origins", "last_evaluated", "oncogenicity", "oncogenicity_review_statuses",
        "somatic_clinical_impact", "somatic_review_statuses",
    )
    if any(evidence[key] for key in detail_keys):
        evidence["status"] = "available"
    elif identifiers:
        evidence["status"] = "identifier_only"
    return evidence


def _clinvar_field_key(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _clinvar_display_values(values):
    result = []
    seen = set()
    for raw_value in values:
        for item in re.split(r"[|&]", str(raw_value).replace("%3D", "=")):
            display = " ".join(item.strip().replace("_", " ").split())
            if not display or display == ".":
                continue
            display = display[0].upper() + display[1:]
            folded = display.casefold()
            if folded not in seen:
                seen.add(folded)
                result.append(display)
    return result


def _clinvar_review_stars(review_status):
    value = str(review_status or "").casefold()
    if "practice guideline" in value:
        return 4
    if "expert panel" in value:
        return 3
    if "multiple submitters" in value and "no conflict" in value:
        return 2
    if "criteria provided" in value:
        return 1
    return 0


def _clinvar_has_conflict_text(value):
    normalized = " ".join(str(value or "").casefold().replace("_", " ").split())
    normalized = re.sub(
        r"\b(?:no|without)\s+conflicts?\b|\bnot\s+conflicting\b", "", normalized
    )
    return bool(re.search(r"\bconflict(?:s|ed|ing)?\b", normalized))


def _require_sample(db, sample_id):
    row = db.execute("SELECT id FROM samples WHERE id = ?", (int(sample_id),)).fetchone()
    if row is None:
        raise VariantQueryError("sample not found in this variant database")


def _family_parent_ids(database, sample_id):
    """Resolve the indexed father and mother for one family sample."""
    with store.connect(database) as db:
        current = db.execute(
            "SELECT s.metadata_json, a.run_id FROM samples s "
            "JOIN analyses a ON a.sample_id = s.id WHERE s.id = ? ORDER BY a.id LIMIT 1",
            (int(sample_id),),
        ).fetchone()
        if current is None:
            return None, None
        metadata = _json_value(current["metadata_json"])
        family_id = str(metadata.get("analysis_id") or "").strip().casefold()
        expected = {
            "father": str(metadata.get("father") or "").strip().casefold(),
            "mother": str(metadata.get("mother") or "").strip().casefold(),
        }
        rows = db.execute(
            "SELECT s.id, s.display_name, s.metadata_json, a.role FROM samples s "
            "JOIN analyses a ON a.sample_id = s.id "
            "WHERE a.run_id = ? AND s.id != ? ORDER BY a.id",
            (current["run_id"], int(sample_id)),
        ).fetchall()

    candidates = []
    for row in rows:
        candidate_metadata = _json_value(row["metadata_json"])
        identifiers = {
            str(row["display_name"] or "").strip().casefold(),
            str(candidate_metadata.get("sample_name") or "").strip().casefold(),
            str(candidate_metadata.get("individual_id") or "").strip().casefold(),
        }
        identifiers.discard("")
        candidates.append({
            "id": int(row["id"]), "identifiers": identifiers,
            "family_id": str(candidate_metadata.get("analysis_id") or "").strip().casefold(),
            "relationship": str(
                candidate_metadata.get("relationship") or row["role"] or ""
            ).strip().casefold(),
        })

    resolved = {}
    for relationship in ("father", "mother"):
        named = expected[relationship]
        match = next(
            (item for item in candidates if named and named in item["identifiers"]), None
        )
        if match is None:
            match = next((
                item for item in candidates
                if item["relationship"] == relationship
                and (not family_id or not item["family_id"] or item["family_id"] == family_id)
            ), None)
        resolved[relationship] = match["id"] if match else None
    return resolved["father"], resolved["mother"]


def _family_member_ids(database, sample_id):
    """Return sample ids belonging to the proband family in the indexed run."""
    with store.connect(database) as db:
        current = db.execute(
            "SELECT s.metadata_json, a.run_id FROM samples s "
            "JOIN analyses a ON a.sample_id = s.id WHERE s.id = ? ORDER BY a.id LIMIT 1",
            (int(sample_id),),
        ).fetchone()
        if current is None:
            return set()
        metadata = _json_value(current["metadata_json"])
        family_id = str(metadata.get("analysis_id") or "").strip().casefold()
        expected = {
            str(metadata.get("father") or "").strip().casefold(),
            str(metadata.get("mother") or "").strip().casefold(),
        }
        expected.discard("")
        rows = db.execute(
            "SELECT s.id, s.display_name, s.metadata_json FROM samples s "
            "JOIN analyses a ON a.sample_id = s.id WHERE a.run_id = ? ORDER BY a.id",
            (current["run_id"],),
        ).fetchall()
    members = {int(sample_id)}
    for row in rows:
        candidate = _json_value(row["metadata_json"])
        candidate_family = str(candidate.get("analysis_id") or "").strip().casefold()
        identifiers = {
            str(row["display_name"] or "").strip().casefold(),
            str(candidate.get("sample_name") or "").strip().casefold(),
            str(candidate.get("individual_id") or "").strip().casefold(),
        }
        identifiers.discard("")
        if (family_id and candidate_family == family_id) or identifiers.intersection(expected):
            members.add(int(row["id"]))
    return members


def _family_call_exists(prefix, variant_expression, heterozygous=False):
    call = "{}_call".format(prefix)
    analysis = "{}_analysis".format(prefix)
    genotype = "replace(trim(COALESCE({}.genotype, '')), '|', '/')".format(call)
    if heterozygous:
        carried = (
            "(lower(COALESCE({0}.zygosity, '')) = 'het' OR "
            "(({1} LIKE '0/%' OR {1} LIKE '%/0') "
            "AND {1} != '0/0' AND instr({1}, '.') = 0))"
        ).format(call, genotype)
    else:
        carried = (
            "(lower(COALESCE({0}.zygosity, '')) IN "
            "('het', 'hom_alt', 'hemi', 'hemizygous', 'compound_het') OR "
            "({1} NOT IN ('', '.', './.', '0', '0/0') AND instr({1}, '.') = 0))"
        ).format(call, genotype)
    return (
        "EXISTS (SELECT 1 FROM calls {0} JOIN analyses {1} "
        "ON {1}.id = {0}.analysis_id WHERE {0}.variant_id = {2} "
        "AND {1}.sample_id = ? AND {3})"
    ).format(call, analysis, variant_expression, carried)


def _family_evidence_clause(evidence, sample_id, father_id, mother_id):
    father = _family_call_exists("family_father", "v.id")
    mother = _family_call_exists("family_mother", "v.id")
    if evidence == "de_novo":
        proband = _family_call_exists("family_de_novo_proband", "v.id")
        return (
            "({} AND NOT {} AND NOT {})".format(proband, father, mother),
            [sample_id, father_id, mother_id],
        )
    if evidence == "father_only":
        return "({} AND NOT {})".format(father, mother), [father_id, mother_id]
    if evidence == "mother_only":
        return "({} AND NOT {})".format(mother, father), [mother_id, father_id]
    if evidence == "both_parents":
        return "({} AND {})".format(father, mother), [father_id, mother_id]

    proband = _family_call_exists("family_proband", "v.id", heterozygous=True)
    partner_proband = _family_call_exists(
        "family_partner_proband", "family_partner_variant.id", heterozygous=True
    )
    partner_father = _family_call_exists(
        "family_partner_father", "family_partner_variant.id"
    )
    partner_mother = _family_call_exists(
        "family_partner_mother", "family_partner_variant.id"
    )
    paternal_partner = (
        "EXISTS (SELECT 1 FROM variants family_partner_variant "
        "JOIN annotations family_partner_annotation "
        "ON family_partner_annotation.variant_id = family_partner_variant.id "
        "WHERE family_partner_variant.id != v.id "
        "AND family_partner_annotation.gene COLLATE NOCASE = an.gene "
        "AND {0} AND {1} AND NOT {2})"
    ).format(partner_proband, partner_mother, partner_father)
    maternal_partner = (
        "EXISTS (SELECT 1 FROM variants family_partner_variant "
        "JOIN annotations family_partner_annotation "
        "ON family_partner_annotation.variant_id = family_partner_variant.id "
        "WHERE family_partner_variant.id != v.id "
        "AND family_partner_annotation.gene COLLATE NOCASE = an.gene "
        "AND {0} AND {1} AND NOT {2})"
    ).format(partner_proband, partner_father, partner_mother)
    clause = (
        "(trim(COALESCE(an.gene, '')) != '' AND (({0} AND {1} AND NOT {2} AND {3}) "
        "OR ({4} AND {5} AND NOT {6} AND {7})))"
    ).format(proband, father, mother, paternal_partner,
             proband, mother, father, maternal_partner)
    parameters = [
        sample_id, father_id, mother_id, sample_id, mother_id, father_id,
        sample_id, mother_id, father_id, sample_id, father_id, mother_id,
    ]
    return clause, parameters


def _priority_order_cache_key(database, sample_id, signature):
    return (
        os.path.abspath(os.fspath(database)),
        _file_fingerprint(database),
        _file_fingerprint(gene_phenotype.cache_path()),
        _file_fingerprint(gnomad_frequency.cache_path()),
        int(sample_id),
        RULESET_VERSION,
        signature,
    )


def _file_fingerprint(path):
    try:
        status = os.stat(os.fspath(path))
        return status.st_mtime_ns, status.st_size
    except OSError:
        return None


def _priority_order_cache_get(key):
    with _PRIORITY_ORDER_CACHE_LOCK:
        value = _PRIORITY_ORDER_CACHE.get(key)
        if value is not None:
            _PRIORITY_ORDER_CACHE.move_to_end(key)
        return value


def _priority_order_cache_put(key, variant_ids):
    if key is None:
        return
    with _PRIORITY_ORDER_CACHE_LOCK:
        _PRIORITY_ORDER_CACHE[key] = tuple(variant_ids)
        _PRIORITY_ORDER_CACHE.move_to_end(key)
        while len(_PRIORITY_ORDER_CACHE) > _PRIORITY_ORDER_CACHE_SIZE:
            _PRIORITY_ORDER_CACHE.popitem(last=False)


def _page_size(limit):
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        raise VariantQueryError("page size must be an integer")
    if limit < 1 or limit > MAX_PAGE_SIZE:
        raise VariantQueryError("page size must be between 1 and {}".format(MAX_PAGE_SIZE))
    return limit


def _variant_filters(gene="", genes="", max_af=None, include_missing_af=True,
                     population_frequency="MAX_AF", consequences="", clinical_significances="",
                     inheritance_candidates="", family_evidence="", family_pattern="",
                     priority_classes="", min_priority=None, max_priority=None,
                     filter_mode="all", filter_statuses="", zygosities="",
                     min_depth=None, min_vaf=None, min_quality=None,
                     possible_compound=False):
    gene_values = _filter_values(genes, split_whitespace=True)
    if gene:
        gene_values = [gene]
    if len(gene_values) > 5000:
        raise VariantQueryError("gene panel must contain at most 5000 genes")
    consequence_values = _filter_values(consequences)
    population_frequency = str(population_frequency or "MAX_AF").strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", population_frequency):
        raise VariantQueryError("invalid population frequency field")
    clinical_values = _filter_values(clinical_significances)
    inheritance_values = [
        "mitochondrial" if item.lower() == "maternal" else item.lower()
        for item in _filter_values(inheritance_candidates)
    ]
    if possible_compound and "compound" not in inheritance_values:
        inheritance_values.append("compound")
    allowed_inheritance = {
        "compound", "recessive", "dominant", "x_linked", "y_linked", "mitochondrial",
    }
    if any(item not in allowed_inheritance for item in inheritance_values):
        raise VariantQueryError("invalid inheritance candidate")
    family_values = [item.lower() for item in _filter_values(family_evidence)]
    allowed_family = {
        "de_novo", "father_only", "mother_only", "both_parents", "parental_compound",
    }
    if any(item not in allowed_family for item in family_values):
        raise VariantQueryError("invalid family evidence filter")
    family_pattern_values = []
    family_pattern_seen = {}
    for item in _filter_values(family_pattern):
        match = re.fullmatch(r"([1-9][0-9]*):(present|absent)", item.lower())
        if match is None:
            raise VariantQueryError("invalid family pattern filter")
        member_id, state = int(match.group(1)), match.group(2)
        if member_id in family_pattern_seen and family_pattern_seen[member_id] != state:
            raise VariantQueryError("conflicting states for one family member")
        if member_id not in family_pattern_seen:
            family_pattern_values.append((member_id, state))
        family_pattern_seen[member_id] = state
    priority_values = [item.upper() for item in _filter_values(priority_classes)]
    if any(item not in {"P1", "P2", "P3", "P4"} for item in priority_values):
        raise VariantQueryError("invalid priority class")
    minimum_priority = _optional_number(min_priority, "minimum priority", 0, 100)
    maximum_priority = _optional_number(max_priority, "maximum priority", 0, 100)
    if (minimum_priority is not None and maximum_priority is not None
            and minimum_priority > maximum_priority):
        raise VariantQueryError("minimum priority cannot exceed maximum priority")
    status_values = []
    for status in _filter_values(filter_statuses):
        canonical = _canonical_filter_status(status)
        if canonical and canonical not in status_values:
            status_values.append(canonical)
    zygosity_values = [item.lower() for item in _filter_values(zygosities)]
    mode = str(filter_mode or "all").lower()
    if mode not in ("all", "pass", "selected", "exclude"):
        raise VariantQueryError("filter mode must be all, pass, selected, or exclude")
    if mode in {"selected", "exclude"} and not status_values:
        raise VariantQueryError("at least one FILTER status must be selected")
    return {
        "genes": gene_values, "max_af": _optional_number(max_af, "MAF", 0, 1),
        "population_frequency": population_frequency,
        "include_missing_af": bool(include_missing_af), "consequences": consequence_values,
        "clinical_significances": clinical_values, "inheritance_candidates": inheritance_values,
        "family_evidence": family_values, "family_pattern": family_pattern_values,
        "priority_classes": priority_values,
        "min_priority": minimum_priority, "max_priority": maximum_priority,
        "filter_mode": mode, "filter_statuses": status_values, "zygosities": zygosity_values,
        "min_depth": _optional_number(min_depth, "minimum depth", 0),
        "min_vaf": _optional_number(min_vaf, "minimum VAF", 0, 1),
        "min_quality": _optional_number(min_quality, "minimum QUAL", 0),
        "possible_compound": "compound" in inheritance_values,
    }


def _filter_values(raw, split_whitespace=False):
    if isinstance(raw, (list, tuple)):
        values = raw
    else:
        pattern = r"[,;\s]+" if split_whitespace else r"[,;]+"
        values = re.split(pattern, str(raw or ""))
    result = []
    for item in values:
        normalized = str(item).strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _canonical_filter_status(status):
    value = str(status or "").strip()
    upper_value = value.upper()
    for canonical, aliases in FILTER_STATUS_ALIASES.items():
        if upper_value in aliases:
            return canonical
    return value


def _optional_number(raw, label, minimum=None, maximum=None):
    if raw is None or raw == "":
        return None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        raise VariantQueryError("{} must be a number".format(label))
    if ((minimum is not None and number < minimum)
            or (maximum is not None and number > maximum)):
        raise VariantQueryError("{} must be between {} and {}".format(label, minimum, maximum))
    return number


def _variant_sort(sort_by, sort_direction):
    sort_by = str(sort_by or "").strip().lower()
    aliases = {"af_max": "population_af", "clinical": "clinical_significance"}
    sort_by = aliases.get(sort_by, sort_by) or "priority"
    allowed = {"priority", "gene", "population_af", "clinical_significance", "consequence"}
    if sort_by not in allowed:
        raise VariantQueryError("unsupported variant sort column")
    sort_direction = str(sort_direction or "").strip().lower()
    if not sort_direction:
        sort_direction = "desc" if sort_by == "priority" else "asc"
    if sort_direction not in {"asc", "desc"}:
        raise VariantQueryError("sort direction must be asc or desc")
    return sort_by, sort_direction


def _variant_order(sort_by, sort_direction):
    direction = "DESC" if sort_direction == "desc" else "ASC"
    if sort_by == "gene":
        return (
            "CASE WHEN trim(COALESCE(an.gene, '')) = '' THEN 1 ELSE 0 END, "
            "an.gene COLLATE NOCASE {} , v.id".format(direction)
        )
    if sort_by == "population_af":
        # Missing AF is intentionally lower than every valid population frequency.
        return "COALESCE(an.population_af, -1.0) {}, v.id".format(direction)
    if sort_by == "clinical_significance":
        normalized = (
            "('&' || replace(replace(replace(lower(trim(COALESCE("
            "an.clinical_significance, ''))), ',', '&'), '|', '&'), ' ', '_') || '&')"
        )
        priority = (
            "CASE "
            "WHEN instr({0}, '&pathogenic&') > 0 THEN 5 "
            "WHEN instr({0}, '&likely_pathogenic&') > 0 THEN 4 "
            "WHEN instr({0}, '&uncertain_significance&') > 0 "
            "  OR instr({0}, '&variant_of_uncertain_significance&') > 0 "
            "  OR instr({0}, '&vus&') > 0 THEN 3 "
            "WHEN instr({0}, '&likely_benign&') > 0 THEN 2 "
            "WHEN instr({0}, '&benign&') > 0 THEN 1 "
            "WHEN trim(COALESCE(an.clinical_significance, '')) IN ('', '.') THEN -1 "
            "ELSE 0 END"
        ).format(normalized)
        return "{} {}, COALESCE(an.clinical_significance, '') COLLATE NOCASE, v.id".format(
            priority, direction
        )
    if sort_by == "consequence":
        return (
            "CASE WHEN trim(COALESCE(an.consequence, '')) = '' THEN 1 ELSE 0 END, "
            "an.consequence COLLATE NOCASE {}, v.id".format(direction)
        )
    return "v.id"


def _filter_priority(items, filters):
    classes = set(filters["priority_classes"])
    minimum = filters["min_priority"]
    maximum = filters["max_priority"]
    result = []
    for item in items:
        priority = item["priority"]
        score = priority["normalized_score"]
        if classes and priority["band"] not in classes:
            continue
        if minimum is not None and score < minimum:
            continue
        if maximum is not None and score > maximum:
            continue
        result.append(item)
    return result


def _sort_priority(items, sort_direction):
    if sort_direction == "desc":
        return sorted(
            items,
            key=lambda item: (
                -item["priority"]["normalized_score"],
                -item["priority"]["score"],
                item["variant_id"],
            ),
        )
    return sorted(
        items,
        key=lambda item: (
            item["priority"]["normalized_score"],
            item["priority"]["score"],
            item["variant_id"],
        ),
    )


def _encode_cursor(sample_id, variant_id, filter_signature=""):
    raw = json.dumps(
        {"sample_id": sample_id, "variant_id": variant_id, "filters": filter_signature},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor, sample_id, filter_signature=""):
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        if (payload["sample_id"] != sample_id or int(payload["variant_id"]) < 0
                or payload.get("filters", "") != filter_signature):
            raise ValueError
        return int(payload["variant_id"])
    except (KeyError, TypeError, ValueError, UnicodeError, binascii.Error, json.JSONDecodeError):
        raise VariantQueryError("invalid or mismatched variant cursor")


def _encode_offset_cursor(sample_id, offset, filter_signature):
    raw = json.dumps(
        {"sample_id": sample_id, "offset": offset, "filters": filter_signature},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_offset_cursor(cursor, sample_id, filter_signature):
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        if (payload["sample_id"] != sample_id or int(payload["offset"]) < 0
                or payload.get("filters", "") != filter_signature):
            raise ValueError
        return int(payload["offset"])
    except (KeyError, TypeError, ValueError, UnicodeError, binascii.Error, json.JSONDecodeError):
        raise VariantQueryError("invalid or mismatched variant cursor")


def _json_value(value):
    try:
        return json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}


def _csv(value):
    return value.split(",") if value else []
