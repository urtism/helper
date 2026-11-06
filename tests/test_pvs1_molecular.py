"""Coherent synthetic references only; no HTTP, provider instance or engine."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from helper_next.core.acmg_digest import digest
from helper_next.core.acmg_pvs1 import nonsense as task25_nonsense
from helper_next.core.acmg_transcripts import complement, mrna_to_genomic, qualify, translate
from helper_variants.indexer import IndexedFasta, sha256_file

from pvs1.models import PVS1Input
from pvs1.molecular import (
    compute_molecular_evidence, frame_effect, junction_distances,
    map_variant_to_cds, protein_region_change, reconstruct_cds, reconstruct_splice_product,
    transcript_facts, translate_altered_cds,
)


TX = "ENST00000000001.1"
GENE = "ENSG00000000001"
CDS = "ATGAAACTAAAGCAATAA"  # MKLKQ*, standard code.


def reference_fixture(strand="+", first_exon_length=12, cds=CDS, exon_lengths=None):
    cdna = "GGG" + cds + "CCC"
    lengths = exon_lengths if exon_lengths is not None else [first_exon_length, len(cdna) - first_exon_length]
    assert sum(lengths) == len(cdna)
    starts = [100 * i for i in range(1, len(lengths) + 1)]
    if strand == "-":
        starts.reverse()
    exons, cursor = [], 1
    for index, (start, length) in enumerate(zip(starts, lengths), 1):
        exons.append({"exon_id": "SYNTHETIC_E" + str(index), "genomic_start": start,
                      "genomic_end": start + length - 1, "mrna_start": cursor,
                      "mrna_end": cursor + length - 1})
        cursor += length
    endpoints = [mrna_to_genomic(exons, strand, p) for p in (4, 3 + len(cds))]
    accession = TX.rsplit(".", 1)[0]
    lookup = {
        "id": accession, "version": 1, "assembly_name": "GRCh38", "species": "homo_sapiens",
        "object_type": "Transcript", "strand": 1 if strand == "+" else -1,
        "seq_region_name": "1", "length": len(cdna), "Parent": GENE,
        "biotype": "protein_coding", "MANE": [],
        "Translation": {"id": "ENSP00000000001", "length": len(cds) // 3 - 1,
                        "start": min(endpoints), "end": max(endpoints)},
        "Exon": [{"id": e["exon_id"], "start": e["genomic_start"], "end": e["genomic_end"],
                  "assembly_name": "GRCh38", "seq_region_name": "1", "strand": 1 if strand == "+" else -1}
                 for e in exons],
    }
    raw = {"lookup": lookup, "cdna": {"id": accession, "seq": cdna},
           "cds": {"id": accession, "seq": cds},
           "protein": {"id": "ENSP00000000001", "seq": translate(cds)[:-1]},
           "release_before": {"releases": [116]}, "release_after": {"releases": [116]}, "hgnc": []}
    reference = qualify(raw, TX, "GRCh38", "116")
    reference.update(artifact_digest=digest(raw), source_urls={"fixture": "synthetic:local:v1"},
                     coordinate_convention="1-based inclusive; transcript 5-prime to 3-prime; CDS includes stop")
    return reference


def sample_for_snv(reference, mrna_position=7, alternate="T", consequence="stop_gained"):
    original = reference["cdna"][mrna_position - 1]
    ref, alt = (original, alternate) if reference["strand"] == "+" else (complement(original), complement(alternate))
    return PVS1Input(
        variant={"assembly": "GRCh38", "contig": "1",
                 "position": mrna_to_genomic(reference["exons"], reference["strand"], mrna_position),
                 "reference_allele": ref, "alternate_allele": alt, "consequence": consequence,
                 "coordinate_system": "genomic_1_based"},
        disease_context={"gene": GENE, "molecular_mechanism": "UNKNOWN"},
        transcript={"accession": TX})


class MolecularEvidenceTest(unittest.TestCase):
    def assert_compatible(self, sample, result):
        data = result["data"]
        PVS1Input(variant=sample.variant, disease_context=sample.disease_context,
                  transcript=data["transcript"], molecular_effect=data["molecular_effect"])
        return data["molecular_effect"]["products"][0]

    def test_nonsense_reuses_task25_on_both_strands(self):
        for strand in ("+", "-"):
            with self.subTest(strand=strand):
                ref = reference_fixture(strand)
                sample = sample_for_snv(ref)
                sample.molecular_effect = {"products": [{"basis": "OBSERVED", "event_type": "UNKNOWN",
                                                        "evidence_quality": "Synthetic RNA; preserve separately."}]}
                original = copy.deepcopy(sample)
                with patch("pvs1.molecular.task25_nonsense", wraps=task25_nonsense) as reused:
                    result = compute_molecular_evidence(sample, ref, "SYNTHETIC_STOP_RNA.1")
                reused.assert_called_once()
                self.assertEqual(result["status"], "COMPLETE", result)
                product = self.assert_compatible(sample, result)
                self.assertEqual(product["ptc_start"], 7)
                self.assertEqual(product["ptc_junction_distances"], [[12, 5]])
                self.assertEqual(product["lost_protein_region"], [2, 5])
                self.assertEqual(product["basis"], "PREDICTED")
                self.assertIn("helper-nonsense-1.0", product["source_refs"]["ptc_start"])
                self.assertNotIn("lost_region_critical", product)
                self.assertEqual(sample, original)

    def test_frameshift_new_stop_and_minus_repeat_anchor(self):
        for strand in ("+", "-"):
            with self.subTest(strand=strand):
                ref = reference_fixture(strand)
                sample = sample_for_snv(ref, consequence="frameshift_variant")
                if strand == "+":
                    sample.variant.update(position=105, reference_allele="GA", alternate_allele="G")
                else:
                    sample.variant.update(position=204, reference_allele="TT", alternate_allele="T")
                result = compute_molecular_evidence(sample, ref, "SYNTHETIC_FS_RNA.1")
                self.assertEqual(result["status"], "COMPLETE", result)
                product = self.assert_compatible(sample, result)
                self.assertEqual(result["data"]["molecular_effect"]["cds_edit_interval"], [3, 4])
                self.assertEqual(result["data"]["calculation"]["altered_cds"], "ATGAACTAAAGCAATAA")
                self.assertEqual(product["frame_effect"], "OUT_OF_FRAME")
                self.assertEqual(product["ptc_start"], 10)
                self.assertEqual(product["ptc_junction_distances"], [[11, 1]])
                self.assertEqual(product["altered_protein_region"], [2, 5])
                self.assertIsNone(product["lost_protein_region"])
                self.assertEqual(result["data"]["calculation"]["protein_change"]["reference_changed_fraction"], 0.8)

    def test_in_frame_deletion_retains_shifted_native_stop(self):
        ref = reference_fixture()
        sample = sample_for_snv(ref, consequence="inframe_deletion")
        sample.variant.update(position=105, reference_allele="GAAA", alternate_allele="G")
        result = compute_molecular_evidence(sample, ref, "SYNTHETIC_INFRAME_RNA.1")
        self.assertEqual(result["status"], "COMPLETE", result)
        product = self.assert_compatible(sample, result)
        self.assertEqual(product["frame_effect"], "IN_FRAME")
        self.assertIsNone(product["ptc_start"])
        self.assertEqual(product["lost_protein_region"], [2, 2])
        self.assertEqual(result["data"]["calculation"]["translation"]["stop_kind"], "REFERENCE_STOP_RETAINED")

    def test_in_frame_insertion_on_both_strands(self):
        for strand in ("+", "-"):
            with self.subTest(strand=strand):
                ref = reference_fixture(strand)
                sample = sample_for_snv(ref, consequence="inframe_insertion")
                if strand == "+":
                    sample.variant.update(position=105, reference_allele="G", alternate_allele="GGCC")
                else:
                    sample.variant.update(position=205, reference_allele="T", alternate_allele="TGGC")
                result = compute_molecular_evidence(sample, ref, "SYNTHETIC_INSERTION_RNA.1")
                self.assertEqual(result["status"], "COMPLETE", result)
                product = self.assert_compatible(sample, result)
                self.assertEqual(result["data"]["molecular_effect"]["cds_edit_interval"], [3, 3])
                self.assertEqual(product["frame_effect"], "IN_FRAME")
                self.assertIsNone(product["ptc_start"])
                self.assertIsNone(product["lost_protein_region"])
                self.assertIsNone(product["altered_protein_region"])

    def test_missing_stop_does_not_invent_downstream_sequence(self):
        ref = reference_fixture(cds="ATG" + "CAA" * 5 + "TAA")
        sample = sample_for_snv(ref, consequence="frameshift_variant")
        sample.variant.update(position=105, reference_allele="GC", alternate_allele="G")
        result = compute_molecular_evidence(sample, ref, "SYNTHETIC_UNRESOLVED_RNA.1")
        self.assertEqual(result["status"], "INCOMPLETE", result)
        product = self.assert_compatible(sample, result)
        self.assertIsNone(product["ptc_start"])
        self.assertEqual(product["frame_effect"], "OUT_OF_FRAME")
        self.assertNotIn("lost_protein_region", product)
        self.assertIn("downstream", result["missing_data"][0])

    def test_ptc_at_junction_and_in_terminal_exon(self):
        ref = reference_fixture(first_exon_length=13)
        sample = sample_for_snv(ref, mrna_position=13)
        result = compute_molecular_evidence(sample, ref, "SYNTHETIC_BOUNDARY_RNA.1")
        self.assertEqual(result["status"], "COMPLETE", result)
        self.assertEqual(self.assert_compatible(sample, result)["ptc_junction_distances"], [[13, 0]])
        ref = reference_fixture()
        sample = sample_for_snv(ref, mrna_position=16)
        result = compute_molecular_evidence(sample, ref, "SYNTHETIC_TERMINAL_RNA.1")
        self.assertEqual(result["status"], "COMPLETE", result)
        self.assertEqual(self.assert_compatible(sample, result)["ptc_junction_distances"], [[12, -4]])
        self.assertIsNone(result["data"]["calculation"]["ptc_geometry"]["last_downstream_offset_nt"])
        self.assertEqual(junction_distances(10, [], "RNA.1")["data"]["ptc_junction_distances"], [])

    def test_qualified_reference_and_exact_version_required(self):
        ref = reference_fixture()
        for missing in ("artifact_digest", "annotation_release", "cdna", "coordinate_convention"):
            with self.subTest(missing=missing):
                incomplete = copy.deepcopy(ref)
                del incomplete[missing]
                result = compute_molecular_evidence(sample_for_snv(ref), incomplete, "RNA.1")
                self.assertEqual(result["status"], "INCOMPLETE")
                self.assertTrue(result["missing_data"])
        for accession in (None, TX.rsplit(".", 1)[0], TX.replace(".1", ".2")):
            sample = sample_for_snv(ref)
            sample.transcript["accession"] = accession
            self.assertEqual(compute_molecular_evidence(sample, ref, "RNA.1")["status"], "INCOMPLETE")
        self.assertEqual(compute_molecular_evidence(sample_for_snv(ref), None, "RNA.1")["status"], "INCOMPLETE")

    def test_incoherent_coordinates_identity_and_ref_are_incomplete(self):
        ref = reference_fixture()
        for field, value in (("assembly", "GRCh37"), ("contig", "2"),
                             ("reference_allele", "C"), ("alternate_allele", "N"),
                             ("alternate_allele", "<DEL>")):
            with self.subTest(field=field, value=value):
                sample = sample_for_snv(ref)
                sample.variant[field] = value
                self.assertEqual(map_variant_to_cds(sample, ref)["status"], "INCOMPLETE")
        sample = sample_for_snv(ref)
        sample.transcript["cds_interval"] = [5, 21]
        self.assertEqual(transcript_facts(sample, ref)["status"], "INCOMPLETE")
        broken = copy.deepcopy(ref)
        broken["exons"][1]["mrna_start"] += 1
        self.assertEqual(transcript_facts(sample_for_snv(ref), broken)["status"], "INCOMPLETE")

    def test_splice_boundary_and_start_loss_remain_unresolved(self):
        ref = reference_fixture()
        sample = sample_for_snv(ref, consequence="splice_donor_variant")
        sample.variant.update(position=112, reference_allele="G", alternate_allele="A")
        self.assertEqual(compute_molecular_evidence(sample, ref, "RNA.1")["status"], "INCOMPLETE")
        sample.variant.update(position=111, reference_allele="A", alternate_allele="ATG")
        self.assertEqual(compute_molecular_evidence(sample, ref, "RNA.1")["status"], "INCOMPLETE")
        sample = sample_for_snv(ref, mrna_position=4, alternate="G", consequence="start_lost")
        result = compute_molecular_evidence(sample, ref, "RNA.1")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIsNone(self.assert_compatible(sample, result)["ptc_start"])

    def test_phases_from_reference_with_unknown_input_entries(self):
        for strand in ("+", "-"):
            ref = reference_fixture(strand, first_exon_length=11)
            sample = sample_for_snv(ref)
            sample.transcript["exon_phases"] = [None, None]
            result = transcript_facts(sample, ref)
            self.assertEqual(result["status"], "COMPLETE", result)
            self.assertEqual(result["data"]["exon_phases"], [0, 1])
            self.assertNotIn("biologically_relevant", result["data"])
            sample.transcript["exon_phases"] = [0, 0]
            self.assertEqual(transcript_facts(sample, ref)["status"], "INCOMPLETE")

    def test_standalone_functions_reject_unqualified_inputs(self):
        self.assertEqual(reconstruct_cds(CDS, [3, 4], "A", "", None)["status"], "INCOMPLETE")
        self.assertEqual(reconstruct_cds(CDS, [3, 4], "C", "", "CDS.1")["status"], "INCOMPLETE")
        self.assertEqual(reconstruct_cds(CDS, [-1, 4], "A", "", "CDS.1")["status"], "INCOMPLETE")
        self.assertEqual(frame_effect(CDS, CDS[:-1], "CDS.1")["data"]["frame_effect"], "OUT_OF_FRAME")
        self.assertEqual(translate_altered_cds(CDS, "GTG" + CDS[3:], [0, 1], 4, "CDS.1")["status"], "INCOMPLETE")
        self.assertEqual(junction_distances(None, [12], "RNA.1")["status"], "INCOMPLETE")
        self.assertEqual(junction_distances(7, [12, 12], "RNA.1")["status"], "INCOMPLETE")

    def test_protein_difference_is_sequence_only(self):
        changed = protein_region_change("MKLKQ", "MN", "protein.1")["data"]
        self.assertEqual(changed["altered_protein_region"], [2, 5])
        self.assertEqual(changed["reference_changed_residues"], 4)
        self.assertEqual(changed["reference_changed_fraction"], 0.8)
        self.assertIsNone(changed["lost_protein_region"])
        deleted = protein_region_change("MKLKQ", "MLKQ", "protein.1")["data"]
        self.assertEqual(deleted["lost_protein_region"], [2, 2])
        self.assertEqual(deleted["reference_changed_fraction"], 0.2)
        self.assertEqual(protein_region_change("MKLKQ", "MKLKQ", "protein.1")["data"]["reference_changed_fraction"], 0)
        self.assertEqual(protein_region_change("MKX", "MK", "protein.1")["status"], "INCOMPLETE")
        ref = reference_fixture()
        sample = sample_for_snv(ref)
        result = compute_molecular_evidence(sample, ref, "RNA.1")
        product = self.assert_compatible(sample, result)
        product["ptc_junction_distances"] = [[12, "5"]]
        with self.assertRaises(ValueError):
            self.assert_compatible(sample, result)


class SpliceReconstructionTest(unittest.TestCase):
    def reconstruct(self, ref, skipped, basis="PREDICTED", sources=None):
        sample = sample_for_snv(ref, consequence="splice_donor_variant")
        event = {"basis": basis, "event_type": "EXON_SKIPPING", "involved_exons": skipped}
        if sources is not None:
            event["source_refs"] = sources
        result = reconstruct_splice_product(sample, ref, event, "SYNTHETIC_SKIP_RNA.1")
        if "molecular_effect" in result["data"]:
            data = result["data"]
            PVS1Input(variant=sample.variant, disease_context=sample.disease_context,
                      transcript=data["transcript"], molecular_effect=data["molecular_effect"])
        return result

    def test_in_frame_skip_and_actual_junctions_on_both_strands(self):
        for strand in ("+", "-"):
            with self.subTest(strand=strand):
                ref = reference_fixture(strand, exon_lengths=[6, 3, 6, 9])
                result = self.reconstruct(ref, [2])
                self.assertEqual(result["status"], "COMPLETE", result)
                product = result["data"]["molecular_effect"]["products"][0]
                audit = result["data"]["calculation"]
                self.assertEqual(product["sequence"], "GGGATGCTAAAGCAATAACCC")
                self.assertEqual(audit["altered_cds"], "ATGCTAAAGCAATAA")
                self.assertEqual(audit["translation"]["protein"], "MLKQ")
                self.assertEqual(product["frame_effect"], "IN_FRAME")
                self.assertIsNone(product["ptc_start"])
                self.assertEqual(product["lost_protein_region"], [2, 2])
                self.assertEqual(audit["protein_change"]["reference_changed_fraction"], 0.2)
                self.assertEqual(audit["retained_exons"], [1, 3, 4])
                self.assertEqual([j["mrna_position"] for j in audit["junctions"]], [6, 12])
                self.assertEqual([j["new"] for j in audit["junctions"]], [True, False])
                expected = [[105, 300], [305, 400]] if strand == "+" else [[400, 205], [200, 108]]
                self.assertEqual(product["genomic_junctions"], expected)
                self.assertEqual(product["basis"], "PREDICTED")
                self.assertTrue(result["warnings"])

    def test_out_of_frame_skip_with_new_ptc_and_product_distances(self):
        for strand in ("+", "-"):
            with self.subTest(strand=strand):
                ref = reference_fixture(strand, exon_lengths=[6, 1, 5, 12])
                with patch("pvs1.molecular.junction_distances", wraps=junction_distances) as reused:
                    result = self.reconstruct(ref, [2])
                reused.assert_called_once_with(10, [6, 11], "SYNTHETIC_SKIP_RNA.1")
                self.assertEqual(result["status"], "COMPLETE", result)
                product = result["data"]["molecular_effect"]["products"][0]
                audit = result["data"]["calculation"]
                self.assertEqual(audit["altered_cds"], "ATGAACTAAAGCAATAA")
                self.assertEqual(audit["translation"]["protein"], "MN")
                self.assertEqual(product["frame_effect"], "OUT_OF_FRAME")
                self.assertEqual(product["ptc_start"], 10)
                self.assertEqual(product["ptc_junction_distances"], [[6, -4], [11, 1]])
                self.assertEqual(audit["ptc_geometry"]["next_downstream_offset_nt"], 1)
                self.assertEqual(product["altered_protein_region"], [2, 5])
                self.assertIsNone(product["lost_protein_region"])
                self.assertEqual([j["mrna_position"] for j in audit["junctions"]], [6, 11])

    def test_skip_across_partial_codons_is_in_frame_with_mixed_protein_change(self):
        for strand in ("+", "-"):
            with self.subTest(strand=strand):
                ref = reference_fixture(strand, exon_lengths=[7, 3, 5, 9])
                result = self.reconstruct(ref, [2])
                self.assertEqual(result["status"], "COMPLETE", result)
                audit = result["data"]["calculation"]
                product = result["data"]["molecular_effect"]["products"][0]
                self.assertEqual(result["data"]["molecular_effect"]["cds_edit_interval"], [4, 7])
                self.assertEqual(audit["translation"]["protein"], "MIKQ")
                self.assertEqual(product["frame_effect"], "IN_FRAME")
                self.assertEqual(product["altered_protein_region"], [2, 3])
                self.assertIsNone(product["lost_protein_region"])
                self.assertIsNone(product["ptc_start"])

    def test_multiple_consecutive_exons_reuse_molecular_primitives(self):
        from pvs1 import molecular

        for strand in ("+", "-"):
            with self.subTest(strand=strand):
                ref = reference_fixture(strand, exon_lengths=[6, 1, 2, 6, 9])
                with patch("pvs1.molecular.reconstruct_cds", wraps=molecular.reconstruct_cds) as cds_reused, \
                     patch("pvs1.molecular.frame_effect", wraps=molecular.frame_effect) as frame_reused, \
                     patch("pvs1.molecular.translate_altered_cds", wraps=molecular.translate_altered_cds) as translation_reused, \
                     patch("pvs1.molecular.protein_region_change", wraps=molecular.protein_region_change) as protein_reused:
                    result = self.reconstruct(ref, [2, 3])
                for reused in (cds_reused, frame_reused, translation_reused, protein_reused):
                    reused.assert_called_once()
                self.assertEqual(result["status"], "COMPLETE", result)
                product = result["data"]["molecular_effect"]["products"][0]
                self.assertEqual(product["involved_exons"], [2, 3])
                self.assertEqual(result["data"]["calculation"]["altered_cds"], "ATGCTAAAGCAATAA")
                self.assertEqual(result["data"]["calculation"]["retained_exons"], [1, 4, 5])
                self.assertEqual(len(product["genomic_junctions"]), 2)

    def test_absent_unknown_and_nonrepresentable_events_are_incomplete(self):
        ref = reference_fixture(exon_lengths=[6, 3, 6, 9])
        sample = sample_for_snv(ref, consequence="splice_donor_variant")
        events = [None, {}, {"basis": "UNKNOWN", "event_type": "UNKNOWN"},
                  {"basis": "UNKNOWN", "event_type": "EXON_SKIPPING", "involved_exons": [2]}]
        for event in events:
            with self.subTest(event=event):
                result = reconstruct_splice_product(sample, ref, event, "RNA.1")
                self.assertEqual(result["status"], "INCOMPLETE", result)
                self.assertTrue(result["missing_data"])
                self.assertEqual(result["data"]["calculation"]["input_event"], event)
                self.assertNotIn("molecular_effect", result["data"])
        for skipped in (None, [], [0], [5], [2, 2], [3, 2], [1, 3], [1, 2, 3, 4], [True]):
            with self.subTest(skipped=skipped):
                self.assertEqual(self.reconstruct(ref, skipped)["status"], "INCOMPLETE")
        for event_type in (None, "UNKNOWN", "CRYPTIC_SITE", "INTRON_RETENTION", "OTHER"):
            event = {"basis": "PREDICTED", "event_type": event_type, "involved_exons": [2]}
            self.assertEqual(reconstruct_splice_product(sample, ref, event, "RNA.1")["status"], "INCOMPLETE")

    def test_reference_identity_coordinates_and_required_data(self):
        ref = reference_fixture(exon_lengths=[6, 3, 6, 9])
        sample = sample_for_snv(ref)
        event = {"basis": "PREDICTED", "event_type": "EXON_SKIPPING", "involved_exons": [2]}
        for key in ("cdna", "cds", "exons", "artifact_digest", "coordinate_convention"):
            broken = copy.deepcopy(ref)
            del broken[key]
            self.assertEqual(reconstruct_splice_product(sample, broken, event, "RNA.1")["status"], "INCOMPLETE")
        for key, value in (("assembly", "GRCh37"), ("chromosome", "2"), ("gene_ids", ["OTHER"])):
            broken = copy.deepcopy(ref)
            broken[key] = value
            self.assertEqual(reconstruct_splice_product(sample, broken, event, "RNA.1")["status"], "INCOMPLETE")
        sample.transcript["accession"] = TX.replace(".1", ".2")
        self.assertEqual(reconstruct_splice_product(sample, ref, event, "RNA.1")["status"], "INCOMPLETE")
        sample.transcript["accession"] = TX
        sample.transcript["exon_genomic_intervals"] = [[100, 105], [200, 202], [300, 305], [400, 409]]
        self.assertEqual(reconstruct_splice_product(sample, ref, event, "RNA.1")["status"], "INCOMPLETE")
        sample.transcript.pop("exon_genomic_intervals")
        for key in ("mrna_start", "genomic_end"):
            broken = copy.deepcopy(ref)
            broken["exons"][1][key] += 1
            self.assertEqual(reconstruct_splice_product(sample, broken, event, "RNA.1")["status"], "INCOMPLETE")
        for product_ref in (None, "", TX):
            self.assertEqual(reconstruct_splice_product(sample, ref, event, product_ref)["status"], "INCOMPLETE")

    def test_basis_original_rna_sources_and_inputs_are_preserved(self):
        ref = reference_fixture(exon_lengths=[6, 3, 6, 9])
        sample = sample_for_snv(ref)
        sample.molecular_effect = {"products": [{"basis": "UNKNOWN"}]}
        for basis in ("PREDICTED", "OBSERVED"):
            with self.subTest(basis=basis):
                event = {"basis": basis, "event_type": "EXON_SKIPPING", "involved_exons": [2],
                         "source_refs": {"basis": ["synthetic:RNA-assay:v1:sample7"],
                                         "involved_exons": ["synthetic:RNA-assay:v1:junction1-3"]},
                         "functional_evidence": ["Original synthetic RNA record"], "evidence_quality": "Not assessed"}
                original = copy.deepcopy((sample, ref, event))
                result = reconstruct_splice_product(sample, ref, event, "RNA.1")
                self.assertEqual(result["status"], "COMPLETE", result)
                product = result["data"]["molecular_effect"]["products"][0]
                self.assertEqual(product["basis"], basis)
                for key, value in event["source_refs"].items():
                    self.assertEqual(product["source_refs"][key], value)
                self.assertEqual(result["data"]["calculation"]["input_event"], event)
                self.assertEqual(product["functional_evidence"], event["functional_evidence"])
                self.assertEqual(product["evidence_quality"], event["evidence_quality"])
                sequence_sources = product["source_refs"]["sequence"]
                self.assertIn("helper-pvs1-molecular-1.0", sequence_sources)
                self.assertTrue(any("release=116|sha256:" in source for source in sequence_sources))
                self.assertIn("synthetic:RNA-assay:v1:sample7", sequence_sources)
                self.assertIn("does not experimentally validate", result["warnings"][0])
                self.assertEqual((sample, ref, event), original)
        for sources in (None, {"sequence": ["synthetic:sequence-only"]}):
            self.assertEqual(self.reconstruct(ref, [2], "OBSERVED", sources)["status"], "INCOMPLETE")

    def test_noncoding_skips_keep_cds_and_shift_transcript_axis(self):
        for strand in ("+", "-"):
            for lengths, skipped, cds_start, new_junction in (([3, 6, 12, 3], [1], 1, False),
                                                            ([3, 6, 12, 3], [4], 4, False),
                                                            ([1, 1, 4, 18], [2], 3, True)):
                with self.subTest(strand=strand, skipped=skipped):
                    ref = reference_fixture(strand, exon_lengths=lengths)
                    result = self.reconstruct(ref, skipped)
                    self.assertEqual(result["status"], "COMPLETE", result)
                    audit = result["data"]["calculation"]
                    product = result["data"]["molecular_effect"]["products"][0]
                    self.assertEqual(audit["altered_cds"], CDS)
                    self.assertEqual(audit["product_cds_start"], cds_start)
                    self.assertEqual(audit["translation"]["protein"], "MKLKQ")
                    self.assertEqual(product["frame_effect"], "IN_FRAME")
                    self.assertIsNone(product["ptc_start"])
                    self.assertIsNone(product["altered_protein_region"])
                    self.assertNotIn("cds_edit_interval", result["data"]["molecular_effect"])
                    self.assertEqual(any(j["new"] for j in audit["junctions"]), new_junction)

    def test_start_stop_loss_and_missing_stop_do_not_invent_proteins(self):
        for strand in ("+", "-"):
            ref = reference_fixture(strand, exon_lengths=[6, 3, 6, 9])
            for skipped, retained_flag in (([1], "original_start_retained"), ([4], "original_stop_retained"),
                                           ([1, 2, 3], "original_start_retained")):
                with self.subTest(strand=strand, skipped=skipped):
                    result = self.reconstruct(ref, skipped)
                    self.assertEqual(result["status"], "INCOMPLETE", result)
                    audit = result["data"]["calculation"]
                    product = result["data"]["molecular_effect"]["products"][0]
                    self.assertFalse(audit[retained_flag])
                    self.assertIsNone(audit["translation"])
                    self.assertIsNone(product["ptc_start"])
                    self.assertNotIn("altered_protein_region", product)
                    self.assertTrue(product["sequence"])
                    self.assertIn("initiation/native stop affected", result["missing_data"][0])
                    if skipped == [1, 2, 3]:
                        self.assertEqual(product["genomic_junctions"], [])
            ref = reference_fixture(strand, cds="ATG" + "CAA" * 5 + "TAA", exon_lengths=[6, 1, 6, 14])
            result = self.reconstruct(ref, [2])
            self.assertEqual(result["status"], "INCOMPLETE", result)
            product = result["data"]["molecular_effect"]["products"][0]
            self.assertEqual(product["frame_effect"], "OUT_OF_FRAME")
            self.assertIsNone(product["ptc_start"])
            self.assertNotIn("protein_accession", product)
            self.assertIn("no stop", result["missing_data"][0])

    def test_partial_start_or_stop_codon_loss_stays_incomplete(self):
        for strand in ("+", "-"):
            for lengths, skipped, flag in (([4, 1, 7, 12], [2], "original_start_retained"),
                                           ([6, 3, 10, 1, 4], [4], "original_stop_retained")):
                with self.subTest(strand=strand, skipped=skipped):
                    result = self.reconstruct(reference_fixture(strand, exon_lengths=lengths), skipped)
                    self.assertEqual(result["status"], "INCOMPLETE", result)
                    self.assertFalse(result["data"]["calculation"][flag])
                    self.assertIsNone(result["data"]["calculation"]["translation"])
                    self.assertIsNone(result["data"]["molecular_effect"]["products"][0]["ptc_start"])


class CrypticSpliceTest(unittest.TestCase):
    def reconstruct(self, ref, exon, interval):
        event = {"basis": "PREDICTED", "event_type": "CRYPTIC_SITE", "involved_exons": [exon],
                 "retained_exon_interval": interval}
        return reconstruct_splice_product(sample_for_snv(ref), ref, event, "SYNTHETIC_CRYPTIC_RNA.1")

    def product(self, result, ref):
        self.assertEqual(result["status"], "COMPLETE", result)
        sample = sample_for_snv(ref)
        data = result["data"]
        PVS1Input(variant=sample.variant, disease_context=sample.disease_context,
                  transcript=data["transcript"], molecular_effect=data["molecular_effect"])
        self.assertEqual(data["transcript"]["accession"], TX)
        self.assertEqual(data["calculation"]["reference_transcript"], TX)
        return data["molecular_effect"]["products"][0]

    def test_exonic_donor_in_frame_on_both_strands(self):
        for strand in ("+", "-"):
            with self.subTest(strand=strand):
                ref = reference_fixture(strand, exon_lengths=[3, 9, 6, 6])
                result = self.reconstruct(ref, 2, [4, 9])
                product = self.product(result, ref)
                audit = result["data"]["calculation"]
                self.assertEqual(product["sequence"], ref["cdna"][:9] + ref["cdna"][12:])
                self.assertEqual(audit["altered_cds"], "ATGAAAAAGCAATAA")
                self.assertEqual(audit["translation"]["protein"], "MKKQ")
                self.assertEqual(product["frame_effect"], "IN_FRAME")
                self.assertIsNone(product["ptc_start"])
                self.assertEqual(product["lost_protein_region"], [3, 3])
                self.assertEqual(product["retained_exon_interval"], [4, 9])
                self.assertEqual(audit["cryptic_site_type"], "DONOR")
                self.assertEqual(audit["cryptic_site_position"], 9)
                self.assertEqual(audit["retained_exons"], [1, 2, 3, 4])
                self.assertEqual([j["mrna_position"] for j in audit["junctions"]], [3, 9, 15])
                self.assertEqual([j["new"] for j in audit["junctions"]], [False, True, False])
                expected = [[102, 200], [205, 300], [305, 400]] if strand == "+" else [[400, 308], [303, 205], [200, 105]]
                self.assertEqual(product["genomic_junctions"], expected)

    def test_exonic_acceptor_in_frame_on_both_strands(self):
        for strand in ("+", "-"):
            with self.subTest(strand=strand):
                ref = reference_fixture(strand, exon_lengths=[6, 6, 6, 6])
                result = self.reconstruct(ref, 2, [10, 12])
                product = self.product(result, ref)
                audit = result["data"]["calculation"]
                self.assertEqual(product["sequence"], ref["cdna"][:6] + ref["cdna"][9:])
                self.assertEqual(audit["altered_cds"], "ATGCTAAAGCAATAA")
                self.assertEqual(audit["translation"]["protein"], "MLKQ")
                self.assertEqual(product["frame_effect"], "IN_FRAME")
                self.assertIsNone(product["ptc_start"])
                self.assertEqual(product["lost_protein_region"], [2, 2])
                self.assertEqual(audit["cryptic_site_type"], "ACCEPTOR")
                self.assertEqual(audit["cryptic_site_position"], 10)
                self.assertEqual([j["mrna_position"] for j in audit["junctions"]], [6, 9, 15])
                self.assertEqual([j["new"] for j in audit["junctions"]], [True, False, False])
                expected = [[105, 203], [205, 300], [305, 400]] if strand == "+" else [[400, 302], [300, 205], [200, 105]]
                self.assertEqual(product["genomic_junctions"], expected)

    def test_cryptic_out_of_frame_ptc_reuses_existing_calculations(self):
        from pvs1 import molecular

        for strand in ("+", "-"):
            for lengths, exon, interval in (([7, 5, 6, 6], 1, [1, 6]), ([6, 6, 6, 6], 2, [8, 12])):
                with self.subTest(strand=strand, interval=interval):
                    ref = reference_fixture(strand, exon_lengths=lengths)
                    with patch("pvs1.molecular.reconstruct_cds", wraps=molecular.reconstruct_cds) as cds_reused, \
                         patch("pvs1.molecular.frame_effect", wraps=molecular.frame_effect) as frame_reused, \
                         patch("pvs1.molecular.translate_altered_cds", wraps=molecular.translate_altered_cds) as translation_reused, \
                         patch("pvs1.molecular.protein_region_change", wraps=molecular.protein_region_change) as protein_reused, \
                         patch("pvs1.molecular.junction_distances", wraps=molecular.junction_distances) as junction_reused:
                        result = self.reconstruct(ref, exon, interval)
                    for reused in (cds_reused, frame_reused, translation_reused, protein_reused):
                        reused.assert_called_once()
                    junction_reused.assert_called_once_with(10, [6, 11, 17], "SYNTHETIC_CRYPTIC_RNA.1")
                    product = self.product(result, ref)
                    audit = result["data"]["calculation"]
                    self.assertEqual(audit["altered_cds"], "ATGAACTAAAGCAATAA")
                    self.assertEqual(audit["translation"]["protein"], "MN")
                    self.assertEqual(product["frame_effect"], "OUT_OF_FRAME")
                    self.assertEqual(product["ptc_start"], 10)
                    self.assertEqual(product["ptc_junction_distances"], [[6, -4], [11, 1], [17, 7]])
                    self.assertEqual(product["altered_protein_region"], [2, 5])
                    self.assertIsNone(product["lost_protein_region"])

    def test_invalid_or_missing_cryptic_boundaries_are_incomplete(self):
        for strand in ("+", "-"):
            ref = reference_fixture(strand, exon_lengths=[6, 6, 6, 6])
            for interval in (None, [], [8], [8, 12, 13], [0, 12], [-1, 12], [8, 7], [True, 12],
                             [8.0, 12], [5, 12], [8, 13], [7, 12], [8, 11]):
                with self.subTest(strand=strand, interval=interval):
                    result = self.reconstruct(ref, 2, interval)
                    self.assertEqual(result["status"], "INCOMPLETE", result)
                    self.assertTrue(result["missing_data"])
                    self.assertEqual(result["data"]["calculation"]["reference_transcript"], TX)
                    self.assertNotIn("molecular_effect", result["data"])
            for exon, interval in ((1, [2, 6]), (4, [19, 23]), (5, [25, 26])):
                self.assertEqual(self.reconstruct(ref, exon, interval)["status"], "INCOMPLETE")
            sample = sample_for_snv(ref)
            event = {"basis": "PREDICTED", "event_type": "CRYPTIC_SITE", "involved_exons": [2]}
            self.assertEqual(reconstruct_splice_product(sample, ref, event, "RNA.1")["status"], "INCOMPLETE")
            event.update(involved_exons=[2, 3], retained_exon_interval=[8, 12])
            self.assertEqual(reconstruct_splice_product(sample, ref, event, "RNA.1")["status"], "INCOMPLETE")
            event.update(event_type="EXON_SKIPPING", involved_exons=[2])
            self.assertEqual(reconstruct_splice_product(sample, ref, event, "RNA.1")["status"], "INCOMPLETE")

    def test_cryptic_basis_provenance_and_selected_transcript_are_preserved(self):
        for strand in ("+", "-"):
            ref = reference_fixture(strand, exon_lengths=[6, 6, 6, 6])
            sample = sample_for_snv(ref, consequence="splice_acceptor_variant")
            sample.transcript["biologically_relevant"] = None
            sample.molecular_effect = {"products": [{"basis": "UNKNOWN"}]}
            for basis in ("PREDICTED", "OBSERVED", "UNKNOWN"):
                event = {"basis": basis, "event_type": "CRYPTIC_SITE", "involved_exons": [2],
                         "retained_exon_interval": [10, 12], "evidence_quality": "Not assessed",
                         "source_refs": {"retained_exon_interval": ["synthetic:RNA:v1:cryptic-acceptor"]}}
                original = copy.deepcopy((sample, ref, event))
                result = reconstruct_splice_product(sample, ref, event, "RNA.1")
                self.assertEqual(result["data"]["calculation"]["input_event"], event)
                self.assertEqual(result["data"]["calculation"]["reference_transcript"], TX)
                if basis == "UNKNOWN":
                    self.assertEqual(result["status"], "INCOMPLETE")
                    self.assertNotIn("molecular_effect", result["data"])
                else:
                    product = self.product(result, ref)
                    self.assertEqual(product["basis"], basis)
                    self.assertEqual(product["source_refs"]["retained_exon_interval"], event["source_refs"]["retained_exon_interval"])
                    self.assertIn("synthetic:RNA:v1:cryptic-acceptor", product["source_refs"]["sequence"])
                    self.assertTrue(any(TX in source and "release=116|sha256:" in source for source in product["source_refs"]["sequence"]))
                    self.assertEqual(product["evidence_quality"], "Not assessed")
                    self.assertIsNone(result["data"]["transcript"]["biologically_relevant"])
                    self.assertIn("does not experimentally validate", result["warnings"][0])
                self.assertEqual((sample, ref, event), original)
            event.update(basis="OBSERVED", source_refs={})
            self.assertEqual(reconstruct_splice_product(sample, ref, event, "RNA.1")["status"], "INCOMPLETE")
            event["basis"] = "PREDICTED"
            for accession in (TX.replace(".1", ".2"), "ENST00000000002.1"):
                sample.transcript["accession"] = accession
                result = reconstruct_splice_product(sample, ref, event, "RNA.1")
                self.assertEqual(result["status"], "INCOMPLETE")
                self.assertEqual(result["data"]["calculation"]["reference_transcript"], accession)
                self.assertNotIn("molecular_effect", result["data"])

    def test_cryptic_noncoding_boundaries_keep_reference_translation(self):
        for strand in ("+", "-"):
            ref = reference_fixture(strand, exon_lengths=[3, 6, 12, 3])
            for exon, interval, cds_start in ((1, [1, 2], 3), (4, [23, 24], 4)):
                result = self.reconstruct(ref, exon, interval)
                product = self.product(result, ref)
                audit = result["data"]["calculation"]
                self.assertEqual(audit["altered_cds"], CDS)
                self.assertEqual(audit["translation"]["protein"], "MKLKQ")
                self.assertEqual(audit["product_cds_start"], cds_start)
                self.assertEqual(product["frame_effect"], "IN_FRAME")
                self.assertIsNone(product["ptc_start"])
                self.assertIsNone(product["altered_protein_region"])

    def test_cryptic_start_stop_loss_remains_partial(self):
        for strand in ("+", "-"):
            for lengths, exon, interval, flag in (([6, 6, 6, 6], 1, [1, 4], "original_start_retained"),
                                                  ([4, 5, 6, 9], 2, [6, 9], "original_start_retained"),
                                                  ([6, 6, 9, 3], 3, [13, 20], "original_stop_retained"),
                                                  ([6, 6, 6, 3, 3], 4, [20, 21], "original_stop_retained")):
                with self.subTest(strand=strand, interval=interval):
                    ref = reference_fixture(strand, exon_lengths=lengths)
                    result = self.reconstruct(ref, exon, interval)
                    self.assertEqual(result["status"], "INCOMPLETE", result)
                    audit = result["data"]["calculation"]
                    product = result["data"]["molecular_effect"]["products"][0]
                    self.assertFalse(audit[flag])
                    self.assertIsNone(audit["translation"])
                    self.assertIsNone(product["ptc_start"])
                    self.assertNotIn("protein_accession", product)
                    self.assertTrue(product["sequence"])


class IntronicCrypticSpliceTest(unittest.TestCase):
    def fixture(self, strand="+", site="DONOR", inserted="GCC", lengths=None, exon_index=None):
        ref = reference_fixture(strand, exon_lengths=lengths or [6, 6, 6, 6])
        index = exon_index if exon_index is not None else (1 if site == "DONOR" else 2)
        exon = ref["exons"][index - 1]
        direction = 1 if strand == "+" else -1
        if site == "DONOR":
            edge = mrna_to_genomic(ref["exons"], strand, exon["mrna_end"])
            pair = [edge + direction * len(inserted), mrna_to_genomic(ref["exons"], strand, ref["exons"][index]["mrna_start"])]
            interval = sorted([edge + direction, pair[0]])
        else:
            edge = mrna_to_genomic(ref["exons"], strand, exon["mrna_start"])
            pair = [mrna_to_genomic(ref["exons"], strand, ref["exons"][index - 2]["mrna_end"]), edge - direction * len(inserted)]
            interval = sorted([pair[1], edge - direction])
        bases = list("C" * 500)
        for e in ref["exons"]:
            sequence = ref["cdna"][e["mrna_start"] - 1:e["mrna_end"]]
            bases[e["genomic_start"] - 1:e["genomic_end"]] = sequence if strand == "+" else complement(sequence)
        bases[interval[0] - 1:interval[1]] = inserted if strand == "+" else complement(inserted)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "synthetic.fa"
        path.write_text(">1\n" + "".join(bases) + "\n")
        Path(str(path) + ".fai").write_text("1\t500\t3\t500\t501\n")
        reader = IndexedFasta(path)
        self.addCleanup(reader.close)
        genome = {"assembly": "GRCh38", "chromosome": "1", "reader": reader,
                  "source_ref": "synthetic:genome", "source_version": "v1",
                  "artifact_digest": {"algorithm": "sha256", "value": sha256_file(path)}}
        supplied = {"assembly": "GRCh38", "chromosome": "1", "genomic_interval": interval,
                    "strand": strand, "coordinate_system": "genomic_1_based_closed", "sequence": inserted,
                    "source_ref": "synthetic:intronic-sequence", "source_version": "v1"}
        event = {"basis": "PREDICTED", "event_type": "CRYPTIC_SITE", "involved_exons": [index],
                 "genomic_junctions": [pair], "functional_evidence": ["Synthetic event; no biological assay"],
                 "evidence_quality": "Not assessed",
                 "source_refs": {"genomic_junctions": ["synthetic:splice-event:v7"],
                                 "method": ["synthetic-splice-method"], "method_version": ["2.1"]}}
        return ref, event, supplied, genome

    def reconstruct(self, ref, event, supplied, genome):
        return reconstruct_splice_product(sample_for_snv(ref), ref, event, "INTRONIC_RNA.1",
                                          intronic_sequence=supplied, genomic_reference=genome)

    def product(self, ref, result):
        self.assertEqual(result["status"], "COMPLETE", result)
        sample, data = sample_for_snv(ref), result["data"]
        PVS1Input(variant=sample.variant, disease_context=sample.disease_context,
                  transcript=data["transcript"], molecular_effect=data["molecular_effect"])
        self.assertEqual(data["transcript"]["accession"], TX)
        self.assertEqual(data["calculation"]["reference_transcript"], TX)
        return data["molecular_effect"]["products"][0]

    def test_intronic_donor_and_acceptor_in_frame_on_both_strands(self):
        for strand in ("+", "-"):
            for site in ("DONOR", "ACCEPTOR"):
                with self.subTest(strand=strand, site=site):
                    ref, event, supplied, genome = self.fixture(strand, site)
                    result = self.reconstruct(ref, event, supplied, genome)
                    product = self.product(ref, result)
                    audit = result["data"]["calculation"]
                    self.assertEqual(product["sequence"], ref["cdna"][:6] + "GCC" + ref["cdna"][6:])
                    self.assertEqual(audit["altered_cds"], "ATGGCCAAACTAAAGCAATAA")
                    self.assertEqual(audit["translation"]["protein"], "MAKLKQ")
                    self.assertEqual(product["frame_effect"], "IN_FRAME")
                    self.assertIsNone(product["ptc_start"])
                    self.assertIsNone(product["altered_protein_region"])
                    self.assertEqual(audit["protein_change"]["product_difference_region"], [2, 2])
                    self.assertEqual(result["data"]["molecular_effect"]["cds_edit_interval"], [3, 3])
                    self.assertEqual(audit["cryptic_site_type"], site)
                    self.assertEqual(audit["cryptic_site_coordinate_system"], "genomic_1_based")
                    self.assertEqual(audit["intronic_sequence"]["sequence"], "GCC")
                    self.assertEqual(audit["input_intronic_sequence"], supplied)
                    self.assertEqual([j["mrna_position"] for j in audit["junctions"]], [9 if site == "DONOR" else 6, 15, 21])
                    self.assertEqual([j["new"] for j in audit["junctions"]], [True, False, False])
                    if strand == "+":
                        expected = [[108, 200] if site == "DONOR" else [105, 197], [205, 300], [305, 400]]
                    else:
                        expected = [[397, 305] if site == "DONOR" else [400, 308], [300, 205], [200, 105]]
                    self.assertEqual(product["genomic_junctions"], expected)

    def test_intronic_frameshift_ptc_reuses_molecular_primitives(self):
        from pvs1 import molecular

        for strand in ("+", "-"):
            for site in ("DONOR", "ACCEPTOR"):
                with self.subTest(strand=strand, site=site):
                    ref, event, supplied, genome = self.fixture(strand, site, "T")
                    with patch("pvs1.molecular.reconstruct_cds", wraps=molecular.reconstruct_cds) as cds_reused, \
                         patch("pvs1.molecular.frame_effect", wraps=molecular.frame_effect) as frame_reused, \
                         patch("pvs1.molecular.translate_altered_cds", wraps=molecular.translate_altered_cds) as translation_reused, \
                         patch("pvs1.molecular.protein_region_change", wraps=molecular.protein_region_change) as protein_reused, \
                         patch("pvs1.molecular.junction_distances", wraps=molecular.junction_distances) as junction_reused:
                        result = self.reconstruct(ref, event, supplied, genome)
                    for reused in (cds_reused, frame_reused, translation_reused, protein_reused):
                        reused.assert_called_once()
                    positions = [7 if site == "DONOR" else 6, 13, 19]
                    junction_reused.assert_called_once_with(7, positions, "INTRONIC_RNA.1")
                    product = self.product(ref, result)
                    self.assertEqual(product["frame_effect"], "OUT_OF_FRAME")
                    self.assertEqual(product["ptc_start"], 7)
                    self.assertEqual(product["ptc_junction_distances"], [[p, p - 7] for p in positions])
                    self.assertEqual(product["lost_protein_region"], [2, 5])
                    self.assertEqual(result["data"]["calculation"]["translation"]["protein"], "M")

    def test_intronic_sequence_can_be_read_from_verified_existing_fasta(self):
        for strand in ("+", "-"):
            ref, event, supplied, genome = self.fixture(strand)
            result = self.reconstruct(ref, event, None, genome)
            self.product(ref, result)
            self.assertEqual(result["data"]["calculation"]["intronic_sequence"]["sequence"], supplied["sequence"])
            for provided in (None, supplied):
                result = self.reconstruct(ref, event, provided, None)
                self.assertEqual(result["status"], "INCOMPLETE", result)
                self.assertIn("genomic FASTA required", result["missing_data"][0])
                self.assertNotIn("molecular_effect", result["data"])

    def test_intronic_reference_metadata_checksum_and_flanks_must_be_verified(self):
        for strand in ("+", "-"):
            ref, event, supplied, genome = self.fixture(strand)
            for key, value in (("assembly", "GRCh37"), ("chromosome", "2"), ("reader", None),
                               ("source_ref", None), ("source_version", None), ("artifact_digest", None),
                               ("artifact_digest", {"algorithm": "sha256", "value": "0" * 64})):
                with self.subTest(strand=strand, key=key):
                    broken = dict(genome, **{key: value})
                    result = self.reconstruct(ref, event, supplied, broken)
                    self.assertEqual(result["status"], "INCOMPLETE", result)
                    self.assertNotIn("molecular_effect", result["data"])
            path = genome["reader"].path
            bases = list(path.read_text().splitlines()[1])
            position = ref["exons"][0]["genomic_start"] - 1
            bases[position] = "A" if bases[position] != "A" else "T"
            path.write_text(">1\n" + "".join(bases) + "\n")
            genome["artifact_digest"]["value"] = sha256_file(path)
            result = self.reconstruct(ref, event, supplied, genome)
            self.assertEqual(result["status"], "INCOMPLETE", result)
            self.assertIn("flanking exon sequence", result["missing_data"][0])

    def test_caller_intronic_sequence_metadata_and_bases_must_match(self):
        for strand in ("+", "-"):
            ref, event, supplied, genome = self.fixture(strand)
            for key in supplied:
                with self.subTest(strand=strand, missing=key):
                    broken = dict(supplied)
                    del broken[key]
                    result = self.reconstruct(ref, event, broken, genome)
                    self.assertEqual(result["status"], "INCOMPLETE", result)
            for key, value in (("sequence", "AAA"), ("sequence", "GC"), ("sequence", "GCN"),
                               ("strand", "+" if strand == "-" else "-"), ("genomic_interval", [1, 3]),
                               ("coordinate_system", "genomic_0_based_half_open")):
                broken = dict(supplied, **{key: value})
                self.assertEqual(self.reconstruct(ref, event, broken, genome)["status"], "INCOMPLETE")

    def test_intronic_event_coordinates_exclude_full_retention_and_multiple_events(self):
        for strand in ("+", "-"):
            for site in ("DONOR", "ACCEPTOR"):
                ref, event, supplied, genome = self.fixture(strand, site)
                direction = 1 if strand == "+" else -1
                donor, acceptor = event["genomic_junctions"][0]
                full_pair = [acceptor - direction, acceptor] if site == "DONOR" else [donor, donor + direction]
                for pairs in ([], [[donor, acceptor], [donor, acceptor]], [[0, acceptor]],
                              [full_pair], [[acceptor, donor]], [[donor + 10 * direction, acceptor - 10 * direction]]):
                    with self.subTest(strand=strand, site=site, pairs=pairs):
                        broken = copy.deepcopy(event)
                        broken["genomic_junctions"] = pairs
                        result = self.reconstruct(ref, broken, supplied, genome)
                        self.assertEqual(result["status"], "INCOMPLETE", result)
                broken = copy.deepcopy(event)
                broken["involved_exons"] = [1, 2]
                self.assertEqual(self.reconstruct(ref, broken, supplied, genome)["status"], "INCOMPLETE")
                broken = copy.deepcopy(event)
                broken["event_type"] = "INTRON_RETENTION"
                self.assertEqual(self.reconstruct(ref, broken, supplied, genome)["status"], "INCOMPLETE")

    def test_intronic_evidence_and_transcript_provenance_are_preserved(self):
        for strand in ("+", "-"):
            ref, event, supplied, genome = self.fixture(strand)
            sample = sample_for_snv(ref)
            sample.molecular_effect = {"products": [{"basis": "UNKNOWN"}]}
            for basis in ("PREDICTED", "OBSERVED", "UNKNOWN"):
                event["basis"] = basis
                original = copy.deepcopy((sample, ref, event, supplied))
                result = reconstruct_splice_product(sample, ref, event, "INTRONIC_RNA.1",
                                                    intronic_sequence=supplied, genomic_reference=genome)
                self.assertEqual(result["data"]["calculation"]["reference_transcript"], TX)
                self.assertEqual(result["data"]["calculation"]["input_event"], event)
                self.assertEqual((sample, ref, event, supplied), original)
                if basis == "UNKNOWN":
                    self.assertEqual(result["status"], "INCOMPLETE")
                    self.assertNotIn("molecular_effect", result["data"])
                    continue
                product = self.product(ref, result)
                self.assertEqual(product["basis"], basis)
                self.assertEqual(product["functional_evidence"], event["functional_evidence"])
                self.assertEqual(product["evidence_quality"], event["evidence_quality"])
                for key, sources in event["source_refs"].items():
                    for source in sources:
                        self.assertIn(source, product["source_refs"][key])
                self.assertTrue(any("synthetic:genome|version=v1|sha256:" in source for source in product["source_refs"]["sequence"]))
                self.assertIn("synthetic:intronic-sequence|version=v1", product["source_refs"]["sequence"])
                self.assertIn("does not experimentally validate", result["warnings"][0])
            event["basis"] = "OBSERVED"
            event["source_refs"].pop("genomic_junctions")
            self.assertEqual(self.reconstruct(ref, event, supplied, genome)["status"], "INCOMPLETE")
            event["basis"] = "PREDICTED"
            event["source_refs"]["genomic_junctions"] = ["synthetic:event"]
            event["source_refs"].pop("method")
            self.assertEqual(self.reconstruct(ref, event, supplied, genome)["status"], "INCOMPLETE")
            event["source_refs"]["method"] = ["synthetic:method"]
            sample.transcript["accession"] = TX.replace(".1", ".2")
            result = reconstruct_splice_product(sample, ref, event, "RNA.1", genomic_reference=genome)
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertEqual(result["data"]["calculation"]["reference_transcript"], TX.replace(".1", ".2"))

    def test_intronic_utr_and_disrupted_start_stop_use_existing_limits(self):
        for strand in ("+", "-"):
            for site, index, expected_start in (("DONOR", 1, 7), ("ACCEPTOR", 2, 7), ("DONOR", 3, 4), ("ACCEPTOR", 4, 4)):
                ref, event, supplied, genome = self.fixture(strand, site, lengths=[3, 6, 12, 3], exon_index=index)
                result = self.reconstruct(ref, event, supplied, genome)
                product = self.product(ref, result)
                audit = result["data"]["calculation"]
                self.assertEqual(audit["altered_cds"], CDS)
                self.assertEqual(audit["product_cds_start"], expected_start)
                self.assertEqual(audit["translation"]["protein"], "MKLKQ")
                self.assertEqual(product["frame_effect"], "IN_FRAME")
                self.assertIsNone(product["ptc_start"])
            for lengths, index, flag in (([4, 5, 6, 9], 1, "original_start_retained"),
                                         ([6, 6, 8, 4], 3, "original_stop_retained")):
                ref, event, supplied, genome = self.fixture(strand, lengths=lengths, exon_index=index)
                result = self.reconstruct(ref, event, supplied, genome)
                self.assertEqual(result["status"], "INCOMPLETE", result)
                self.assertFalse(result["data"]["calculation"][flag])
                product = result["data"]["molecular_effect"]["products"][0]
                self.assertIsNone(product["ptc_start"])
                self.assertNotIn("protein_accession", product)
