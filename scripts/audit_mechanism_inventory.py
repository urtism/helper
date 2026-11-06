"""Offline scientific audit; optional stratified pilot is capped at 30 matrices.

The MONDO SSSOM file is an audit reference only, never injected into the resolver.
Run from the repository root with PYTHONPATH=helper_next/src. No full-population mode.
"""
import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from helper_next.core import acmg_mechanism_normalizer as norm
from helper_next.core.acmg_digest import digest
from helper_next.core.acmg_mechanism_store import MechanismStore, load_snapshot
from helper_next.core.acmg_mechanisms import MechanismEvidenceCache
from helper_next.core.acmg_mechanisms_bulk import build_inventory, disease_order
from helper_next.core.acmg_sources import SourceManager

MONDO_RELEASE = 'v2026-10-06'
MONDO_URL = ('https://raw.githubusercontent.com/monarch-initiative/mondo/' + MONDO_RELEASE
             + '/src/ontology/mappings/mondo.sssom.tsv')
MONDO_SHA256 = 'ec15afdb32fab3d3cb679d357e25ef4fb38b5e2c468ff4ac5456da10e2f6c80b'


def file_hash(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def legacy_allelic(value):
    word = str(value or '').lower().replace('_', ' ').replace('-', ' ')
    word = ' '.join(word.split())
    old = {'monoallelic autosomal': 'MONOALLELIC_AUTOSOMAL',
           'biallelic autosomal': 'OTHER:biallelic autosomal',
           'monoallelic x hemizygous': 'OTHER:monoallelic x hemizygous',
           'monoallelic x heterozygous': 'OTHER:monoallelic x heterozygous',
           'monoallelic y hemizygous': 'OTHER:monoallelic y hemizygous',
           'y linked inheritance': 'OTHER:y linked inheritance'}
    return old.get(word, norm.allelic(value))


def component(graph, start):
    seen, todo = {start}, [start]
    while todo:
        for other in graph.get(todo.pop(), set()) - seen:
            seen.add(other)
            todo.append(other)
    return seen


def ambiguous(nodes):
    return any(count > 1 for count in Counter(n.split(':')[0] for n in nodes).values())


def ontology_audit(tables, mondo_file):
    checksum = file_hash(mondo_file)
    if checksum != MONDO_SHA256:
        raise ValueError('MONDO audit reference checksum does not match the pinned release')
    targets, exact, reference_graph = defaultdict(set), set(), defaultdict(set)
    with Path(mondo_file).open() as stream:
        for row in csv.DictReader((line for line in stream if not line.startswith('#')), delimiter='\t'):
            if row['predicate_id'] != 'skos:exactMatch' or not row['object_id'].startswith(('OMIM:', 'Orphanet:')):
                continue
            left, right = norm.curie(row['subject_id']), norm.curie(row['object_id'])
            exact.add(frozenset((left, right)))
            targets[right].add(left)
            reference_graph[left].add(right)
            reference_graph[right].add(left)
    orpha, by_id = defaultdict(set), defaultdict(set)
    for link in tables.get('orpha_aliases', []):
        if not norm._is_exact_mapping(link['mapping_relation']):
            continue
        o, identifier = norm.curie(link['orpha_id']), norm.curie(link['identifier'])
        orpha[o].update((o, identifier))
    for o, identifiers in orpha.items():
        for identifier in identifiers:
            by_id[identifier].add(o)
    graphs, rows, source_edges, unverified = {}, [], Counter(), []
    for source, table in [('g2p', 'g2p_records'), ('gencc', 'assertions')]:
        for row in tables[table]:
            info = norm.describe(source, row)
            if not info['disease_ids']:
                continue
            gene, ids = norm.curie(info['gene_id'], gene=True), info['disease_ids']
            full, source_only, verified = graphs.setdefault(gene, [defaultdict(set) for _ in range(3)])
            for identifier in ids:
                full[identifier]  # Include isolated primary IDs in the reference lookup.
            primary = norm.curie(row.get('disease_curie') or row.get('disease_mim') or row.get('disease_original_curie'))
            rows.append((source, gene, primary, info['original_inheritance']))
            for right in ids[1:]:
                left = ids[0]
                for graph in (full, source_only):
                    graph[left].add(right)
                    graph[right].add(left)
                match = frozenset((left, right)) in exact
                source_edges[source + ':' + ('verified_exact' if match else 'not_confirmed_exact')+':rows'] += 1
                if match:
                    verified[left].add(right)
                    verified[right].add(left)
                else:
                    unverified.append({'gene': gene, 'symbol': row['gene_symbol'], 'record_id': info['source_record_id'],
                                       'source': source, 'left': left, 'right': right,
                                       'exact_mondo_targets_of_right': sorted(targets[right])})
            for o in {o for identifier in ids for o in by_id[identifier]}:
                for identifier in orpha[o]:
                    full[identifier].add(o)
                    full[o].add(identifier)
                    a = {identifier} if identifier.startswith('MONDO:') else targets[identifier]
                    b = targets[o]
                    # Audited counterfactual: only one shared exact MONDO target.
                    if len(a) == len(b) == 1 and a == b:
                        verified[identifier].add(o)
                        verified[o].add(identifier)
    # Include verified links between identifiers from DIFFERENT source records,
    # rather than only retaining links that happen to be coassigned in one row.
    # Expansion is limited to components touched by this gene's local records.
    for full, source_only, verified in graphs.values():
        pending, visited = list(full), set()
        while pending:
            node = pending.pop()
            if node in visited:
                continue
            visited.add(node)
            for other in reference_graph[node]:
                verified[node].add(other)
                verified[other].add(node)
                if other not in visited:
                    pending.append(other)
    counts, examples, cached = Counter(), [], {}
    source_keys = {s: set() for s in ('g2p', 'gencc')}
    corrected_keys = {s: set() for s in source_keys}
    origins = defaultdict(set)
    pairs, primary_sets = {s: set() for s in source_keys}, {s: set() for s in source_keys}
    corrected_primary = {s: set() for s in source_keys}
    for source, gene, disease, requirement in rows:
        key = gene, disease
        if key not in cached:
            full, source_only, verified = graphs[gene]
            cached[key] = (component(full, disease), component(source_only, disease), component(verified, disease))
        full, local, checked = cached[key]
        canonical = disease if ambiguous(full) else min(full, key=disease_order)
        source_keys[source].add((gene, canonical, legacy_allelic(requirement)))
        corrected_key = (gene, canonical, norm.allelic(requirement))
        corrected_keys[source].add(corrected_key)
        origins[source, corrected_key].add(disease)
        pairs[source].add((gene, disease))
        primary_sets[source].add((gene, disease, legacy_allelic(requirement)))
        corrected_primary[source].add((gene, disease, norm.allelic(requirement)))
    old_keys = source_keys['g2p'] | source_keys['gencc']
    for gene, disease, requirement in sorted(old_keys):
        if (gene, disease) not in cached:
            cached[gene, disease] = tuple(component(g, disease) for g in graphs[gene])
        full, local, checked = cached[(gene, disease)]
        if not ambiguous(full):
            continue
        cause = 'source_cross_references' if ambiguous(local) else 'orphadata_bridge_only'
        outcome = ('still_ambiguous_verified_exact' if ambiguous(checked) else
                   'nonambiguous_verified_component' if len(checked) > 1 else 'no_verified_mapping')
        counts[cause] += 1
        counts[outcome] += 1
        ns = Counter(n.split(':')[0] for n in full)
        counts['duplicate_namespace:' + ','.join(sorted(k for k, v in ns.items() if v > 1))] += 1
        if len(examples) < 6:
            examples.append({'gene': gene, 'disease': disease, 'requirement': requirement,
                             'original_component': sorted(full), 'verified_component': sorted(checked), 'cause': cause})
    unconfirmed_reasons = Counter()
    unconfirmed_protected = Counter()
    for row in unverified:
        targets_for_id = row['exact_mondo_targets_of_right']
        reason = ('MULTIPLE_EXACT_TARGETS' if len(targets_for_id) > 1 else 'DIFFERENT_MONDO_TARGET' if targets_for_id
                  else 'MONDO_TO_MONDO_REQUIRES_TERM_REVIEW' if row['right'].startswith('MONDO:') else 'NO_EXACT_MATCH_IN_PINNED_REFERENCE')
        unconfirmed_reasons[reason] += 1
        unconfirmed_protected['currently_ambiguous' if ambiguous(component(graphs[row['gene']][0], row['left']))
                              else 'currently_unambiguous_but_not_ontology_verified'] += 1
    alias_overlap, alias_examples = Counter(), []
    for key in corrected_keys['g2p'] & corrected_keys['gencc']:
        left, right = origins['g2p', key], origins['gencc', key]
        if left & right:
            continue
        checked = component(graphs[key[0]][2], next(iter(left)))
        confirmed = not ambiguous(checked) and (left | right) <= checked
        alias_overlap['verified_nonambiguous' if confirmed else 'not_confirmed_nonambiguous'] += 1
        if not confirmed:
            alias_examples.append({'gene': key[0], 'canonical_disease': key[1], 'requirement': key[2],
                                   'g2p_primary_ids': sorted(left), 'gencc_primary_ids': sorted(right),
                                   'verified_component_from_g2p': sorted(checked)})
    return {'reference_url': MONDO_URL, 'release': MONDO_RELEASE, 'sha256': checksum,
            'mode': 'AUDIT_ONLY_COUNTERFACTUAL_NOT_APPLIED', 'old_unique_associations': len(old_keys),
            'old_normalized_source_associations': {s: len(v) for s, v in source_keys.items()},
            'old_cross_source_associations': len(source_keys['g2p'] & source_keys['gencc']),
            'old_exact_primary_key_overlap': len(primary_sets['g2p'] & primary_sets['gencc']),
            'corrected_exact_primary_key_overlap': len(corrected_primary['g2p'] & corrected_primary['gencc']),
            'corrected_alias_only_overlap': dict(alias_overlap),
            'unconfirmed_alias_overlap_examples': sorted(alias_examples, key=lambda r: (r['gene'], r['canonical_disease'], r['requirement'])),
            'shared_primary_gene_disease_pairs': len(pairs['g2p'] & pairs['gencc']),
            'shared_gene_ids': len({g for g, _ in pairs['g2p']} & {g for g, _ in pairs['gencc']}),
            'old_ambiguous_associations': sum(counts[k] for k in ['source_cross_references', 'orphadata_bridge_only']),
            'ambiguity_classification': dict(counts), 'source_cross_reference_checks': dict(source_edges),
            'unconfirmed_cross_reference_reasons': dict(unconfirmed_reasons),
            'unconfirmed_cross_reference_current_protection': dict(unconfirmed_protected),
            'unconfirmed_cross_reference_examples': unverified[:12],
            'unconfirmed_cardiogenetic_examples': [r for r in unverified if r['symbol'] in {'MYH7', 'MYBPC3', 'LMNA', 'GLA', 'FLNA'}][:12],
            'ambiguous_examples': examples}


def initial_pilot_audit(store, tables):
    output = []
    with store.readonly() as db:
        if db is None:
            return {}
        run = db.execute('SELECT run_id FROM mechanism_bulk_runs ORDER BY created_at LIMIT 1').fetchone()
        if not run:
            return {}
        for row in db.execute('SELECT s.payload,s.matrix_hash FROM mechanism_bulk_items i JOIN mechanism_snapshots s '
                              'ON i.snapshot_id=s.snapshot_id WHERE i.run_id=? AND i.status=\'SUCCESS\' ORDER BY i.ordinal', (run[0],)):
            m = load_snapshot(row)
            g2p = [e for e in m.direct_evidence + m.contextual_evidence if e.source == 'g2p']
            reason = ('DIRECT_ASSERTION' if m.direct_evidence else 'NO_G2P_DISEASE_RECORD' if not g2p else
                      'G2P_MECHANISM_UNDETERMINED' if all(e.original_mechanism == 'undetermined' for e in g2p) else
                      'G2P_DIFFERENT_INHERITANCE' if all(e.applicability == 'DIFFERENT_INHERITANCE' for e in g2p) else 'OTHER')
            output.append({'gene': m.identity.gene_id, 'symbol': m.identity.gene_symbol, 'disease': m.identity.disease_id,
                           'requirement': m.identity.allelic_requirement, 'direct': bool(m.direct_evidence), 'reason': reason,
                           'g2p_records': [{'id': e.source_record_id, 'mechanism': e.original_mechanism,
                                            'inheritance': e.original_allelic_requirement, 'applicability': e.applicability} for e in g2p]})
            if reason == 'G2P_DIFFERENT_INHERITANCE':
                output[-1]['resolved_by_qualified_crosswalk'] = any(
                    norm.allelic(e.original_allelic_requirement) == norm.allelic(m.identity.allelic_requirement) for e in g2p)
            if reason == 'NO_G2P_DISEASE_RECORD':
                output[-1]['other_disease_g2p_record_ids'] = [r['g2p_id'] for r in tables['g2p_records']
                                                            if r['gene_curie'] == m.identity.gene_id]
    return {'run_id': run[0], 'matrices': len(output), 'reasons': dict(Counter(r['reason'] for r in output)),
            'inheritance_rows_resolved_by_crosswalk': sum(r.get('resolved_by_qualified_crosswalk', False) for r in output), 'items': output}


def select_pilot(associations):
    selected = {}
    for symbol in ['MYH7', 'MYBPC3', 'LMNA', 'GLA', 'FLNA']:
        candidates = [a for a in associations if a['symbol'] == symbol]
        if not candidates:
            raise ValueError('Requested pilot gene absent: ' + symbol)
        for a in [a for a in candidates if 'g2p' in a['sources']][:3]:
            selected[a['key']] = a
        for a in [a for a in candidates if a['sources'] == ['gencc']][:1]:
            selected[a['key']] = a
    # Known same-disease/different-inheritance and different-mechanism controls.
    for symbol, disease in [('LMNA', 'MONDO:0030781'), ('MYBPC3', 'MONDO:0007268'),
                            ('LMNA', 'MONDO:0021569'), ('FLNA', 'MONDO:0024550')]:
        for a in associations:
            if a['symbol'] == symbol and a['disease'] == disease:
                selected[a['key']] = a
    # Include existing constraint data without making any remote request.
    for a in [a for a in associations if a['symbol'] == 'COL5A2'][:1]:
        selected[a['key']] = a
    for stratum in [['g2p'], ['gencc'], ['g2p', 'gencc']]:
        for a in [a for a in associations if a['sources'] == stratum]:
            selected.setdefault(a['key'], a)
            if len(selected) >= 30:
                break
        if len(selected) >= 30:
            break
    if len(selected) > 30:
        raise ValueError('Pilot cap exceeded')
    return list(selected.values())


def stratified_pilot(inventory, sources, database, tables):
    cache = MechanismEvidenceCache(sources, database)
    originals = {}
    for source, table, identifier in [('g2p', 'g2p_records', 'g2p_id'), ('gencc', 'assertions', 'sgc_id'),
                                      ('gnomad', 'gnomad_constraints', 'gene_symbol'), ('clingen_dosage', 'clingen_dosage', 'gene_symbol')]:
        for row in tables.get(table, []):
            originals[source, str(row[identifier])] = row
    selected, output = select_pilot(inventory['associations']), []
    before = cache.store.statistics()
    for association in selected:
        matrix = cache.resolve_gene_disease_mechanism(association['gene'], association['disease'],
            association['resolver_requirement'], symbol=association['symbol'], disease_name=association['disease_name'], rebuild=True)
        checked = 0
        evidence = matrix.direct_evidence + matrix.contextual_evidence
        for e in evidence:
            identifier = e.source_record_id if e.source in ('g2p', 'gencc') else e.raw_assertion['gene_symbol']
            original = originals[e.source, identifier]
            if any(e.raw_assertion.get(k) != v for k, v in original.items()):
                raise ValueError('Original source record mismatch: ' + e.source_record_ref)
            if digest(e.raw_assertion)['value'] != e.source_record_hash:
                raise ValueError('Source record hash mismatch')
            if e in matrix.direct_evidence and (e.gene_id != matrix.identity.gene_id
                    or e.allelic_requirement != matrix.identity.allelic_requirement
                    or e.applicability not in ('EXACT', 'MAPPED')):
                raise ValueError('Direct evidence scope mismatch')
            checked += 1
        replay = cache.resolve_gene_disease_mechanism(association['gene'], association['disease'],
            association['resolver_requirement'], cache_policy='CACHE_ONLY')
        if replay.snapshot_id != matrix.snapshot_id:
            raise ValueError('Snapshot replay mismatch')
        output.append({'symbol': association['symbol'], 'gene': association['gene'], 'disease': association['disease'],
                       'requirement': matrix.identity.allelic_requirement, 'stratum': association['sources'],
                       'snapshot_id': matrix.snapshot_id, 'candidate_mechanisms': matrix.candidate_mechanisms,
                       'direct_g2p_records': [{'id': e.source_record_id, 'mechanism': e.original_mechanism,
                                               'requirement': e.original_allelic_requirement} for e in matrix.direct_evidence],
                       'contextual_g2p_records': [{'id': e.source_record_id, 'mechanism': e.original_mechanism,
                                                  'requirement': e.original_allelic_requirement, 'applicability': e.applicability} for e in matrix.contextual_evidence if e.source == 'g2p'],
                       'sources': {s.source: s.status for s in matrix.source_status},
                       'original_records_verified': checked, 'review_status': matrix.review_status, 'issues': matrix.issues})
    after = cache.store.statistics()
    return {'cache': str(database), 'matrices': len(output), 'strata': dict(Counter('+'.join(r['stratum']) for r in output)),
            'direct_assertion_matrices': sum(bool(r['direct_g2p_records']) for r in output),
            'context_only_matrices': sum(not r['direct_g2p_records'] for r in output),
            'original_records_verified': sum(r['original_records_verified'] for r in output),
            'snapshots_created': after['snapshots'] - before.get('snapshots', 0),
            'cache_statistics': after,
            'sources': dict(Counter(s + ':' + status for r in output for s, status in r['sources'].items())), 'items': output}


def verify_acquired_g2p_responses(directory, tables):
    """Audit selected official responses, never overwrite synchronized index rows."""
    originals = {r['g2p_id']: r for r in tables['g2p_records']}
    checked = []
    for path in sorted(directory.glob('g2p-G2P*.json')):
        document = json.loads(path.read_text())
        identifier = document['stable_id']
        cached = originals[identifier]
        terms = document['disease']['ontology_terms']
        ids = {norm.curie(t['accession']) for t in terms if t['source'] in ('Mondo', 'OMIM')}
        molecular = document['molecular_mechanism']
        fields = {'gene_curie': document['locus']['ids']['HGNC'], 'gene_symbol': document['locus']['gene_symbol'],
                  'allelic_requirement': document['genotype'], 'mechanism': molecular['mechanism'],
                  'mechanism_support': molecular['mechanism_support'], 'confidence': document['confidence']}
        differences = {k: {'indexed': cached[k], 'live': value} for k, value in fields.items() if cached[k] != value}
        indexed_ids = set(norm.describe('g2p', cached)['disease_ids'])
        if indexed_ids != ids:
            differences['disease_ids'] = {'indexed': sorted(indexed_ids), 'live': sorted(ids)}
        checked.append({'record_id': identifier, 'source_url': 'https://www.ebi.ac.uk/gene2phenotype/api/lgd/' + identifier + '/',
                        'response_sha256': file_hash(path), 'response_acquired_at': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                        'dataset_version': None, 'source_last_updated': document['last_updated'],
                        'verified_fields': fields, 'disease_ids': sorted(ids), 'differences': differences})
    return {'records': len(checked), 'records_with_differences': sum(bool(r['differences']) for r in checked), 'items': checked}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mondo-mappings', type=Path, required=True)
    parser.add_argument('--source-db', type=Path)
    parser.add_argument('--pilot-db', type=Path, help='Explicit separate database; at most 30 offline matrices')
    parser.add_argument('--g2p-response-dir', type=Path, help='Previously acquired selected public G2P responses; no HTTP calls')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    sources = SourceManager(gene_database=args.source_db, mechanism_fetch=False)
    source = sources.mechanism_association_inventory()
    default_store = MechanismStore()
    protected = {Path(source['database']).resolve(), default_store.path.resolve(), args.mondo_mappings.resolve()}
    if args.pilot_db and args.pilot_db.resolve() in protected:
        parser.error('Use a separate pilot database; existing source/production databases must remain unchanged')
    if args.report.resolve() in protected | ({args.pilot_db.resolve()} if args.pilot_db else set()):
        parser.error('Report path must not overwrite input/database files')
    inventory = build_inventory(sources)
    if inventory['report']['source_problems']:
        parser.error('Local datasets are not ready: ' + str(inventory['report']['source_problems']))
    report = {'acquired_at': datetime.now(timezone.utc).isoformat(), 'inventory': inventory['report'],
              'ontology': ontology_audit(source['tables'], args.mondo_mappings),
              'initial_pilot': initial_pilot_audit(default_store, source['tables'])}
    if args.pilot_db:
        report['stratified_pilot'] = stratified_pilot(inventory, sources, args.pilot_db, source['tables'])
    if args.g2p_response_dir:
        report['live_g2p_verification'] = verify_acquired_g2p_responses(args.g2p_response_dir, source['tables'])
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print('Report:', args.report)
    print('Associations:', inventory['report']['unique_associations'], 'shared:', inventory['report']['cross_source_associations'])
    print('Old ambiguous:', report['ontology']['old_ambiguous_associations'])
    if args.pilot_db:
        print('Pilot:', report['stratified_pilot']['matrices'], 'matrices;', report['stratified_pilot']['original_records_verified'], 'original records verified')


if __name__ == '__main__':
    main()
