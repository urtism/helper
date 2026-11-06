"""Synthetic allele/reference fixtures; expected metrics use explicit arithmetic."""
import copy
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from helper_next.core.acmg_digest import digest
from helper_next.core.acmg_molecular_impact import analyze_transcripts, annotation_release
from helper_next.core.acmg_sources import SourceManager
from helper_next.core.acmg_transcripts import TranscriptReferenceProvider, complement, mrna_to_genomic, qualify, translate
from pvs1.calculator import calculate_pvs1
from pvs1.impact import molecular_impact
from pvs1.models import PVS1Input


GENE = "ENSG00000000001"
TX = "ENST00000000001.1"


def reference(cds="ATGAAACTAAAGCAATAA", utr="CCC", strand="+", first_exon=None, tx=TX):
    cdna = "GGG" + cds + utr
    lengths = [first_exon, len(cdna) - first_exon] if first_exon else [len(cdna)]
    starts = [1000, 10000] if strand == "+" else [10000, 1000]
    exons, cursor = [], 1
    for index, length in enumerate(lengths):
        exons.append({"id": "EX" + str(index), "start": starts[index], "end": starts[index] + length - 1,
                      "assembly_name": "GRCh38", "seq_region_name": "1", "strand": 1 if strand == "+" else -1,
                      "genomic_start": starts[index], "genomic_end": starts[index] + length - 1,
                      "mrna_start": cursor, "mrna_end": cursor + length - 1})
        cursor += length
    endpoints = [mrna_to_genomic(exons, strand, p) for p in (4, 3 + len(cds))]
    accession, version = tx.split(".")
    lookup = {"id": accession, "version": int(version), "assembly_name": "GRCh38", "species": "homo_sapiens",
              "object_type": "Transcript", "Parent": GENE, "biotype": "protein_coding",
              "seq_region_name": "1", "strand": 1 if strand == "+" else -1, "length": len(cdna),
              "start": min(e["start"] for e in exons), "end": max(e["end"] for e in exons), "Exon": exons,
              "Translation": {"id": accession.replace("ENST", "ENSP"), "start": min(endpoints), "end": max(endpoints), "length": len(cds) // 3 - 1}}
    raw = {"lookup": lookup, "release_before": {"releases": [116]}, "release_after": {"releases": [116]},
           "cdna": {"id": accession, "seq": cdna}, "cds": {"id": accession, "seq": cds},
           "protein": {"id": lookup["Translation"]["id"], "seq": translate(cds)[:-1]}, "hgnc": []}
    ref = qualify(raw, tx, "GRCh38", "116")
    ref.update(artifact_digest=digest(raw), source_urls={"fixture": "synthetic:test"},
               coordinate_convention="1-based inclusive; transcript 5-prime to 3-prime; CDS includes stop")
    return ref, raw


def allele(ref, cds_position=4, delete=False):
    mrna = ref["cds_start"] + cds_position - 1
    if delete:
        # VCF anchoring is in genomic orientation on both strands.
        genomic = mrna_to_genomic(ref["exons"], ref["strand"], mrna)
        position = genomic - 1
        by_genomic = {}
        for p in (position, genomic):
            for e in ref["exons"]:
                if e["genomic_start"] <= p <= e["genomic_end"]:
                    rna = e["mrna_start"] + (p - e["genomic_start"] if ref["strand"] == "+" else e["genomic_end"] - p)
                    base = ref["cdna"][rna - 1]
                    by_genomic[p] = base if ref["strand"] == "+" else complement(base)
        original = by_genomic[position] + by_genomic[genomic]
        alternate = original[0]
    else:
        position = mrna_to_genomic(ref["exons"], ref["strand"], mrna)
        original, alternate = ref["cdna"][mrna - 1], "T"
        if ref["strand"] == "-":
            original, alternate = complement(original), complement(alternate)
    return {"assembly": "GRCh38", "contig": "1", "position": position,
            "reference_allele": original, "alternate_allele": alternate, "coordinate_system": "genomic_1_based"}


def decision(variant, row, consequence):
    context = {"gene": GENE, "disease": "SYNTHETIC", "inheritance": "AD", "scope": "DISEASE_SPECIFIC",
               "molecular_mechanism": "LoF", "confidence": "DEFINITIVE"}
    context["source_refs"] = {k: ["synthetic:curation"] for k in context}
    return calculate_pvs1(PVS1Input(variant=dict(variant, consequence=consequence), disease_context=context,
                                   **row["pvs1_input"]))


def test_stop_gain_eighty_percent_is_not_physical_deletion():
    ref, _ = reference(cds="ATG" + "CAA" * 499 + "TAA", first_exon=600)
    row = molecular_impact(allele(ref, 301), GENE, TX, ref, "stop_gained")
    assert row["status"] == "AFFECTED_CODING"
    assert row["cds_length_nt"] == 1503 and row["translated_cds_length_nt"] == 1500
    assert row["first_affected_reference_codon"] == row["termination_codon"] == 101
    assert row["predicted_protein_length"] == 100
    assert row["reference_amino_acids_lost"] == 400
    assert row["reference_cds_untranslated_percent"] == row["protein_impact_percent"] == 80
    assert row["physical_cds_deleted_percent"] == 0 and row["nmd_predicted"] is True


def test_terminal_stop_gain_has_no_nmd():
    ref, _ = reference()
    row = molecular_impact(allele(ref, 13), GENE, TX, ref, "stop_gained")
    assert row["status"] == "AFFECTED_CODING" and row["nmd_predicted"] is False
    assert row["reference_cds_untranslated_percent"] == 20


@pytest.mark.parametrize("nmd", [False, True])
def test_frameshift_separates_reference_change_replacement_and_shortening(nmd):
    cds = "ATGAAACTAAAGCAA" + ("CAA" * 40 if nmd else "") + "TAA"
    ref, _ = reference(cds=cds, first_exon=100 if nmd else None)
    row = molecular_impact(allele(ref, delete=True), GENE, TX, ref, "frameshift_variant")
    n = 45 if nmd else 5
    assert row["status"] == "AFFECTED_CODING" and row["nmd_predicted"] is nmd
    # Removing CDS base 4: ATG AAC TAA ... -> MN*, not the original MKLKQ...
    assert row["termination_codon"] == 3 and row["predicted_protein_length"] == 2
    assert row["physical_deleted_nt"] == 1 and row["physical_inserted_nt"] == 0
    assert row["physical_cds_deleted_percent"] == pytest.approx(100 / (3 * n))
    assert row["reference_cds_disrupted_percent"] == pytest.approx(100 * (n - 1) / n)
    assert row["reference_amino_acids_replaced"] == 1
    assert row["reference_amino_acids_lost"] == row["predicted_protein_shortening_aa"] == n - 2
    assert row["protein_impact_percent"] == pytest.approx(100 * (n - 1) / n)
    result = decision(allele(ref, delete=True), row, "frameshift_variant")
    if nmd:
        assert result.applied_strength == "VERY_STRONG"
    else:
        # 80% altered CDS/protein is not a pure protein deletion for P12/P13.
        assert result.applied_strength is None and any("regione realmente persa" in m for m in result.missing_data)


def test_frameshift_extends_into_utr_without_inventing_a_ptc():
    ref, _ = reference(cds="ATG" + "CAA" * 5 + "TAA", utr="ATAA")
    row = molecular_impact(allele(ref, delete=True), GENE, TX, ref, "frameshift_variant")
    assert row["status"] == "AFFECTED_CODING"
    # ATG AAC AAC AAC AAC AAT AAA TAA -> MNNNNNK*, 7 aa vs 6 reference aa.
    assert row["predicted_protein_length"] == 7 and row["termination_codon"] == 8
    assert row["extends_into_utr"] is True and row["ptc_mrna_position"] is None
    assert row["predicted_protein_shortening_aa"] == row["reference_amino_acids_lost"] == 0
    assert row["reference_amino_acids_replaced"] == 5
    assert row["reference_cds_disrupted_percent"] == pytest.approx(500 / 6)
    assert row["nmd_predicted"] is False
    assert decision(allele(ref, delete=True), row, "frameshift_variant").applied_strength is None


def test_unresolved_stop_retains_disrupted_cds_metric_only():
    ref, _ = reference(cds="ATG" + "CAA" * 5 + "TAA", utr="CCC")
    row = molecular_impact(allele(ref, delete=True), GENE, TX, ref, "frameshift_variant")
    assert row["status"] == "INSUFFICIENT_DATA"
    assert row["termination_codon"] is row["predicted_protein_length"] is row["protein_impact_percent"] is None
    assert row["reference_cds_disrupted_percent"] == pytest.approx(500 / 6)
    assert row["pvs1_input"] is None and row["missing_data"]


def test_frameshift_can_disrupt_more_cds_than_protein_sequence():
    ref, _ = reference(cds="ATGAAAAAACTGCAATAA", utr="ATAA")
    row = molecular_impact(allele(ref, delete=True), GENE, TX, ref, "frameshift_variant")
    # MKKLQ* -> MKN CNK* (MKNCNK): codon 2 still encodes Lys after the deletion.
    assert row["status"] == "AFFECTED_CODING" and row["first_divergent_aa"] == 3
    assert row["reference_cds_disrupted_percent"] == 80
    assert row["protein_impact_percent"] == 60 and row["predicted_protein_length"] == 6
    assert row["predicted_protein_shortening_aa"] == 0


@pytest.mark.parametrize("strand", ["+", "-"])
def test_exact_strand_mapping_for_stop_and_normalized_indel(strand):
    ref, _ = reference(strand=strand)
    stop = molecular_impact(allele(ref, 13), GENE, TX, ref, "stop_gained")
    fs = molecular_impact(allele(ref, delete=True), GENE, TX, ref, "frameshift_variant")
    assert stop["status"] == fs["status"] == "AFFECTED_CODING"
    assert stop["cds_position"] == 13 and fs["cds_position"] == 4


def test_partial_cds_or_wrong_alleles_never_produce_metrics():
    ref, _ = reference()
    partial = copy.deepcopy(ref)
    partial["cds"] = partial["cds"][:-3]
    row = molecular_impact(allele(ref, 13), GENE, TX, partial, "stop_gained")
    assert row["status"] == "INSUFFICIENT_DATA" and row["protein_impact_percent"] is None
    for change in ({"reference_allele": "G"}, {"alternate_allele": "T,G"}, {"alternate_allele": "<DEL>"}, {"assembly": "GRCh37"}):
        row = molecular_impact(dict(allele(ref, 13), **change), GENE, TX, ref, "stop_gained")
        assert row["status"] == "INSUFFICIENT_DATA" and row["pvs1_input"] is None


def test_mixed_splice_frameshift_is_computed_but_pvs1_requires_review():
    ref, _ = reference(cds="ATGAAACTAAAGCAA" + "CAA" * 40 + "TAA", first_exon=100)
    row = molecular_impact(allele(ref, delete=True), GENE, TX, ref, "frameshift_variant&splice_region_variant")
    assert row["status"] == "AFFECTED_CODING" and row["conditional"]
    result = decision(allele(ref, delete=True), row, "frameshift_variant&splice_region_variant")
    assert result.status == "REQUIRES_REVIEW" and result.applied_strength is None
    assert any("condizionale" in m for m in result.warnings)


def test_conflicting_vep_stop_is_not_used_for_decision():
    ref, _ = reference()
    row = molecular_impact(allele(ref, 13), GENE, TX, ref, "stop_gained", {"hgvsp": "p.Gln2Ter"})
    assert row["status"] == "INSUFFICIENT_DATA" and row["pvs1_input"] is None
    assert any("HGVSp" in m for m in row["missing_data"])


@pytest.mark.parametrize("distance, strength", [(49, "STRONG"), (50, "STRONG"), (51, "VERY_STRONG")])
def test_nmd_boundary_is_independent_of_reference_percentages(distance, strength):
    ref, _ = reference(cds="ATG" + "CAA" * 99 + "TAA", first_exon=7 + distance)
    variant = allele(ref, 4)
    row = molecular_impact(variant, GENE, TX, ref, "stop_gained")
    assert row["nmd_distance_nt"] == distance and row["reference_cds_untranslated_percent"] == 99
    assert decision(variant, row, "stop_gained").applied_strength == strength


@pytest.mark.parametrize("lost, strength", [(9, "MODERATE"), (11, "STRONG")])
def test_pvs1_protein_loss_threshold_is_from_the_product(lost, strength):
    ref, _ = reference(cds="ATG" + "CAA" * 99 + "TAA")
    variant = allele(ref, 3 * (100 - lost) + 1)
    row = molecular_impact(variant, GENE, TX, ref, "stop_gained")
    assert row["protein_impact_percent"] == lost and row["physical_cds_deleted_percent"] == 0
    assert decision(variant, row, "stop_gained").applied_strength == strength


def annotation(tx=TX, consequence="stop_gained", identifier=1):
    return {"id": identifier, "gene": "SYNTHETIC", "transcript": tx, "consequence": consequence,
            "release_key": "synthetic-116", "metadata": {"fields": {"Gene": GENE, "BIOTYPE": "protein_coding"}},
            "release_resources": {"header_metadata": ['##VEP="v116" ensembl=116.1']}}


def sources(tmp_path, raws, extra=None):
    calls = []
    txs = [copy.deepcopy(raw["lookup"]) for raw in raws]
    txs.extend(extra or [])
    gene = {"id": GENE, "version": 1, "assembly_name": "GRCh38", "species": "homo_sapiens",
            "object_type": "Gene", "seq_region_name": "1", "strand": 1, "Transcript": txs}

    def fetch(url):
        calls.append(url)
        path, params = urlsplit(url).path, parse_qs(urlsplit(url).query)
        if path == "/info/data":
            return {"releases": [116]}
        if path == "/lookup/id/" + GENE:
            return copy.deepcopy(gene)
        if path.startswith("/xrefs/"):
            return []
        for raw in raws:
            if path == "/lookup/id/" + raw["lookup"]["id"]:
                return copy.deepcopy(raw["lookup"])
            if path.startswith("/sequence/id/"):
                key = params["type"][0]
                if path.endswith(raw[key]["id"]):
                    return copy.deepcopy(raw[key])
        raise AssertionError("Unexpected reference request: " + url)

    provider = TranscriptReferenceProvider(cache=tmp_path / "transcripts", release="116", fetch_json=fetch)
    return SourceManager(transcript_provider=provider), calls, gene


def detail_for(variant, annotations):
    return {"reference_build": variant["assembly"], "chromosome": variant["contig"], "position": variant["position"],
            "reference": variant["reference_allele"], "alternate": variant["alternate_allele"], "annotations": annotations}


def test_gene_catalog_fills_in_missing_vep_with_independent_consequences_and_cache(tmp_path, monkeypatch):
    monkeypatch.delenv("HELPER_TRANSCRIPT_FETCH", raising=False)
    ref, raw1 = reference(cds="ATG" + "CAA" * 4 + "TAA", utr="CCTAA", first_exon=6)
    _, raw2 = reference(cds="ATGA" + "CAA" * 4 + "TAACCTAA", utr="", first_exon=7, tx="ENST00000000002.2")
    raw2["lookup"]["MANE"] = [{"type": "MANE_Select"}]
    nc = {"id": "ENST00000000003", "version": 1, "Parent": GENE, "assembly_name": "GRCh38",
          "seq_region_name": "1", "strand": 1, "biotype": "lncRNA", "Exon": []}
    manager, calls, _ = sources(tmp_path, [raw1, raw2], [nc])
    selected = annotation()
    detail = detail_for(allele(ref, 4), [selected])
    before = copy.deepcopy(detail)
    result = analyze_transcripts(detail, selected, manager)
    assert result["catalog_complete"] and result["release_verified"]
    rows = result["transcripts"]
    assert [r["status"] for r in rows] == ["AFFECTED_CODING", "OTHER_CONSEQUENCE", "NON_CODING"]
    assert rows[0]["reference_cds_untranslated_percent"] == 80
    assert rows[1]["protein_impact_percent"] is None
    assert rows[1]["cds_position"] == 5  # Same genomic C is codon 2 base 2: ACA -> ATA.
    assert detail == before
    count = len(calls)
    second = analyze_transcripts(detail, selected, manager)
    assert len(calls) == count and len(second["transcripts"]) == 3
    assert sum("/lookup/id/" + GENE in url for url in calls) == 1
    # A second variant shares every public reference; no HTTP requests.
    detail["alternate"] = "G"
    analyze_transcripts(detail, selected, manager)
    assert len(calls) == count


def test_catalog_not_affected_and_partial_cds_rows_remain_visible(tmp_path, monkeypatch):
    monkeypatch.setenv("HELPER_TRANSCRIPT_FETCH", "1")
    ref, raw1 = reference(cds="ATG" + "CAA" * 4 + "TAA")
    _, raw2 = reference(tx="ENST00000000002.1")
    # Move a distinct coding transcript away from the allele.
    for exon in raw2["lookup"]["Exon"]:
        exon["start"] += 30000
        exon["end"] += 30000
    raw2["lookup"]["Translation"]["start"] += 30000
    raw2["lookup"]["Translation"]["end"] += 30000
    _, raw3 = reference(tx="ENST00000000003.1")
    raw3["cds"]["seq"] = raw3["cds"]["seq"][:-3]
    manager, _, _ = sources(tmp_path, [raw1, raw2, raw3])
    selected = annotation()
    result = analyze_transcripts(detail_for(allele(ref, 4), [selected]), selected, manager)
    assert [r["status"] for r in result["transcripts"]] == ["AFFECTED_CODING", "NOT_AFFECTED", "INSUFFICIENT_DATA"]


def test_absent_cache_offline_and_unknown_release_are_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("HELPER_TRANSCRIPT_FETCH", "0")
    ref, raw = reference(cds="ATG" + "CAA" * 4 + "TAA")
    manager, calls, _ = sources(tmp_path, [raw])
    selected = annotation()
    result = analyze_transcripts(detail_for(allele(ref, 4), [selected]), selected, manager)
    assert not result["catalog_complete"] and not calls
    assert result["transcripts"][0]["status"] == "INSUFFICIENT_DATA"
    monkeypatch.delenv("HELPER_ENSEMBL_RELEASE", raising=False)
    selected["release_resources"] = {}
    result = analyze_transcripts(detail_for(allele(ref, 4), [selected]), selected)
    assert result["release"] is None and result["transcripts"] and result["warnings"]


def test_release_mismatch_never_fetches_a_different_release(tmp_path, monkeypatch):
    monkeypatch.setenv("HELPER_TRANSCRIPT_FETCH", "1")
    ref, raw = reference(cds="ATG" + "CAA" * 4 + "TAA")
    manager, calls, _ = sources(tmp_path, [raw])
    manager.transcript_provider.release = "115"
    selected = annotation()
    selected["release_resources"] = {"header_metadata": ['##VEP="v115" ensembl=115.1']}
    result = analyze_transcripts(detail_for(allele(ref, 4), [selected]), selected, manager)
    assert not result["catalog_complete"] and len(calls) == 1
    assert result["transcripts"][0]["status"] == "INSUFFICIENT_DATA"


def test_transcript_versions_and_unversioned_vep_resolution(tmp_path):
    ref, raw = reference(cds="ATG" + "CAA" * 4 + "TAA")
    manager, _, _ = sources(tmp_path, [raw])
    selected = annotation(tx=TX.split(".")[0])
    stale = annotation(tx=TX.replace(".1", ".9"), identifier=2)
    result = analyze_transcripts(detail_for(allele(ref, 4), [selected, stale]), selected, manager)
    assert result["transcripts"][0]["transcript"] == TX and result["transcripts"][0]["selected"]
    assert result["transcripts"][1]["status"] == "INSUFFICIENT_DATA"


@pytest.mark.parametrize("headers, expected", [
    (['##VEP="v116" ensembl=113.2'], "113"),
    (['##VEP="v116"'], "116"),
    (['##VEP="v116" ensembl=113.2', '##command=vep --cache_version 115'], None),
    ([], None),
])
def test_header_release_provenance(headers, expected):
    assert annotation_release({"release_resources": {"header_metadata": headers}})[0] == expected


def test_api_molecular_analysis_survives_missing_disease_mechanism(tmp_path, monkeypatch):
    from helper_next.api import acmg_calculator as api
    ref, raw = reference(cds="ATG" + "CAA" * 4 + "TAA")
    manager, _, _ = sources(tmp_path, [raw])
    selected = annotation()
    detail = detail_for(allele(ref, 4), [selected])
    monkeypatch.setattr(api, "_entry", lambda _: {})
    monkeypatch.setattr(api, "_entry_database", lambda _: "synthetic")
    monkeypatch.setattr(api.query, "variant_detail", lambda *args: detail)
    monkeypatch.setattr(api, "analyze_transcripts", lambda d, a: analyze_transcripts(d, a, manager))
    response = api.evaluate_pvs1({"run_id": "synthetic", "sample_id": 1, "variant_id": 1, "annotation_id": 1, "transcript": TX})
    assert response["result"]["status"] == "NOT_EVALUABLE"  # No LoF context.
    assert response["molecular_impact"]["transcripts"][0]["protein_impact_percent"] == 80
    assert response["input"]["molecular_effect"]["products"][0]["ptc_start"] == 7
    assert "pvs1_input" not in response["molecular_impact"]["transcripts"][0]
    # Standalone artifact for the manual example documented with this task.
    (tmp_path / "multi-transcript-output.json").write_text(json.dumps(response["molecular_impact"], indent=2))


def test_vep_indexer_preserves_nonpicked_rows_and_separates_alt_alleles(tmp_path, monkeypatch):
    from helper_variants import indexer
    captured = []
    monkeypatch.setattr(indexer.variant_store, "record_annotation", lambda db, variant, release, **kwargs: captured.append((variant, kwargs)))
    layout = ["Allele", "Consequence", "Gene", "Feature", "ALLELE_NUM", "PICK"]
    info = {"CSQ": "T|stop_gained|" + GENE + "|" + TX + "|1|1,T|missense_variant|" + GENE
            + "|ENST00000000002.1|1|,G|missense_variant|" + GENE + "|" + TX + "|2|1"}
    indexer._record_annotations(None, 1, 1, "T", ["T", "G"], info, {"CSQ": layout}, reference="C")
    indexer._record_annotations(None, 2, 1, "G", ["T", "G"], info, {"CSQ": layout}, reference="C")
    assert [variant for variant, _ in captured] == [1, 1, 2]
    assert captured[1][1]["metadata"]["fields"]["PICK"] == ""
    ref, raw = reference(cds="ATG" + "CAA" * 4 + "TAA")
    manager, _, _ = sources(tmp_path, [raw])
    selected_t, selected_g = annotation(), annotation(consequence="missense_variant")
    result_t = analyze_transcripts(detail_for(allele(ref, 4), [selected_t]), selected_t, manager)
    variant_g = dict(allele(ref, 4), alternate_allele="G")
    result_g = analyze_transcripts(detail_for(variant_g, [selected_g]), selected_g, manager)
    assert result_t["transcripts"][0]["status"] == "AFFECTED_CODING"
    assert result_g["transcripts"][0]["status"] == "OTHER_CONSEQUENCE"
    assert result_g["transcripts"][0]["ptc_mrna_position"] is None


def test_api_never_selects_the_strongest_transcript(tmp_path, monkeypatch):
    from helper_next.api import acmg_calculator as api
    ref, raw1 = reference()
    _, raw2 = reference(utr="CCC" + "A" * 150, first_exon=100, tx="ENST00000000002.1")
    manager, _, _ = sources(tmp_path, [raw1, raw2])
    selected = annotation()
    variant = allele(ref, 13)
    detail = detail_for(variant, [selected])
    molecular = molecular_impact(variant, GENE, TX, ref, "stop_gained")
    context = {"gene": GENE, "disease": "SYNTHETIC", "inheritance": "AD", "scope": "DISEASE_SPECIFIC",
               "molecular_mechanism": "LoF", "confidence": "DEFINITIVE"}
    context["source_refs"] = {k: ["synthetic:curation"] for k in context}
    sample = PVS1Input(variant=dict(variant, consequence="stop_gained"), disease_context=context, **molecular["pvs1_input"])
    monkeypatch.setattr(api, "_entry", lambda _: {})
    monkeypatch.setattr(api, "_entry_database", lambda _: "synthetic")
    monkeypatch.setattr(api.query, "variant_detail", lambda *args: detail)
    monkeypatch.setattr(api, "analyze_transcripts", lambda d, a: analyze_transcripts(d, a, manager))
    monkeypatch.setattr(api, "prepare_pvs1_input", lambda *args: (sample, "TRANSCRIPT_CACHE", []))
    response = api.evaluate_pvs1({"run_id": "synthetic", "sample_id": 1, "variant_id": 1, "annotation_id": 1, "transcript": TX})
    rows = response["molecular_impact"]["transcripts"]
    assert rows[0]["nmd_predicted"] is False and rows[1]["nmd_predicted"] is True
    assert response["input"]["transcript"]["accession"] == TX
    assert response["result"]["applied_strength"] == "STRONG"
    assert response["result"]["ruleset_version"] == "1.1.0"
    assert sum("Dato opzionale" in warning for warning in response["result"]["warnings"]) == 3
