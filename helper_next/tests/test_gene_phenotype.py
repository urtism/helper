import io

from helper_variants import gene_phenotype


HEADER = (
    "sgc_id,version_number,gene_curie,gene_symbol,disease_curie,disease_title,"
    "disease_original_curie,disease_original_title,classification_title,moi_curie,"
    "moi_title,submitter_title,submitted_as_date,submitted_as_public_report_url,"
    "submitted_as_pmids,submitted_as_assertion_criteria_url,submitted_run_date\n"
)


def test_builds_cache_and_aggregates_gene_disease_assertions(tmp_path):
    rows = (
        'SGC-1,1,HGNC:10896,SKI,MONDO:0008426,Shprintzen-Goldberg syndrome,'
        'OMIM:182212,SGS,Strong,HP:0000006,Autosomal dominant,PanelApp,'
        '2025-01-01,https://example.test/panel,PMID:1,https://example.test/criteria,2025-01-02\n'
        'SGC-2,1,HGNC:10896,SKI,MONDO:0008426,Shprintzen-Goldberg syndrome,'
        'ORPHA:2462,SGS,Definitive,HP:0000006,Autosomal dominant,ClinGen,'
        '2025-02-01,https://example.test/clingen,PMID:2,https://example.test/criteria,2025-02-02\n'
        'SGC-3,1,HGNC:10896,SKI,MONDO:0019999,Another phenotype,'
        ',,Limited,HP:0000007,Autosomal recessive,G2P,'
        '2025-03-01,,,https://example.test/criteria,2025-03-02\n'
    )
    database = tmp_path / "gene_phenotype.sqlite3"

    status = gene_phenotype.build_cache(io.StringIO(HEADER + rows), database)
    result = gene_phenotype.query_gene("SKI", "10896", database)

    assert status["status"] == "ready"
    assert status["row_count"] == 3
    assert result["association_count"] == 2
    assert result["assertion_count"] == 3
    first = result["associations"][0]
    assert first["disease_id"] == "MONDO:0008426"
    assert first["strongest_classification"] == "Definitive"
    assert first["original_disease_ids"] == ["OMIM:182212", "ORPHA:2462"]
    assert [assertion["source"] for assertion in first["assertions"]] == ["ClinGen", "PanelApp"]


def test_newer_submission_version_replaces_older_version(tmp_path):
    rows = (
        'SGC-1,1,HGNC:1,GENE1,MONDO:1,Old disease,,,Limited,HP:1,AD,Source,'
        '2025-01-01,,,,2025-01-02\n'
        'SGC-1,2,HGNC:1,GENE1,MONDO:2,Current disease,,,Strong,HP:1,AD,Source,'
        '2026-01-01,,,,2026-01-02\n'
    )
    database = tmp_path / "gene_phenotype.sqlite3"

    gene_phenotype.build_cache(io.StringIO(HEADER + rows), database)
    result = gene_phenotype.query_gene("GENE1", "HGNC:1", database)

    assert result["association_count"] == 1
    assert result["associations"][0]["disease"] == "Current disease"
    assert result["associations"][0]["strongest_classification"] == "Strong"


def test_missing_cache_returns_explicit_state(tmp_path):
    result = gene_phenotype.query_gene("SKI", "HGNC:10896", tmp_path / "missing.sqlite3")

    assert result["associations"] == []
    assert result["cache"]["status"] == "missing"


def test_enriches_exact_disease_with_hpo_features_and_g2p_mechanism(tmp_path):
    gencc = (
        HEADER
        + 'SGC-1,1,HGNC:10896,SKI,MONDO:0008426,Shprintzen-Goldberg syndrome,'
        'OMIM:182212,SGS,Definitive,HP:0000006,Autosomal dominant,ClinGen,'
        '2025-02-01,https://example.test/clingen,PMID:2,https://example.test/criteria,2025-02-02\n'
    )
    hpo = (
        "#description: test fixture\n"
        "database_id\tdisease_name\tqualifier\thpo_id\treference\tevidence\tonset\t"
        "frequency\tsex\tmodifier\taspect\tbiocuration\n"
        "OMIM:182212\tShprintzen-Goldberg syndrome\t\tHP:0000256\tPMID:1\tPCS\t"
        "HP:0003593\t8/10\t\t\tP\tHPO:test[2026-01-01]\n"
        "OMIM:999999\tOther disease\t\tHP:0001250\tPMID:2\tPCS\t\t\t\t\tP\tHPO:test\n"
    )
    hpo_terms = (
        "format-version: 1.2\n\n[Term]\n"
        "id: HP:0000256\nname: Macrocephaly\n\n[Term]\n"
        "id: HP:0001250\nname: Seizure\n"
    )
    g2p = (
        "g2p id,gene symbol,hgnc id,disease name,disease mim,disease MONDO,"
        "allelic requirement,confidence,molecular mechanism,molecular mechanism categorisation,"
        "molecular mechanism support,variant consequence,publications,date of last review\n"
        "G2P01276,SKI,HGNC:10896,SKI-related SGS,182212,MONDO:0008426,"
        "monoallelic_autosomal,definitive,dominant negative,altered complex,evidence,"
        "altered gene product structure,PMID:1,2026-01-15\n"
    )
    dosage = (
        "#ClinGen dosage test fixture\n"
        "#Gene Symbol\tGene ID\tcytoBand\tGenomic Location\t"
        "Haploinsufficiency Score\tHaploinsufficiency Description\t"
        "Haploinsufficiency PMID1\tTriplosensitivity Score\t"
        "Triplosensitivity Description\tTriplosensitivity PMID1\t"
        "Date Last Evaluated\tHaploinsufficiency Disease ID\t"
        "Triplosensitivity Disease ID\n"
        "SKI\t6497\t1p36.33\tchr1:1-10\t3\tSufficient evidence for dosage pathogenicity\t"
        "123456\t0\tNo evidence available\t\t2025-06-01\tMONDO:0008426\t\n"
    )
    orphadata = b'''<?xml version="1.0" encoding="UTF-8"?>
    <JDBOR><DisorderList><Disorder id="1">
      <OrphaCode>2462</OrphaCode><Name>Shprintzen-Goldberg syndrome</Name>
      <ExternalReferenceList>
        <ExternalReference><Source>ICD-10</Source><Reference>Q87.8</Reference>
          <DisorderMappingRelation><Name>NTBT (ORPHAcode is narrower than the targeted code)</Name></DisorderMappingRelation>
          <DisorderMappingICDRelation><Name>Attributed code</Name></DisorderMappingICDRelation>
          <DisorderMappingValidationStatus><Name>Validated</Name></DisorderMappingValidationStatus>
        </ExternalReference>
        <ExternalReference><Source>ICD-11</Source><Reference>LD2H.Y</Reference>
          <DisorderMappingRelation><Name>E (Exact mapping: the two concepts are equivalent)</Name></DisorderMappingRelation>
          <DisorderMappingICDRelation><Name>Specific code</Name></DisorderMappingICDRelation>
          <DisorderMappingValidationStatus><Name>Validated</Name></DisorderMappingValidationStatus>
          <DisorderMappingICDRefUrl>https://icd.who.int/example</DisorderMappingICDRefUrl>
          <DisorderMappingICDRefUri>123</DisorderMappingICDRefUri>
        </ExternalReference>
        <ExternalReference><Source>MONDO</Source><Reference>0008426</Reference>
          <DisorderMappingRelation><Name>E (Exact mapping: the two concepts are equivalent)</Name></DisorderMappingRelation>
        </ExternalReference>
        <ExternalReference><Source>OMIM</Source><Reference>182212</Reference>
          <DisorderMappingRelation><Name>E (Exact mapping: the two concepts are equivalent)</Name></DisorderMappingRelation>
        </ExternalReference>
      </ExternalReferenceList>
    </Disorder></DisorderList></JDBOR>'''
    database = tmp_path / "gene_knowledge.sqlite3"

    status = gene_phenotype.build_cache(
        io.StringIO(gencc), database,
        hpo_stream=io.StringIO(hpo), hpo_terms_stream=io.StringIO(hpo_terms),
        g2p_stream=io.StringIO(g2p), dosage_stream=io.StringIO(dosage),
        orphadata_stream=io.BytesIO(orphadata),
    )
    result = gene_phenotype.query_gene("SKI", "HGNC:10896", database)

    assert status["hpo_row_count"] == 2
    assert status["g2p_row_count"] == 1
    assert status["dosage_row_count"] == 1
    assert status["disease_code_count"] == 2
    association = result["associations"][0]
    assert association["phenotypic_feature_count"] == 1
    assert association["phenotypic_features"][0]["name"] == "Macrocephaly"
    assert association["phenotypic_features"][0]["frequencies"] == ["8/10"]
    assert association["molecular_mechanism"]["status"] == "supported"
    assert association["molecular_mechanism"]["value"] == "dominant negative"
    assert association["molecular_mechanism"]["records"][0]["id"] == "G2P01276"
    assert result["dosage_sensitivity"]["haploinsufficiency"]["score"] == "3"
    assert result["dosage_sensitivity"]["haploinsufficiency"]["disease_id"] == "MONDO:0008426"
    assert [(item["system"], item["code"]) for item in association["icd_codes"]] == [
        ("ICD-10", "Q87.8"), ("ICD-11", "LD2H.Y"),
    ]
    assert association["icd_codes"][0]["mapping_kind"] == "narrower-to-broader"
    assert association["icd_codes"][1]["source_url"] == "https://icd.who.int/example"


def test_caches_gnomad_constraint_metrics_per_gene(tmp_path, monkeypatch):
    database = tmp_path / "gene_knowledge.sqlite3"
    gene_phenotype.build_cache(io.StringIO(
        HEADER
        + "SGC-1,1,HGNC:10896,SKI,MONDO:0008426,SGS,,,Definitive,,AD,ClinGen,,,,,\n"
    ), database)
    response = io.BytesIO(b'''{
      "data": {"gene": {
        "gene_id": "ENSG00000157933",
        "symbol": "SKI",
        "canonical_transcript_id": "ENST00000378536",
        "gnomad_constraint": {
          "exp_lof": 24.1, "obs_lof": 2, "oe_lof": 0.083,
          "oe_lof_upper": 0.21, "pLI": 0.99, "lof_z": 5.1,
          "exp_mis": 120.0, "obs_mis": 80, "oe_mis": 0.667, "mis_z": 3.2
        }
      }}}
    ''')
    monkeypatch.setattr(gene_phenotype, "_open_request", lambda request, timeout: response)

    assert gene_phenotype.refresh_gnomad_constraint("SKI", database) is True
    result = gene_phenotype.query_gene("SKI", "HGNC:10896", database)

    assert result["gene_constraint"]["status"] == "ready"
    assert result["gene_constraint"]["pli"] == 0.99
    assert result["gene_constraint"]["loeuf"] == 0.21
    assert result["gene_constraint"]["missense_z"] == 3.2


def test_knowledge_download_retries_rate_limit(monkeypatch):
    calls = []
    response = object()

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout))
        if len(calls) == 1:
            raise gene_phenotype.HTTPError(
                request.full_url, 429, "rate limited", {"Retry-After": "0"}, None
            )
        return response

    monkeypatch.setattr(gene_phenotype, "urlopen", fake_urlopen)
    monkeypatch.setattr(gene_phenotype.time, "sleep", lambda _delay: None)

    assert gene_phenotype._open_source("https://example.test/data", {}, 5) is response
    assert len(calls) == 2
