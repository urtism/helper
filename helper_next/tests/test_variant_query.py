import json

import pytest

from helper_variants import query, store


def query_store(tmp_path):
    path = tmp_path / "variants.sqlite"
    with store.connect(path, "run") as db:
        run_id = store.register_run(db, "RUN-Q", "GRCh38", "/runs/RUN-Q")
        first_sample = store.register_sample(db, "RUN-Q:S1", "S1", specimen_type="blood")
        second_sample = store.register_sample(db, "RUN-Q:S2", "S2")
        first_analysis = store.register_analysis(db, "RUN-Q:S1", run_id, first_sample, "proband")
        second_analysis = store.register_analysis(db, "RUN-Q:S2", run_id, second_sample, "mother")
        release = store.register_annotation_release(db, "release-1", "VEP", "GRCh38", "116")
        for position in range(1, 6):
            variant = store.get_or_create_variant(
                db, "GRCh38", "1", position, "A", "G", "SNV",
                {"vcf_id": "rs123"} if position == 1 else None,
            )
            store.record_call(
                db, first_analysis, variant, "GATK", "0/1", depth=position * 10,
                alternate_depth=position * 4, allele_fraction=0.4, filter_status="PASS",
            )
            if position == 1:
                store.record_call(db, second_analysis, variant, "GATK", "0/1", depth=20)
                store.record_annotation(
                    db, variant, release, gene="GENE1", transcript="TX-NONCANONICAL",
                    consequence="intron_variant", impact="MODIFIER",
                    clinical_significance="drug_response",
                    metadata={"fields": {"INTRON": "1/9"}},
                )
                store.record_annotation(
                    db, variant, release, gene="GENE1", transcript="TX-CANONICAL",
                    consequence="missense_variant", impact="MODERATE", canonical=True,
                    hgvsc="c.1A>G", hgvsp="p.Lys1Arg",
                    clinical_significance="pathogenic", population_af=0.001,
                    metadata={"fields": {
                        "EXON": "2/10",
                        "AFR_AF": "0.0002", "EUR_AF": "0.02",
                        "Existing_variation": "rs123&VCV000000456.2",
                        "ClinVarVariationID": "456",
                        "ClinVar_CLNREVSTAT": "criteria_provided,_multiple_submitters,_no_conflicts",
                        "ClinVar_CLNDN": "Gene_1_disorder",
                        "ClinVar_CLNDISDB": "MONDO:0000001",
                        "ClinVar_CLNSIGCONF": "Pathogenic(2)|Uncertain_significance(1)",
                        "ClinVar_LAST_EVALUATED": "2026-09-01",
                        "ClinGen_CAID": "CA789",
                    }},
                )
            elif position in (2, 3):
                store.record_annotation(
                    db, variant, release, gene="GENE1" if position == 2 else "GENE2",
                    transcript="TX-{}".format(position), consequence="intron_variant",
                )
    return path, first_sample, second_sample


def test_run_and_sample_summaries_keep_variants_calls_and_annotations_distinct(tmp_path):
    path, first_sample, second_sample = query_store(tmp_path)

    summary = query.run_summary(path)
    samples = query.list_samples(path)

    assert summary["sample_count"] == 2
    assert summary["variant_count"] == 5
    assert summary["call_count"] == 6
    by_id = {row["sample_id"]: row for row in samples}
    assert by_id[first_sample]["variant_count"] == 5
    assert by_id[first_sample]["call_count"] == 5
    assert by_id[first_sample]["annotated_variant_count"] == 3
    assert by_id[second_sample]["variant_count"] == 1


def test_keyset_pagination_has_no_gaps_or_duplicates_and_caps_page_size(tmp_path):
    path, sample_id, other_sample = query_store(tmp_path)
    seen = []
    cursor = None
    while True:
        page = query.list_variants(path, sample_id, cursor, limit=2)
        seen.extend(item["variant_id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert seen == sorted(set(seen))
    assert len(seen) == 5
    first_page = query.list_variants(path, sample_id, limit=2)
    with pytest.raises(query.VariantQueryError, match="mismatched"):
        query.list_variants(path, other_sample, first_page["next_cursor"], limit=2)
    with pytest.raises(query.VariantQueryError, match="between 1 and 500"):
        query.list_variants(path, sample_id, limit=501)


def test_variant_priority_sorts_cover_gene_af_clinical_and_consequence(tmp_path):
    path, sample_id, _ = query_store(tmp_path)
    with store.connect(path) as db:
        release_id = db.execute("SELECT id FROM annotation_releases LIMIT 1").fetchone()[0]
        clinical_by_position = {
            2: "likely_pathogenic", 3: "uncertain_significance",
            4: "likely_benign", 5: "benign",
        }
        for position, significance in clinical_by_position.items():
            variant_id = db.execute(
                "SELECT id FROM variants WHERE position = ?", (position,)
            ).fetchone()[0]
            updated = db.execute(
                "UPDATE annotations SET clinical_significance = ? WHERE variant_id = ?",
                (significance, variant_id),
            ).rowcount
            if not updated:
                store.record_annotation(
                    db, variant_id, release_id, clinical_significance=significance
                )

    def positions(sort_by, direction):
        result = query.list_variants(
            path, sample_id, sort_by=sort_by, sort_direction=direction
        )
        return [item["position"] for item in result["items"]]

    assert positions("gene", "asc") == [1, 2, 3, 4, 5]
    assert positions("gene", "desc") == [3, 1, 2, 4, 5]
    assert positions("population_af", "asc") == [2, 3, 4, 5, 1]
    assert positions("population_af", "desc") == [1, 2, 3, 4, 5]
    assert positions("clinical_significance", "desc") == [1, 2, 3, 4, 5]
    assert positions("clinical_significance", "asc") == [5, 4, 3, 2, 1]
    assert positions("consequence", "asc") == [2, 3, 1, 4, 5]
    assert positions("consequence", "desc") == [1, 2, 3, 4, 5]


def test_priority_is_default_sort_and_supports_class_and_score_range(tmp_path):
    path, sample_id, _ = query_store(tmp_path)

    default = query.list_variants(path, sample_id)
    descending = query.list_variants(
        path, sample_id, sort_by="priority", sort_direction="desc"
    )
    ascending = query.list_variants(
        path, sample_id, sort_by="priority", sort_direction="asc"
    )
    default_scores = [item["priority"]["normalized_score"] for item in default["items"]]
    ascending_scores = [item["priority"]["normalized_score"] for item in ascending["items"]]

    assert default["sort_by"] == "priority"
    assert default["sort_direction"] == "desc"
    assert [item["variant_id"] for item in default["items"]] == [
        item["variant_id"] for item in descending["items"]
    ]
    assert default_scores == sorted(default_scores, reverse=True)
    assert ascending_scores == sorted(ascending_scores)

    selected_classes = sorted({
        item["priority"]["band"] for item in default["items"]
    })[:2]
    by_class = query.list_variants(
        path, sample_id, priority_classes=",".join(selected_classes)
    )
    assert by_class["items"]
    assert all(item["priority"]["band"] in selected_classes for item in by_class["items"])

    by_value = query.list_variants(path, sample_id, min_priority=5, max_priority=30)
    assert by_value["items"]
    assert all(
        5 <= item["priority"]["normalized_score"] <= 30 for item in by_value["items"]
    )
    with pytest.raises(query.VariantQueryError, match="minimum priority"):
        query.list_variants(path, sample_id, min_priority=80, max_priority=20)
    with pytest.raises(query.VariantQueryError, match="invalid priority class"):
        query.list_variants(path, sample_id, priority_classes="P5")


def test_priority_pagination_reuses_cached_global_order(tmp_path, monkeypatch):
    path, sample_id, _ = query_store(tmp_path)
    original = query.score_variant
    scored = []

    def counting_score(variant):
        scored.append(variant)
        return original(variant)

    monkeypatch.setattr(query, "score_variant", counting_score)
    first = query.list_variants(path, sample_id, limit=2)
    assert len(scored) == 5

    second = query.list_variants(
        path, sample_id, cursor=first["next_cursor"], limit=2
    )

    assert len(second["items"]) == 2
    assert len(scored) == 7


def test_sorted_variant_pagination_is_bound_to_sort_order(tmp_path):
    path, sample_id, _ = query_store(tmp_path)
    positions = []
    cursor = None
    while True:
        page = query.list_variants(
            path, sample_id, cursor=cursor, limit=2,
            sort_by="gene", sort_direction="desc",
        )
        positions.extend(item["position"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert positions == [3, 1, 2, 4, 5]
    first = query.list_variants(path, sample_id, limit=2, sort_by="gene")
    with pytest.raises(query.VariantQueryError, match="mismatched"):
        query.list_variants(
            path, sample_id, cursor=first["next_cursor"], limit=2,
            sort_by="gene", sort_direction="desc",
        )
    with pytest.raises(query.VariantQueryError, match="unsupported"):
        query.list_variants(path, sample_id, sort_by="quality")


def test_compact_projection_chooses_canonical_annotation_and_detail_is_lazy(tmp_path):
    path, sample_id, other_sample = query_store(tmp_path)
    item = query.list_variants(path, sample_id, limit=1)["items"][0]

    assert item["gene"] == "GENE1"
    assert item["hgvsc"] == "c.1A>G"
    assert item["hgvsp"] == "p.Lys1Arg"
    assert item["transcript"] == "TX-CANONICAL"
    assert item["consequence"] == "missense_variant"
    assert item["exon_intron"] == "Exon 2/10"
    assert item["clinical_significance"] == "pathogenic"
    assert item["population_af"] == 0.001
    assert item["canonical"] is True
    detail = query.variant_detail(path, sample_id, item["variant_id"])
    assert len(detail["calls"]) == 1
    assert len(detail["annotations"]) == 2
    locations = {
        annotation["transcript"]: annotation["exon_intron"]
        for annotation in detail["annotations"]
    }
    assert locations == {"TX-CANONICAL": "Exon 2/10", "TX-NONCANONICAL": "Intron 1/9"}
    assert detail["database_ids"] == {
        "dbsnp": ["rs123"],
        "clinvar": ["456", "VCV000000456.2"],
        "clingen": ["CA789"],
    }
    assert detail["clinvar_evidence"]["status"] == "available"
    assert detail["clinvar_evidence"]["review_statuses"] == [{
        "label": "Criteria provided, multiple submitters, no conflicts", "stars": 2,
    }]
    assert detail["clinvar_evidence"]["conditions"] == ["Gene 1 disorder"]
    assert detail["clinvar_evidence"]["condition_ids"] == ["MONDO:0000001"]
    assert detail["clinvar_evidence"]["has_conflict"] is True
    assert detail["clinvar_evidence"]["last_evaluated"] == ["2026-09-01"]
    assert query.variant_detail(path, other_sample, item["variant_id"]) is not None
    second_variant = query.list_variants(path, sample_id, limit=2)["items"][1]
    assert query.variant_detail(path, other_sample, second_variant["variant_id"]) is None


def test_cached_gnomad_coverage_distinguishes_verified_absence_from_missing_af(
        tmp_path, monkeypatch):
    path, sample_id, _ = query_store(tmp_path)

    def frequency_contexts(alleles):
        return [
            {
                "population_frequency_status": "not_observed_covered",
                "population_frequency_source": "gnomAD genomes v4.1",
                "population_absent": True,
                "population_coverage_adequate": True,
            } if allele[2] == 2 else {}
            for allele in alleles
        ]

    monkeypatch.setattr(query.gnomad_frequency, "cached_contexts", frequency_contexts)

    page = query.list_variants(path, sample_id)
    by_position = {item["position"]: item for item in page["items"]}
    verified = by_position[2]
    unknown = by_position[3]
    verified_maf = next(
        component for component in verified["priority"]["components"]
        if component["key"] == "maf"
    )
    unknown_maf = next(
        component for component in unknown["priority"]["components"]
        if component["key"] == "maf"
    )

    assert verified["population_frequency_status"] == "not_observed_covered"
    assert verified_maf["score"] == verified_maf["max_score"]
    assert verified_maf["evaluated"] is True
    assert unknown_maf["score"] == 0
    assert unknown_maf["evaluated"] is False


def test_missing_sample_is_rejected(tmp_path):
    path, _, _ = query_store(tmp_path)
    with pytest.raises(query.VariantQueryError, match="sample not found"):
        query.list_variants(path, 999)


@pytest.mark.parametrize("label, expected", [
    ("criteria provided, multiple submitters, no conflicts", False),
    ("criteria provided, conflicting classifications", True),
    ("conflicting interpretations of pathogenicity", True),
])
def test_clinvar_conflict_detection_does_not_misread_no_conflicts(label, expected):
    assert query._clinvar_has_conflict_text(label) is expected


def test_variant_carriers_are_returned_for_the_exact_run_allele(tmp_path):
    path, _, _ = query_store(tmp_path)

    shared = query.variant_carriers(path, "GRCh38", "1", 1, "A", "G")
    private = query.variant_carriers(path, "GRCh38", "1", 2, "A", "G")

    assert [carrier["display_name"] for carrier in shared] == ["S1", "S2"]
    assert {carrier["variant_id"] for carrier in shared} == {shared[0]["variant_id"]}
    assert shared[0]["genotypes"] == ["0/1"]
    assert [carrier["display_name"] for carrier in private] == ["S1"]


def test_variant_can_be_loaded_directly_for_carrier_table_focus(tmp_path):
    path, sample_id, _ = query_store(tmp_path)
    all_variants = query.list_variants(path, sample_id)["items"]
    target = next(item for item in all_variants if item["position"] == 4)

    focused = query.list_variants(path, sample_id, limit=1, variant_id=target["variant_id"])

    assert [item["variant_id"] for item in focused["items"]] == [target["variant_id"]]
    assert focused["next_cursor"] is None
    with pytest.raises(query.VariantQueryError, match="positive"):
        query.list_variants(path, sample_id, variant_id=0)


def test_gene_filter_returns_only_that_samples_gene_and_binds_the_cursor(tmp_path):
    path, sample_id, _ = query_store(tmp_path)

    first = query.list_variants(path, sample_id, limit=1, gene="gene1")
    second = query.list_variants(
        path, sample_id, cursor=first["next_cursor"], limit=1, gene="gene1"
    )

    assert [item["gene"] for item in first["items"] + second["items"]] == ["GENE1", "GENE1"]
    assert second["next_cursor"] is None
    with pytest.raises(query.VariantQueryError, match="mismatched"):
        query.list_variants(path, sample_id, cursor=first["next_cursor"], gene="GENE2")


def test_variant_panel_annotation_and_numeric_filters_are_server_side(tmp_path):
    path, sample_id, _ = query_store(tmp_path)

    panel = query.list_variants(path, sample_id, genes="GENE2, GENE1", consequences="missense_variant")
    assert [item["position"] for item in panel["items"]] == [1]
    clinical = query.list_variants(path, sample_id, clinical_significances="pathogenic")
    assert [item["position"] for item in clinical["items"]] == [1]
    not_reported = query.list_variants(
        path, sample_id, clinical_significances="__not_reported__"
    )
    assert [item["position"] for item in not_reported["items"]] == [2, 3, 4, 5]
    african = query.list_variants(
        path, sample_id, max_af=0.001, population_frequency="AFR_AF", include_missing_af=False
    )
    european = query.list_variants(
        path, sample_id, max_af=0.001, population_frequency="EUR_AF", include_missing_af=False
    )
    assert [item["position"] for item in african["items"]] == [1]
    assert european["items"] == []
    rare = query.list_variants(path, sample_id, max_af=0.0001, include_missing_af=True)
    assert [item["position"] for item in rare["items"]] == [2, 3, 4, 5]
    strict_rare = query.list_variants(path, sample_id, max_af=0.01, include_missing_af=False)
    assert [item["position"] for item in strict_rare["items"]] == [1]
    assert [item["position"] for item in query.list_variants(
        path, sample_id, min_depth=10, min_vaf=0.3
    )["items"]] == [1, 2, 3, 4, 5]


def test_pass_selected_filter_status_and_filter_options(tmp_path):
    path, sample_id, _ = query_store(tmp_path)
    with store.connect(path) as db:
        db.execute(
            "UPDATE calls SET filter_status = 'LowQual;strand_bias' "
            "WHERE analysis_id = ? AND depth = 20", (1,),
        )
        db.execute(
            "UPDATE calls SET filter_status = 'LOW_AD' "
            "WHERE analysis_id = ? AND depth = 30", (1,),
        )
        db.execute(
            "UPDATE calls SET filter_status = 'LOW_DP' "
            "WHERE analysis_id = ? AND depth = 40", (1,),
        )

    passed = query.list_variants(path, sample_id, filter_mode="pass")
    selected = query.list_variants(
        path, sample_id, filter_mode="selected", filter_statuses="strand_bias"
    )
    excluded = query.list_variants(
        path, sample_id, filter_mode="exclude", filter_statuses="strand_bias"
    )
    alternate_depth = query.list_variants(
        path, sample_id, filter_mode="selected", filter_statuses="LOW_ALTERNATE_DEPTH"
    )
    low_depth = query.list_variants(
        path, sample_id, filter_mode="selected", filter_statuses="LOW_DEPTH"
    )
    options = query.variant_filter_options(path, sample_id)

    assert 2 not in [item["position"] for item in passed["items"]]
    assert [item["position"] for item in selected["items"]] == [2]
    assert [item["position"] for item in excluded["items"]] == [1, 3, 4, 5]
    assert [item["position"] for item in alternate_depth["items"]] == [3]
    assert [item["position"] for item in low_depth["items"]] == [4]
    assert options["consequences"] == ["intron_variant", "missense_variant"]
    assert options["clinical_significances"] == [
        "pathogenic", "likely_pathogenic", "uncertain_significance",
        "likely_benign", "benign", "drug_response", "__not_reported__",
    ]
    assert options["population_frequencies"] == ["MAX_AF", "AFR_AF", "EUR_AF"]
    assert options["filter_statuses"] == list(query.DEFAULT_FILTER_STATUSES)
    assert "LOW_AD" not in options["filter_statuses"]
    assert "LOW_DP" not in options["filter_statuses"]
    assert options["zygosities"] == []
    with pytest.raises(query.VariantQueryError, match="at least one FILTER"):
        query.list_variants(path, sample_id, filter_mode="exclude")


def test_zygosity_and_possible_compound_candidates(tmp_path):
    path, sample_id, _ = query_store(tmp_path)
    with store.connect(path) as db:
        db.execute("UPDATE calls SET zygosity = 'het' WHERE analysis_id = ?", (1,))
        release = db.execute("SELECT id FROM annotation_releases LIMIT 1").fetchone()[0]
        fourth = db.execute("SELECT id FROM variants WHERE position = 4").fetchone()[0]
        store.record_annotation(
            db, fourth, release, gene="GENE1", transcript="TX-4", consequence="missense_variant"
        )

    heterozygous = query.list_variants(path, sample_id, zygosities="het")
    compound = query.list_variants(path, sample_id, possible_compound=True)

    assert len(heterozygous["items"]) == 5
    assert sorted(item["position"] for item in compound["items"]) == [1, 2, 4]
    assert query.variant_filter_options(path, sample_id)["zygosities"] == ["het"]


def test_inheritance_candidate_filters_are_combined_with_or(tmp_path):
    path, sample_id, _ = query_store(tmp_path)
    with store.connect(path) as db:
        db.execute("UPDATE calls SET zygosity = 'het' WHERE analysis_id = ?", (1,))
        db.execute(
            "UPDATE calls SET zygosity = 'hom_alt' WHERE analysis_id = ? AND depth = 50", (1,)
        )
        db.execute("UPDATE variants SET chromosome = 'chrX' WHERE position = 3")
        db.execute("UPDATE variants SET chromosome = 'Y' WHERE position = 4")
        db.execute("UPDATE variants SET chromosome = 'chrM' WHERE position = 5")

    dominant = query.list_variants(path, sample_id, inheritance_candidates="dominant")
    recessive = query.list_variants(path, sample_id, inheritance_candidates="recessive")
    sex_linked = query.list_variants(path, sample_id, inheritance_candidates="x_linked,y_linked")
    mitochondrial = query.list_variants(
        path, sample_id, inheritance_candidates="mitochondrial"
    )
    maternal_alias = query.list_variants(path, sample_id, inheritance_candidates="maternal")

    assert [item["position"] for item in dominant["items"]] == [1, 2, 3, 4]
    assert [item["position"] for item in recessive["items"]] == [5]
    assert [item["position"] for item in sex_linked["items"]] == [3, 4]
    assert [item["position"] for item in mitochondrial["items"]] == [5]
    assert [item["position"] for item in maternal_alias["items"]] == [5]
    with pytest.raises(query.VariantQueryError, match="invalid inheritance"):
        query.list_variants(path, sample_id, inheritance_candidates="autosomal")


def test_family_filters_resolve_parents_and_biparental_compound_candidates(tmp_path):
    path, proband_id, mother_id = query_store(tmp_path)
    with store.connect(path) as db:
        run_id = db.execute("SELECT id FROM runs LIMIT 1").fetchone()[0]
        release_id = db.execute("SELECT id FROM annotation_releases LIMIT 1").fetchone()[0]
        db.execute(
            "UPDATE samples SET metadata_json = ? WHERE id = ?",
            (json.dumps({
                "sample_name": "S1", "analysis_id": "FAM-01", "relationship": "proband",
                "father": "FATHER", "mother": "MOTHER",
            }), proband_id),
        )
        db.execute(
            "UPDATE samples SET display_name = 'MOTHER', metadata_json = ? WHERE id = ?",
            (json.dumps({
                "sample_name": "MOTHER", "analysis_id": "FAM-01", "relationship": "mother",
            }), mother_id),
        )
        father_id = store.register_sample(
            db, "RUN-Q:FATHER", "FATHER", metadata={
                "sample_name": "FATHER", "analysis_id": "FAM-01", "relationship": "father",
            },
        )
        father_analysis = store.register_analysis(
            db, "RUN-Q:FATHER", run_id, father_id, "father"
        )
        mother_analysis = db.execute(
            "SELECT id FROM analyses WHERE sample_id = ?", (mother_id,)
        ).fetchone()[0]
        proband_analysis = db.execute(
            "SELECT id FROM analyses WHERE sample_id = ?", (proband_id,)
        ).fetchone()[0]
        db.execute(
            "UPDATE calls SET zygosity = 'het' WHERE analysis_id = ?", (proband_analysis,)
        )
        variants = {
            position: db.execute(
                "SELECT id FROM variants WHERE position = ?", (position,)
            ).fetchone()[0]
            for position in range(1, 6)
        }
        variants[6] = store.get_or_create_variant(
            db, "GRCh38", "1", 6, "A", "G", "SNV"
        )
        store.record_call(
            db, proband_analysis, variants[6], "GATK", "0/1", zygosity="het"
        )
        for position in (2, 3, 4):
            store.record_call(
                db, father_analysis, variants[position], "GATK", "0/1", zygosity="het"
            )
        store.record_call(
            db, father_analysis, variants[5], "GATK", "0/0", zygosity="hom_ref"
        )
        for position in (3, 5):
            store.record_call(
                db, mother_analysis, variants[position], "GATK", "0/1", zygosity="het"
            )
        for position in (4, 5):
            store.record_annotation(
                db, variants[position], release_id, gene="COMP1",
                transcript="TX-{}".format(position), consequence="missense_variant",
            )

    father_only = query.list_variants(path, proband_id, family_evidence="father_only")
    mother_only = query.list_variants(path, proband_id, family_evidence="mother_only")
    both = query.list_variants(path, proband_id, family_evidence="both_parents")
    compound = query.list_variants(path, proband_id, family_evidence="parental_compound")
    de_novo = query.list_variants(path, proband_id, family_evidence="de_novo")
    combined = query.list_variants(
        path, proband_id, family_evidence="father_only,both_parents"
    )
    paternal_pattern = query.list_variants(
        path, proband_id,
        family_pattern="{}:present,{}:absent".format(father_id, mother_id),
    )
    de_novo_pattern = query.list_variants(
        path, proband_id,
        family_pattern="{}:present,{}:absent,{}:absent".format(
            proband_id, father_id, mother_id,
        ),
    )

    assert sorted(item["position"] for item in father_only["items"]) == [2, 4]
    assert sorted(item["position"] for item in mother_only["items"]) == [1, 5]
    assert [item["position"] for item in both["items"]] == [3]
    assert sorted(item["position"] for item in compound["items"]) == [1, 2, 4, 5]
    assert [item["position"] for item in de_novo["items"]] == [6]
    inheritance = next(
        component for component in de_novo["items"][0]["priority"]["components"]
        if component["key"] == "inheritance"
    )
    assert "De novo status: candidate" in inheritance["evidence"]
    assert sorted(item["position"] for item in combined["items"]) == [2, 3, 4]
    assert sorted(item["position"] for item in paternal_pattern["items"]) == [2, 4]
    assert [item["position"] for item in de_novo_pattern["items"]] == [6]
    with pytest.raises(query.VariantQueryError, match="invalid family evidence"):
        query.list_variants(path, proband_id, family_evidence="segregating")
    with pytest.raises(query.VariantQueryError, match="invalid family pattern"):
        query.list_variants(path, proband_id, family_pattern="father:present")
    with pytest.raises(query.VariantQueryError, match="outside the current family"):
        query.list_variants(path, proband_id, family_pattern="999:present")
    with pytest.raises(query.VariantQueryError, match="conflicting states"):
        query.list_variants(
            path, proband_id,
            family_pattern="{}:present,{}:absent".format(father_id, father_id),
        )


def test_large_sample_stays_bounded_to_requested_pages(tmp_path):
    path = tmp_path / "large.sqlite"
    with store.connect(path, "run") as db:
        run_id = store.register_run(db, "RUN-LARGE", "GRCh38")
        sample_id = store.register_sample(db, "RUN-LARGE:S1", "S1")
        analysis_id = store.register_analysis(db, "RUN-LARGE:S1", run_id, sample_id)
        for position in range(1, 1202):
            variant_id = store.get_or_create_variant(db, "GRCh38", "1", position, "A", "G")
            store.record_call(db, analysis_id, variant_id, genotype="0/1")

    first = query.list_variants(path, sample_id, limit=200)
    second = query.list_variants(path, sample_id, first["next_cursor"], limit=200)

    assert len(first["items"]) == 200
    assert len(second["items"]) == 200
    assert first["items"][-1]["variant_id"] < second["items"][0]["variant_id"]
