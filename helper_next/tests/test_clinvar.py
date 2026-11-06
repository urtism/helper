import json
from datetime import datetime, timedelta, timezone
from urllib.error import URLError

import pytest

from helper_variants import clinvar


SUMMARY = {
    "result": {
        "uids": ["139111"],
        "139111": {
            "uid": "139111", "accession_version": "VCV000139111.62",
            "variation_set": [{
                "canonical_spdi": "NC_000001.11:2229221:C:T",
                "variation_loc": [{
                    "assembly_name": "GRCh37", "chr": "1", "start": "2160661",
                    "ref": "", "alt": "",
                }],
            }],
            "supporting_submissions": {
                "scv": ["SCV{:09d}".format(number) for number in range(12)],
                "rcv": ["RCV000128045"],
            },
            "germline_classification": {
                "description": "Benign/Likely benign",
                "last_evaluated": "2026/06/01 00:00",
                "review_status": "criteria provided, multiple submitters, no conflicts",
                "trait_set": [{
                    "trait_name": "Shprintzen-Goldberg syndrome",
                    "trait_xrefs": [
                        {"db_source": "MONDO", "db_id": "MONDO:0008426"},
                        {"db_source": "OMIM", "db_id": "182212"},
                    ],
                }],
            },
        },
    },
}
VCV_XML = b"""<?xml version="1.0"?>
<ClinVarResult-Set><VariationArchive VariationID="139111"><ClassifiedRecord>
  <Classifications><GermlineClassification>
    <Explanation DataSource="ClinVar" Type="public">Benign (12); Likely benign (1)</Explanation>
  </GermlineClassification></Classifications>
</ClassifiedRecord></VariationArchive></ClinVarResult-Set>"""


def test_bulk_cached_evidence_is_exact_and_never_fetches(tmp_path, monkeypatch):
    database = tmp_path / "clinvar.sqlite3"
    evidence = {
        "status": "available", "classifications": ["Likely pathogenic"],
        "classification_breakdown": [{"label": "Likely pathogenic", "count": 2}],
        "review_statuses": [{"label": "multiple submitters, no conflicts", "stars": 2}],
    }
    clinvar._store(database, "GRCh38|1|100|A|G", evidence)

    def unexpected_request(*args, **kwargs):
        raise AssertionError("Cached evidence must not fetch from ClinVar")

    monkeypatch.setattr(clinvar, "_request", unexpected_request)
    result = clinvar.cached_evidence([
        ("hg38", "chr1", 100, "a", "g"),
        ("GRCh38", "1", 100, "A", "T"),
        ("GRCh37", "1", 100, "A", "G"),
        ("unknown", "1", 100, "A", "G"),
    ], database)

    assert result[0]["classifications"] == evidence["classifications"]
    assert result[0]["availability"] == "AVAILABLE"
    assert result[0]["freshness"] == "FRESH"
    assert result[0]["cache"] == "hit"
    assert result[1:] == [{}, {}, {}]


def test_bulk_cached_evidence_retains_stale_and_ignores_malformed_records(tmp_path):
    database = tmp_path / "clinvar.sqlite3"
    clinvar._store(database, "GRCh38|1|100|A|G", {
        "status": "available", "classifications": ["Pathogenic"],
        "retrieved_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
    })
    with clinvar._connect(database) as connection:
        connection.execute(
            "INSERT INTO evidence VALUES (?, ?, ?)",
            ("GRCh38|1|101|A|G", "[]", datetime.now(timezone.utc).isoformat()),
        )
        connection.execute(
            "INSERT INTO evidence VALUES (?, ?, ?)",
            ("GRCh38|1|102|A|G", "invalid json", "invalid date"),
        )
    alleles = [
        ("GRCh38", "1", position, "A", "G") for position in (100, 101, 102)
    ]
    results = clinvar.cached_evidence(alleles, database)
    assert results[0]["availability"] == "AVAILABLE"
    assert results[0]["freshness"] == "STALE"
    assert all(result["availability"] == "ERROR" for result in results[1:])
    fresh_only = clinvar.cached_evidence(alleles, database, include_stale=False)
    assert fresh_only[0] == {}
    assert all(result["availability"] == "ERROR" for result in fresh_only[1:])


def test_bulk_cached_evidence_does_not_create_missing_cache(tmp_path):
    database = tmp_path / "missing.sqlite3"
    assert clinvar.cached_evidence([("GRCh38", "1", 100, "A", "G")], database) == [{}]
    assert not database.exists()


def test_lookup_matches_the_exact_allele_and_caches_the_result(tmp_path, monkeypatch):
    calls = []

    def fake_request(endpoint, parameters, timeout):
        calls.append((endpoint, parameters))
        if endpoint == "esearch.fcgi":
            return json.dumps({"esearchresult": {"idlist": ["520165", "139111"]}}).encode()
        if endpoint == "esummary.fcgi":
            return json.dumps(SUMMARY).encode()
        return VCV_XML

    monkeypatch.setattr(clinvar, "_request", fake_request)
    database = tmp_path / "clinvar.sqlite3"

    first = clinvar.lookup_variant(
        "GRCh37", "chr1", 2160661, "C", "T", database=database
    )
    second = clinvar.lookup_variant(
        "hg19", "1", 2160661, "C", "T", database=database
    )

    assert len(calls) == 3
    assert calls[0][1]["term"] == "1[chr] AND 2160661[chrpos37]"
    assert first["cache"] == "miss"
    assert second["cache"] == "hit"
    assert first["identifiers"] == ["139111", "VCV000139111.62"]
    assert first["classifications"] == ["Benign/Likely benign"]
    assert first["review_statuses"] == [{
        "label": "criteria provided, multiple submitters, no conflicts", "stars": 2,
    }]
    assert first["classification_breakdown"] == [
        {"label": "Benign", "count": 12},
        {"label": "Likely benign", "count": 1},
    ]
    assert first["conditions"] == ["Shprintzen-Goldberg syndrome"]
    assert first["condition_ids"] == ["MONDO:0008426", "OMIM:182212"]
    assert first["submission_count"] == 12
    assert first["submitter_count"] is None
    assert first["rcv_accessions"] == ["RCV000128045"]


def test_lookup_does_not_accept_a_different_alternate_allele(tmp_path, monkeypatch):
    monkeypatch.setattr(
        clinvar, "_request",
        lambda endpoint, parameters, timeout: (
            json.dumps({"esearchresult": {"idlist": ["139111"]}}).encode()
            if endpoint == "esearch.fcgi" else json.dumps(SUMMARY).encode()
        ),
    )

    result = clinvar.lookup_variant(
        "GRCh37", "1", 2160661, "C", "G", database=tmp_path / "cache.sqlite3"
    )

    assert result["status"] == "not_found"


def test_legacy_cache_breakdown_is_optional_and_can_be_requested_once(tmp_path, monkeypatch):
    database = tmp_path / "clinvar.sqlite3"
    clinvar._store(database, "GRCh37|1|2160661|C|T", {
        "status": "available", "identifiers": ["139111", "VCV000139111.62"],
        "classifications": ["Benign"], "review_statuses": [],
        "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    calls = []

    def fake_request(endpoint, parameters, timeout):
        calls.append(endpoint)
        return VCV_XML

    monkeypatch.setattr(clinvar, "_request", fake_request)

    result = clinvar.lookup_variant(
        "GRCh37", "1", 2160661, "C", "T", database=database
    )
    assert calls == []
    assert "classification_breakdown" not in result
    result = clinvar.lookup_variant(
        "GRCh37", "1", 2160661, "C", "T", database=database, require_breakdown=True
    )
    clinvar.lookup_variant(
        "GRCh37", "1", 2160661, "C", "T", database=database, require_breakdown=True
    )

    assert calls == ["efetch.fcgi"]
    assert result["classification_breakdown"][0] == {"label": "Benign", "count": 12}
    assert result["cache"] == "hit"


def test_refresh_bypasses_a_fresh_cached_clinvar_result(tmp_path, monkeypatch):
    database = tmp_path / "clinvar.sqlite3"
    clinvar._store(database, "GRCh38|1|100|A|G", {
        "status": "available", "classifications": ["Pathogenic"],
        "identifiers": ["1"], "retrieved_at": datetime.now(timezone.utc).isoformat(),
    })
    requests = []

    def fake_request(endpoint, parameters, timeout):
        requests.append(endpoint)
        return json.dumps({"esearchresult": {"idlist": []}}).encode()

    monkeypatch.setattr(clinvar, "_request", fake_request)

    result = clinvar.lookup_variant(
        "GRCh38", "1", 100, "A", "G", database=database, refresh=True
    )

    assert requests == ["esearch.fcgi"]
    assert result["status"] == "not_found"
    assert result["cache"] == "miss"


def test_merge_prefers_the_current_aggregate_classification_and_review():
    merged = clinvar.merge_evidence(
        {"status": "available", "classifications": ["Benign"], "identifiers": []},
        {
            "status": "available", "classifications": ["Benign/Likely benign"],
            "identifiers": ["139111"], "review_statuses": [
                {"label": "criteria provided, multiple submitters, no conflicts", "stars": 2}
            ],
        },
    )

    assert merged["classifications"] == ["Benign/Likely benign"]
    assert merged["review_statuses"][0]["stars"] == 2
    assert merged["has_conflict"] is False
    assert merged["retrieval_status"] == "available"


def test_merge_marks_an_actual_conflicting_classification():
    merged = clinvar.merge_evidence({}, {
        "status": "available", "classifications": ["Conflicting classifications"],
        "review_statuses": [{
            "label": "criteria provided, conflicting classifications", "stars": 1,
        }],
    })

    assert merged["has_conflict"] is True


@pytest.mark.parametrize("status,age,expected_calls", [
    ("available", timedelta(days=6), 0),
    ("available", timedelta(days=8), 1),
    ("not_found", timedelta(hours=12), 0),
    ("not_found", timedelta(days=2), 1),
])
def test_lookup_respects_positive_and_negative_ttl(tmp_path, monkeypatch, status, age, expected_calls):
    database = tmp_path / "cache.sqlite3"
    clinvar._store(database, "GRCh38|1|100|A|G", {
        "status": status, "classifications": ["Benign"] if status == "available" else [],
        "review_statuses": [], "classification_breakdown": [],
        "retrieved_at": (datetime.now(timezone.utc) - age).isoformat(),
    })
    calls = []

    def request(*args):
        calls.append(args)
        return b'{"esearchresult":{"idlist":[]}}'

    monkeypatch.setattr(clinvar, "_request", request)
    result = clinvar.lookup_variant("GRCh38", "1", 100, "A", "G", database)
    assert len(calls) == expected_calls
    assert result["freshness"] == "FRESH"
    assert result["availability"] == ("NOT_FOUND" if expected_calls or status == "not_found" else "AVAILABLE")


@pytest.mark.parametrize("age", [timedelta(hours=1), timedelta(days=8)])
def test_failed_refresh_retains_evidence_and_acquisition_time(tmp_path, monkeypatch, age):
    database = tmp_path / "cache.sqlite3"
    acquired = (datetime.now(timezone.utc) - age).isoformat()
    clinvar._store(database, "GRCh38|1|100|A|G", {
        "status": "available", "identifiers": ["1", "VCV000000001.2"],
        "classifications": ["Pathogenic"], "review_statuses": [],
        "classification_breakdown": [], "retrieved_at": acquired,
        "record_updated": "2026-01-01", "provenance": {"fixture": "retained"},
    })

    def request(*args):
        raise URLError("fixture network failure")

    monkeypatch.setattr(clinvar, "_request", request)
    result = clinvar.lookup_variant("GRCh38", "1", 100, "A", "G", database, refresh=True)
    assert result["availability"] == "AVAILABLE"
    assert result["freshness"] == ("STALE" if age.days else "FRESH")
    assert result["retrieved_at"] == acquired
    assert "fixture network failure" in result["last_error"]
    stored = clinvar.lookup_variant("GRCh38", "1", 100, "A", "G", database, fetch=False)
    assert stored == result
    assert stored["provenance"] == {"fixture": "retained"}
    assert stored["record_updated"] == "2026-01-01"


@pytest.mark.parametrize("response", [None, b'{}', b'{"esearchresult":{}}',
                                      b'{"esearchresult":{"idlist":[],"ERROR":"bad query"}}'])
def test_transport_and_invalid_responses_are_not_negative_cache_entries(tmp_path, monkeypatch, response):
    def request(*args):
        if response is None:
            raise URLError("offline fixture")
        return response

    monkeypatch.setattr(clinvar, "_request", request)
    database = tmp_path / "cache.sqlite3"
    result = clinvar.lookup_variant("GRCh38", "1", 100, "A", "G", database)
    assert result["availability"] == "ERROR"
    assert result["freshness"] == "UNKNOWN"
    assert result["last_error"]
    assert not database.exists()


def test_incomplete_aggregate_is_fetched_and_empty_breakdown_is_complete(tmp_path, monkeypatch):
    database = tmp_path / "cache.sqlite3"
    clinvar._store(database, "GRCh37|1|2160661|C|T", {
        "status": "available", "identifiers": ["139111"],
    })
    calls = []

    def request(endpoint, parameters, timeout):
        calls.append(endpoint)
        if endpoint == "esearch.fcgi":
            return b'{"esearchresult":{"idlist":["139111"]}}'
        if endpoint == "esummary.fcgi":
            return json.dumps(SUMMARY).encode()
        return b"<ClinVarResult-Set/>"

    monkeypatch.setattr(clinvar, "_request", request)
    for _ in range(3):
        result = clinvar.lookup_variant("GRCh37", "1", 2160661, "C", "T", database, require_breakdown=True)
        assert result["availability"] == "AVAILABLE"
        assert result["classification_breakdown"] == []
    assert calls == ["esearch.fcgi", "esummary.fcgi", "efetch.fcgi"]


@pytest.mark.parametrize("offline", [False, True])
def test_offline_forbids_refresh_and_optional_enrichment(tmp_path, monkeypatch, offline):
    monkeypatch.setenv("HELPER_CLINVAR_OFFLINE", "1" if offline else "0")
    monkeypatch.setattr(clinvar, "_request", lambda *args: pytest.fail("unexpected HTTP"))
    database = tmp_path / "cache.sqlite3"
    args = ("GRCh38", "1", 100, "A", "G")
    options = {"refresh": True, "require_breakdown": True, "fetch": offline}
    result = clinvar.lookup_variant(*args, database=database, **options)
    assert result["availability"] == "NOT_QUERIED"
    assert not database.exists()
    clinvar._store(database, "GRCh38|1|100|A|G", {
        "status": "available", "classifications": ["Benign"], "identifiers": ["1"],
        "retrieved_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
    })
    result = clinvar.lookup_variant(*args, database=database, **options)
    assert result["availability"] == "AVAILABLE"
    assert result["freshness"] == "STALE"


def test_unsupported_multiallelic_query_never_merges_alternates(tmp_path, monkeypatch):
    monkeypatch.setattr(clinvar, "_request", lambda *args: pytest.fail("unexpected HTTP"))
    result = clinvar.lookup_variant("GRCh38", "1", 100, "A", "G,T", tmp_path / "cache.sqlite3")
    assert result["availability"] == "UNSUPPORTED"


def test_batch_deduplicates_sql_and_preserves_all_positions(tmp_path, monkeypatch):
    database = tmp_path / "cache.sqlite3"
    clinvar._store(database, "GRCh38|1|100|A|G", {
        "status": "available", "classifications": ["Benign"], "review_statuses": [],
    })
    queries = []
    connect = clinvar.sqlite3.connect

    def traced_connect(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connection.set_trace_callback(queries.append)
        return connection

    monkeypatch.setattr(clinvar.sqlite3, "connect", traced_connect)
    monkeypatch.setattr(clinvar, "_request", lambda *args: pytest.fail("unexpected HTTP"))
    alleles = [("GRCh38", "1", 100, "A", alt) for alt in ["G", "T"] * 550]
    results = clinvar.cached_evidence(alleles, database)
    assert len(results) == 1100
    assert all(result.get("availability") == "AVAILABLE" for result in results[::2])
    assert results[1::2] == [{}] * 550
    assert len([query for query in queries if query.startswith("SELECT")]) == 1


def test_invalid_existing_cache_is_error_when_fetch_is_forbidden(tmp_path):
    database = tmp_path / "cache.sqlite3"
    with clinvar._connect(database) as connection:
        connection.execute("INSERT INTO evidence VALUES (?, ?, ?)", (
            "GRCh38|1|100|A|G", "invalid json", datetime.now(timezone.utc).isoformat(),
        ))
    result = clinvar.lookup_variant("GRCh38", "1", 100, "A", "G", database, fetch=False)
    assert result["availability"] == "ERROR"
    assert result["freshness"] == "UNKNOWN"
    assert result["last_error"]


@pytest.mark.parametrize("reference,alternate", [("AT", "A"), ("A", "<DEL>"), ("N", "T")])
def test_existing_lookup_does_not_require_a_resolved_ga2_or_fasta(tmp_path, monkeypatch, reference, alternate):
    calls = []

    def request(*args):
        calls.append(args)
        return b'{"esearchresult":{"idlist":[]}}'

    monkeypatch.setattr(clinvar, "_request", request)
    result = clinvar.lookup_variant("GRCh38", "1", 100, reference, alternate, tmp_path / "cache.sqlite3")
    assert result["availability"] == "NOT_FOUND"
    assert len(calls) == 1


def test_fresh_record_without_germline_assertion_is_complete(tmp_path, monkeypatch):
    database = tmp_path / "cache.sqlite3"
    clinvar._store(database, "GRCh38|1|100|A|G", {
        "status": "available", "identifiers": ["1"],
        "classifications": [], "review_statuses": [], "classification_breakdown": [],
    })
    monkeypatch.setattr(clinvar, "_request", lambda *args: pytest.fail("unexpected HTTP"))
    result = clinvar.lookup_variant("GRCh38", "1", 100, "A", "G", database)
    assert result["availability"] == "AVAILABLE"
    assert result["cache"] == "hit"
