"""Explicit offline import and consultation of the versioned ontology registry."""
import argparse
import json
from pathlib import Path
from helper_next.core.acmg_mechanism_store import MechanismStore
from helper_next.core.acmg_ontology import OntologyMappingRegistry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--load-mondo', type=Path, help='Checksum-verified MONDO v2026-10-06 SSSOM file; no downloads')
    action.add_argument('--lookup', help='Disease CURIE; include original and rejected mapping records')
    action.add_argument('--status', action='store_true')
    parser.add_argument('--cache-db', type=Path)
    args = parser.parse_args(argv)
    registry = OntologyMappingRegistry(MechanismStore(args.cache_db))
    try:
        result = registry.import_mondo(args.load_mondo) if args.load_mondo else registry.lookup(args.lookup) if args.lookup else registry.manifest()
    except (OSError, ValueError) as exc:
        parser.exit(2, str(exc) + '\n')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
