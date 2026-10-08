import pytest

from helper_variants import gnomad_frequency


def _response(variant=None, coverage=None, errors=None):
    return {
        "data": {
            "variant": variant,
            "region": {"coverage": {"genome": [coverage] if coverage else []}},
        },
        "errors": errors or [],
    }


def test_grch38_uses_v41_genomes_and_caches_frequency(tmp_path, monkeypatch):
    calls = []

    def fake_request(query, variables, timeout):
        calls.append(variables)
        return _response(
            variant={
                "variant_id": "1-11973063-G-C",
                "coverage": {"genome": {"mean": 30.4, "median": 30, "over_20": 0.91}},
                "genome": {
                    "ac": 2, "an": 100000, "ac_hom": 0, "ac_hemi": 0, "filters": [],
                    "populations": [
                        {"id": "nfe", "ac": 2, "an": 40000, "ac_hom": 0, "ac_hemi": 0},
                        {"id": "nfe_XX", "ac": 1, "an": 20000, "ac_hom": 0, "ac_hemi": 0},
                    ],
                },
            },
            coverage={"pos": 11973063, "mean": 30.4, "median": 30, "over_20": 0.91},
        )

    monkeypatch.setattr(gnomad_frequency, "_request_graphql", fake_request)
    database = tmp_path / "frequency.sqlite3"

    result = gnomad_frequency.lookup_variant(
        "hg38", "chr1", 11973063, "g", "c", database=database
    )

    assert result["status"] == "observed"
    assert result["dataset"] == "gnomad_r4"
    assert result["release"] == "4.1"
    assert result["af"] == 0.00002
    assert result["populations"] == [{
        "id": "nfe", "ac": 2, "an": 40000, "af": 0.00005,
        "ac_hom": 0, "ac_hemi": 0, "status": "observed",
    }]
    assert calls[0]["referenceGenome"] == "GRCh38"
    assert calls[0]["datasetId"] == "gnomad_r4"

    cached = gnomad_frequency.lookup_variant(
        "GRCh38", "1", 11973063, "G", "C", database=database
    )
    assert cached["cache"] == "hit"
    assert len(calls) == 1


def test_hg19_uses_v211_genomes(tmp_path, monkeypatch):
    captured = {}

    def fake_request(query, variables, timeout):
        captured.update(variables)
        return _response(
            variant={
                "variant_id": variables["variantId"],
                "coverage": {"genome": {"mean": 28, "median": 29, "over_20": 0.85}},
                "genome": {
                    "ac": 1, "an": 30000, "ac_hom": 0, "ac_hemi": 0,
                    "filters": [], "populations": [],
                },
            },
            coverage={"pos": 12033120, "mean": 28, "median": 29, "over_20": 0.85},
        )

    monkeypatch.setattr(gnomad_frequency, "_request_graphql", fake_request)
    result = gnomad_frequency.lookup_variant(
        "GRCh37", "1", 12033120, "G", "C", database=tmp_path / "v2.sqlite3"
    )

    assert result["release"] == "2.1.1"
    assert captured["datasetId"] == "gnomad_r2_1"
    assert captured["referenceGenome"] == "GRCh37"


def test_region_variants_are_returned_as_igv_features(monkeypatch):
    captured = {}

    def fake_request(query, variables, timeout):
        captured.update(variables)
        return {"data": {"region": {"variants": [{
            "variant_id": "2-200-A-G", "pos": 200, "ref": "A", "alt": "G",
            "genome": {"ac": 2, "an": 1000}, "exome": {"ac": 1, "an": 2000},
        }]}}}

    monkeypatch.setattr(gnomad_frequency, "_request_graphql", fake_request)

    features = gnomad_frequency.region_variants("hg38", "chr2", 150, 250)

    assert captured == {
        "chrom": "2", "start": 150, "stop": 250,
        "datasetId": "gnomad_r4", "referenceGenome": "GRCh38",
    }
    assert features == [{
        "chr": "chr2", "start": 199, "end": 200,
        "name": "A>G · AF 0.002", "variant_id": "2-200-A-G", "position": 200,
        "reference": "A", "alternate": "G", "af": 0.002,
        "genome_af": 0.002, "genome_ac": 2, "genome_an": 1000,
        "exome_af": 0.0005, "exome_ac": 1, "exome_an": 2000,
        "release": "4.1", "source": "gnomAD v4.1",
        "url": "https://gnomad.broadinstitute.org/variant/2-200-A-G?dataset=gnomad_r4",
    }]


def test_region_variants_reject_large_windows(monkeypatch):
    monkeypatch.setattr(
        gnomad_frequency, "_request_graphql",
        lambda *args: (_ for _ in ()).throw(AssertionError("network should not be used")),
    )

    with pytest.raises(ValueError, match="100000"):
        gnomad_frequency.region_variants("GRCh38", "1", 1, 100_002)


def test_missing_allele_is_only_absent_when_locus_coverage_is_adequate(tmp_path, monkeypatch):
    monkeypatch.setattr(
        gnomad_frequency, "_request_graphql",
        lambda *args: _response(
            variant=None,
            coverage={"pos": 100, "mean": 31, "median": 30, "over_20": 0.9},
            errors=[{"message": "Variant not found"}],
        ),
    )

    result = gnomad_frequency.lookup_variant(
        "GRCh38", "2", 100, "A", "G", database=tmp_path / "absent.sqlite3"
    )
    context = gnomad_frequency.priority_context(result)

    assert result["status"] == "not_observed_covered"
    assert result["population_absent"] is True
    assert context["population_absent"] is True
    assert context["population_coverage_adequate"] is True
    assert "population_af" not in context


def test_missing_allele_with_low_coverage_is_not_treated_as_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(
        gnomad_frequency, "_request_graphql",
        lambda *args: _response(
            variant=None,
            coverage={"pos": 100, "mean": 12, "median": 9, "over_20": 0.2},
            errors=[{"message": "Variant not found"}],
        ),
    )

    result = gnomad_frequency.lookup_variant(
        "GRCh38", "2", 100, "A", "T", database=tmp_path / "low.sqlite3"
    )

    assert result["status"] == "not_observed_low_coverage"
    assert gnomad_frequency.priority_context(result).get("population_absent") is None


def test_observed_frequency_context_uses_highest_major_population_af():
    context = gnomad_frequency.priority_context({
        "status": "observed", "release": "4.1", "filters": [],
        "af": 0.00001, "max_population_af": 0.00004,
    })

    assert context["population_af"] == 0.00004
    assert context["population_frequency_source"] == "gnomAD genomes v4.1"


def test_unsupported_mitochondrial_lookup_does_not_use_network(tmp_path, monkeypatch):
    monkeypatch.setattr(
        gnomad_frequency, "_request_graphql",
        lambda *args: (_ for _ in ()).throw(AssertionError("network should not be used")),
    )

    result = gnomad_frequency.lookup_variant(
        "GRCh38", "MT", 100, "A", "G", database=tmp_path / "mt.sqlite3"
    )

    assert result["status"] == "unsupported"
