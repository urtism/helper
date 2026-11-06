"""Task 27A.2: capped offline pilot and comparison against the historical policy.

Only this audit helper reconstructs the retired cross-reference graph for
comparison. Runtime and bulk both use OntologyMappingRegistry exclusively.
"""
import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from helper_next.core import acmg_mechanism_normalizer as norm
from helper_next.core.acmg_digest import digest
from helper_next.core.acmg_mechanism_store import MechanismStore
from helper_next.core.acmg_mechanisms import MechanismEvidenceCache
from helper_next.core.acmg_mechanisms_bulk import build_inventory
from helper_next.core.acmg_sources import SourceManager
from helper_next.core.acmg_ontology import OntologyMappingRegistry, closure, cardinality_conflict, canonical_order
from audit_mechanism_inventory import verify_acquired_g2p_responses

GENES = {'HGNC:5099', 'HGNC:7758', 'HGNC:8859', 'HGNC:3754', 'HGNC:7577', 'HGNC:7551', 'HGNC:6636', 'HGNC:4296'}
NEGATIVES = [('HGNC:5099', 'MONDO:0011099', 'AR', 'G2P00123'),
             ('HGNC:7758', 'MONDO:0009738', 'AR', 'G2P00573'),
             ('HGNC:8859', 'MONDO:0014709', 'AR', 'G2P03626'),
             ('HGNC:3754', 'MONDO:0010571', 'X-linked recessive', 'G2P00850')]


def historical_inventory_comparison(tables, registry):
    """Retired 1.1 policy used only as an audit oracle, never to resolve evidence."""
    orpha, by_id, genes, rows = defaultdict(set), defaultdict(set), defaultdict(list), []
    for link in tables['orpha_aliases']:
        if norm._is_exact_mapping(link['mapping_relation']):
            o, d = norm.curie(link['orpha_id']), norm.curie(link['identifier'])
            orpha[o].update((d, o))
    for o, ids in orpha.items():
        for d in ids:
            by_id[d].add(o)
    for source, table in [('g2p', 'g2p_records'), ('gencc', 'assertions')]:
        for row in tables[table]:
            info = norm.describe(source, row)
            if not info['disease_ids']:
                continue
            primary = norm.curie(row.get('disease_curie') or row.get('disease_mim') or row.get('disease_original_curie'))
            entry = dict(source=source, gene=info['gene_id'], disease=primary, requirement=info['inheritance'],
                         ids=info['disease_ids'], record_id=info['source_record_id'])
            genes[entry['gene']].append(entry)
            rows.append(entry)
    graphs = {}
    for gene, entries in genes.items():
        graph = defaultdict(set)
        for row in entries:
            ids = row['ids']
            for right in ids[1:]:
                graph[ids[0]].add(right)
                graph[right].add(ids[0])
            for o in {o for d in ids for o in by_id[d]}:
                for d in orpha[o]:
                    graph[d].add(o)
                    graph[o].add(d)
        graphs[gene] = graph
    old, new, old_by_new, new_by_old = defaultdict(list), defaultdict(list), defaultdict(set), defaultdict(set)
    cache = {}
    for row in rows:
        gene, disease, requirement = row['gene'], row['disease'], row['requirement']
        if (gene, disease) not in cache:
            component = closure(graphs[gene], disease)
            cache[gene, disease] = disease if cardinality_conflict(component) else min(component, key=canonical_order)
        before = gene, cache[gene, disease], requirement
        after = gene, registry.canonical(disease), requirement
        old[before].append(row)
        new[after].append(row)
        old_by_new[after].add(before)
        new_by_old[before].add(after)
    shared_old = {k for k, entries in old.items() if {r['source'] for r in entries} == {'g2p', 'gencc'}}
    shared_new = {k for k, entries in new.items() if {r['source'] for r in entries} == {'g2p', 'gencc'}}
    no_longer = []
    for key in sorted(shared_old):
        g2p = {(r['gene'], registry.canonical(r['disease']), r['requirement']) for r in old[key] if r['source'] == 'g2p'}
        gencc = {(r['gene'], registry.canonical(r['disease']), r['requirement']) for r in old[key] if r['source'] == 'gencc'}
        if not g2p & gencc:
            no_longer.append(dict(gene=key[0], previous_disease=key[1], requirement=key[2],
                                 g2p_diseases=sorted(k[1] for k in g2p), gencc_diseases=sorted(k[1] for k in gencc)))
    return dict(previous_unique=len(old), previous_shared=len(shared_old), new_unique=len(new), new_shared=len(shared_new),
                unique_delta=len(new) - len(old), shared_delta=len(shared_new) - len(shared_old),
                previously_merged_groups_now_split=sum(len(v) > 1 for v in new_by_old.values()),
                newly_qualified_merges=sum(len(v) > 1 for v in old_by_new.values()),
                old_shared_no_longer_permitted=no_longer,
                split_examples=[dict(gene=k[0], previous_disease=k[1], requirement=k[2], new_diseases=sorted(n[1] for n in v))
                                for k, v in sorted(new_by_old.items()) if len(v) > 1][:15])


def pilot(cache, inventory, tables):
    queries = {}
    for source, table in [('g2p', 'g2p_records')]:
        for row in tables[table]:
            if row['gene_curie'] not in GENES:
                continue
            info = norm.describe(source, row)
            primary = row['disease_curie'] or row['disease_mim']
            if primary:
                queries[row['gene_curie'], norm.curie(primary), row['allelic_requirement']] = row['gene_symbol']
    for gene, disease, requirement, _ in NEGATIVES:
        queries[gene, disease, requirement] = next(r['gene_symbol'] for r in tables['g2p_records'] if r['gene_curie'] == gene)
    for gene, disease, requirement in [('HGNC:5099', 'MONDO:7770750', 'AR'),
                                      ('HGNC:8859', 'MONDO:0100263', 'AR'),
                                      ('HGNC:7758', 'OMIM:256150', 'AR'),
                                      ('HGNC:3754', 'OMIM:304120', 'X-linked recessive'),
                                      ('HGNC:4296', 'MONDO:0010526', 'X-linked'),
                                      ('HGNC:7551', 'MONDO:0007268', 'AR')]:
        queries[gene, disease, requirement] = next(r['gene_symbol'] for r in tables['g2p_records'] if r['gene_curie'] == gene)
    if len(queries) > 70:
        raise ValueError('Capped scientific pilot exceeds 70 queries')
    originals = {}
    for source, table, key in [('g2p', 'g2p_records', 'g2p_id'), ('gencc', 'assertions', 'sgc_id'),
                               ('gnomad', 'gnomad_constraints', 'gene_symbol'), ('clingen_dosage', 'clingen_dosage', 'gene_symbol')]:
        originals.update({(source, str(r[key])): r for r in tables[table]})
    results, rows_checked = [], 0
    before = cache.store.statistics()
    snapshots = {}
    inventory_keys = {a['key'] for a in inventory['associations']}
    for (gene, disease, requirement), symbol in sorted(queries.items()):
        result = cache.resolve_gene_disease_mechanism(gene, disease, requirement, symbol=symbol)
        evidence = result.direct_evidence + result.contextual_evidence
        for evidence_row in evidence:
            lookup = evidence_row.source_record_id if evidence_row.source in ('g2p', 'gencc') else evidence_row.raw_assertion['gene_symbol']
            original = originals[evidence_row.source, lookup]
            if any(evidence_row.raw_assertion.get(k) != v for k, v in original.items()):
                raise ValueError('Evidence does not match original indexed source: ' + evidence_row.source_record_ref)
            rows_checked += 1
        for direct in result.direct_evidence:
            original = direct.raw_assertion
            primary = original.get('disease_curie') or original.get('disease_mim')
            if cache.registry.decision(primary, result.identity.disease_id)[0] not in ('IDENTITY', 'VERIFIED_EXACT'):
                raise ValueError('Unqualified direct assertion transfer')
            if direct.allelic_requirement != result.identity.allelic_requirement:
                raise ValueError('Inheritance scope was merged')
        for g, d, req, forbidden in NEGATIVES:
            if (gene, disease, requirement) == (g, d, req) and any(e.source_record_id == forbidden for e in result.direct_evidence):
                raise ValueError('Critical negative failed: ' + forbidden)
        key = norm.association_key(result.identity)
        # Some explicitly queried secondary/unresolved IDs have no primary
        # source association and therefore are queryable but outside bulk plan.
        if key in snapshots and snapshots[key] != result.snapshot_id:
            raise ValueError('Equivalent identifiers created duplicate scientific matrices')
        snapshots[key] = result.snapshot_id
        results.append(dict(gene=gene, symbol=symbol, requested_disease=disease, canonical_disease=result.identity.disease_id,
                            requirement=result.identity.allelic_requirement, snapshot_id=result.snapshot_id,
                            in_bulk_inventory=key in inventory_keys,
                            candidate_mechanisms=result.candidate_mechanisms,
                            direct_records=[dict(source=e.source, id=e.source_record_id, disease_ids=e.disease_ids,
                                                 mechanism=e.original_mechanism, inheritance=e.original_allelic_requirement) for e in result.direct_evidence],
                            mapping_uncertainty=result.mapping_uncertainty, issues=result.issues, review_status=result.review_status))
    after = cache.store.statistics()
    return dict(queries=len(queries), unique_matrices=len(snapshots), snapshots_created=after['snapshots'] - before['snapshots'],
                direct_assertion_queries=sum(bool(r['direct_records']) for r in results),
                original_record_occurrences_verified=rows_checked, critical_negatives_passed=len(NEGATIVES),
                no_remote_calls=True, items=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--pilot-db', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--g2p-response-dir', type=Path)
    args = parser.parse_args()
    original_store = MechanismStore()
    sources = SourceManager(mechanism_fetch=False)
    source = sources.mechanism_association_inventory()
    protected = {original_store.path.resolve(), Path(source['database']).resolve(), args.reference.resolve()}
    if args.pilot_db.resolve() in protected or args.report.resolve() in protected | {args.pilot_db.resolve()}:
        parser.error('Use separate pilot/report files; never overwrite source or production cache')
    with original_store.readonly() as origin:
        previous = [dict(r) for r in origin.execute('SELECT snapshot_id,payload,matrix_hash,gene_disease_key FROM mechanism_snapshots')]
        if not args.pilot_db.exists():
            args.pilot_db.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(args.pilot_db) as target:
                origin.backup(target)
    store = MechanismStore(args.pilot_db)
    registry = OntologyMappingRegistry(store)
    manifest = registry.import_mondo(args.reference)
    sources.mapping_registry = registry
    cache = MechanismEvidenceCache(sources, args.pilot_db)
    inventory = build_inventory(sources)
    if inventory['report']['source_problems']:
        raise ValueError('Required local sources unavailable')
    comparison = historical_inventory_comparison(source['tables'], registry.pin())
    if comparison['previous_unique'] != 15590 or comparison['previous_shared'] != 3374:
        raise ValueError('Local inventory differs from the audited baseline; do not claim the old comparison is current')
    if comparison['new_unique'] != inventory['report']['unique_associations'] or comparison['new_shared'] != inventory['report']['cross_source_associations']:
        raise ValueError('Independent inventory comparison failed')
    report = dict(created_at=datetime.now(timezone.utc).isoformat(), registry=manifest,
                  inventory=inventory['report'], inventory_changes=comparison)
    report['pilot'] = pilot(cache, inventory, source['tables'])
    report['pilot_replay'] = pilot(cache, inventory, source['tables'])
    if report['pilot_replay']['snapshots_created']:
        raise ValueError('Pilot replay generated duplicate snapshots')
    preserved = []
    with store.readonly() as target:
        for row in previous:
            current = target.execute('SELECT payload,matrix_hash,gene_disease_key FROM mechanism_snapshots WHERE snapshot_id=?', (row['snapshot_id'],)).fetchone()
            if tuple(current) != (row['payload'], row['matrix_hash'], row['gene_disease_key']):
                raise ValueError('Historical snapshot changed')
            decoded = store.snapshot(row['snapshot_id'])
            replay = cache.resolve_gene_disease_mechanism(decoded.identity.gene_id, decoded.identity.disease_id,
                decoded.identity.allelic_requirement.removeprefix('OTHER:'), cache_policy='SNAPSHOT', snapshot_id=decoded.snapshot_id)
            if replay.snapshot_id != row['snapshot_id']:
                raise ValueError('Historical explicit snapshot replay failed')
            preserved.append(dict(snapshot_id=row['snapshot_id'], payload_sha256=digest(json.loads(row['payload']))['value']))
        fk_errors = list(target.execute('PRAGMA foreign_key_check'))
    if fk_errors:
        raise ValueError('Foreign key violations')
    report['historical_preservation'] = dict(snapshots=len(preserved), byte_identical=True, replay_passed=True,
                                           foreign_key_violations=0, items=preserved)
    report['production_cache'] = original_store.statistics()
    report['pilot_cache'] = store.statistics()
    if args.g2p_response_dir:
        report['live_g2p_verification'] = verify_acquired_g2p_responses(args.g2p_response_dir, source['tables'])
    report['decision'] = 'GO_CONSERVATIVE_LOCAL_POPULATION'
    report['limitations'] = ['Qualified exactMatch is operational scope, not complete OWL equivalence or clinical approval',
                            'Unresolved and conflicting links isolated; no evidence transfer based on coassignment or Orphadata alone',
                            'Legacy upstream dataset releases remain unrecorded; 232 records without disease IDs remain excluded',
                            'gnomAD misses and ClinVar gene-disease NOT_SUPPORTED remain explicit',
                            'Full population was not started']
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Report:', args.report)
    print('Inventory:', comparison['new_unique'], 'shared:', comparison['new_shared'])
    print('Pilot:', report['pilot']['queries'], 'queries,', report['pilot']['unique_matrices'], 'matrices;', report['pilot']['original_record_occurrences_verified'], 'source records verified')
    print('Historical snapshots preserved:', len(previous))


if __name__ == '__main__':
    main()
