"""Supervised v4.1.2 TSV import into the existing Gene-Phenotype database.

No Hail dependency, downloads, structural transcript cache or clinical rules.
The TSV is consumed as a stream and the previous data survive a failed import.
"""
import csv
import gzip
import hashlib
import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

RELEASE = "4.1.2"
SOURCE_URL = ("https://storage.googleapis.com/gcp-public-data--gnomad/release/4.1.2/"
              "constraint/gnomad.v4.1.2.constraint_metrics.tsv.bgz")
REQUIRED = {"gene", "gene_id", "transcript", "canonical", "constraint_flags", "gene_flags",
            "lof.pLI", "lof.oe_ci.upper_rank", "lof.oe_ci.upper_bin_decile"}
for _kind in ("lof", "mis", "syn"):
    REQUIRED.update(_kind + "." + field for field in ("obs", "exp", "oe", "oe_ci.lower", "oe_ci.upper"))

# Existing scalar columns keep the current mechanism adapter contract intact.
TABLE_SQL = """CREATE TABLE gnomad_constraints (
 gene_symbol TEXT NOT NULL COLLATE NOCASE, gene_id TEXT NOT NULL,
 transcript_id TEXT NOT NULL, available INTEGER NOT NULL,
 pli REAL, loeuf REAL, lof_oe REAL, lof_observed REAL, lof_expected REAL, lof_z REAL,
 missense_z REAL, missense_oe REAL, missense_observed REAL, missense_expected REAL,
 updated_at TEXT NOT NULL, source_url TEXT NOT NULL,
 release TEXT NOT NULL DEFAULT '', assembly TEXT NOT NULL DEFAULT 'GRCh38',
 canonical INTEGER, mane_select INTEGER, payload TEXT,
 PRIMARY KEY(gene_symbol, transcript_id, release))"""


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _database(database):
    from helper_variants.gene_phenotype import cache_path
    return Path(database or cache_path())


def _migrate(connection):
    columns = {row[1] for row in connection.execute("PRAGMA table_info(gnomad_constraints)")}
    if "release" in columns:
        return
    if not columns:
        raise ValueError("Initialize the Gene-Phenotype database through its existing workflow first")
    connection.execute("ALTER TABLE gnomad_constraints RENAME TO gnomad_constraints_legacy")
    connection.execute(TABLE_SQL)
    names = ",".join(row[1] for row in connection.execute("PRAGMA table_info(gnomad_constraints_legacy)"))
    connection.execute(f"INSERT INTO gnomad_constraints ({names}) SELECT {names} FROM gnomad_constraints_legacy")
    connection.execute("DROP TABLE gnomad_constraints_legacy")
    connection.execute("CREATE INDEX idx_gnomad_constraint_gene ON gnomad_constraints(gene_id,release)")


def _number(raw):
    if raw in (None, "", "NA", "NaN", "nan", "null"):
        return None
    if isinstance(raw, str) and raw.startswith("["):
        values = json.loads(raw)
        if not isinstance(values, list):
            raise ValueError("Invalid constraint downsampling array")
        return [_number(value) for value in values]
    number = float(raw)
    if not math.isfinite(number):
        raise ValueError("Constraint contains a nonfinite value")
    return number


def _boolean(raw):
    if raw in (None, "", "NA"):
        return None
    if str(raw).lower() not in ("true", "false"):
        raise ValueError("Invalid transcript canonical/MANE flag")
    return str(raw).lower() == "true"


def _flags(raw):
    if raw in (None, "", "NA"):
        return []
    flags = json.loads(raw)
    if not isinstance(flags, list) or any(not isinstance(f, str) for f in flags):
        raise ValueError("Invalid constraint flags")
    return flags


def _row(row):
    transcript = row["transcript"]
    if not re.fullmatch(r"(?:ENSG[0-9]+|[0-9]+)", row["gene_id"]) or not re.fullmatch(r"(?:ENST[0-9]+|[NX][MR]_[0-9]+)(?:\.[0-9]+)?", transcript) or not row["gene"]:
        raise ValueError("Constraint row requires qualified gene/transcript identifiers and symbol")
    version = row.get("transcript_version")
    if version and version != "NA":
        if version.startswith(transcript.split(".")[0] + "."):
            if not version.rsplit(".", 1)[1].isdigit() or ("." in transcript and version != transcript):
                raise ValueError("Transcript ID/version mismatch")
            transcript = version
        elif version.isdigit() and "." not in transcript:
            transcript += "." + version
        elif not version.isdigit() or transcript.rsplit(".", 1)[1] != version:
            raise ValueError("Transcript ID/version mismatch")
    payload = {"transcript_id": transcript, "gene_id": row["gene_id"], "gene_symbol": row["gene"],
               "canonical": _boolean(row["canonical"]), "mane_select": _boolean(row.get("mane_select")),
               "constraint_flags": _flags(row["constraint_flags"]), "gene_flags": _flags(row["gene_flags"])}
    # Statistical fields only. Gene/transcript structures belong to gene_struct.
    payload["metrics"] = {key: _number(value) for key, value in row.items()
                          if key.startswith(("lof.", "mis.", "syn.", "lof_hc_lc.", "gene_quality_metrics."))}
    metrics = payload["metrics"]
    for kind in ("lof", "mis", "syn"):
        payload[kind] = {key: metrics.get(kind + "." + key) for key in
                        ("obs", "exp", "oe", "z_score", "oe_ci.lower", "oe_ci.upper")}
    payload.update(loeuf=metrics.get("lof.oe_ci.upper"), pli=metrics.get("lof.pLI"),
                   lof_oe=metrics.get("lof.oe"), lof_observed=metrics.get("lof.obs"),
                   lof_expected=metrics.get("lof.exp"), lof_z=metrics.get("lof.z_score"),
                   missense_z=metrics.get("mis.z_score"), missense_oe=metrics.get("mis.oe"),
                   missense_observed=metrics.get("mis.obs"), missense_expected=metrics.get("mis.exp"),
                   rank=metrics.get("lof.oe_ci.upper_rank"), decile=metrics.get("lof.oe_ci.upper_bin_decile"))
    if payload["decile"] is not None and (payload["decile"] % 1 or not 0 <= payload["decile"] <= 9):
        raise ValueError("Invalid v4.1.2 decile")
    return payload


def import_tsv(path, database=None, *, confirmed=False):
    """Explicit local import only; release qualification includes URL and SHA256."""
    if not confirmed:
        raise ValueError("Persistent constraint import requires explicit confirmation")
    path, database = Path(path), _database(database)
    if not database.is_file():
        raise ValueError("Gene-Phenotype database is not initialized")
    before = path.stat()
    sha = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            sha.update(block)
    count, updated = 0, _now()
    opener = gzip.open if path.suffix in (".gz", ".bgz") else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as stream, sqlite3.connect(database) as connection:
        reader = csv.DictReader(stream, delimiter="\t")
        if not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError("Not the verified gnomAD v4.1.2 constraint TSV schema")
        # Explicit transaction also covers DDL and deletion on parser errors.
        connection.execute("BEGIN IMMEDIATE")
        _migrate(connection)
        connection.execute("DELETE FROM gnomad_constraints WHERE release=?", (RELEASE,))
        columns = [row[1] for row in connection.execute("PRAGMA table_info(gnomad_constraints)")]
        sql = "INSERT INTO gnomad_constraints (" + ",".join(columns) + ") VALUES (" + ",".join("?" for _ in columns) + ")"
        batch = []
        for raw in reader:
            payload = _row(raw)
            row = {**payload, "available": int(any(payload[k] is not None for k in ("loeuf", "pli", "missense_oe"))),
                   "updated_at": updated, "source_url": SOURCE_URL, "release": RELEASE, "assembly": "GRCh38",
                   "payload": json.dumps(payload, separators=(",", ":"), allow_nan=False)}
            batch.append(tuple(row.get(key) for key in columns))
            count += 1
            if len(batch) == 1000:
                connection.executemany(sql, batch)
                batch.clear()
        if batch:
            connection.executemany(sql, batch)
        if not count:
            raise ValueError("Empty constraint dataset")
        after = path.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise ValueError("Constraint file changed during import")
        manifest = dict(release=RELEASE, assembly="GRCh38", source_url=SOURCE_URL,
                        sha256=sha.hexdigest(), acquired_at=updated, record_count=count,
                        access_mode="supervised_local_tsv", release_basis="operator_selected_official_release",
                        parser_version="gnomad-constraint-1")
        connection.execute("INSERT INTO metadata(key,value) VALUES ('gnomad_constraint_manifest',?) "
                           "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(manifest),))
    return manifest


def status(database=None):
    database = _database(database)
    result = dict(release=None, target_release=RELEASE, assembly="GRCh38", record_count=0,
                  access_mode="supervised_local_tsv", source_url=SOURCE_URL, status="missing")
    if database.is_file():
        try:
            with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
                row = connection.execute("SELECT value FROM metadata WHERE key='gnomad_constraint_manifest'").fetchone()
                if row:
                    result.update(json.loads(row[0]), status="ready")
        except (sqlite3.Error, ValueError) as exc:
            result.update(status="invalid", error=str(exc))
    return result


def decode(row):
    result = dict(row)
    raw = result.pop("payload", None)
    if raw:
        result.update(json.loads(raw))
    result["release"] = result.get("release") or None
    return result


def transcripts(connection, gene_symbol):
    try:
        rows = connection.execute("SELECT * FROM gnomad_constraints WHERE gene_symbol=? COLLATE NOCASE", (gene_symbol,)).fetchall()
    except sqlite3.OperationalError:
        return []
    records = [decode(row) for row in rows]
    pinned = [row for row in records if row.get("release") == RELEASE]
    return sorted(pinned or records, key=lambda row: row["transcript_id"])


def preserve_import(previous, connection):
    """Preserve the supervised component across the existing full G2P rebuild."""
    if not Path(previous).is_file():
        return
    with sqlite3.connect(Path(previous).resolve().as_uri() + "?mode=ro", uri=True) as old:
        old.row_factory = sqlite3.Row
        columns = [row[1] for row in old.execute("PRAGMA table_info(gnomad_constraints)")]
        if not columns:
            return
        if "release" in columns:
            _migrate(connection)
        sql = "INSERT INTO gnomad_constraints (" + ",".join(columns) + ") VALUES (" + ",".join("?" for _ in columns) + ")"
        connection.executemany(sql, old.execute("SELECT * FROM gnomad_constraints"))
        row = old.execute("SELECT value FROM metadata WHERE key='gnomad_constraint_manifest'").fetchone()
        if row:
            connection.execute("INSERT INTO metadata VALUES ('gnomad_constraint_manifest',?)", (row[0],))
