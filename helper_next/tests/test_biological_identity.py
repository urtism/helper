"""CACHE-02: synthetic, offline identity and compatibility checks."""
import copy
import json
import os
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib import request

import pytest

from helper_next.core import biological_identity as identities
from helper_next.core import acmg_mechanism_normalizer as mechanism
from helper_next.core import acmg_transcripts
from helper_next.core.acmg_digest import digest
from helper_next.core.acmg_mechanism_store import MechanismStore
from helper_next.core.acmg_ontology import OntologyMappingRegistry
from helper_variants import indexer, store
from test_acmg_pvs1 import bundle


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Biological identity must never access the network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(request, "urlopen", forbidden)
    monkeypatch.setattr(acmg_transcripts, "urlopen", forbidden)


def reference_record(tmp_path, entries=None):
    entries = entries or {"1": "CAAAAAGTACGT"}
    fasta, fai, offset = bytearray(), [], 0
    for name, sequence in entries.items():
        header = (">" + name + "\n").encode()
        offset += len(header)
        fai.append(f"{name}\t{len(sequence)}\t{offset}\t{len(sequence)}\t{len(sequence) + 1}\n")
        fasta.extend(header + sequence.encode() + b"\n")
        offset += len(sequence) + 1
    path = tmp_path / "reference.fa"
    path.write_bytes(fasta)
    Path(str(path) + ".fai").write_text("".join(fai))
    return {"run_config": {"reference_fasta": str(path), "reference_version": "synthetic-reference-1"}}


def allele(record, position=7, ref="G", alt="T", assembly="GRCh38", chromosome="1"):
    return identities.allele_refs(assembly, chromosome, position, ref, alt, record=record)[0]


def association(gene="HGNC:1", disease="MONDO:1", requirement="AD", **kwargs):
    return identities.association_ref(gene, disease, requirement, verified_gene_ids=["HGNC:1"], **kwargs)


def assert_unresolved(result, field):
    assert result["status"] == "UNRESOLVED", result
    assert result[field] is None
    assert result["identity"] is None
    assert result["reason"]
    assert result["original"]


def test_batch_keeps_exact_results_and_opens_reference_once(tmp_path, monkeypatch):
    record = reference_record(tmp_path)
    queries = [
        ("GRCh38", "1", 7, "G", "T"),
        ("hg38", "chr1", 4, "AA", "A"),
        ("GRCh38", "NC_000001.11", 5, "A", "AA"),
        ("GRCh38", "1", 7, "G", "T,A,<DEL>"),
        ("GRCh38", "1", 4, "GA", "G"),
        ("GRCh38", "1", 7, "G", "G"),
        ("unknown", "1", 7, "G", "T"),
    ] * 3
    expected = [identities.allele_refs(*item, record=record) for item in queries]
    opened, normalized, verified = [], [], []
    original_open = indexer.open_reference
    original_normalize = indexer.normalize_allele
    original_verify = identities.acmg_reference.verify
    def tracking_open(*args, **kwargs):
        fasta = original_open(*args, **kwargs)
        opened.append(fasta)
        return fasta
    def tracking_normalize(*args, **kwargs):
        normalized.append(args)
        return original_normalize(*args, **kwargs)
    def tracking_verify(*args, **kwargs):
        verified.append(args)
        return original_verify(*args, **kwargs)
    monkeypatch.setattr(indexer, "open_reference", tracking_open)
    monkeypatch.setattr(indexer, "normalize_allele", tracking_normalize)
    monkeypatch.setattr(identities.acmg_reference, "verify", tracking_verify)
    assert identities.allele_refs_batch(queries, record=record) == expected
    assert len(opened) == 1
    assert opened[0].handle.closed
    assert len(verified) == 15  # Five valid ALTs per repetition, including duplicates.
    assert len(normalized) == 30  # Alignment and existing normalized-allele verification retained.


def test_batch_closes_reference_on_interruption(tmp_path, monkeypatch):
    record = reference_record(tmp_path)
    opened = []
    original = indexer.open_reference
    def tracking(*args):
        fasta = original(*args)
        opened.append(fasta)
        return fasta
    monkeypatch.setattr(indexer, "open_reference", tracking)
    def interrupted():
        yield ("GRCh38", "1", 7, "G", "T")
        raise RuntimeError("cancelled batch")
    with pytest.raises(RuntimeError, match="cancelled"):
        identities.allele_refs_batch(interrupted(), record=record)
    assert len(opened) == 1 and opened[0].handle.closed


def test_batch_does_not_reuse_reference_metadata_across_operations(tmp_path):
    record = reference_record(tmp_path)
    query = [("GRCh38", "1", 7, "G", "T")]
    before = identities.allele_refs_batch(query, record=record)[0][0]
    reference_record(tmp_path, {"1": "CAAAAAGTACGA"})
    fasta = Path(record["run_config"]["reference_fasta"])
    changed = fasta.stat()
    # The sandbox can give consecutive writes the same timestamp. Exercise the
    # existing checksum cache contract with an explicit metadata revision.
    os.utime(fasta, ns=(changed.st_atime_ns, changed.st_mtime_ns + 1_000_000_000))
    after = identities.allele_refs_batch(query, record=record)[0][0]
    assert before["allele_ref"] == after["allele_ref"]
    assert before["reference_provenance"]["digest"] != after["reference_provenance"]["digest"]


def test_batch_preserves_configured_checksum_errors_and_assembly_separation(tmp_path, monkeypatch):
    record = reference_record(tmp_path)
    queries = [("GRCh37", "1", 7, "G", "T"), ("GRCh38", "1", 7, "G", "T")]
    result = identities.allele_refs_batch(queries, record=record)
    assert result[0][0]["allele_ref"] != result[1][0]["allele_ref"]
    config = tmp_path / "references.json"
    config.write_text(json.dumps({"GRCh38": dict(version="v1", fasta=record["run_config"]["reference_fasta"], sha256="0" * 64)}))
    monkeypatch.setenv("HELPER_ACMG_REFERENCE_CONFIG", str(config))
    bad_queries = [queries[1]] * 3
    expected = [identities.allele_refs(*item, record=record) for item in bad_queries]
    actual = identities.allele_refs_batch(bad_queries, record=record)
    assert actual == expected
    assert all("checksum mismatch" in result[0]["reason"] for result in actual)


def test_same_allele_across_runs_preserves_run_store_ids(tmp_path):
    record = reference_record(tmp_path)
    first = dict(record, id="history-one", run_id="run-one")
    second = dict(record, id="history-two", run_id="run-two")
    expected = allele(first)
    assert expected["status"] == "RESOLVED"
    assert expected["allele_ref"] == "ga2:81779b725eb7f73c358ee904774e5a0827f05664495377437c5c09a5ac9a900e"
    assert expected["contract_version"] == "helper-genomic-allele-2"
    assert expected["identity"] == {
        "contract": "helper-genomic-allele-2", "kind": "allele_ref", "assembly": "GRCh38",
        "chromosome": "NC_000001.11", "position": 7, "reference": "G", "alternate": "T",
    }
    assert expected == allele(second)
    db_path = tmp_path / "run.sqlite"
    with store.connect(db_path, "run") as db:
        old_id = store.get_or_create_variant(db, "GRCh38", "1", 7, "G", "T")
        schema = [tuple(row) for row in db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY name")]
    before = db_path.read_bytes()
    assert allele(first)["allele_ref"] == expected["allele_ref"]
    assert db_path.read_bytes() == before
    with store.connect(db_path) as db:
        assert db.execute("SELECT id FROM variants").fetchone()[0] == old_id
        assert [tuple(row) for row in db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY name")] == schema


def test_assembly_aliases_are_reused_but_builds_remain_distinct(tmp_path):
    record = reference_record(tmp_path)
    a, b = allele(record, assembly="GRCh37"), allele(record, assembly="GRCh38")
    assert a["allele_ref"] != b["allele_ref"]
    assert allele(record, assembly="hg19")["allele_ref"] == a["allele_ref"]
    assert allele(record, assembly="hg38")["allele_ref"] == b["allele_ref"]


def test_chromosome_alias_is_verified_against_actual_fasta(tmp_path):
    record = reference_record(tmp_path)
    assert allele(record, chromosome="chr1")["allele_ref"] == allele(record)["allele_ref"]
    assert allele(record, chromosome="chr1")["identity"]["chromosome"] == "NC_000001.11"
    both = reference_record(tmp_path, {"1": "CAAAAAGTACGT", "chr1": "CAAAAAGTACGT"})
    assert_unresolved(allele(both, chromosome="chr1"), "allele_ref")
    assert_unresolved(allele(both, chromosome="missing"), "allele_ref")


@pytest.mark.parametrize("ref,alt,position,normalized", [
    ("g", "t", 7, (7, "G", "T")),
    ("GT", "GC", 7, (8, "T", "C")),
    ("A", "AA", 5, (1, "C", "CA")),
    ("AA", "A", 4, (1, "CA", "C")),
])
def test_snv_trimming_and_left_aligned_insertions_deletions(tmp_path, ref, alt, position, normalized):
    result = allele(reference_record(tmp_path), position, ref, alt)
    assert result["status"] == "RESOLVED", result
    actual = result["identity"]
    assert (actual["position"], actual["reference"], actual["alternate"]) == normalized
    assert result["original"]["reference"] == ref


@pytest.mark.parametrize("ref,alt", [("A", "AA"), ("AA", "A")])
def test_repetitive_indel_equivalence_is_proved_by_fasta(tmp_path, ref, alt):
    record = reference_record(tmp_path)
    assert allele(record, 3, ref, alt)["allele_ref"] == allele(record, 5, ref, alt)["allele_ref"]


@pytest.mark.parametrize("ref,alt", [("A", "AA"), ("AA", "A")])
def test_missing_fasta_keeps_indel_normalization_unresolved(ref, alt):
    result = allele(None, 3, ref, alt)
    assert_unresolved(result, "allele_ref")
    assert "FASTA" in result["reason"]


def test_snv_without_fasta_shares_declared_identity_but_not_verification(tmp_path):
    unverified = allele(None)
    verified = allele(reference_record(tmp_path))
    assert unverified["status"] == "RESOLVED"
    assert unverified["allele_ref"] == verified["allele_ref"]
    assert unverified["reference_provenance"]["ref_status"] == "UNVERIFIED"
    assert unverified["reference_provenance"]["digest"] is None
    assert "UNVERIFIED" in unverified["reason"]
    assert verified["reference_provenance"]["ref_status"] == "VERIFIED"


def test_unaligned_indel_representations_without_fasta_are_not_equated():
    results = [allele(None, pos, "AA", "A") for pos in [3, 5]]
    for result in results:
        assert_unresolved(result, "allele_ref")
    assert results[0]["original"]["position"] != results[1]["original"]["position"]


def test_ref_mismatch_cannot_be_hidden_by_trimming(tmp_path):
    record = reference_record(tmp_path)
    # Last base is the real REF at position 8; the mismatching anchor at 7
    # must still invalidate the original representation before normalization.
    result = allele(record, 7, "AT", "AC")
    assert_unresolved(result, "allele_ref")
    assert "Original REF" in result["reason"]
    assert result["reference_provenance"]["ref_status"] == "MISMATCH"
    assert result["reference_provenance"]["source_file"]
    assert result["reference_provenance"]["digest"]


def test_multiallelic_alt_order_and_unsupported_members_are_preserved(tmp_path):
    record = reference_record(tmp_path)
    results = identities.allele_refs("GRCh38", "1", 7, "G", "T,<DEL>,A", record=record)
    assert len(results) == 3
    assert [r["original"]["alt_index"] for r in results] == [1, 2, 3]
    assert results[0]["allele_ref"] == allele(record, alt="T")["allele_ref"]
    assert results[2]["allele_ref"] == allele(record, alt="A")["allele_ref"]
    assert results[0]["allele_ref"] != results[2]["allele_ref"]
    assert_unresolved(results[1], "allele_ref")
    assert results[1]["original"]["alternate"] == "<DEL>"


@pytest.mark.parametrize("changes", [
    {"assembly": "unknown"}, {"position": 0}, {"position": True}, {"position": 7.5},
    {"alt": "<CNV>"}, {"alt": "*"}, {"alt": "G]2:10]"}, {"alt": "."},
    {"alt": "N"}, {"ref": ""}, {"alt": "G"},
])
def test_invalid_and_unsupported_alleles_remain_local(tmp_path, changes):
    assert_unresolved(allele(reference_record(tmp_path), **changes), "allele_ref")


def test_fasta_provenance_is_not_hashed_and_configured_checksum_is_still_checked(tmp_path, monkeypatch):
    record = reference_record(tmp_path)
    before = allele(record)
    other_reference = tmp_path / "other-reference"
    other_reference.mkdir()
    record = reference_record(other_reference, {"1": "CAAAAAGTACGA"})
    after = allele(record)
    assert after["allele_ref"] == before["allele_ref"]
    assert after["reference_provenance"]["digest"] != before["reference_provenance"]["digest"]
    assert after["reference_provenance"]["source_file"] != before["reference_provenance"]["source_file"]
    config = tmp_path / "references.json"
    config.write_text(json.dumps({"GRCh38": {"version": "v1", "fasta": record["run_config"]["reference_fasta"], "sha256": "0" * 64}}))
    monkeypatch.setenv("HELPER_ACMG_REFERENCE_CONFIG", str(config))
    result = allele(record)
    assert_unresolved(result, "allele_ref")
    assert "checksum mismatch" in result["reason"]


@pytest.mark.parametrize("position,ref,alt", [(7, "G", "T"), (5, "A", "AA"), (4, "AA", "A")])
def test_grch37_equivalent_fastas_with_different_checksums_share_allele_ref(tmp_path, position, ref, alt):
    first_dir, second_dir = tmp_path / "bundle-one", tmp_path / "bundle-two"
    first_dir.mkdir()
    second_dir.mkdir()
    first_record = reference_record(first_dir, {"1": "CAAAAAGTACGT"})
    # Different contig naming and an extra sequence change the file checksum,
    # while preserving the relevant primary chromosome reference sequence.
    second_record = reference_record(second_dir, {"chr1": "CAAAAAGTACGT", "decoy": "ACGT"})
    first = allele(first_record, position, ref, alt, assembly="GRCh37", chromosome="1")
    second = allele(second_record, position, ref, alt, assembly="hg19", chromosome="chr1")
    assert first["status"] == second["status"] == "RESOLVED"
    assert first["allele_ref"] == second["allele_ref"]
    assert first["reference_provenance"]["digest"] != second["reference_provenance"]["digest"]
    assert first["reference_provenance"]["ref_status"] == second["reference_provenance"]["ref_status"] == "VERIFIED"


@pytest.mark.parametrize("build,alias,accession", [
    ("GRCh37", "hg19", "NC_000001.10"), ("GRCh38", "hg38", "NC_000001.11"),
])
def test_primary_versioned_accession_and_named_chromosome_share_identity(tmp_path, build, alias, accession):
    record = reference_record(tmp_path, {accession: "CAAAAAGTACGT"})
    assert allele(record, assembly=build, chromosome="1")["allele_ref"] == allele(
        record, assembly=alias, chromosome=accession)["allele_ref"]
    assert allele(None, assembly=alias, chromosome=accession)["allele_ref"] == allele(
        record, assembly=build, chromosome="chr1")["allele_ref"]


@pytest.mark.parametrize("chromosome", ["MT", "M", "chrM", "hs37d5", "chr1_KI270706v1_random"])
def test_unqualified_mitochondrial_alt_and_decoy_names_do_not_invent_equivalence(chromosome):
    assert_unresolved(allele(None, assembly="hg19", chromosome=chromosome), "allele_ref")


def test_versioned_nonprimary_and_mitochondrial_sequences_remain_distinct(tmp_path):
    record = reference_record(tmp_path, {name: "CAAAAAGTACGT" for name in
                                        ["NC_012920.1", "NC_001807.4", "GL000207.1", "GL000207.2"]})
    results = [allele(record, chromosome=name) for name in
               ["NC_012920.1", "NC_001807.4", "GL000207.1", "GL000207.2"]]
    assert all(result["status"] == "RESOLVED" for result in results)
    assert len({result["allele_ref"] for result in results}) == 4
    assert_unresolved(allele(record, chromosome="chrM"), "allele_ref")


def test_primary_accession_from_another_assembly_is_rejected():
    assert_unresolved(allele(None, assembly="GRCh38", chromosome="NC_000001.10"), "allele_ref")


def test_reuses_normalizer_and_reference_verifier(tmp_path, monkeypatch):
    calls = []
    normalize, verify = indexer.normalize_allele, identities.acmg_reference.verify

    def normalizer(*args, **kwargs):
        calls.append("normalize")
        return normalize(*args, **kwargs)

    def verifier(*args, **kwargs):
        calls.append("verify")
        return verify(*args, **kwargs)

    monkeypatch.setattr(indexer, "normalize_allele", normalizer)
    monkeypatch.setattr(identities.acmg_reference, "verify", verifier)
    assert allele(reference_record(tmp_path))["status"] == "RESOLVED"
    assert "normalize" in calls and "verify" in calls


def test_transcript_identity_uses_qualifier_without_modifying_bundle():
    raw = bundle()
    before = copy.deepcopy(raw)
    result = identities.transcript_context_ref("ENST000001.1", "GRCh38", "115", raw=raw)
    assert result["status"] == "RESOLVED", result
    assert result["transcript_context_ref"] == "tc1:1c6baf07ff876df29b4b16fabd31a0cb78d411a11644372e63dc2392e8e4964f"
    assert result["transcript_context_ref"] == identities.transcript_context_ref(
        "ENST000001.1", "GRCh38", 115, raw=raw)["transcript_context_ref"]
    assert raw == before
    for version, release in [(2, 115), (1, 116)]:
        other = copy.deepcopy(raw)
        other["lookup"]["version"] = version
        other["release_before"] = other["release_after"] = {"releases": [release]}
        changed = identities.transcript_context_ref(f"ENST000001.{version}", "GRCh38", release, raw=other)
        assert changed["status"] == "RESOLVED", changed
        assert changed["transcript_context_ref"] != result["transcript_context_ref"]


@pytest.mark.parametrize("transcript,assembly,release,namespace,has_raw", [
    ("ENST000001", "GRCh38", "115", "Ensembl", True),
    ("ENST000001.1", "GRCh38", "115", "RefSeq", True),
    ("NM_000001.1", "GRCh38", "115", "RefSeq", True),
    ("ENST000001.2", "GRCh38", "115", "Ensembl", True),
    ("ENST000001.1", "GRCh37", "115", "Ensembl", True),
    ("ENST000001.1", "GRCh38", "116", "Ensembl", True),
    ("ENST000001.1", "GRCh38", None, "Ensembl", True),
    ("ENST000001.1", "GRCh38", "115", "Ensembl", False),
])
def test_transcript_context_missing_or_mismatched_is_unresolved(transcript, assembly, release, namespace, has_raw):
    result = identities.transcript_context_ref(transcript, assembly, release, namespace=namespace,
                                               raw=bundle() if has_raw else None)
    assert_unresolved(result, "transcript_context_ref")


def test_association_identity_normalization_scopes_and_legacy_keys(monkeypatch):
    first = association()
    assert first["status"] == "RESOLVED", first
    assert first["association_ref"] == association(requirement="monoallelic_autosomal")["association_ref"]
    assert first["association_ref"] == association(gene="hgnc:1", disease="mondo:1")["association_ref"]
    for disease, requirement in [("MONDO:2", "AD"), ("MONDO:1", "AR"),
                                 ("MONDO:1", "monoallelic"), ("MONDO:1", None)]:
        assert first["association_ref"] != association(disease=disease, requirement=requirement)["association_ref"]
    assert association(disease="MIM:1")["association_ref"] == association(disease="OMIM:1")["association_ref"]
    request = mechanism.identity("HGNC:1", "MONDO:1", "AD")
    old_key = mechanism.association_key(request)
    monkeypatch.setattr(mechanism, "MAPPING_VERSION", "different-policy")
    monkeypatch.setattr(mechanism, "RECONCILIATION_VERSION", "different-rules")
    assert mechanism.association_key(request) != old_key
    assert association()["association_ref"] == first["association_ref"]


@pytest.mark.parametrize("gene,disease,verified", [
    ("DEMO", "MONDO:1", ["HGNC:1"]), ("HGNC:1", "Disease name", ["HGNC:1"]),
    ("HGNC:1", "MONDO:1", []), ("HGNC:1", "MONDO:1", ["HGNC:2"]),
    ("HGNC:fake", "MONDO:1", ["HGNC:fake"]), ("HGNC:1", "MONDO:fake", ["HGNC:1"]),
    ("HGNC:1", "1", ["HGNC:1"]), ("HGNC:1", "MONDO:0", ["HGNC:1"]),
])
def test_associations_without_verifiable_identifiers_have_no_ref(gene, disease, verified):
    result = identities.association_ref(gene, disease, "AD", verified_gene_ids=verified)
    assert_unresolved(result, "association_ref")


def test_gene_namespaces_are_never_equated_without_mapping():
    refs = [identities.association_ref(gene, "MONDO:1", "AD", verified_gene_ids=[gene])["association_ref"]
            for gene in ["HGNC:1", "ENSEMBL:ENSG000001", "NCBI_GENE:1"]]
    assert None not in refs and len(set(refs)) == 3


def test_ontology_registry_context_is_readonly_and_never_rewrites_source_anchor(tmp_path):
    registry = OntologyMappingRegistry(MechanismStore(tmp_path / "ontology.sqlite"))
    mapping = tmp_path / "mapping.tsv"
    mapping.write_text("subject_id\tpredicate_id\tobject_id\nMONDO:1\tskos:exactMatch\tOMIM:1\n")
    registry.import_mondo(mapping, release="synthetic-1", checksum=indexer.sha256_file(mapping))
    before = registry.store.path.read_bytes()
    first = association(disease="OMIM:1", registry=registry)
    assert first["disease_mapping"]["status"] == "VERIFIED_EXACT"
    assert first["disease_mapping"]["canonical"] == "MONDO:1"
    assert first["original"]["disease"] == "OMIM:1"
    assert first["identity"]["disease"] == "OMIM:1"
    assert first["association_ref"] != association(registry=registry)["association_ref"]
    assert registry.store.path.read_bytes() == before
    # Add a second same-namespace target: ambiguous links must never collapse.
    mapping.write_text(mapping.read_text() + "MONDO:2\tskos:exactMatch\tOMIM:1\n")
    registry.import_mondo(mapping, release="synthetic-2", checksum=indexer.sha256_file(mapping))
    before = registry.store.path.read_bytes()
    ambiguous = association(disease="OMIM:1", registry=registry)
    assert ambiguous["disease_mapping"]["status"] == "AMBIGUOUS_MAPPING"
    assert ambiguous["association_ref"] == first["association_ref"]
    assert len({association(disease=d, registry=registry)["association_ref"]
                for d in ["MONDO:1", "MONDO:2", "OMIM:1"]}) == 3
    assert registry.store.path.read_bytes() == before


def test_missing_registry_and_no_database_creation(tmp_path, monkeypatch):
    registry = OntologyMappingRegistry(MechanismStore(tmp_path / "absent.sqlite"))
    assert association(registry=registry)["status"] == "RESOLVED"
    assert not registry.store.path.exists()

    def forbidden(*args, **kwargs):
        pytest.fail("Identity generation must not initialize or write a database")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    assert association()["status"] == "RESOLVED"
    assert allele(reference_record(tmp_path))["status"] == "RESOLVED"
    assert identities.transcript_context_ref("ENST000001.1", "GRCh38", 115, raw=bundle())["status"] == "RESOLVED"


def test_hash_contract_and_existing_digest_remain_unchanged():
    result = association()
    assert result["identity"] == {
        "contract": "helper-biological-identity-1", "kind": "association_ref",
        "gene": "HGNC:1", "disease": "MONDO:1", "allelic_requirement": "AUTOSOMAL_DOMINANT",
    }
    # Fixed vector, independent of dict insertion order and process hash seed.
    assert result["association_ref"] == "gd1:87edb854e7decdd41b6b35fd134b70b8356e91ef693123f5db97cacc8f9d0cc7"
    assert digest({"b": 2, "a": 1}) == {
        "algorithm": "sha256", "value": "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777"}


def test_all_three_references_are_deterministic_across_processes(tmp_path):
    record = reference_record(tmp_path)
    payload = json.dumps({"record": record, "raw": bundle()})
    script = """
import json,socket,sys,urllib.request
def forbidden(*args,**kwargs):
    raise AssertionError('Network access during identity calculation')
socket.socket.connect = socket.create_connection = urllib.request.urlopen = forbidden
from helper_next.core.biological_identity import allele_refs,transcript_context_ref,association_ref
data=json.load(sys.stdin)
print(json.dumps([
 allele_refs('GRCh38','chr1',3,'AA','A',record=data['record']),
 transcript_context_ref('ENST000001.1','GRCh38',115,raw=data['raw']),
 association_ref('HGNC:1','MONDO:1','AD',verified_gene_ids=['HGNC:1'])
],sort_keys=True))
"""
    outputs = [subprocess.run([sys.executable, "-c", script], input=payload, text=True,
                              capture_output=True, check=True, timeout=20,
                              env=dict(os.environ, PYTHONHASHSEED=seed)).stdout for seed in ["1", "98765"]]
    assert outputs[0] == outputs[1]
    values = json.loads(outputs[0])
    assert values[0][0]["status"] == values[1]["status"] == values[2]["status"] == "RESOLVED"
