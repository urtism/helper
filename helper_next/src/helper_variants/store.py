"""Versioned storage primitives for standalone run and cohort variant databases.

The source VCF/GVCF remains authoritative. These databases are rebuildable
indexes that preserve calls and annotation releases without conflating them.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 2
STORE_KINDS = ("run", "cohort")


SCHEMA = """
CREATE TABLE IF NOT EXISTS store_metadata (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    store_kind TEXT NOT NULL CHECK (store_kind IN ('run', 'cohort')),
    schema_version INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    run_key TEXT NOT NULL UNIQUE,
    source_path TEXT NOT NULL DEFAULT '',
    reference_build TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY,
    subject_key TEXT NOT NULL UNIQUE,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY,
    sample_key TEXT NOT NULL UNIQUE,
    subject_id INTEGER REFERENCES subjects(id),
    display_name TEXT NOT NULL,
    specimen_type TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY,
    analysis_key TEXT NOT NULL UNIQUE,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    sample_id INTEGER NOT NULL REFERENCES samples(id),
    role TEXT NOT NULL DEFAULT '',
    pipeline_json TEXT NOT NULL DEFAULT '{}',
    qc_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS variants (
    id INTEGER PRIMARY KEY,
    reference_build TEXT NOT NULL,
    chromosome TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position > 0),
    reference TEXT NOT NULL,
    alternate TEXT NOT NULL,
    variant_type TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(reference_build, chromosome, position, reference, alternate)
);

CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY,
    analysis_id INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    variant_id INTEGER NOT NULL REFERENCES variants(id),
    caller TEXT NOT NULL DEFAULT '',
    genotype TEXT NOT NULL DEFAULT '',
    phased INTEGER NOT NULL DEFAULT 0 CHECK (phased IN (0, 1)),
    zygosity TEXT NOT NULL DEFAULT '',
    depth INTEGER,
    reference_depth INTEGER,
    alternate_depth INTEGER,
    allele_fraction REAL,
    genotype_quality REAL,
    quality REAL,
    filter_status TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(analysis_id, variant_id, caller)
);

CREATE TABLE IF NOT EXISTS annotation_releases (
    id INTEGER PRIMARY KEY,
    release_key TEXT NOT NULL UNIQUE,
    annotator TEXT NOT NULL,
    annotator_version TEXT NOT NULL DEFAULT '',
    reference_build TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resources_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS annotations (
    id INTEGER PRIMARY KEY,
    variant_id INTEGER NOT NULL REFERENCES variants(id) ON DELETE CASCADE,
    release_id INTEGER NOT NULL REFERENCES annotation_releases(id),
    allele TEXT NOT NULL DEFAULT '',
    gene TEXT NOT NULL DEFAULT '',
    transcript TEXT NOT NULL DEFAULT '',
    consequence TEXT NOT NULL DEFAULT '',
    impact TEXT NOT NULL DEFAULT '',
    hgvsc TEXT NOT NULL DEFAULT '',
    hgvsp TEXT NOT NULL DEFAULT '',
    clinical_significance TEXT NOT NULL DEFAULT '',
    population_af REAL,
    canonical INTEGER NOT NULL DEFAULT 0 CHECK (canonical IN (0, 1)),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(variant_id, release_id, allele, transcript, consequence, hgvsc, hgvsp)
);

CREATE INDEX IF NOT EXISTS idx_analyses_run ON analyses(run_id, sample_id);
CREATE INDEX IF NOT EXISTS idx_calls_variant ON calls(variant_id, analysis_id);
CREATE INDEX IF NOT EXISTS idx_variants_locus ON variants(reference_build, chromosome, position);
CREATE INDEX IF NOT EXISTS idx_annotations_gene ON annotations(release_id, gene, variant_id);
CREATE INDEX IF NOT EXISTS idx_annotations_variant ON annotations(variant_id, release_id);
"""


MIGRATIONS = {
    2: """
    CREATE TABLE IF NOT EXISTS index_sources (
        id INTEGER PRIMARY KEY,
        run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
        relative_path TEXT NOT NULL,
        stage TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        mtime_ns INTEGER NOT NULL,
        sha256 TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('pending', 'indexing', 'complete', 'failed')),
        records_processed INTEGER NOT NULL DEFAULT 0,
        error TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL,
        UNIQUE(run_id, relative_path)
    );
    CREATE INDEX IF NOT EXISTS idx_index_sources_status ON index_sources(run_id, status);
    """,
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def _json(value):
    return json.dumps(value or {}, sort_keys=True, separators=(",", ":"))


def _existing_id(db, table, key_column, key):
    row = db.execute(
        "SELECT id FROM {} WHERE {} = ?".format(table, key_column), (key,)
    ).fetchone()
    return row[0]


@contextmanager
def connect(path, store_kind=None):
    """Open a store, initializing it when ``store_kind`` is provided."""
    path = Path(path)
    if store_kind is not None:
        if store_kind not in STORE_KINDS:
            raise ValueError("store_kind must be 'run' or 'cohort'")
        path.parent.mkdir(parents=True, exist_ok=True)
    elif not path.is_file():
        raise FileNotFoundError(str(path))

    db = sqlite3.connect(str(path), timeout=30)
    try:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA busy_timeout = 30000")
        if store_kind is not None:
            db.execute("PRAGMA journal_mode = WAL")
            _initialize(db, store_kind)
        else:
            _validate(db)
        with db:
            yield db
    finally:
        db.close()


def _initialize(db, store_kind):
    db.executescript(SCHEMA)
    row = db.execute(
        "SELECT store_kind, schema_version FROM store_metadata WHERE singleton = 1"
    ).fetchone()
    if row is None:
        db.execute(
            "INSERT INTO store_metadata VALUES (1, ?, ?, ?)",
            (store_kind, 1, utc_now()),
        )
        row = {"store_kind": store_kind, "schema_version": 1}
    if row["store_kind"] != store_kind:
        raise ValueError(
            "variant database is {!r}, not {!r}".format(row["store_kind"], store_kind)
        )
    if row["schema_version"] > SCHEMA_VERSION:
        raise ValueError(
            "unsupported variant database schema version {} (expected {})".format(
                row["schema_version"], SCHEMA_VERSION
            )
        )
    for version in range(row["schema_version"] + 1, SCHEMA_VERSION + 1):
        migration = MIGRATIONS.get(version)
        if migration is None:
            raise ValueError("missing variant database migration {}".format(version))
        db.executescript(migration)
        db.execute(
            "UPDATE store_metadata SET schema_version = ? WHERE singleton = 1", (version,)
        )


def _validate(db):
    try:
        row = db.execute(
            "SELECT store_kind, schema_version FROM store_metadata WHERE singleton = 1"
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if row is None:
        raise ValueError("not a Helper variant database")
    if row["schema_version"] != SCHEMA_VERSION:
        raise ValueError(
            "unsupported variant database schema version {} (expected {})".format(
                row["schema_version"], SCHEMA_VERSION
            )
        )


def store_info(db):
    return dict(db.execute("SELECT * FROM store_metadata WHERE singleton = 1").fetchone())


def register_run(db, run_key, reference_build, source_path="", metadata=None):
    db.execute(
        "INSERT OR IGNORE INTO runs "
        "(run_key, source_path, reference_build, imported_at, metadata_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (run_key, source_path, reference_build, utc_now(), _json(metadata)),
    )
    row = db.execute(
        "SELECT id, reference_build FROM runs WHERE run_key = ?", (run_key,)
    ).fetchone()
    if row["reference_build"] != reference_build:
        raise ValueError("run {!r} is already registered with another reference build".format(run_key))
    return row["id"]


def register_subject(db, subject_key, metadata=None):
    db.execute(
        "INSERT OR IGNORE INTO subjects (subject_key, metadata_json) VALUES (?, ?)",
        (subject_key, _json(metadata)),
    )
    return _existing_id(db, "subjects", "subject_key", subject_key)


def register_sample(db, sample_key, display_name, subject_id=None, specimen_type="", metadata=None):
    db.execute(
        "INSERT OR IGNORE INTO samples "
        "(sample_key, subject_id, display_name, specimen_type, metadata_json) VALUES (?, ?, ?, ?, ?)",
        (sample_key, subject_id, display_name, specimen_type, _json(metadata)),
    )
    row = db.execute(
        "SELECT id, subject_id FROM samples WHERE sample_key = ?", (sample_key,)
    ).fetchone()
    if row["subject_id"] != subject_id:
        raise ValueError("sample {!r} is already associated with another subject".format(sample_key))
    return row["id"]


def register_analysis(db, analysis_key, run_id, sample_id, role="", pipeline=None, qc=None):
    db.execute(
        "INSERT OR IGNORE INTO analyses "
        "(analysis_key, run_id, sample_id, role, pipeline_json, qc_json) VALUES (?, ?, ?, ?, ?, ?)",
        (analysis_key, run_id, sample_id, role, _json(pipeline), _json(qc)),
    )
    row = db.execute(
        "SELECT id, run_id, sample_id FROM analyses WHERE analysis_key = ?", (analysis_key,)
    ).fetchone()
    if row["run_id"] != run_id or row["sample_id"] != sample_id:
        raise ValueError("analysis {!r} is already associated with another run or sample".format(analysis_key))
    return row["id"]


def get_or_create_variant(db, reference_build, chromosome, position, reference, alternate,
                          variant_type="", metadata=None):
    if int(position) <= 0 or not reference or not alternate:
        raise ValueError("a variant requires a positive position and non-empty REF/ALT")
    values = (reference_build, str(chromosome), int(position), reference.upper(), alternate.upper())
    db.execute(
        "INSERT OR IGNORE INTO variants "
        "(reference_build, chromosome, position, reference, alternate, variant_type, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        values + (variant_type, _json(metadata)),
    )
    row = db.execute(
        "SELECT id FROM variants WHERE reference_build = ? AND chromosome = ? AND position = ? "
        "AND reference = ? AND alternate = ?",
        values,
    ).fetchone()
    return row["id"]


def record_call(db, analysis_id, variant_id, caller="", genotype="", phased=False,
                zygosity="", depth=None, reference_depth=None, alternate_depth=None,
                allele_fraction=None, genotype_quality=None, quality=None,
                filter_status="", metadata=None):
    db.execute(
        "INSERT OR IGNORE INTO calls "
        "(analysis_id, variant_id, caller, genotype, phased, zygosity, depth, reference_depth, "
        "alternate_depth, allele_fraction, genotype_quality, quality, filter_status, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (analysis_id, variant_id, caller, genotype, int(bool(phased)), zygosity, depth,
         reference_depth, alternate_depth, allele_fraction, genotype_quality, quality,
         filter_status, _json(metadata)),
    )
    row = db.execute(
        "SELECT * FROM calls WHERE analysis_id = ? AND variant_id = ? AND caller = ?",
        (analysis_id, variant_id, caller),
    ).fetchone()
    expected = {
        "genotype": genotype, "phased": int(bool(phased)), "zygosity": zygosity,
        "depth": depth, "reference_depth": reference_depth, "alternate_depth": alternate_depth,
        "allele_fraction": allele_fraction, "genotype_quality": genotype_quality,
        "quality": quality, "filter_status": filter_status, "metadata_json": _json(metadata),
    }
    if any(row[key] != value for key, value in expected.items()):
        raise ValueError("conflicting duplicate call for analysis, variant, and caller")
    return row["id"]


def register_annotation_release(db, release_key, annotator, reference_build,
                                annotator_version="", resources=None):
    db.execute(
        "INSERT OR IGNORE INTO annotation_releases "
        "(release_key, annotator, annotator_version, reference_build, created_at, resources_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (release_key, annotator, annotator_version, reference_build, utc_now(), _json(resources)),
    )
    row = db.execute(
        "SELECT id, annotator, annotator_version, reference_build, resources_json "
        "FROM annotation_releases WHERE release_key = ?", (release_key,)
    ).fetchone()
    if row["reference_build"] != reference_build:
        raise ValueError("annotation release {!r} is registered for another build".format(release_key))
    if (row["annotator"], row["annotator_version"], row["resources_json"]) != (
            annotator, annotator_version, _json(resources)):
        raise ValueError("annotation release {!r} has conflicting provenance".format(release_key))
    return row["id"]


def record_annotation(db, variant_id, release_id, allele="", gene="", transcript="",
                      consequence="", impact="", hgvsc="", hgvsp="",
                      clinical_significance="", population_af=None, canonical=False,
                      metadata=None):
    db.execute(
        "INSERT OR IGNORE INTO annotations "
        "(variant_id, release_id, allele, gene, transcript, consequence, impact, hgvsc, hgvsp, "
        "clinical_significance, population_af, canonical, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (variant_id, release_id, allele, gene, transcript, consequence, impact, hgvsc, hgvsp,
         clinical_significance, population_af, int(bool(canonical)), _json(metadata)),
    )
    row = db.execute(
        "SELECT * FROM annotations WHERE variant_id = ? AND release_id = ? AND allele = ? "
        "AND transcript = ? AND consequence = ? AND hgvsc = ? AND hgvsp = ?",
        (variant_id, release_id, allele, transcript, consequence, hgvsc, hgvsp),
    ).fetchone()
    expected = {
        "gene": gene, "impact": impact, "clinical_significance": clinical_significance,
        "population_af": population_af, "canonical": int(bool(canonical)),
        "metadata_json": _json(metadata),
    }
    if any(row[key] != value for key, value in expected.items()):
        raise ValueError("conflicting annotation within one immutable release")
    return row["id"]
