import pytest

from helper_variants import liftover


def test_source_url_points_to_the_current_ncbi_variation_services_page():
    assert liftover.SOURCE_URL == "https://www.ncbi.nlm.nih.gov/variation/services/"


def test_projects_exact_grch37_allele_to_grch38_and_caches_it(tmp_path, monkeypatch):
    calls = []

    def fake_request(path, timeout):
        calls.append(path)
        if path.endswith("all_equivalent_contextual"):
            return {"data": {"spdis": [
                {
                    "seq_id": "NC_000001.10", "position": 12033119,
                    "deleted_sequence": "G", "inserted_sequence": "C",
                },
                {
                    "seq_id": "NC_000001.11", "position": 11973062,
                    "deleted_sequence": "G", "inserted_sequence": "C",
                },
            ]}}
        return {"data": {
            "chrom": "NC_000001.11", "pos": 11973063, "ref": "G", "alt": "C",
        }}

    monkeypatch.setattr(liftover, "_request_json", fake_request)
    database = tmp_path / "liftover.sqlite3"

    result = liftover.project_variant(
        "GRCh37", "chr1", 12033120, "G", "C", database=database
    )

    assert result["status"] == "mapped"
    assert result["source"]["accession"] == "NC_000001.10"
    assert result["target"] == {
        "reference_build": "GRCh38", "browser_name": "hg38", "chromosome": "1",
        "position": 11973063, "reference": "G", "alternate": "C",
        "accession": "NC_000001.11",
    }
    assert result["validation"]["status"] == "contextual_allele"
    assert result["cache"] == "miss"

    cached = liftover.project_variant(
        "hg19", "1", 12033120, "G", "C", database=database
    )
    assert cached["cache"] == "hit"
    assert len(calls) == 1
    assert result['validation']['vcf_conversion'] == 'SPDI_SNV'


@pytest.mark.parametrize('position,reference,alternate', [
    (0, 'A', 'G'), (100, 'T', 'C'), (100, 'C', 'G'),
])
def test_contextual_snv_needs_no_second_request(tmp_path, monkeypatch, position, reference, alternate):
    calls = []
    def request(path, timeout):
        calls.append(path)
        assert path.endswith('all_equivalent_contextual')
        return {'data': {'spdis': [dict(seq_id='NC_000001.11', position=position,
                                       deleted_sequence=reference, inserted_sequence=alternate)]}}
    monkeypatch.setattr(liftover, '_request_json', request)
    result = liftover.project_variant('GRCh37', '1', 123, 'G', 'T', database=tmp_path / 'projection.sqlite3')
    assert result['status'] == 'mapped'
    assert result['target']['position'] == position + 1
    assert result['target']['reference'] == reference and result['target']['alternate'] == alternate
    assert result['validation']['vcf_conversion'] == 'SPDI_SNV'
    assert len(calls) == 1


@pytest.mark.parametrize('source_ref,source_alt,target_ref,target_alt', [
    ('AT', 'A', 'TT', 'T'), ('A', 'AT', 'T', 'TT'),
    ('A', 'G', 'T', 'TT'), ('AT', 'GC', 'A', 'C'),
])
def test_non_snv_keeps_ncbi_vcf_conversion(tmp_path, monkeypatch, source_ref, source_alt, target_ref, target_alt):
    calls = []
    def request(path, timeout):
        calls.append(path)
        if path.endswith('all_equivalent_contextual'):
            return {'data': {'spdis': [dict(seq_id='NC_000001.11', position=100,
                                           deleted_sequence=target_ref, inserted_sequence=target_alt)]}}
        assert path.endswith('vcf_fields')
        return {'data': dict(chrom='NC_000001.11', pos=99, ref=target_ref, alt=target_alt)}
    monkeypatch.setattr(liftover, '_request_json', request)
    result = liftover.project_variant('GRCh37', '1', 123, source_ref, source_alt,
                                     database=tmp_path / 'projection.sqlite3')
    assert result['status'] == 'mapped' and result['target']['position'] == 99
    assert result['validation']['vcf_conversion'] == 'NCBI_VCF_FIELDS'
    assert len(calls) == 2


@pytest.mark.parametrize('change', [
    {'position': -1}, {'position': '100'}, {'position': True},
    {'deleted_sequence': 'N'}, {'inserted_sequence': ''},
    {'inserted_sequence': 'A'}, {'deleted_sequence': 1},
])
def test_uncertain_contextual_representation_uses_original_converter(change):
    spdi = dict(seq_id='NC_000001.11', position=100, deleted_sequence='A', inserted_sequence='G')
    spdi.update(change)
    assert liftover._snv_vcf_fields(spdi) is None


@pytest.mark.parametrize('targets,status', [([], 'not_mapped'), ([100, 200], 'ambiguous')])
def test_snv_optimization_preserves_missing_and_ambiguous_projection(tmp_path, monkeypatch, targets, status):
    def request(path, timeout):
        assert path.endswith('all_equivalent_contextual')
        return {'data': {'spdis': [dict(seq_id='NC_000001.11', position=pos,
                                       deleted_sequence='G', inserted_sequence='T') for pos in targets]}}
    monkeypatch.setattr(liftover, '_request_json', request)
    result = liftover.project_variant('GRCh37', '1', 123, 'G', 'T', database=tmp_path / 'projection.sqlite3')
    assert result['status'] == status and result['target'] is None


def test_projects_in_both_directions(tmp_path, monkeypatch):
    def fake_request(path, timeout):
        if path.endswith("all_equivalent_contextual"):
            return {"data": {"spdis": [{
                "seq_id": "NC_000001.10", "position": 12033119,
                "deleted_sequence": "G", "inserted_sequence": "C",
            }]}}
        return {"data": {
            "chrom": "NC_000001.10", "pos": 12033120, "ref": "G", "alt": "C",
        }}

    monkeypatch.setattr(liftover, "_request_json", fake_request)
    result = liftover.project_variant(
        "GRCh38", "1", 11973063, "G", "C", database=tmp_path / "reverse.sqlite3"
    )

    assert result["status"] == "mapped"
    assert result["target"]["reference_build"] == "GRCh37"
    assert result["target"]["position"] == 12033120


def test_reports_unsupported_symbolic_alleles_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(
        liftover, "_request_json",
        lambda *args: (_ for _ in ()).throw(AssertionError("network should not be used")),
    )

    result = liftover.project_variant(
        "GRCh38", "1", 10, "A", "<DEL>", database=tmp_path / "unused.sqlite3"
    )

    assert result["status"] == "unsupported"
    assert result["target_build"] == "GRCh37"


def test_offline_mode_uses_cached_results_only(tmp_path, monkeypatch):
    monkeypatch.setenv("HELPER_LIFTOVER_OFFLINE", "1")
    result = liftover.project_variant(
        "GRCh37", "2", 20, "A", "G", database=tmp_path / "missing.sqlite3"
    )

    assert result["status"] == "unavailable"
    assert "offline mode" in result["message"]
