"""Read-only, keyset-paginated queries for a run-local variant database."""
import base64
import binascii
import json
import re

from helper_variants import store


DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500


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
                  genes="", max_af=None, population_frequency="MAX_AF",
                  include_missing_af=True, consequences="",
                  clinical_significances="", inheritance_candidates="",
                  filter_mode="all", filter_statuses="", zygosities="", min_depth=None,
                  min_vaf=None, min_quality=None, possible_compound=False):
    limit = _page_size(limit)
    gene = str(gene or "").strip()
    if len(gene) > 100:
        raise VariantQueryError("gene filter must be at most 100 characters")
    filters = _variant_filters(
        gene=gene, genes=genes, max_af=max_af, population_frequency=population_frequency,
        include_missing_af=include_missing_af,
        consequences=consequences, clinical_significances=clinical_significances,
        inheritance_candidates=inheritance_candidates, filter_mode=filter_mode,
        filter_statuses=filter_statuses, zygosities=zygosities, min_depth=min_depth,
        min_vaf=min_vaf, min_quality=min_quality, possible_compound=possible_compound,
    )
    signature = json.dumps(filters, sort_keys=True, separators=(",", ":"))
    after_variant_id = _decode_cursor(cursor, int(sample_id), signature) if cursor else 0

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
    if inheritance_clauses:
        result_clauses.append("(" + " OR ".join(inheritance_clauses) + ")")
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
    elif filters["filter_mode"] == "selected":
        status_matches = []
        for status in filters["filter_statuses"]:
            status_matches.append(
                "instr(',' || replace(upper(filtered.filter_status), ';', ',') || ',', ?) > 0"
            )
            call_parameters.append(",{},".format(status.upper()))
        call_clauses.append(
            "EXISTS (SELECT 1 FROM calls filtered JOIN analyses filtered_analysis "
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
    parameters = (annotation_parameters + [int(sample_id), after_variant_id] + result_parameters
                  + call_parameters + having_parameters + [limit + 1])
    with store.connect(database) as db:
        _require_sample(db, sample_id)
        rows = db.execute(
            "SELECT v.id AS variant_id, v.reference_build, v.chromosome, v.position, v.reference, "
            "v.alternate, v.variant_type, GROUP_CONCAT(DISTINCT NULLIF(c.caller, '')) AS callers, "
            "GROUP_CONCAT(DISTINCT NULLIF(c.genotype, '')) AS genotypes, MAX(c.depth) AS depth, "
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
            ") WHERE a.sample_id = ? AND v.id > ? " + result_filter + call_filter +
            " GROUP BY v.id" + having_filter + " ORDER BY v.id LIMIT ?",
            parameters,
        ).fetchall()
        has_more = len(rows) > limit
        page = rows[:limit]
        items = [_compact_variant(row) for row in page]
        next_cursor = _encode_cursor(int(sample_id), page[-1]["variant_id"], signature) if has_more else None
        return {"items": items, "next_cursor": next_cursor, "limit": limit}


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
        statuses = set()
        for row in db.execute(
            "SELECT DISTINCT c.filter_status FROM calls c JOIN analyses a ON a.id = c.analysis_id "
            "WHERE a.sample_id = ? AND c.filter_status NOT IN ('', '.', 'PASS')", (int(sample_id),),
        ):
            statuses.update(part for part in re.split(r"[;,]", row[0]) if part)
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
                "filter_statuses": sorted(statuses, key=str.casefold), "zygosities": zygosities}


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
            "an.clinical_significance, an.population_af, an.canonical, an.metadata_json "
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
        return result


def variant_carriers(database, reference_build, chromosome, position, reference, alternate):
    """Return samples carrying one exact normalized allele in a run store."""
    with store.connect(database) as db:
        rows = db.execute(
            "SELECT s.id AS sample_id, s.sample_key, s.display_name, s.specimen_type, "
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
            "sample_id": row["sample_id"], "sample_key": row["sample_key"],
            "display_name": row["display_name"], "specimen_type": row["specimen_type"],
            "metadata": _json_value(row["metadata_json"]), "roles": _csv(row["roles"]),
            "genotypes": _csv(row["genotypes"]), "depth": row["depth"],
            "allele_fraction": row["allele_fraction"],
        } for row in rows]


def _compact_variant(row):
    metadata = _json_value(row["metadata_json"])
    return {
        "variant_id": row["variant_id"], "reference_build": row["reference_build"],
        "chromosome": row["chromosome"], "position": row["position"],
        "reference": row["reference"], "alternate": row["alternate"],
        "variant_type": row["variant_type"], "callers": _csv(row["callers"]),
        "genotypes": _csv(row["genotypes"]), "depth": row["depth"],
        "alternate_depth": row["alternate_depth"], "allele_fraction": row["allele_fraction"],
        "genotype_quality": row["genotype_quality"], "quality": row["quality"],
        "filter_status": _csv(row["filter_status"]), "gene": row["gene"] or "",
        "transcript": row["transcript"] or "", "consequence": row["consequence"] or "",
        "exon_intron": _annotation_exon_intron(metadata, row["consequence"]),
        "impact": row["impact"] or "", "hgvsc": row["hgvsc"] or "",
        "hgvsp": row["hgvsp"] or "", "clinical_significance": row["clinical_significance"] or "",
        "population_af": row["population_af"], "canonical": bool(row["canonical"] or 0),
    }


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
                     inheritance_candidates="",
                     filter_mode="all", filter_statuses="", zygosities="",
                     min_depth=None, min_vaf=None, min_quality=None, possible_compound=False):
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
    inheritance_values = [item.lower() for item in _filter_values(inheritance_candidates)]
    if possible_compound and "compound" not in inheritance_values:
        inheritance_values.append("compound")
    allowed_inheritance = {"compound", "recessive", "dominant", "x_linked", "y_linked"}
    if any(item not in allowed_inheritance for item in inheritance_values):
        raise VariantQueryError("invalid inheritance candidate")
    status_values = _filter_values(filter_statuses)
    zygosity_values = [item.lower() for item in _filter_values(zygosities)]
    mode = str(filter_mode or "all").lower()
    if mode not in ("all", "pass", "selected"):
        raise VariantQueryError("filter mode must be all, pass, or selected")
    if mode == "selected" and not status_values:
        raise VariantQueryError("at least one FILTER status must be selected")
    return {
        "genes": gene_values, "max_af": _optional_number(max_af, "MAF", 0, 1),
        "population_frequency": population_frequency,
        "include_missing_af": bool(include_missing_af), "consequences": consequence_values,
        "clinical_significances": clinical_values, "inheritance_candidates": inheritance_values,
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


def _json_value(value):
    try:
        return json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}


def _csv(value):
    return value.split(",") if value else []
