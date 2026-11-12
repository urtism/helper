"""Canonical splice hypotheses from verified alleles, never observed RNA."""
import copy
import json
import os

import pytest

from helper_next.core.acmg_splice import splice_impact
from helper_next.core.acmg_transcripts import complement, mrna_to_genomic
from pvs1.calculator import calculate_pvs1
from pvs1.impact import molecular_impact
from pvs1.models import PVS1Input
from test_pvs1_molecular import GENE, TX, reference_fixture


@pytest.fixture(autouse=True)
def isolated_reference_configuration(monkeypatch):
    monkeypatch.delenv("HELPER_ACMG_REFERENCE_CONFIG", raising=False)


def write_fasta(path, sequence):
    header = ">chr1\n"
    path.write_text(header + sequence + "\n")
    path.with_suffix(path.suffix + ".fai").write_text(f"chr1\t{len(sequence)}\t{len(header)}\t{len(sequence)}\t{len(sequence) + 1}\n")


def splice_case(tmp_path, kind="DONOR", strand="+", *, in_frame=False, deletion=True, exon_number=2, cds=None):
    cds = cds or "ATGAAACTAAAGCAA" + "CAA" * 40 + "TAA"
    lengths = [6, 3, 51, 60, 24] if in_frame else [6, 4, 50, 60, 24]
    ref = reference_fixture(strand, cds=cds, exon_lengths=lengths)
    direction = 1 if strand == "+" else -1
    genome = list("A" * 1000)

    def put(position, sequence):
        for index, base in enumerate(sequence):
            genome[position + direction * index - 1] = base if strand == "+" else complement(base)

    for index, exon in enumerate(ref["exons"]):
        start = mrna_to_genomic(ref["exons"], strand, exon["mrna_start"])
        end = mrna_to_genomic(ref["exons"], strand, exon["mrna_end"])
        put(start, ref["cdna"][exon["mrna_start"] - 1:exon["mrna_end"]])
        if index:
            put(start - 2 * direction, "AG")
        if index < len(ref["exons"]) - 1:
            put(end + direction, "GT")
    genome = "".join(genome)
    exon = ref["exons"][exon_number - 1]
    anchor = mrna_to_genomic(ref["exons"], strand, exon["mrna_end"] if kind == "DONOR" else exon["mrna_start"])
    side = direction if kind == "DONOR" else -direction
    if deletion:
        position = min(anchor + side, anchor + 10 * side) - 1
        original = genome[position - 1:position + 10]
        alternate = original[0]
    else:
        position = anchor + side
        original = genome[position - 1]
        alternate = "A" if strand == "+" else "T"
    variant = dict(assembly="GRCh38", contig="chr1", position=position, reference_allele=original,
                   alternate_allele=alternate, coordinate_system="genomic_1_based")
    fasta = tmp_path / "reference.fa"
    write_fasta(fasta, genome)
    record = dict(run_config=dict(reference_fasta=str(fasta), reference_version="synthetic-GRCh38"))
    return variant, ref, record, genome, fasta, anchor


def reconstruct(variant, ref, record, kind="DONOR"):
    consequence = "splice_donor_variant" if kind == "DONOR" else "splice_acceptor_variant"
    row = molecular_impact(variant, GENE, TX, ref, consequence)
    return splice_impact(row, variant, GENE, ref, record=record)


def decision(variant, row):
    context = dict(gene=GENE, disease="SYNTHETIC", inheritance="AD", scope="DISEASE_SPECIFIC",
                   molecular_mechanism="LoF", confidence="DEFINITIVE")
    context["source_refs"] = {key: ["synthetic:curation"] for key in context}
    return calculate_pvs1(PVS1Input(variant=dict(variant, consequence=row["consequence"]),
                                   disease_context=context, **row["pvs1_input"]))


@pytest.mark.parametrize("kind", ["DONOR", "ACCEPTOR"])
@pytest.mark.parametrize("strand", ["+", "-"])
@pytest.mark.parametrize("deletion", [True, False])
def test_canonical_sites_reconstruct_conditional_rna_and_nmd(tmp_path, kind, strand, deletion):
    variant, ref, record, _, _, _ = splice_case(tmp_path, kind, strand, deletion=deletion)
    before = copy.deepcopy((variant, ref, record))
    row = reconstruct(variant, ref, record, kind)
    assert row["status"] == "SPLICE_SCENARIO", row["missing_data"]
    assert row["product_resolution"]["status"] == "CONDITIONAL"
    assert row["product_resolution"]["reason_codes"] == ["ALTERNATIVE_SPLICE_PRODUCTS_UNASSESSED"]
    scenario = row["splice_analysis"]["scenarios"][0]
    assert scenario["event"]["basis"] == "PREDICTED"
    assert scenario["event"]["involved_exons"] == [2]
    assert scenario["rna_deleted_nt"] == scenario["coding_deleted_nt"] == 4
    assert scenario["frame_effect"] == "OUT_OF_FRAME"
    assert row["nmd_predicted"] is True
    assert row["nmd_distance_nt"] == 109
    assert row["predicted_protein_length"] == 1 and row["termination_codon"] == 2
    assert row["physical_deleted_nt"] == (10 if deletion else 0)
    assert row["physical_cds_deleted_percent"] == 0  # The DNA edit is intronic.
    product = row["pvs1_input"]["molecular_effect"]["products"][0]
    assert len(product["sequence"]) == len(ref["cdna"]) - 4
    assert (variant, ref, record) == before
    result = decision(variant, row)
    assert result.status == "ACTIVE" and result.applied_strength == "VERY_STRONG"
    assert result.requires_review is False
    assert any("PREDICTED" in warning for warning in result.warnings)
    assert not result.missing_data
    requirements = {item["id"]: item for item in map(json.loads, result.decision_trace)}
    assert requirements["product"]["status"] == requirements["nmd"]["status"] == "PASS"


@pytest.mark.parametrize("strand", ["+", "-"])
def test_in_frame_skip_preserves_the_natural_stop_and_applies_protein_loss_branch(tmp_path, strand):
    variant, ref, record, *_ = splice_case(tmp_path, strand=strand, in_frame=True)
    row = reconstruct(variant, ref, record)
    assert row["splice_analysis"]["scenarios"][0]["frame_effect"] == "IN_FRAME"
    assert row["ptc_mrna_position"] is None and row["nmd_predicted"] is False
    assert row["predicted_protein_length"] == ref["protein_length"] - 1
    result = decision(variant, row)
    assert result.status == "ACTIVE" and result.applied_strength == "MODERATE"


@pytest.mark.parametrize("kind", ["DONOR", "ACCEPTOR"])
@pytest.mark.parametrize("strand", ["+", "-"])
def test_retained_native_or_gc_donor_does_not_invent_exon_skipping(tmp_path, kind, strand):
    variant, ref, record, genome, _, anchor = splice_case(tmp_path, kind, strand)
    direction = 1 if strand == "+" else -1
    # +2 T>C creates GC; +3 donor / -3 acceptor does not change the dinucleotide.
    offset = 2 * direction if kind == "DONOR" else -3 * direction
    position = anchor + offset
    variant.update(position=position, reference_allele=genome[position - 1],
                   alternate_allele="C" if strand == "+" else "G")
    row = reconstruct(variant, ref, record, kind)
    assert row["pvs1_input"] is None and not row["splice_analysis"]["scenarios"]
    assert row["product_resolution"]["status"] == "UNRESOLVED"


@pytest.mark.parametrize("problem", ["missing_fasta", "wrong_ref", "wrong_exon", "wrong_consequence", "noncanonical_native", "exonic_edit"])
def test_inconsistent_or_missing_data_cannot_produce_a_splice_product(tmp_path, problem):
    variant, ref, record, genome, fasta, anchor = splice_case(tmp_path)
    kind = "DONOR"
    if problem == "missing_fasta":
        record = {}
    elif problem == "wrong_ref":
        variant["reference_allele"] = variant["reference_allele"][0] + "C" + variant["reference_allele"][2:]
    elif problem == "wrong_exon":
        exon = ref["exons"][1]
        position = exon["genomic_start"]
        write_fasta(fasta, genome[:position - 1] + "C" + genome[position:])
    elif problem == "wrong_consequence":
        kind = "ACCEPTOR"
    elif problem == "noncanonical_native":
        position = anchor + 1
        genome = genome[:position - 1] + "C" + genome[position:]
        write_fasta(fasta, genome)
        variant["reference_allele"] = genome[variant["position"] - 1:variant["position"] + 10]
    elif problem == "exonic_edit":
        variant.update(position=anchor - 1, reference_allele=genome[anchor - 2:anchor + 1],
                       alternate_allele=genome[anchor - 2])
    row = reconstruct(variant, ref, record, kind)
    assert row["pvs1_input"] is None
    assert "SPLICE_SCENARIO_UNRESOLVED" in row["product_resolution"]["reason_codes"]
    assert any("Splice reconstruction unavailable" in item for item in row["missing_data"])


def test_reference_mutation_is_rechecked_instead_of_reusing_a_previous_product(tmp_path):
    variant, ref, record, genome, fasta, _ = splice_case(tmp_path)
    assert reconstruct(variant, ref, record)["pvs1_input"]
    position = variant["position"] + 1
    write_fasta(fasta, genome[:position - 1] + "C" + genome[position:])
    assert reconstruct(variant, ref, record)["pvs1_input"] is None


@pytest.mark.parametrize("kind, exon", [("DONOR", 1), ("ACCEPTOR", 5)])
def test_terminal_exon_skipping_does_not_invent_an_initiation_or_stop(tmp_path, kind, exon):
    variant, ref, record, *_ = splice_case(tmp_path, kind, exon_number=exon)
    row = reconstruct(variant, ref, record, kind)
    assert row["pvs1_input"] is None
    assert row["splice_analysis"]["scenarios"][0]["status"] == "INCOMPLETE"


def test_multiple_affected_sites_and_an_unchanged_vcf_anchor_are_not_resolved_arbitrarily(tmp_path):
    variant, ref, record, genome, _, anchor = splice_case(tmp_path)
    # Delete all of the intron: both its donor and acceptor are affected.
    next_start = ref["exons"][2]["genomic_start"]
    variant.update(position=anchor, reference_allele=genome[anchor - 1:next_start - 1], alternate_allele=genome[anchor - 1])
    row = reconstruct(variant, ref, record)
    assert row["pvs1_input"] is None and not row["splice_analysis"]["scenarios"]
    # The anchor is +2 but the deletion starts at +3: the canonical GT survives.
    position = anchor + 2
    variant.update(position=position, reference_allele=genome[position - 1:position + 2], alternate_allele=genome[position - 1])
    assert reconstruct(variant, ref, record)["pvs1_input"] is None


@pytest.mark.parametrize("strand", ["+", "-"])
def test_insertions_between_canonical_donor_bases_use_the_mutant_motif(tmp_path, strand):
    variant, ref, record, genome, _, anchor = splice_case(tmp_path, strand=strand)
    position = anchor + 1 if strand == "+" else anchor - 2
    original = genome[position - 1]
    variant.update(position=position, reference_allele=original, alternate_allele=original + ("A" if strand == "+" else "T"))
    row = reconstruct(variant, ref, record)
    assert row["status"] == "SPLICE_SCENARIO", row["missing_data"]
    assert row["splice_analysis"]["site"]["altered_motif"] == "GA"
    assert row["physical_inserted_nt"] == 1 and row["physical_deleted_nt"] == 0


def test_api_uses_the_run_reference_and_keeps_scenario_provenance(tmp_path, monkeypatch):
    from helper_next.api import acmg_calculator as api
    from helper_next.core.acmg_molecular_impact import analyze_transcripts
    from test_pvs1_impact import annotation, detail_for, sources, reference
    variant, ref, record, *_ = splice_case(tmp_path)
    _, raw = reference()
    manager, calls, _ = sources(tmp_path, [raw])
    monkeypatch.setattr(manager, "transcript", lambda *a, **kw: {"status": "CACHED", "data": ref})
    selected = annotation(consequence="splice_donor_variant")
    detail = detail_for(variant, [selected])
    monkeypatch.setattr(api, "_selected_annotation", lambda _: (detail, selected))
    monkeypatch.setattr(api, "_entry", lambda _: {"record": record})
    monkeypatch.setenv("HELPER_VEP_CACHE", str(tmp_path / "absent"))
    monkeypatch.setattr(api, "analyze_transcripts", lambda d, a, **kw: analyze_transcripts(d, a, manager, **kw))
    response = api.evaluate_pvs1({"run_id": "synthetic"})
    row = response["molecular_impact"]["transcripts"][0]
    assert response["molecular_origin"] == "TRANSCRIPT_MOLECULAR_ANALYSIS"
    assert response["input"]["molecular_effect"]["products"][0]["basis"] == "PREDICTED"
    assert row["splice_analysis"]["site"]["reference_source"]["version"] == "synthetic-GRCh38"
    assert row["provenance"]["splice_scenario"] in response["input"]["molecular_effect"]["source_refs"]["splice_site_offset"]
    assert not calls


def test_intronic_reconstruction_does_not_scan_or_hash_the_genome(tmp_path, monkeypatch):
    from helper_variants import indexer
    variant, ref, record, *_ = splice_case(tmp_path)
    monkeypatch.setattr(indexer, "sha256_file", lambda *a: pytest.fail("Unexpected whole-genome scan"))
    assert reconstruct(variant, ref, record)["status"] == "SPLICE_SCENARIO"


def test_splice_failure_is_explained_in_the_calculator_requirement(tmp_path, monkeypatch):
    from helper_next.api import acmg_calculator as api
    from test_pvs1_impact import annotation, detail_for
    variant, ref, record, *_ = splice_case(tmp_path)
    row = reconstruct(variant, ref, {})
    row["selected"] = True
    selected = annotation(consequence="splice_donor_variant")
    monkeypatch.setattr(api, "_selected_annotation", lambda _: (detail_for(variant, [selected]), selected))
    monkeypatch.setattr(api, "analyze_transcripts", lambda *a, **kw: dict(transcripts=[row], release_verified=True, warnings=[]))
    response = api.evaluate_pvs1({})
    requirement = next(item for item in map(json.loads, response["result"]["decision_trace"]) if item["id"] == "product")
    assert "configured local FASTA" in requirement["reason"]


@pytest.mark.skipif(os.environ.get("HELPER_TEST_PVS1_ATM_SPLICE") != "1", reason="Opt in with installed VEP 113/GRCh37 and FASTA")
def test_atm_c3746_intronic_deletion_with_installed_public_references():
    """Exact requested allele, using installed public references and no sample data."""
    from helper_next.core.acmg_vep_reference import local_transcript_reference
    variant = dict(assembly="GRCh37", contig="chr11", position=108153606,
                   reference_allele="GGTAAGTTTAT", alternate_allele="G", coordinate_system="genomic_1_based")
    gene, transcript = "ENSG00000149311", "ENST00000278616.4"
    source = local_transcript_reference(variant, gene, transcript, "113")
    assert source["status"] == "CACHED", source.get("missing")
    record = dict(run_config=dict(reference_fasta=os.environ["HELPER_TEST_GRCH37_FASTA"], reference_version="GRCh37"))
    row = splice_impact(molecular_impact(variant, gene, transcript, source["data"], "splice_donor_variant"),
                        variant, gene, source["data"], record=record)
    assert row["status"] == "SPLICE_SCENARIO", row["missing_data"]
    assert row["splice_analysis"]["site"]["native_motif"] == "GT"
    assert row["splice_analysis"]["site"]["altered_motif"] == "AC"
    scenario = row["splice_analysis"]["scenarios"][0]
    assert scenario["event"]["involved_exons"] == [25]
    assert scenario["rna_deleted_nt"] == scenario["coding_deleted_nt"] == 170
    assert row["physical_deleted_nt"] == 10
    assert row["predicted_protein_length"] == 1195 and row["termination_codon"] == 1196
    assert row["ptc_mrna_position"] == 3971
    assert row["nmd_predicted"] is True and row["nmd_distance_nt"] == 5231
    context = dict(gene=gene, disease="synthetic:qualified-context", inheritance="AR", scope="DISEASE_SPECIFIC",
                   molecular_mechanism="LoF", confidence="DEFINITIVE")
    context["source_refs"] = {key: ["synthetic:curation-for-policy-test"] for key in context}
    sample = PVS1Input(variant=dict(variant, consequence="splice_donor_variant"), disease_context=context,
                       **row["pvs1_input"])
    result = calculate_pvs1(sample)
    assert result.status == "ACTIVE" and result.applied_strength == "VERY_STRONG"
    assert result.requires_review is False
    assert sample.molecular_effect["products"][0]["basis"] == "PREDICTED"

