"""Synthetic allele-bound SpliceAI/RNA integration; never clinical validation."""
import copy
import json
import os
from pathlib import Path

import pytest

from helper_next.core.acmg_splice import splice_impact
from helper_next.core.acmg_splice_prediction import FIELDS, spliceai_prediction
from helper_next.core.acmg_transcripts import complement, mrna_to_genomic
from pvs1.impact import molecular_impact
from test_pvs1_molecular import GENE, TX
from test_pvs1_splice import decision, splice_case, write_fasta


def annotation_for(variant, anchor, gained, kind="DONOR", **changes):
    code = "D" if kind == "DONOR" else "A"
    values = {"SYMBOL": "GENE_X", **{key: 0 for key in FIELDS}}
    values.update({"DS_" + code + "G": 0.9, "DS_" + code + "L": 0.95,
                   "DP_" + code + "G": gained - variant["position"],
                   "DP_" + code + "L": anchor - variant["position"]})
    values.update(changes)
    return {"id": 7, "gene": "GENE_X", "metadata": {"fields": {"SpliceAI_pred_" + k: str(v) for k, v in values.items()}}}


def cryptic_case(tmp_path, kind="DONOR", strand="+", *, intronic=False, deletion=False):
    cds = list("ATG" + "CAA" * 44 + "TAA")
    cds[90:99] = "CTAACTAAC"  # Reference sense codons; stop in both shifted frames.
    gained_rna = 55 if kind == "DONOR" else 15  # Exon 3 spans reference RNA 11..60.
    if not intronic:
        motif_rna = gained_rna + 1 if kind == "DONOR" else gained_rna - 2
        cds[motif_rna - 4:motif_rna - 2] = "GT" if kind == "DONOR" else "AG"
    variant, ref, record, genome, fasta, anchor = splice_case(
        tmp_path, kind, strand, deletion=deletion, exon_number=3, cds="".join(cds))
    direction = 1 if strand == "+" else -1
    bases = list(genome)

    def put(position, sequence):
        for index, base in enumerate(sequence):
            bases[position + direction * index - 1] = base if strand == "+" else complement(base)

    if intronic:
        gained = anchor + direction * (25 if kind == "DONOR" else -25)
        # A stop cassette in all three reading frames, unaffected by a ten-base
        # canonical deletion; the retained allele must still be applied.
        included = "GT" + "A" * 8 + "TAATTAACTGA" + "A" * 4 if kind == "DONOR" else "TAATTAACTGA" + "A" * 12 + "AG"
        put(anchor + direction if kind == "DONOR" else gained, included)
        put(gained + direction if kind == "DONOR" else gained - 2 * direction, "GT" if kind == "DONOR" else "AG")
    else:
        gained = mrna_to_genomic(ref["exons"], strand, gained_rna)
    genome = "".join(bases)
    write_fasta(fasta, genome)
    variant["reference_allele"] = genome[variant["position"] - 1:variant["position"] - 1 + len(variant["reference_allele"])]
    if deletion:
        variant["alternate_allele"] = variant["reference_allele"][0]
    annotation = annotation_for(variant, anchor, gained, kind)
    return variant, ref, record, annotation, gained, fasta


def reconstruct(case, kind="DONOR", original=None):
    variant, ref, record, annotation, *_ = case
    consequence = "splice_donor_variant" if kind == "DONOR" else "splice_acceptor_variant"
    row = molecular_impact(variant, GENE, TX, ref, consequence)
    return splice_impact(row, variant, GENE, ref, record=record, annotation=annotation, original=original)


@pytest.mark.parametrize("kind", ["DONOR", "ACCEPTOR"])
@pytest.mark.parametrize("strand", ["+", "-"])
@pytest.mark.parametrize("intronic", [False, True])
def test_spliceai_builds_the_cryptic_rna_and_keeps_the_selected_transcript(tmp_path, kind, strand, intronic):
    case = cryptic_case(tmp_path, kind, strand, intronic=intronic)
    before = copy.deepcopy(case[:-1])
    row = reconstruct(case, kind)
    assert row["status"] == "SPLICE_SCENARIO", row["missing_data"]
    assert row["product_resolution"]["method"] == "SPLICEAI_CRYPTIC_SCENARIO"
    scenario, = row["splice_analysis"]["scenarios"]
    assert scenario["event"]["event_type"] == "CRYPTIC_SITE"
    assert scenario["event"]["involved_exons"] == [3]
    assert scenario["event"]["basis"] == "PREDICTED"
    assert row["splice_analysis"]["prediction"]["gained_site"]["genomic_position"] == case[4]
    assert row["splice_analysis"]["alternatives_not_assessed"][0] == "EXON_SKIPPING"
    assert "CRYPTIC_SITE" not in row["splice_analysis"]["alternatives_not_assessed"]
    product, = row["pvs1_input"]["molecular_effect"]["products"]
    assert product["event_type"] == "CRYPTIC_SITE" and row["pvs1_input"]["transcript"]["accession"] == TX
    assert len(product["sequence"]) == len(case[1]["cdna"]) + (25 if intronic else -5 if kind == "DONOR" else -4)
    assert scenario["coding_deleted_nt"] == (0 if intronic else 5 if kind == "DONOR" else 4)
    assert scenario["frame_effect"] == "OUT_OF_FRAME"
    if intronic:
        assert scenario["rna_inserted_nt"] == scenario["coding_inserted_nt"] == 25
        assert row["calculation"]["retained_variant_edit"]
        assert row["calculation"]["inserted_rna_sequence"] != row["calculation"]["intronic_sequence"]["sequence"]
        assert row["nmd_predicted"] is True
        result = decision(case[0], row)
        assert result.status == "ACTIVE" and result.applied_strength == "VERY_STRONG"
        assert not any("Siti criptici" in warning and "non valutati" in warning for warning in result.warnings)
    assert case[:-1] == before


@pytest.mark.parametrize("kind", ["DONOR", "ACCEPTOR"])
@pytest.mark.parametrize("strand", ["+", "-"])
def test_intronic_cryptic_product_applies_a_retained_deletion_before_frame_and_nmd(tmp_path, kind, strand):
    case = cryptic_case(tmp_path, kind, strand, intronic=True, deletion=True)
    row = reconstruct(case, kind)
    assert row["status"] == "SPLICE_SCENARIO", row["missing_data"]
    scenario, = row["splice_analysis"]["scenarios"]
    assert scenario["rna_inserted_nt"] == scenario["coding_inserted_nt"] == 15
    assert scenario["frame_effect"] == "IN_FRAME"  # 25 retained bases minus the actual ten-base deletion.
    assert len(row["calculation"]["inserted_rna_sequence"]) == 15
    assert row["calculation"]["retained_variant_edit"]["length_delta_nt"] == -10
    assert row["nmd_predicted"] is True  # An in-frame inclusion can still introduce a PTC.


@pytest.mark.parametrize("kind", ["DONOR", "ACCEPTOR"])
@pytest.mark.parametrize("strand", ["+", "-"])
def test_retained_insertions_are_included_in_the_cryptic_product(tmp_path, kind, strand):
    case = list(cryptic_case(tmp_path, kind, strand, intronic=True))
    variant, _, _, _, gained, fasta = case
    anchor = variant["position"] - (1 if kind == "DONOR" else -1) * (1 if strand == "+" else -1)
    position = anchor + 1 if (kind == "DONOR") == (strand == "+") else anchor - 2
    genome = fasta.read_text().splitlines()[1]
    original = genome[position - 1]
    alternate = ("A" if strand == "+" else "T") if kind == "DONOR" else ("C" if strand == "+" else "G")
    variant.update(position=position, reference_allele=original, alternate_allele=original + alternate)
    case[3] = annotation_for(variant, anchor, gained, kind)
    row = reconstruct(case, kind)
    assert row["status"] == "SPLICE_SCENARIO", row["missing_data"]
    scenario, = row["splice_analysis"]["scenarios"]
    assert scenario["rna_inserted_nt"] == scenario["coding_inserted_nt"] == 26
    assert row["calculation"]["retained_variant_edit"]["length_delta_nt"] == 1
    assert scenario["frame_effect"] == "OUT_OF_FRAME"


@pytest.mark.parametrize("change", [
    {"DP_DL": 500}, {"DS_DL": 0.49}, {"DS_AG": 0.8}, {"DS_DG": "nan"},
    {"DP_DG": "1.5"}, {"DS_DG": 1.5},
])
def test_inconsistent_or_ambiguous_predictions_do_not_fall_back_to_a_different_product(tmp_path, change):
    case = list(cryptic_case(tmp_path, intronic=True))
    fields = case[3]["metadata"]["fields"]
    fields.update({"SpliceAI_pred_" + k: str(v) for k, v in change.items()})
    row = reconstruct(case)
    assert row["pvs1_input"] is None
    assert row["product_resolution"]["status"] == "UNRESOLVED"
    assert any("Splice reconstruction unavailable" in message for message in row["missing_data"])


def test_low_gain_keeps_the_existing_skip_hypothesis(tmp_path):
    case = list(cryptic_case(tmp_path, intronic=True))
    case[3]["metadata"]["fields"]["SpliceAI_pred_DS_DG"] = "0.49"
    row = reconstruct(case)
    assert row["pvs1_input"]["molecular_effect"]["products"][0]["event_type"] == "EXON_SKIPPING"


@pytest.mark.parametrize("kind", ["DONOR", "ACCEPTOR"])
def test_missing_cryptic_motif_does_not_invent_a_product(tmp_path, kind):
    case = cryptic_case(tmp_path, kind, intronic=True)
    fasta = case[-1]
    genome = list(fasta.read_text().splitlines()[1])
    gain = case[4]
    position = gain + 1 if kind == "DONOR" else gain - 2
    genome[position - 1] = "C"
    write_fasta(fasta, "".join(genome))
    row = reconstruct(case, kind)
    assert row["pvs1_input"] is None
    assert any("compatible GT/AG motif" in issue for issue in row["missing_data"])


def test_cryptic_inclusion_uses_bounded_reads_and_detects_reference_changes(tmp_path, monkeypatch):
    import pvs1.molecular as molecular
    from helper_variants import indexer
    case = cryptic_case(tmp_path, intronic=True)
    monkeypatch.setattr(molecular, "sha256_file", lambda *_: pytest.fail("Whole-genome checksum scan"))
    monkeypatch.setattr(indexer, "sha256_file", lambda *_: pytest.fail("Whole-genome checksum scan"))
    assert reconstruct(case)["status"] == "SPLICE_SCENARIO"
    original_read = indexer.IndexedFasta.sequence
    reads = []
    def bounded(reader, chromosome, position, length):
        reads.append(length)
        assert length < 1000
        return original_read(reader, chromosome, position, length)
    monkeypatch.setattr(indexer.IndexedFasta, "sequence", bounded)
    assert reconstruct(case)["pvs1_input"]
    assert reads
    def changed(reader, chromosome, position, length):
        value = bounded(reader, chromosome, position, length)
        if length == 25:
            reader.path.write_bytes(reader.path.read_bytes())
        return value
    monkeypatch.setattr(indexer.IndexedFasta, "sequence", changed)
    broken = reconstruct(case)
    assert broken["pvs1_input"] is None
    assert any("changed" in issue for issue in broken["missing_data"])


@pytest.mark.parametrize("format", ["split", "packed", "native"])
def test_supported_spliceai_formats_keep_offsets_raw_record_and_gene_binding(tmp_path, format):
    case = list(cryptic_case(tmp_path, intronic=True))
    variant, _, _, annotation, *_ = case
    fields = annotation["metadata"]["fields"]
    parts = [fields["SpliceAI_pred_" + key] for key in ("SYMBOL", *FIELDS)]
    original = None
    if format == "packed":
        annotation["metadata"]["fields"] = {"SpliceAI_pred": "|".join(parts)}
    elif format == "native":
        annotation["metadata"]["fields"] = {}
        original = {"position": variant["position"], "reference": variant["reference_allele"],
                    "alternate": variant["alternate_allele"], "info": {"SpliceAI": variant["alternate_allele"] + "|" + "|".join(parts)}}
    row = reconstruct(case, original=original)
    assert row["status"] == "SPLICE_SCENARIO", row["missing_data"]
    prediction = row["splice_analysis"]["prediction"]
    assert prediction["status"] == "AVAILABLE"
    assert prediction["records"][0]["position"] == variant["position"]
    assert prediction["model_version"] is None and prediction["raw"]


def test_wrong_gene_and_ambiguous_same_gene_records_are_not_selected_by_score(tmp_path):
    case = cryptic_case(tmp_path, intronic=True)
    variant, _, _, annotation, *_ = case
    fields = annotation["metadata"]["fields"]
    parts = [fields["SpliceAI_pred_" + key] for key in ("SYMBOL", *FIELDS)]
    wrong = copy.deepcopy(annotation)
    wrong["metadata"]["fields"]["SpliceAI_pred_SYMBOL"] = "OTHER_GENE"
    assert spliceai_prediction(wrong, variant)["status"] == "NOT_APPLICABLE"
    second = list(parts)
    second[3] = "0.8"
    annotation["metadata"]["fields"] = {"SpliceAI_pred": "|".join(parts) + "," + "|".join(second)}
    prediction = spliceai_prediction(annotation, variant)
    assert prediction["status"] == "UNRESOLVED" and len(prediction["records"]) == 2
    assert reconstruct(case)["pvs1_input"] is None


def test_native_info_offsets_follow_the_original_vcf_position_after_anchor_trimming():
    variant = dict(position=101, reference_allele="AC", alternate_allele="A", contig="chr1")
    annotation = annotation_for(variant, 100, 110)
    fields = annotation["metadata"]["fields"]
    parts = [fields["SpliceAI_pred_" + key] for key in ("SYMBOL", *FIELDS)]
    # The original representation has one additional unchanged left base.
    original = dict(position=100, reference="GAC", alternate="GA", chromosome="1", info={})
    assert spliceai_prediction(annotation, variant, original)["status"] == "UNRESOLVED"
    parts[7] = "10"  # DP_DG relative to original position 100.
    parts[8] = "0"   # DP_DL is a valid zero offset, not a missing value.
    original["info"]["SpliceAI"] = "GA|" + "|".join(parts)
    result = spliceai_prediction(annotation, variant, original)
    assert result["status"] == "AVAILABLE" and result["ignored_formats"]
    row, = result["records"]
    assert row["position"] + row["DP_DG"] == 110 and row["DP_DL"] == 0
    original["chromosome"] = "2"
    assert spliceai_prediction(annotation, variant, original)["status"] == "UNRESOLVED"


def test_supplied_prediction_keeps_its_declared_allele_position_instead_of_the_original_vcf_anchor():
    variant = dict(position=101, reference_allele="AC", alternate_allele="A", contig="1", assembly="GRCh37")
    supplied = {"SYMBOL": "GENE_X", **{key: 0 for key in FIELDS},
                "position": 101, "reference": "AC", "alternate": "A", "assembly": "GRCh37",
                "source_url": "https://example.test/prediction", "DS_DG": 0.8, "DS_DL": 0.9, "DP_DG": 9, "DP_DL": -1}
    annotation = {"gene": "GENE_X", "metadata": {"spliceai_prediction": supplied}}
    original = dict(position=100, reference="GAC", alternate="GA", chromosome="1")
    result = spliceai_prediction(annotation, variant, original)
    assert result["status"] == "AVAILABLE"
    row, = result["records"]
    assert row["position"] == 101 and row["position"] + row["DP_DG"] == 110


@pytest.mark.parametrize("problem", ["other_exon", "outside_intron", "gain_equals_loss", "missing_position", "conflicting_formats"])
def test_unqualified_boundaries_and_source_conflicts_stay_unresolved(tmp_path, problem):
    case = list(cryptic_case(tmp_path, intronic=True))
    fields = case[3]["metadata"]["fields"]
    position = case[0]["position"]
    if problem == "other_exon":
        fields["SpliceAI_pred_DP_DG"] = str(case[1]["exons"][3]["genomic_start"] - position)
    elif problem == "outside_intron":
        fields["SpliceAI_pred_DP_DG"] = "500"
    elif problem == "gain_equals_loss":
        fields["SpliceAI_pred_DP_DG"] = fields["SpliceAI_pred_DP_DL"]
    elif problem == "missing_position":
        fields.pop("SpliceAI_pred_DP_DG")
    else:
        parts = [fields["SpliceAI_pred_" + key] for key in ("SYMBOL", *FIELDS)]
        parts[3] = "0.8"
        fields["SpliceAI_pred"] = "|".join(parts)
    assert reconstruct(case)["pvs1_input"] is None


def test_api_transfers_indexed_predictions_without_changing_the_annotation(tmp_path, monkeypatch):
    from helper_next.api import acmg_calculator as api
    from helper_next.core.acmg_molecular_impact import analyze_transcripts
    from test_pvs1_impact import annotation, detail_for, sources, reference
    case = cryptic_case(tmp_path, intronic=True)
    variant, ref, record, predicted, *_ = case
    _, raw = reference()
    manager, calls, _ = sources(tmp_path, [raw])
    monkeypatch.setattr(manager, "transcript", lambda *a, **kw: {"status": "CACHED", "data": ref})
    selected = annotation(consequence="splice_donor_variant")
    selected["gene"] = predicted["gene"]
    selected["metadata"]["fields"].update(predicted["metadata"]["fields"])
    detail = detail_for(variant, [selected])
    before = copy.deepcopy(detail)
    monkeypatch.setattr(api, "_selected_annotation", lambda _: (detail, selected))
    monkeypatch.setattr(api, "_entry", lambda _: {"record": record})
    monkeypatch.setenv("HELPER_VEP_CACHE", str(tmp_path / "absent"))
    monkeypatch.setattr(api, "analyze_transcripts", lambda d, a, **kw: analyze_transcripts(d, a, manager, **kw))
    response = api.evaluate_pvs1({"run_id": "synthetic"})
    product, = response["input"]["molecular_effect"]["products"]
    assert product["event_type"] == "CRYPTIC_SITE" and product["basis"] == "PREDICTED"
    row, = response["molecular_impact"]["transcripts"]
    assert row["splice_analysis"]["prediction"]["gained_site"]["genomic_position"] == case[4]
    assert row["nmd_predicted"] is True
    assert "pvs1_input" not in row
    assert detail == before and not calls


@pytest.mark.parametrize("kind", ["DONOR", "ACCEPTOR"])
@pytest.mark.parametrize("strand", ["+", "-"])
def test_exonic_low_delta_positions_define_only_an_exploratory_hypothesis(tmp_path, kind, strand):
    case = list(cryptic_case(tmp_path, kind, strand))
    variant, _, _, _, gained, fasta = case
    direction = 1 if strand == "+" else -1
    anchor = variant["position"] - direction * (1 if kind == "DONOR" else -1)
    position = gained + direction * (3 if kind == "DONOR" else -3)
    original = fasta.read_text().splitlines()[1][position - 1]
    variant.update(position=position, reference_allele=original, alternate_allele="T" if original != "T" else "C")
    code = "D" if kind == "DONOR" else "A"
    case[3] = annotation_for(variant, anchor, gained, kind, **{"DS_" + code + "G": 0.085, "DS_" + code + "L": 0.032})
    before = copy.deepcopy(case[3])
    row = molecular_impact(variant, GENE, TX, case[1], "missense_variant")
    row = splice_impact(row, variant, GENE, case[1], record=case[2], annotation=case[3])
    assert row["status"] == "SPLICE_SCENARIO", row["missing_data"]
    assert row["splice_analysis"]["prediction"]["selection_status"] == "EXPLORATORY_LOW_DELTA"
    assert row["splice_analysis"]["prediction"]["automatic_pvs1_eligible"] is False
    assert row["provenance"]["original_consequence"] == "missense_variant"
    assert row["consequence"] == "missense_variant&splice_region_variant"
    assert "P34" in decision(variant, row).reason
    assert case[3] == before


def test_failed_alternative_rna_cannot_reuse_an_existing_reference_splicing_product(tmp_path):
    from test_pvs1_molecular import reference_fixture, sample_for_snv
    ref = reference_fixture(cds="ATGCAATAA")
    sample = sample_for_snv(ref, mrna_position=7, alternate="T")
    row = molecular_impact(sample.variant, GENE, TX, ref, "stop_gained")
    assert row["pvs1_input"] and row["predicted_protein_length"] == 1
    before = copy.deepcopy(row)
    failed = splice_impact(row, sample.variant, GENE, ref, annotation={"gene": "GENE_X"})
    assert failed["pvs1_input"] is None and failed["predicted_protein_length"] is None
    assert failed["nmd_predicted"] is None and failed["product_resolution"]["status"] == "UNRESOLVED"
    assert row == before


@pytest.mark.skipif(os.environ.get("HELPER_TEST_PVS1_LMNA_CRYPTIC") != "1", reason="Opt in with installed VEP 113/GRCh37 and hg19 FASTA")
def test_lmna_c1824_public_prediction_and_reference_reconstruct_progerin(tmp_path, monkeypatch):
    """Real public LMNA allele, public SpliceAI response and installed reference.

    Delta scores remain the acquired low values. The literature outcome is an
    expectation for the test, never supplied as the event to the reconstructor.
    """
    from helper_next.api import acmg_calculator as api
    from helper_next.core.acmg_context import build
    from helper_next.core.acmg_vep_reference import local_transcript_reference
    fixture = json.loads((Path(__file__).parent / "fixtures/pvs1/lmna_c1824_spliceai.json").read_text())
    variant, gene, tx = fixture["variant"], fixture["gene"], fixture["transcript"]
    reference = local_transcript_reference(variant, gene, tx, fixture["ensembl_release"])
    assert reference["status"] == "CACHED", reference.get("missing")
    annotation = dict(id=1, gene="LMNA", transcript=tx, consequence="synonymous_variant", hgvsc=fixture["hgvsc"],
        hgvsp="p.Gly608=", canonical=True, release_key="public-lmna-regression", release_resources={"ensembl_release": "113"},
        metadata={"fields": {"Gene": gene, "HGNC_ID": "6636", "BIOTYPE": "protein_coding"},
                  "spliceai_prediction": fixture["prediction"]})
    detail = dict(variant_id=1, reference_build="GRCh37", chromosome="1", position=variant["position"],
                  reference="C", alternate="T", annotations=[annotation])
    before = copy.deepcopy(detail)
    context = next(c for a in build(detail)["annotations"] for c in a["contexts"]
                   if c["context"]["disease"]["identifier"] == "MONDO:0008310")
    monkeypatch.setenv("HELPER_MECHANISM_DB", str(tmp_path / "public-mechanisms.sqlite"))
    monkeypatch.setenv("HELPER_TRANSCRIPT_FETCH", "0")
    record = {"run_config": {"reference_fasta": os.environ["HELPER_TEST_GRCH37_FASTA"], "reference_version": "hg19"}}
    monkeypatch.setattr(api, "_selected_annotation", lambda _: (detail, annotation))
    monkeypatch.setattr(api, "_entry", lambda _: {"record": record})
    result = api.evaluate_pvs1({"run_id": "public-lmna-regression", "context_id": context["id"]})
    row, = result["molecular_impact"]["transcripts"]
    scenario, = row["splice_analysis"]["scenarios"]
    assert scenario["event"]["event_type"] == "CRYPTIC_SITE" and scenario["event"]["involved_exons"] == [11]
    assert scenario["rna_deleted_nt"] == scenario["coding_deleted_nt"] == 150
    assert row["reference_protein_length"] == 664 and row["predicted_protein_length"] == 614
    assert scenario["frame_effect"] == "IN_FRAME" and row["nmd_predicted"] is False
    assert row["splice_analysis"]["prediction"]["records"][0]["DS_DG"] == 0.085
    assert row["splice_analysis"]["prediction"]["selection_status"] == "EXPLORATORY_LOW_DELTA"
    assert result["input"]["variant"]["consequence"] == "synonymous_variant&splice_region_variant"
    assert result["input"]["disease_context"]["molecular_mechanism"] == "GoF"
    assert result["result"]["status"] == "INACTIVE" and result["result"]["applied_strength"] is None
    assert detail == before
