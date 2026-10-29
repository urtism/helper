"""Versioned offline mapping registry. Exact-match qualification is not OWL identity."""
import csv
import copy
import hashlib
import json
import threading
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from helper_next.core.acmg_client import digest

REGISTRY_VERSION = 'ontology-registry-1.0'
POLICY_VERSION = 'qualified-mondo-singleton-1.0'
MONDO_RELEASE = 'v2026-10-06'
MONDO_SHA256 = 'ec15afdb32fab3d3cb679d357e25ef4fb38b5e2c468ff4ac5456da10e2f6c80b'
MONDO_URL = ('https://raw.githubusercontent.com/monarch-initiative/mondo/' + MONDO_RELEASE
             + '/src/ontology/mappings/mondo.sssom.tsv')

SCHEMA = """
CREATE TABLE IF NOT EXISTS ontology_registry_releases (
 registry_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ontology_registry_current (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), registry_id TEXT NOT NULL
 REFERENCES ontology_registry_releases(registry_id));
CREATE TABLE IF NOT EXISTS ontology_mapping_records (
 mapping_id TEXT PRIMARY KEY, registry_id TEXT, source_identifier TEXT NOT NULL,
 target_identifier TEXT NOT NULL, verification_status TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ontology_mapping_lookup ON ontology_mapping_records(registry_id,source_identifier,target_identifier);
"""


def identifier(value):
    from helper_next.core.acmg_mechanism_normalizer import curie
    return curie(value)


def canonical_order(value):
    return ({'MONDO': 0, 'OMIM': 1, 'ORPHA': 2}.get(value.split(':')[0], 3), value)


def closure(graph, start):
    seen, pending = {start}, [start]
    while pending:
        for other in graph.get(pending.pop(), set()) - seen:
            seen.add(other)
            pending.append(other)
    return seen


def cardinality_conflict(nodes):
    return any(n > 1 for n in Counter(node.split(':')[0] for node in nodes).values())


def mapping_record(left_id, right_id, predicate, source_name, record, version, fingerprint, status, basis,
                   registry_id=None, conflict_reason=None, valid_from=None, valid_until=None, **extra):
    payload = dict(source_identifier=left_id, target_identifier=right_id, mapping_predicate=predicate,
                   mapping_source=source_name, mapping_source_record=record, source_version=version,
                   dataset_fingerprint=fingerprint, verification_status=status, verification_basis=basis,
                   conflict_reason=conflict_reason, valid_from=valid_from, valid_until=valid_until,
                   registry_version=REGISTRY_VERSION, registry_id=registry_id, policy_version=POLICY_VERSION, **extra)
    payload['mapping_id'] = 'om-' + digest(payload)['value']
    return payload


def save_records(db, records):
    """Called by registry import and the existing transactional snapshot publisher."""
    from helper_next.core.acmg_mechanism_store import json_text
    records = [{k: v for k, v in r.items() if k not in ('left', 'right', 'relation', 'source', 'source_record_ref')}
               if r['mapping_source'] == 'MONDO' else r for r in records]
    db.executemany('INSERT OR IGNORE INTO ontology_mapping_records VALUES(?,?,?,?,?,?)',
                   [(r['mapping_id'], r.get('registry_id'), r['source_identifier'], r['target_identifier'],
                     r['verification_status'], json_text(r)) for r in records])


class OntologyMappingRegistry:
    def __init__(self, store=None):
        from helper_next.core.acmg_mechanism_store import MechanismStore
        self.store = store or MechanismStore()
        self._loaded = None
        self._manifest = None
        self._graph = {}
        self._rows = []
        self._components = {}
        self._by_identifier = {}
        self._lock = threading.RLock()
        self._pinned = False

    def _load(self):
        if self._pinned:
            return
        with self._lock, self.store.readonly() as db:
            if db is None or not db.execute("SELECT 1 FROM sqlite_master WHERE name='ontology_registry_current'").fetchone():
                active = None
            else:
                active = db.execute('SELECT r.registry_id,r.payload FROM ontology_registry_current c JOIN ontology_registry_releases r USING(registry_id)').fetchone()
            registry_id = active['registry_id'] if active else 'NO_REGISTRY'
            if self._loaded == registry_id:
                return
            self._manifest = json.loads(active['payload']) if active else dict(
                registry_id=None, registry_version=REGISTRY_VERSION, policy_version=POLICY_VERSION,
                source_version=None, dataset_fingerprint=None, status='UNAVAILABLE')
            self._rows = [json.loads(r[0]) for r in db.execute(
                "SELECT payload FROM ontology_mapping_records WHERE registry_id=? AND json_extract(payload,'$.mapping_source')='MONDO' AND (target_identifier LIKE 'OMIM:%' OR target_identifier LIKE 'ORPHA:%')",
                (registry_id,))] if active else []
            for row in self._rows:
                if row['mapping_id'] != 'om-' + digest({k: v for k, v in row.items() if k != 'mapping_id'})['value']:
                    raise ValueError('Ontology mapping integrity failure')
            graph = defaultdict(set)
            for row in self._rows:
                if row['mapping_predicate'] == 'skos:exactMatch' and row['verification_basis'].startswith('QUALIFIED_MONDO'):
                    left, right = row['source_identifier'], row['target_identifier']
                    graph[left].add(right)
                    graph[right].add(left)
            by_identifier = defaultdict(list)
            for row in self._rows:
                by_identifier[row['source_identifier']].append(row)
                by_identifier[row['target_identifier']].append(row)
            self._graph, self._components, self._by_identifier = graph, {}, by_identifier
            self._loaded = registry_id

    def manifest(self):
        self._load()
        return dict(self._manifest)

    def pin(self):
        """An immutable release view per request/inventory, including during imports."""
        with self._lock:
            self._load()
            view = copy.copy(self)
            view._pinned = True
        return view

    def component(self, disease):
        if not self._pinned:
            return self.pin().component(disease)
        self._load()
        disease = identifier(disease)
        if disease not in self._components:
            nodes = closure(self._graph, disease)
            for node in nodes:
                self._components[node] = frozenset(nodes)
        return self._components[disease]

    def aliases(self, disease):
        nodes = self.component(disease)
        return {identifier(disease)} if cardinality_conflict(nodes) else set(nodes)

    def canonical(self, disease):
        return min(self.aliases(disease), key=canonical_order)

    def decision(self, left, right):
        if not self._pinned:
            return self.pin().decision(left, right)
        left, right = identifier(left), identifier(right)
        if left == right:
            return 'IDENTITY', 'Same stable identifier; no cross-ontology inference'
        a, b = self.component(left), self.component(right)
        if cardinality_conflict(a) or cardinality_conflict(b):
            return 'AMBIGUOUS_MAPPING', 'Reference component has multiple IDs in one namespace; no canonical chosen'
        if right in a:
            return 'VERIFIED_EXACT', 'QUALIFIED_MONDO_EXACT_SINGLETON: operational scope only, not complete logical equivalence'
        # A mapped external term pointing to another MONDO contradicts this
        # claimed cross-reference, not the biological identity of diseases.
        if (left.startswith('MONDO:') and any(n.startswith('MONDO:') for n in b)) or (
                right.startswith('MONDO:') and any(n.startswith('MONDO:') for n in a)):
            return 'CONFLICTING_MAPPING', 'Claimed target disagrees with the pinned reference; biological difference is not established'
        return 'NO_VERIFIED_MAPPING', 'No qualified equivalence in the active reference; biological difference is not established'

    def observations(self, request_id, records):
        """Keep accepted AND rejected source links with their complete origin."""
        from helper_next.core.acmg_mechanism_normalizer import describe
        self._load()
        aliases = self.aliases(request_id)
        observed = []
        source_fingerprints = {source: digest(sorted(digest(row)['value'] for packet, row, _ in records
                                                   if packet.source == source))['value'] for source in ('g2p', 'gencc')}
        for packet, row, ref in records:
            if packet.source not in ('g2p', 'gencc'):
                continue
            info = describe(packet.source, row)
            ids = info['disease_ids']
            links = [(ids[0], right, 'SOURCE_CROSS_REFERENCE', packet.source, info['source_record_id'],
                      info['version'], packet.dataset_version, None) for right in ids[1:]]
            for link in row.get('disease_mappings', []):
                links.append((identifier(link['identifier']), identifier(link['orpha_id']),
                              link.get('mapping_relation') or 'UNSPECIFIED', 'orphadata', ref,
                              None, None, link.get('source_url')))
            for left, right, predicate, source, origin, version, dataset, url in links:
                status, basis = self.decision(left, right)
                from helper_variants.gene_phenotype import _is_exact_mapping
                if predicate != 'SOURCE_CROSS_REFERENCE' and left != right and not _is_exact_mapping(predicate):
                    status, basis = 'UNVERIFIED_CROSS_REFERENCE', 'Original non-exact predicate is not promoted to exactMatch'
                if status == 'NO_VERIFIED_MAPPING':
                    status = 'UNVERIFIED_CROSS_REFERENCE'
                observed.append(mapping_record(left, right, predicate, source, origin, version,
                    source_fingerprints[packet.source], status, basis, self._manifest['registry_id'],
                    conflict_reason=basis if status in ('CONFLICTING_MAPPING', 'AMBIGUOUS_MAPPING') else None,
                    source_record_ref=ref, source=source, source_url=url or info['url'] or packet.source_url,
                    source_dataset_version=dataset, acquired_at=packet.retrieved_at,
                    fingerprint_scope='GENE_SOURCE_RECORDS_WITH_INDEXED_MAPPINGS',
                    left=left, right=right, relation=predicate))
        # Only links touching this query/reference component or its source rows
        # are pertinent; record-local rejected links remain visible.
        pertinent_refs = {ref for packet, row, ref in records if packet.source in ('g2p', 'gencc') and
                          aliases.intersection(describe(packet.source, row)['disease_ids'])}
        observed = [r for r in observed if r['source_record_ref'] in pertinent_refs
                    or r['left'] in aliases or r['right'] in aliases]
        for row in {r['mapping_id']: r for alias in aliases for r in self._by_identifier.get(alias, [])}.values():
            observed.append(dict(row, source_record_ref=None, source='MONDO',
                                 left=row['source_identifier'], right=row['target_identifier'], relation=row['mapping_predicate']))
        return sorted({r['mapping_id']: r for r in observed}.values(), key=lambda r: r['mapping_id'])

    def lookup(self, disease):
        """Offline query, including previously observed unverified links."""
        if not self._pinned:
            return self.pin().lookup(disease)
        disease = identifier(disease)
        self._load()
        with self.store.readonly() as db:
            rows = [json.loads(r[0]) for r in db.execute(
                'SELECT payload FROM ontology_mapping_records WHERE source_identifier=? OR target_identifier=? ORDER BY mapping_id',
                (disease, disease))] if db and db.execute("SELECT 1 FROM sqlite_master WHERE name='ontology_mapping_records'").fetchone() else []
        status = 'AMBIGUOUS_MAPPING' if cardinality_conflict(self.component(disease)) else (
            'VERIFIED_EXACT' if len(self.aliases(disease)) > 1 else 'NO_VERIFIED_MAPPING')
        return dict(identifier=disease, status=status, aliases=sorted(self.aliases(disease)),
                    canonical=self.canonical(disease), registry=self.manifest(), records=rows)

    def import_mondo(self, path, release=MONDO_RELEASE, checksum=MONDO_SHA256, source_url=MONDO_URL):
        """Explicit load, no HTTP. Validate bytes BEFORE opening a writable DB."""
        path = Path(path)
        with path.open('rb') as handle:
            actual = hashlib.file_digest(handle, 'sha256').hexdigest()
        if actual != checksum:
            raise ValueError('Ontology reference checksum mismatch')
        registry_id = 'omr-' + digest(dict(release=release, sha256=actual, policy=POLICY_VERSION))['value']
        raw, graph = [], defaultdict(set)
        with path.open() as handle:
            reader = csv.DictReader((line for line in handle if not line.startswith('#')), delimiter='\t')
            if not {'subject_id', 'predicate_id', 'object_id'} <= set(reader.fieldnames or []):
                raise ValueError('SSSOM requires subject_id/predicate_id/object_id')
            for ordinal, row in enumerate(reader, 1):
                # Preserve unsupported SSSOM namespaces/IRIs without inventing
                # a normalized clinical CURIE or allowing them into equivalence.
                left = identifier(row['subject_id']) if row['subject_id'].startswith(('MONDO:', 'OMIM:', 'Orphanet:')) else row['subject_id'].strip()
                right = identifier(row['object_id']) if row['object_id'].startswith(('MONDO:', 'OMIM:', 'Orphanet:')) else row['object_id'].strip()
                qualified = (left.startswith('MONDO:') and right.startswith(('OMIM:', 'ORPHA:'))
                             and row['predicate_id'] == 'skos:exactMatch')
                if qualified:
                    graph[left].add(right)
                    graph[right].add(left)
                raw.append((ordinal, row, left, right, qualified))
        if not raw:
            raise ValueError('Ontology mapping reference is empty')
        components = {}
        for node in graph:
            if node not in components:
                nodes = closure(graph, node)
                for member in nodes:
                    components[member] = nodes
        rows = []
        for ordinal, row, left, right, qualified in raw:
            ambiguous = qualified and cardinality_conflict(components[left])
            status = 'AMBIGUOUS_MAPPING' if ambiguous else 'VERIFIED_EXACT' if qualified else 'UNVERIFIED_CROSS_REFERENCE'
            basis = ('QUALIFIED_MONDO_EXACT_SINGLETON: explicit exactMatch, pinned bytes, allowed namespaces; not OWL identity'
                     if qualified else 'Predicate or namespace outside the initial qualified mapping policy')
            reason = 'Multiple same-namespace targets in qualified reference component' if ambiguous else None
            rows.append(mapping_record(left, right, row['predicate_id'], 'MONDO', source_url + '#data-row-' + str(ordinal),
                release, actual, status, basis, registry_id, conflict_reason=reason,
                source_url=source_url, original_mapping=row))
        manifest = dict(registry_id=registry_id, registry_version=REGISTRY_VERSION, policy_version=POLICY_VERSION,
                        source_version=release, dataset_fingerprint=actual, source_url=source_url, status='AVAILABLE',
                        acquired_at=datetime.now(timezone.utc).isoformat(), records=len(rows),
                        verification_status_counts=dict(Counter(r['verification_status'] for r in rows)))
        from helper_next.core.acmg_mechanism_store import json_text
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO ontology_registry_releases VALUES(?,?)', (registry_id, json_text(manifest)))
            save_records(db, rows)
            db.execute('INSERT INTO ontology_registry_current VALUES(1,?) ON CONFLICT(singleton) DO UPDATE SET registry_id=excluded.registry_id', (registry_id,))
        self._loaded = None
        return self.manifest()
