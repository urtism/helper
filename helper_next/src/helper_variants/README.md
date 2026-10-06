# helper_variants

`helper_variants` is the application-independent variant storage, indexing, and
query engine used by Helper Next. It depends only on the Python standard
library and does not import Helper, FastAPI, or UI code.

Host applications are responsible for authentication, authorization, locating
run directories, and mapping their run metadata to the dictionary accepted by
`helper_variants.indexer.index_run`. The engine owns only rebuildable per-run
indexes and the future cohort store; VCF/GVCF files remain authoritative.

Public entry points:

- `helper_variants.store`: versioned SQLite schema and write primitives;
- `helper_variants.indexer`: artifact discovery and streaming indexing;
- `helper_variants.query`: summaries, samples, cursor pagination, and details.

No query API accepts an arbitrary source path from an HTTP client. A host must
resolve its own stable run identifier to a trusted database path before calling
this package.

