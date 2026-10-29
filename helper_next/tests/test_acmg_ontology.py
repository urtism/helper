"""Task 27A.2: source scope, registry qualification, offline persistence/history."""
import hashlib
import io
import json
import sqlite3
from pathlib import Path

import pytest

from helper_next.core.acmg_ontology import OntologyMappingRegistry, MONDO_SHA256
from helper_next.core.acmg_mechanism_store import MechanismStore, load_snapshot, json_text
from helper_next.core.acmg_mechanisms import MechanismEvidenceCache
from helper_next.core.acmg_mechanisms_bulk import BulkPopulation, build_inventory
from helper_next.core import acmg_mechanism_normalizer as norm
from helper_next.acmg_ontology import main
from test_acmg_mechanisms import FixtureSources, packets, g2p, gencc
from test_acmg_mechanisms_bulk import population


def load_reference(registry, directory, rows, release='synthetic-1'):
    path = Path(directory) / ('mapping-' + release + '.tsv')
    path.write_text('subject_id\tpredicate_id\tobject_id\n' + ''.join('\t'.join(r) + '\n' for r in rows))
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    return registry.import_mondo(path, release=release, checksum=checksum, source_url='https://example.test/' + release)


@pytest.fixture
def registry(tmp_path):
    reg = OntologyMappingRegistry(MechanismStore(tmp_path / 'registry.sqlite'))
    load_reference(reg, tmp_path, [('MONDO:1', 'skos:exactMatch', 'OMIM:1'),
                                  ('MONDO:1', 'skos:exactMatch', 'Orphanet:1'),
                                  ('MONDO:2', 'skos:broadMatch', 'OMIM:2')])
    return reg


def test_registry_predicates_and_offline_lookup(registry):
    assert registry.decision('OMIM:1', 'OMIM:1')[0] == 'IDENTITY'
    assert registry.decision('OMIM:1', 'MONDO:1')[0] == 'VERIFIED_EXACT'
    assert registry.canonical('OMIM:1') == registry.canonical('Orphanet:1') == 'MONDO:1'
    assert registry.aliases('OMIM:2') == {'OMIM:2'}
    lookup = OntologyMappingRegistry(registry.store).lookup('MONDO:2')
    assert lookup['status'] == 'NO_VERIFIED_MAPPING'
    assert lookup['records'][0]['verification_status'] == 'UNVERIFIED_CROSS_REFERENCE'
    assert lookup['records'][0]['mapping_predicate'] == 'skos:broadMatch'
    assert all(k in registry.lookup('MONDO:1')['records'][0] for k in [
        'mapping_id', 'mapping_source_record', 'source_version', 'dataset_fingerprint',
        'verification_basis', 'conflict_reason', 'valid_from', 'valid_until', 'registry_version'])


@pytest.mark.parametrize('predicate', ['skos:broadMatch', 'skos:narrowMatch', 'skos:relatedMatch'])
def test_nonexact_never_propagates(registry, tmp_path, predicate):
    load_reference(registry, tmp_path, [('MONDO:1', predicate, 'OMIM:1')], 'nonexact')
    assert registry.aliases('OMIM:1') == {'OMIM:1'}


def test_unknown_namespace_and_iri_retained_but_not_qualified(registry, tmp_path):
    load_reference(registry, tmp_path, [('MONDO:1', 'skos:exactMatch', 'EFO:1'),
                                       ('MONDO:1', 'skos:exactMatch', 'icd11.foundation:123')])
    assert registry.aliases('MONDO:1') == {'MONDO:1'}
    assert len(registry.lookup('MONDO:1')['records']) >= 2


def test_checksum_mismatch_does_not_create_database(tmp_path):
    path = tmp_path / 'bad.tsv'
    path.write_text('untrusted')
    store = MechanismStore(tmp_path / 'absent.sqlite')
    with pytest.raises(ValueError, match='checksum'):
        OntologyMappingRegistry(store).import_mondo(path)
    assert not store.path.exists()


def test_registry_idempotence_and_immutable_history(registry, tmp_path):
    before = registry.manifest()
    load_reference(registry, tmp_path, [('MONDO:1', 'skos:exactMatch', 'OMIM:1'),
                                       ('MONDO:1', 'skos:exactMatch', 'Orphanet:1'),
                                       ('MONDO:2', 'skos:broadMatch', 'OMIM:2')])
    assert registry.manifest() == before
    with registry.store.connect() as db:
        with pytest.raises(sqlite3.IntegrityError, match='Immutable'):
            db.execute('DELETE FROM ontology_mapping_records')
    assert registry.lookup('OMIM:1')['status'] == 'VERIFIED_EXACT'


def test_cardinality_no_canonical_and_release_pin(registry, tmp_path):
    old = registry.pin()
    load_reference(registry, tmp_path, [('MONDO:1', 'skos:exactMatch', 'OMIM:1'),
                                       ('MONDO:1', 'skos:exactMatch', 'OMIM:2')], 'v2')
    assert registry.canonical('OMIM:1') == 'OMIM:1'
    assert registry.decision('MONDO:1', 'OMIM:1')[0] == 'AMBIGUOUS_MAPPING'
    assert old.canonical('OMIM:1') == 'MONDO:1'
    assert old.manifest()['source_version'] == 'synthetic-1'
    with registry.store.readonly() as db:
        assert db.execute('SELECT COUNT(*) FROM ontology_registry_releases').fetchone()[0] == 2


def cache_for(registry, tmp_path, rows):
    sources = FixtureSources(packets({'g2p': rows}))
    sources.mapping_registry = registry
    return MechanismEvidenceCache(sources, tmp_path / 'matrices.sqlite')


def test_verified_aliases_share_one_matrix_and_keep_original_identifiers(registry, tmp_path):
    row = g2p(disease='OMIM:1')
    cache = cache_for(registry, tmp_path, [row])
    first = cache.resolve_gene_disease_mechanism('HGNC:1', 'OMIM:1', 'AD')
    second = cache.resolve_gene_disease_mechanism('HGNC:1', 'MONDO:1', 'AD')
    assert first.snapshot_id == second.snapshot_id
    assert first.identity.disease_id == 'MONDO:1'
    assert first.direct_evidence[0].disease_ids == ['OMIM:1']
    assert first.direct_evidence[0].raw_assertion == row
    assert first.direct_evidence[0].applicability == 'MAPPED'
    assert cache.store.statistics()['snapshots'] == 1
    assert first.review_status == 'NOT_REVIEWED'
    replay = cache.resolve_gene_disease_mechanism('HGNC:1', 'OMIM:1', 'AD', cache_policy='SNAPSHOT', snapshot_id=first.snapshot_id)
    assert replay.snapshot_id == first.snapshot_id


@pytest.mark.parametrize('secondary', ['MONDO:2', 'OMIM:2'])
def test_unqualified_coassignment_never_transfers_mechanism(registry, tmp_path, secondary):
    row = g2p(disease='MONDO:1')
    row['disease_mim'] = secondary
    cache = cache_for(registry, tmp_path, [row])
    direct = cache.resolve_gene_disease_mechanism('HGNC:1', 'MONDO:1', 'AD')
    blocked = cache.resolve_gene_disease_mechanism('HGNC:1', secondary, 'AD')
    assert direct.candidate_mechanisms == ['LOSS_OF_FUNCTION']
    assert blocked.candidate_mechanisms == []
    assert blocked.mapping_uncertainty
    assert any(m.get('source_record_ref') and m['verification_status'] != 'VERIFIED_EXACT' for m in blocked.mapping_evidence)
    assert registry.store.path != cache.store.path
    observed = OntologyMappingRegistry(cache.store).lookup(secondary)['records']
    assert any(m['mapping_source'] == 'g2p' for m in observed)


def test_reference_conflict_is_not_biological_difference(registry):
    status, reason = registry.decision('MONDO:2', 'OMIM:1')
    assert status == 'CONFLICTING_MAPPING'
    assert 'biological difference is not established' in reason


def test_different_allelic_requirements_remain_separate(registry, tmp_path):
    rows = [g2p(disease='OMIM:1'), g2p('G2P-2', disease='OMIM:1', mechanism='gain of function', requirement='biallelic_autosomal')]
    cache = cache_for(registry, tmp_path, rows)
    ad = cache.resolve_gene_disease_mechanism('HGNC:1', 'MONDO:1', 'AD')
    ar = cache.resolve_gene_disease_mechanism('HGNC:1', 'OMIM:1', 'AR')
    assert ad.candidate_mechanisms == ['LOSS_OF_FUNCTION'] and ar.candidate_mechanisms == ['GAIN_OF_FUNCTION']
    assert ad.snapshot_id != ar.snapshot_id


def test_missing_registry_identity_only_and_no_db_creation(tmp_path):
    registry = OntologyMappingRegistry(MechanismStore(tmp_path / 'absent.sqlite'))
    assert registry.manifest()['status'] == 'UNAVAILABLE'
    assert registry.aliases('OMIM:1') == {'OMIM:1'}
    assert registry.decision('MONDO:1', 'OMIM:1')[0] == 'NO_VERIFIED_MAPPING'
    assert not registry.store.path.exists()


def test_registry_revision_invalidates_matrix_without_remote_refresh(registry, tmp_path):
    cache = cache_for(registry, tmp_path, [g2p()])
    before = cache.resolve_gene_disease_mechanism('HGNC:1', 'MONDO:1', 'AD')
    count = len(cache.sources.calls)
    load_reference(registry, tmp_path, [('MONDO:2', 'skos:exactMatch', 'OMIM:2')], 'new-reference')
    after = cache.resolve_gene_disease_mechanism('HGNC:1', 'MONDO:1', 'AD', cache_policy='CACHE_ONLY')
    assert after.snapshot_id != before.snapshot_id
    assert len(cache.sources.calls) == count
    assert cache.store.snapshot(before.snapshot_id).snapshot_id == before.snapshot_id


def test_bulk_registry_change_rejects_resume(population, tmp_path):
    runner, _, _ = population
    runner.run(limit=1, offline=True)
    load_reference(runner.cache.registry, tmp_path, [('MONDO:8', 'skos:exactMatch', 'OMIM:8')], 'new-release')
    with pytest.raises(ValueError, match='inventory changed'):
        runner.run(resume=True, offline=True)


def test_cli_status_lookup_without_writes(tmp_path, capsys):
    database = tmp_path / 'none.sqlite'
    assert main(['--status', '--cache-db', str(database)]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'UNAVAILABLE'
    assert main(['--lookup', 'MONDO:1', '--cache-db', str(database)]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'NO_VERIFIED_MAPPING'
    assert not database.exists()


def test_legacy_v2_migration_replay_and_policy_keys_are_non_destructive(tmp_path):
    from helper_next.core.acmg_mechanism_store import _SCHEMA, _BULK_SCHEMA
    fixtures = json.loads((Path(__file__).parent / 'fixtures/task27a2/legacy_snapshots.json').read_text())
    database = tmp_path / 'historical.sqlite'
    with sqlite3.connect(database) as db:
        db.executescript(_SCHEMA + _BULK_SCHEMA)
        db.execute('PRAGMA user_version=2')
        for row in fixtures:
            db.execute('INSERT INTO mechanism_snapshots VALUES(?,?,?,?,?,?,?,?)', tuple(row[k] for k in (
                'snapshot_id', 'gene_disease_key', 'matrix_hash', 'normalization_version', 'reconciliation_version',
                'mapping_version', 'created_at', 'payload')))
    cache = MechanismEvidenceCache(FixtureSources(packets()), database)
    for row in fixtures:
        old = cache.store.snapshot(row['snapshot_id'])
        assert norm.association_key(old.identity) != row['gene_disease_key']
        replay = cache.resolve_gene_disease_mechanism(old.identity.gene_id, old.identity.disease_id,
            old.identity.allelic_requirement.removeprefix('OTHER:'), cache_policy='SNAPSHOT', snapshot_id=old.snapshot_id)
        assert replay.snapshot_id == old.snapshot_id
    with sqlite3.connect(database) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 3
        assert {r[0]: r[1] for r in db.execute('SELECT snapshot_id,payload FROM mechanism_snapshots')} == {r['snapshot_id']: r['payload'] for r in fixtures}
        assert not db.execute('PRAGMA foreign_key_check').fetchall()


def test_source_failure_cannot_replay_obsolete_mapping_as_current(registry, tmp_path):
    cache = cache_for(registry, tmp_path, [g2p(disease='OMIM:1')])
    old = cache.resolve_gene_disease_mechanism('HGNC:1', 'MONDO:1', 'AD')
    assert old.candidate_mechanisms == ['LOSS_OF_FUNCTION']
    load_reference(registry, tmp_path, [('MONDO:2', 'skos:exactMatch', 'OMIM:2')], 'changed')
    cache.sources.data['g2p'].update(status='ERROR', records=[])
    now = cache.resolve_gene_disease_mechanism('HGNC:1', 'MONDO:1', 'AD', cache_policy='FORCE_REFRESH')
    assert now.candidate_mechanisms == [] and now.snapshot_id != old.snapshot_id
    assert now.provenance['ontology_registry']['source_version'] == 'changed'
    assert cache.store.snapshot(old.snapshot_id).candidate_mechanisms == ['LOSS_OF_FUNCTION']


def test_orphadata_nonexact_predicate_is_not_promoted_even_with_independent_verified_match(registry):
    from helper_next.core.acmg_mechanism_models import SourcePacket
    row = g2p()
    row['disease_mappings'] = [{'identifier': 'MONDO:1', 'orpha_id': 'ORPHA:1', 'mapping_relation': 'BTNT'}]
    packet = SourcePacket(source='g2p', status='AVAILABLE', retrieved_at='2026-01-01T00:00:00Z')
    observations = registry.pin().observations('MONDO:1', [(packet, row, 'synthetic-ref')])
    original_link = next(r for r in observations if r['mapping_source'] == 'orphadata')
    assert original_link['verification_status'] == 'UNVERIFIED_CROSS_REFERENCE'
    assert original_link['mapping_predicate'] == 'BTNT'
    assert registry.decision('MONDO:1', 'ORPHA:1')[0] == 'VERIFIED_EXACT'  # Independent MONDO origin only.


@pytest.mark.parametrize('record_id,old_disease,requirement', [
    ('G2P00123', 'MONDO:0011099', 'AR'),
    ('G2P00573', 'MONDO:0009738', 'AR'),
    ('G2P03626', 'MONDO:0014709', 'AR'),
    ('G2P00850', 'MONDO:0010571', 'X-linked recessive'),
])
def test_real_critical_ids_do_not_transfer_to_old_unsupported_scope(tmp_path, record_id, old_disease, requirement):
    fixture = Path(__file__).parent / 'fixtures/task27a2'
    source = json.loads((fixture / 'real_cases.json').read_text())['records'][record_id]
    registry = OntologyMappingRegistry(MechanismStore(tmp_path / 'registry.sqlite'))
    reference = fixture / 'mondo_cases.tsv'
    registry.import_mondo(reference, release='synthetic-extract-of-v2026-10-06',
                          checksum=hashlib.sha256(reference.read_bytes()).hexdigest(), source_url='https://example.test/closed-mondo-extract')
    sources = FixtureSources(packets({'g2p': [source]}))
    sources.mapping_registry = registry
    cache = MechanismEvidenceCache(sources, tmp_path / 'matrix.sqlite')
    blocked = cache.resolve_gene_disease_mechanism(source['gene_curie'], old_disease, requirement)
    assert blocked.candidate_mechanisms == [] and blocked.direct_evidence == []
    primary = source['disease_curie'] or source['disease_mim']
    own = cache.resolve_gene_disease_mechanism(source['gene_curie'], primary, requirement)
    if source['mechanism'] == 'loss of function':
        assert own.candidate_mechanisms == ['LOSS_OF_FUNCTION']
    assert own.snapshot_id != blocked.snapshot_id
    assert own.review_status == blocked.review_status == 'NOT_REVIEWED'
    # Explicitly synthetic counterfactual for sources whose actual mechanism
    # is undetermined: the negative must not pass merely due to UNKNOWN.
    sources.data['g2p']['records'][0]['mechanism'] = 'loss of function'
    sources.revision += 1
    blocked_again = cache.resolve_gene_disease_mechanism(source['gene_curie'], old_disease, requirement)
    assert blocked_again.direct_evidence == []


def test_registry_activation_interrupts_bulk_plan_instead_of_mixing_fingerprints(population, tmp_path, monkeypatch):
    runner, _, _ = population
    complete = runner.store.finish_bulk_item
    once = [True]

    def change_reference(*args, **kwargs):
        complete(*args, **kwargs)
        if once[0]:
            once[0] = False
            load_reference(runner.cache.registry, tmp_path, [('MONDO:9', 'skos:exactMatch', 'OMIM:9')], 'replacement')

    monkeypatch.setattr(runner.store, 'finish_bulk_item', change_reference)
    with pytest.raises(ValueError, match='registry changed'):
        runner.run(offline=True)
    report = runner.report()
    assert report['status'] == 'INTERRUPTED' and report['processed'] == 1
    with pytest.raises(ValueError, match='inventory changed'):
        runner.run(resume=True, offline=True)


def test_obsolete_bulk_fingerprint_cannot_resume_after_policy_upgrade(population):
    runner, _, _ = population
    run = runner.run(limit=1, offline=True)
    with runner.store.connect() as db:
        db.execute('UPDATE mechanism_bulk_runs SET inventory_hash=? WHERE run_id=?', ('retired-task27a1-policy', run['run_id']))
    with pytest.raises(ValueError, match='inventory changed'):
        runner.run(resume=True, offline=True)
