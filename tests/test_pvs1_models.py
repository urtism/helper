import copy
import json
import re
import unittest
from dataclasses import asdict
from pathlib import Path

from pvs1.models import PVS1Input, PVS1Result


class PVS1ModelsTest(unittest.TestCase):
    def setUp(self):
        self.data = {
            "variant": {
                "assembly": "DEMO_ASSEMBLY_1", "contig": "DEMO_CONTIG_1",
                "position": 2031, "reference_allele": "C", "alternate_allele": "T",
                "consequence": "stop_gained", "coordinate_system": "genomic_1_based",
                "source_refs": {"consequence": ["DEMO_ANNOTATION:v1"]},
            },
            "disease_context": {
                "gene": "DEMO_GENE", "disease": "DEMO_DISEASE", "inheritance": "AD",
                "molecular_mechanism": "LoF", "confidence": "DEFINITIVE",
                "scope": "DISEASE_SPECIFIC",
                "source_refs": {"molecular_mechanism": ["DEMO_CURATION:v1"]},
            },
            "transcript": {
                "accession": "DEMO_TRANSCRIPT.1", "strand": "+",
                "coordinate_system": "transcript_1_based_closed",
                "cds_interval": [31, 420],
                "exon_genomic_intervals": [[1001, 1150], [2001, 2150], [3001, 3150]],
                "exon_coordinate_system": "genomic_1_based_closed", "exon_phases": [0, 0, 0],
                "sequence_ref": "DEMO_TRANSCRIPT.1#spliced_dna:v1",
                "biologically_relevant": None,
            },
        }

    def test_common_validation_and_serialization(self):
        sample = PVS1Input(**self.data)
        payload = json.loads(json.dumps(asdict(sample)))
        self.assertEqual(payload["variant"]["position"], 2031)
        self.assertEqual(payload["transcript"]["cds_interval"], [31, 420])
        self.assertEqual(payload["disease_context"]["source_refs"],
                         self.data["disease_context"]["source_refs"])
        document = (Path(__file__).resolve().parents[1] / "docs" /
                    "ACMG_CALCULATOR_STEP2_MODELS.md").read_text(encoding="utf-8")
        examples = re.findall(r"```json\n(.*?)\n```", document, re.DOTALL)
        self.assertEqual(len(examples), 4)
        for index, example in enumerate(examples):
            with self.subTest(documented_example=index + 1):
                sample = PVS1Input(**json.loads(example))
                json.dumps(asdict(sample))
        for block, name, value in (
            ("variant", "position", 0), ("variant", "position", True),
            ("variant", "coordinate_system", "genomic_0_based"),
            ("variant", "typo", "unsupported"),
            ("disease_context", "molecular_mechanism", "invented"),
            ("disease_context", "confidence", "HIGH"),
            ("transcript", "cds_interval", [420, 31]),
            ("transcript", "exon_phases", [0, 0]),
            ("transcript", "exon_phases", [0, 3, 0]),
            ("transcript", "biologically_relevant", "false"),
            ("transcript", "source_refs", {"cds_interval": "not-a-list"}),
        ):
            with self.subTest(block=block, name=name, value=value):
                invalid = copy.deepcopy(self.data)
                invalid[block][name] = value
                with self.assertRaises(ValueError):
                    PVS1Input(**invalid)
        for product in ({"basis": "RNA"}, {"basis": "OBSERVED", "ptc_start": 181},
                        {"event_type": "EXON_SKIPPING"},
                        {"basis": "UNKNOWN", "genomic_junctions": [[0, 3001]]}):
            with self.subTest(product=product), self.assertRaises(ValueError):
                PVS1Input(**self.data, molecular_effect={"products": [product]})

    def test_stop_gain_input(self):
        sample = PVS1Input(**self.data, molecular_effect={"products": [{
            "basis": "PREDICTED", "transcript_ref": "DEMO_STOP_RNA.1",
            "coordinate_system": "transcript_1_based_closed", "ptc_start": 181,
            "protein_accession": "DEMO_PROTEIN.1",
            "protein_coordinate_system": "protein_1_based_closed",
            "lost_protein_region": [51, 129], "lost_region_critical": None,
            "source_refs": {"ptc_start": ["DEMO_ANNOTATION:v1"]},
        }]})
        product = json.loads(json.dumps(asdict(sample)))["molecular_effect"]["products"][0]
        self.assertEqual(product["ptc_start"], 181)
        self.assertEqual(product["lost_protein_region"], [51, 129])
        self.assertIsNone(product["lost_region_critical"])

    def test_frameshift_with_known_or_missing_ptc(self):
        self.data["variant"].update(position=2030, reference_allele="AC",
                                    alternate_allele="A", consequence="frameshift_variant")
        effect = {
            "cds_edit_interval": [150, 151], "cds_coordinate_system": "cds_0_based_half_open",
            "products": [{"basis": "PREDICTED", "frame_effect": "OUT_OF_FRAME",
                          "transcript_ref": "DEMO_FS_RNA.1#sequence:v1",
                          "coordinate_system": "transcript_1_based_closed", "ptc_start": 196,
                          "source_refs": {"ptc_start": ["DEMO_RECONSTRUCTION:v1"]}}],
        }
        known = PVS1Input(**self.data, molecular_effect=effect)
        self.assertEqual(known.molecular_effect["products"][0]["ptc_start"], 196)
        effect["products"][0]["ptc_start"] = None
        unknown = PVS1Input(**self.data, molecular_effect=effect)
        self.assertIsNone(unknown.molecular_effect["products"][0]["ptc_start"])
        effect["cds_edit_interval"] = [150, 150]  # Structural insertion boundary.
        PVS1Input(**self.data, molecular_effect=effect)  # No frame/consequence inference.

    def test_splice_observed_kept_separate_from_predicted(self):
        self.data["variant"].update(position=2151, reference_allele="G",
                                    alternate_allele="A", consequence="splice_donor_variant")
        observed = {
            "basis": "OBSERVED", "event_type": "EXON_SKIPPING", "involved_exons": [2],
            "genomic_junctions": [[1150, 3001]], "frame_effect": "IN_FRAME",
            "transcript_ref": "DEMO_SPLICE_RNA.1", "ptc_start": None,
            "evidence_quality": "Synthetic RNA assay with matched controls.",
            "source_refs": {"event_type": ["DEMO_RNA:v1"],
                            "frame_effect": ["DEMO_RECONSTRUCTION:v1"]},
        }
        predicted = dict(observed, basis="PREDICTED", evidence_quality=None)
        sample = PVS1Input(**self.data, molecular_effect={
            "splice_site_type": "DONOR", "splice_site_genomic_position": 2150,
            "splice_site_offset": 1, "native_splice_motif": "GT",
            "products": [predicted, observed],
        })
        products = json.loads(json.dumps(asdict(sample)))["molecular_effect"]["products"]
        self.assertEqual([product["basis"] for product in products], ["PREDICTED", "OBSERVED"])
        self.assertIsNone(products[1]["ptc_start"])
        # Descending genomic pairs are valid on a reverse-strand coordinate axis.
        self.data["transcript"]["strand"] = "-"
        PVS1Input(**self.data, molecular_effect={"products": [{
            "basis": "UNKNOWN", "genomic_junctions": [[3001, 1150]]}]})

    def test_splice_annotation_with_unknown_effect(self):
        self.data["variant"].update(position=2155, reference_allele="G",
                                    alternate_allele="A", consequence="splice_region_variant")
        self.data["variant"]["source_refs"] = {"consequence": ["DEMO_VEP:v1"]}
        sample = PVS1Input(**self.data, molecular_effect={
            "splice_site_type": "DONOR", "splice_site_genomic_position": 2150,
            "splice_site_offset": 5, "products": [{"basis": "UNKNOWN"}],
        })
        product = sample.molecular_effect["products"][0]
        self.assertEqual(product, {"basis": "UNKNOWN"})
        for name in ("event_type", "frame_effect", "ptc_start"):
            self.assertIsNone(product.get(name))
        self.data["variant"]["consequence"] = "splice_donor_variant"
        self.data["variant"]["position"] = 2151
        sample.molecular_effect["splice_site_offset"] = 1
        canonical = PVS1Input(**self.data, molecular_effect=sample.molecular_effect)
        self.assertEqual(canonical.molecular_effect["products"][0], {"basis": "UNKNOWN"})

    def test_optional_scientific_fields(self):
        self.data["disease_context"] = {"gene": "DEMO_GENE", "confidence": "UNKNOWN"}
        self.data["transcript"] = None
        sample = PVS1Input(**self.data)
        self.assertIsNone(sample.transcript)
        self.assertIsNone(sample.molecular_effect)
        self.assertIsNone(sample.disease_context.get("molecular_mechanism"))
        sample = PVS1Input(**self.data, molecular_effect={"products": [{
            "basis": "UNKNOWN", "frame_effect": "UNKNOWN", "lost_region_critical": False}]})
        product = json.loads(json.dumps(asdict(sample)))["molecular_effect"]["products"][0]
        self.assertIs(product["lost_region_critical"], False)
        self.assertIsNone(product.get("ptc_start"))

    def test_result_serialization_and_explicit_values(self):
        for status in ("ACTIVE", "INACTIVE", "NOT_EVALUABLE", "REQUIRES_REVIEW", "EXPLORATORY"):
            with self.subTest(status=status):
                result = PVS1Result(status=status, reason="Caller-supplied test values.")
                payload = json.loads(json.dumps(asdict(result)))
                self.assertEqual(payload["status"], status)
                for name in ("calculated_strength", "applied_strength", "requires_review",
                             "ruleset_id", "ruleset_version"):
                    self.assertIsNone(payload[name])
        explicit = PVS1Result(status="REQUIRES_REVIEW", reason="Explicit test values.",
                              calculated_strength="STRONG", requires_review=True,
                              decision_trace=["Caller-provided trace; no evaluation."])
        self.assertIsNone(explicit.applied_strength)
        self.assertTrue(json.loads(json.dumps(asdict(explicit)))["requires_review"])
        for invalid in ({"status": "UNKNOWN"}, {"requires_review": "true"},
                        {"calculated_strength": "Not applicable"}):
            values = {"status": "NOT_EVALUABLE", "reason": "Test values."}
            values.update(invalid)
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                PVS1Result(**values)
