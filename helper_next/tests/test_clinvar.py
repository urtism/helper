import json
from datetime import datetime, timezone

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


def test_legacy_cache_is_enriched_once_with_submission_counts(tmp_path, monkeypatch):
    database = tmp_path / "clinvar.sqlite3"
    clinvar._store(database, "GRCh37|1|2160661|C|T", {
        "status": "available", "identifiers": ["139111", "VCV000139111.62"],
        "classifications": ["Benign"],
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

    assert calls == ["efetch.fcgi"]
    assert result["classification_breakdown"][0] == {"label": "Benign", "count": 12}
    assert result["cache"] == "hit"


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
