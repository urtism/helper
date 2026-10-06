"""Cached gene-disease assertions for the standalone variant browser."""
import csv
import io
import json
import os
import sqlite3
import tempfile
import threading
import time
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from itertools import chain
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree


GENCC_DOWNLOAD_URL = (
    "https://thegencc.org/download/action/submissions-export-csv?format=new"
)
HPO_ANNOTATIONS_URL = (
    "https://github.com/obophenotype/human-phenotype-ontology/"
    "releases/latest/download/phenotype.hpoa"
)
HPO_TERMS_URL = (
    "https://github.com/obophenotype/human-phenotype-ontology/"
    "releases/latest/download/hp.obo"
)
G2P_DOWNLOAD_URL = (
    "https://www.ebi.ac.uk/gene2phenotype/api/panel/all/download/"
)
CLINGEN_DOSAGE_URL = "https://ftp.clinicalgenome.org/ClinGen_gene_curation_list_GRCh38.tsv"
ORPHADATA_URL = "https://www.orphadata.com/data/xml/en_product1.xml"
GNOMAD_API_URL = "https://gnomad.broadinstitute.org/api"
GNOMAD_CONSTRAINT_QUERY = """
query GeneConstraint($gene_symbol: String!, $reference_genome: ReferenceGenomeId!) {
  gene(gene_symbol: $gene_symbol, reference_genome: $reference_genome) {
    gene_id
    symbol
    canonical_transcript_id
    gnomad_constraint {
      exp_lof
      obs_lof
      oe_lof
      oe_lof_lower
      oe_lof_upper
      pLI
      lof_z
      exp_mis
      obs_mis
      oe_mis
      oe_mis_lower
      oe_mis_upper
      mis_z
    }
  }
}
"""
SCHEMA_VERSION = "4"
CACHE_MAX_AGE = timedelta(days=7)
CONSTRAINT_MAX_AGE = timedelta(days=30)
_refresh_lock = threading.Lock()
_refreshing = False
_constraint_lock = threading.Lock()
_constraints_refreshing = set()

_SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE assertions (
    sgc_id TEXT PRIMARY KEY,
    version_number INTEGER NOT NULL,
    gene_curie TEXT NOT NULL,
    gene_symbol TEXT NOT NULL COLLATE NOCASE,
    disease_curie TEXT NOT NULL,
    disease_title TEXT NOT NULL,
    disease_original_curie TEXT NOT NULL,
    disease_original_title TEXT NOT NULL,
    classification_title TEXT NOT NULL,
    moi_curie TEXT NOT NULL,
    moi_title TEXT NOT NULL,
    submitter_title TEXT NOT NULL,
    submitted_as_date TEXT NOT NULL,
    public_report_url TEXT NOT NULL,
    pmids TEXT NOT NULL,
    assertion_criteria_url TEXT NOT NULL,
    submitted_run_date TEXT NOT NULL
);
CREATE INDEX idx_assertions_gene_curie ON assertions(gene_curie);
CREATE INDEX idx_assertions_gene_symbol ON assertions(gene_symbol COLLATE NOCASE);
CREATE TABLE hpo_features (
    disease_curie TEXT NOT NULL,
    disease_name TEXT NOT NULL,
    qualifier TEXT NOT NULL,
    hpo_id TEXT NOT NULL,
    hpo_name TEXT NOT NULL,
    reference TEXT NOT NULL,
    evidence TEXT NOT NULL,
    onset TEXT NOT NULL,
    frequency TEXT NOT NULL,
    sex TEXT NOT NULL,
    modifier TEXT NOT NULL,
    aspect TEXT NOT NULL,
    biocuration TEXT NOT NULL,
    PRIMARY KEY (disease_curie, hpo_id, qualifier, reference)
);
CREATE INDEX idx_hpo_features_disease ON hpo_features(disease_curie);
CREATE TABLE g2p_records (
    g2p_id TEXT PRIMARY KEY,
    gene_curie TEXT NOT NULL,
    gene_symbol TEXT NOT NULL COLLATE NOCASE,
    disease_curie TEXT NOT NULL,
    disease_mim TEXT NOT NULL,
    disease_name TEXT NOT NULL,
    allelic_requirement TEXT NOT NULL,
    confidence TEXT NOT NULL,
    mechanism TEXT NOT NULL,
    mechanism_category TEXT NOT NULL,
    mechanism_support TEXT NOT NULL,
    variant_consequence TEXT NOT NULL,
    publications TEXT NOT NULL,
    last_reviewed TEXT NOT NULL,
    record_url TEXT NOT NULL
);
CREATE INDEX idx_g2p_gene_symbol ON g2p_records(gene_symbol COLLATE NOCASE);
CREATE INDEX idx_g2p_gene_curie ON g2p_records(gene_curie);
CREATE TABLE clingen_dosage (
    gene_symbol TEXT PRIMARY KEY COLLATE NOCASE,
    gene_id TEXT NOT NULL,
    cytoband TEXT NOT NULL,
    genomic_location TEXT NOT NULL,
    hi_score TEXT NOT NULL,
    hi_description TEXT NOT NULL,
    hi_pmids TEXT NOT NULL,
    hi_disease_id TEXT NOT NULL,
    ts_score TEXT NOT NULL,
    ts_description TEXT NOT NULL,
    ts_pmids TEXT NOT NULL,
    ts_disease_id TEXT NOT NULL,
    last_evaluated TEXT NOT NULL,
    report_url TEXT NOT NULL
);
CREATE TABLE gnomad_constraints (
    gene_symbol TEXT PRIMARY KEY COLLATE NOCASE,
    gene_id TEXT NOT NULL,
    transcript_id TEXT NOT NULL,
    available INTEGER NOT NULL,
    pli REAL,
    loeuf REAL,
    lof_oe REAL,
    lof_observed REAL,
    lof_expected REAL,
    lof_z REAL,
    missense_z REAL,
    missense_oe REAL,
    missense_observed REAL,
    missense_expected REAL,
    updated_at TEXT NOT NULL,
    source_url TEXT NOT NULL
);
CREATE TABLE orpha_aliases (
    identifier TEXT NOT NULL COLLATE NOCASE,
    orpha_id TEXT NOT NULL,
    mapping_relation TEXT NOT NULL,
    PRIMARY KEY (identifier, orpha_id)
);
CREATE INDEX idx_orpha_alias_identifier ON orpha_aliases(identifier COLLATE NOCASE);
CREATE TABLE disease_codes (
    orpha_id TEXT NOT NULL,
    disease_name TEXT NOT NULL,
    system TEXT NOT NULL,
    code TEXT NOT NULL,
    mapping_relation TEXT NOT NULL,
    icd_relation TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_uri TEXT NOT NULL,
    PRIMARY KEY (orpha_id, system, code)
);
CREATE INDEX idx_disease_codes_orpha ON disease_codes(orpha_id);
"""

_INSERT = """
INSERT INTO assertions (
    sgc_id, version_number, gene_curie, gene_symbol, disease_curie,
    disease_title, disease_original_curie, disease_original_title,
    classification_title, moi_curie, moi_title, submitter_title,
    submitted_as_date, public_report_url, pmids, assertion_criteria_url,
    submitted_run_date
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(sgc_id) DO UPDATE SET
    version_number=excluded.version_number,
    gene_curie=excluded.gene_curie,
    gene_symbol=excluded.gene_symbol,
    disease_curie=excluded.disease_curie,
    disease_title=excluded.disease_title,
    disease_original_curie=excluded.disease_original_curie,
    disease_original_title=excluded.disease_original_title,
    classification_title=excluded.classification_title,
    moi_curie=excluded.moi_curie,
    moi_title=excluded.moi_title,
    submitter_title=excluded.submitter_title,
    submitted_as_date=excluded.submitted_as_date,
    public_report_url=excluded.public_report_url,
    pmids=excluded.pmids,
    assertion_criteria_url=excluded.assertion_criteria_url,
    submitted_run_date=excluded.submitted_run_date
WHERE excluded.version_number > assertions.version_number
"""

_INSERT_HPO = """
INSERT OR REPLACE INTO hpo_features (
    disease_curie, disease_name, qualifier, hpo_id, hpo_name, reference,
    evidence, onset, frequency, sex, modifier, aspect, biocuration
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERT_G2P = """
INSERT INTO g2p_records (
    g2p_id, gene_curie, gene_symbol, disease_curie, disease_mim,
    disease_name, allelic_requirement, confidence, mechanism,
    mechanism_category, mechanism_support, variant_consequence,
    publications, last_reviewed, record_url
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(g2p_id) DO UPDATE SET
    gene_curie=excluded.gene_curie,
    gene_symbol=excluded.gene_symbol,
    disease_curie=excluded.disease_curie,
    disease_mim=excluded.disease_mim,
    disease_name=excluded.disease_name,
    allelic_requirement=excluded.allelic_requirement,
    confidence=excluded.confidence,
    mechanism=excluded.mechanism,
    mechanism_category=excluded.mechanism_category,
    mechanism_support=excluded.mechanism_support,
    variant_consequence=excluded.variant_consequence,
    publications=excluded.publications,
    last_reviewed=excluded.last_reviewed,
    record_url=excluded.record_url
"""

_INSERT_CLINGEN_DOSAGE = """
INSERT OR REPLACE INTO clingen_dosage (
    gene_symbol, gene_id, cytoband, genomic_location, hi_score,
    hi_description, hi_pmids, hi_disease_id, ts_score, ts_description,
    ts_pmids, ts_disease_id, last_evaluated, report_url
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERT_GNOMAD_CONSTRAINT = """
INSERT OR REPLACE INTO gnomad_constraints (
    gene_symbol, gene_id, transcript_id, available, pli, loeuf, lof_oe,
    lof_observed, lof_expected, lof_z, missense_z, missense_oe,
    missense_observed, missense_expected, updated_at, source_url
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERT_ORPHA_ALIAS = """
INSERT OR REPLACE INTO orpha_aliases (
    identifier, orpha_id, mapping_relation
) VALUES (?, ?, ?)
"""

_INSERT_DISEASE_CODE = """
INSERT OR REPLACE INTO disease_codes (
    orpha_id, disease_name, system, code, mapping_relation, icd_relation,
    validation_status, source_url, source_uri
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_CLASSIFICATION_RANK = {
    "definitive": 0, "strong": 1, "moderate": 2, "supportive": 3,
    "limited": 4, "disputed evidence": 5, "disputed": 5,
    "refuted evidence": 6, "refuted": 6, "animal model only": 7,
    "no known disease relationship": 8,
}
_G2P_ACCEPTED_CONFIDENCE = {"definitive", "strong", "moderate", "confirmed", "probable"}


def cache_path():
    configured = os.environ.get("HELPER_GENE_PHENOTYPE_DB", "").strip()
    if configured:
        return Path(configured).expanduser()
    data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    root = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return root / "helper_variants" / "gene_phenotype.sqlite3"


def begin_refresh():
    global _refreshing
    with _refresh_lock:
        if _refreshing:
            return False
        _refreshing = True
        return True


def finish_refresh():
    global _refreshing
    with _refresh_lock:
        _refreshing = False


def is_refreshing():
    with _refresh_lock:
        return _refreshing


def begin_constraint_refresh(gene_symbol):
    gene_symbol = str(gene_symbol or "").strip().upper()
    if not gene_symbol:
        return False
    with _constraint_lock:
        if gene_symbol in _constraints_refreshing:
            return False
        _constraints_refreshing.add(gene_symbol)
        return True


def finish_constraint_refresh(gene_symbol):
    with _constraint_lock:
        _constraints_refreshing.discard(str(gene_symbol or "").strip().upper())


def constraint_is_refreshing(gene_symbol):
    with _constraint_lock:
        return str(gene_symbol or "").strip().upper() in _constraints_refreshing


def cache_status(database=None):
    database = Path(database or cache_path())
    if not database.is_file():
        return {"status": "missing", "refreshing": is_refreshing(), "database": str(database)}
    try:
        with sqlite3.connect(str(database)) as connection:
            metadata = dict(connection.execute("SELECT key, value FROM metadata"))
            row_count = connection.execute("SELECT COUNT(*) FROM assertions").fetchone()[0]
            hpo_row_count = _table_count(connection, "hpo_features")
            g2p_row_count = _table_count(connection, "g2p_records")
            dosage_row_count = _table_count(connection, "clingen_dosage")
            constraint_row_count = _table_count(connection, "gnomad_constraints")
            disease_code_count = _table_count(connection, "disease_codes")
    except sqlite3.Error as exc:
        return {
            "status": "invalid", "refreshing": is_refreshing(),
            "database": str(database), "error": str(exc),
        }
    updated_at = metadata.get("updated_at", "")
    stale = True
    try:
        updated = datetime.strptime(updated_at, "%Y-%m-%dT%H:%M:%SZ")
        stale = datetime.now(timezone.utc).replace(tzinfo=None) - updated > CACHE_MAX_AGE
    except ValueError:
        pass
    if metadata.get("schema_version") != SCHEMA_VERSION:
        stale = True
    return {
        "status": "ready", "refreshing": is_refreshing(), "stale": stale,
        "database": str(database), "updated_at": updated_at,
        "schema_version": metadata.get("schema_version", ""),
        "source": metadata.get("source", "GenCC"),
        "source_url": metadata.get("source_url", GENCC_DOWNLOAD_URL),
        "hpo_source_url": metadata.get("hpo_source_url", ""),
        "g2p_source_url": metadata.get("g2p_source_url", ""),
        "clingen_dosage_source_url": metadata.get("clingen_dosage_source_url", ""),
        "orphadata_source_url": metadata.get("orphadata_source_url", ""),
        "etag": metadata.get("etag", ""), "last_modified": metadata.get("last_modified", ""),
        "row_count": row_count, "hpo_row_count": hpo_row_count,
        "g2p_row_count": g2p_row_count, "dosage_row_count": dosage_row_count,
        "constraint_row_count": constraint_row_count,
        "disease_code_count": disease_code_count,
    }


def _table_count(connection, table):
    try:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def refresh_cache(database=None, source_url=None, hpo_source_url=None,
                  hpo_terms_url=None, g2p_source_url=None,
                  clingen_dosage_url=None, orphadata_url=None, timeout=90):
    database = Path(database or cache_path())
    source_url = source_url or os.environ.get("HELPER_GENCC_URL", GENCC_DOWNLOAD_URL)
    hpo_source_url = hpo_source_url or os.environ.get(
        "HELPER_HPOA_URL", HPO_ANNOTATIONS_URL
    )
    hpo_terms_url = hpo_terms_url or os.environ.get("HELPER_HPO_TERMS_URL", HPO_TERMS_URL)
    g2p_source_url = g2p_source_url or os.environ.get("HELPER_G2P_URL", G2P_DOWNLOAD_URL)
    clingen_dosage_url = clingen_dosage_url or os.environ.get(
        "HELPER_CLINGEN_DOSAGE_URL", CLINGEN_DOSAGE_URL
    )
    orphadata_url = orphadata_url or os.environ.get(
        "HELPER_ORPHADATA_URL", ORPHADATA_URL
    )
    headers = {"User-Agent": "HelperVariantBrowser/0.1"}
    with ExitStack() as stack:
        response = stack.enter_context(_open_source(source_url, headers, timeout))
        hpo_response = stack.enter_context(
            _open_source(hpo_source_url, headers, timeout)
        )
        terms_response = stack.enter_context(
            _open_source(hpo_terms_url, headers, timeout)
        )
        g2p_response = stack.enter_context(
            _open_source(g2p_source_url, headers, timeout)
        )
        dosage_response = stack.enter_context(
            _open_source(clingen_dosage_url, headers, timeout)
        )
        orphadata_response = stack.enter_context(
            _open_source(orphadata_url, headers, timeout)
        )
        stream = io.TextIOWrapper(response, encoding="utf-8-sig", newline="")
        hpo_stream = io.TextIOWrapper(hpo_response, encoding="utf-8-sig", newline="")
        terms_stream = io.TextIOWrapper(terms_response, encoding="utf-8", newline="")
        g2p_stream = io.TextIOWrapper(g2p_response, encoding="utf-8-sig", newline="")
        dosage_stream = io.TextIOWrapper(dosage_response, encoding="utf-8-sig", newline="")
        return build_cache(
            stream, database, source_url=source_url, hpo_stream=hpo_stream,
            hpo_terms_stream=terms_stream, hpo_source_url=hpo_source_url,
            g2p_stream=g2p_stream, g2p_source_url=g2p_source_url,
            dosage_stream=dosage_stream, clingen_dosage_url=clingen_dosage_url,
            orphadata_stream=orphadata_response, orphadata_url=orphadata_url,
            etag=response.headers.get("ETag", ""),
            last_modified=response.headers.get("Last-Modified", ""),
        )


def _open_source(url, headers, timeout, retries=3):
    return _open_request(Request(url, headers=headers), timeout, retries)


def _open_request(request, timeout, retries=3):
    retryable_statuses = {429, 500, 502, 503, 504}
    for attempt in range(retries):
        try:
            return urlopen(request, timeout=timeout)
        except HTTPError as exc:
            if exc.code not in retryable_statuses or attempt == retries - 1:
                raise
            retry_after = exc.headers.get("Retry-After", "")
            delay = int(retry_after) if str(retry_after).isdigit() else 2 ** attempt
            time.sleep(min(delay, 10))
        except URLError:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Cannot retrieve knowledge source: {request.full_url}")


def refresh_gnomad_constraint(gene_symbol, database=None, timeout=30):
    gene_symbol = str(gene_symbol or "").strip().upper()
    if not gene_symbol:
        raise ValueError("A gene symbol is required for gnomAD constraint retrieval")
    database = Path(database or cache_path())
    if cache_status(database).get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("The gene-phenotype cache must be refreshed first")
    payload = json.dumps({
        "query": GNOMAD_CONSTRAINT_QUERY,
        "variables": {"gene_symbol": gene_symbol, "reference_genome": "GRCh38"},
    }).encode("utf-8")
    request = Request(
        GNOMAD_API_URL, data=payload, method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "HelperVariantBrowser/0.1",
        },
    )
    with _open_request(request, timeout) as response:
        document = json.load(response)
    if document.get("errors"):
        message = "; ".join(
            str(error.get("message", error)) for error in document["errors"]
        )
        raise RuntimeError(f"gnomAD GraphQL error: {message}")
    gene = (document.get("data") or {}).get("gene") or {}
    constraint = gene.get("gnomad_constraint") or {}
    available = bool(gene and constraint)
    gene_id = str(gene.get("gene_id") or "")
    source_url = (
        f"https://gnomad.broadinstitute.org/gene/{gene_id}?dataset=gnomad_r4"
        if gene_id else "https://gnomad.broadinstitute.org/"
    )
    values = (
        gene_symbol, gene_id, str(gene.get("canonical_transcript_id") or ""),
        int(available), _number_or_none(constraint.get("pLI")),
        _number_or_none(constraint.get("oe_lof_upper")),
        _number_or_none(constraint.get("oe_lof")),
        _number_or_none(constraint.get("obs_lof")),
        _number_or_none(constraint.get("exp_lof")),
        _number_or_none(constraint.get("lof_z")),
        _number_or_none(constraint.get("mis_z")),
        _number_or_none(constraint.get("oe_mis")),
        _number_or_none(constraint.get("obs_mis")),
        _number_or_none(constraint.get("exp_mis")),
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), source_url,
    )
    with sqlite3.connect(str(database)) as connection:
        connection.execute(_INSERT_GNOMAD_CONSTRAINT, values)
        connection.commit()
    return available


def _number_or_none(value):
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def build_cache(csv_stream, database=None, source_url=GENCC_DOWNLOAD_URL,
                etag="", last_modified="", hpo_stream=None,
                hpo_terms_stream=None, hpo_source_url=HPO_ANNOTATIONS_URL,
                g2p_stream=None, g2p_source_url=G2P_DOWNLOAD_URL,
                dosage_stream=None, clingen_dosage_url=CLINGEN_DOSAGE_URL,
                orphadata_stream=None, orphadata_url=ORPHADATA_URL):
    database = Path(database or cache_path())
    database.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="gene-phenotype-", suffix=".sqlite3", dir=str(database.parent)
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    count = 0
    try:
        with sqlite3.connect(str(temporary)) as connection:
            connection.executescript(_SCHEMA)
            batch = []
            reader = csv.DictReader(csv_stream)
            required = {"sgc_id", "version_number", "gene_curie", "gene_symbol", "disease_title"}
            if not required.issubset(set(reader.fieldnames or [])):
                raise ValueError("GenCC download does not contain the expected columns")
            for row in reader:
                if not row.get("sgc_id") or not row.get("gene_symbol"):
                    continue
                batch.append(_assertion_values(row))
                if len(batch) >= 1000:
                    connection.executemany(_INSERT, batch)
                    count += len(batch)
                    batch = []
            if batch:
                connection.executemany(_INSERT, batch)
                count += len(batch)
            hpo_count = _import_hpo_features(connection, hpo_stream, hpo_terms_stream)
            g2p_count = _import_g2p_records(connection, g2p_stream)
            dosage_count = _import_clingen_dosage(connection, dosage_stream)
            orpha_alias_count, disease_code_count = _import_orphadata(
                connection, orphadata_stream
            )
            metadata = {
                "schema_version": SCHEMA_VERSION,
                "source": (
                    "GenCC + HPO + G2P + ClinGen Dosage + Orphadata"
                    if hpo_stream or g2p_stream or dosage_stream or orphadata_stream
                    else "GenCC"
                ),
                "source_url": source_url,
                "hpo_source_url": hpo_source_url if hpo_stream else "",
                "g2p_source_url": g2p_source_url if g2p_stream else "",
                "clingen_dosage_source_url": clingen_dosage_url if dosage_stream else "",
                "orphadata_source_url": orphadata_url if orphadata_stream else "",
                "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "etag": etag, "last_modified": last_modified,
            }
            connection.executemany(
                "INSERT INTO metadata (key, value) VALUES (?, ?)", metadata.items()
            )
            connection.commit()
        os.replace(str(temporary), str(database))
    finally:
        if temporary.exists():
            temporary.unlink()
    status = cache_status(database)
    status["rows_processed"] = count
    status["hpo_rows_processed"] = hpo_count
    status["g2p_rows_processed"] = g2p_count
    status["dosage_rows_processed"] = dosage_count
    status["orpha_aliases_processed"] = orpha_alias_count
    status["disease_codes_processed"] = disease_code_count
    return status


def _import_hpo_features(connection, hpo_stream, terms_stream=None):
    if hpo_stream is None:
        return 0
    term_names = _read_hpo_term_names(terms_stream) if terms_stream is not None else {}
    reader = _comment_aware_dict_reader(
        hpo_stream, delimiter="\t", header_hints=("database id", "hpo id")
    )
    required = {"database id", "disease name", "hpo id"}
    fields = {_normal_field(field) for field in (reader.fieldnames or [])}
    if not required.issubset(fields):
        raise ValueError("HPO annotations do not contain the expected columns")
    count = 0
    batch = []
    for original in reader:
        row = {_normal_field(key): str(value or "").strip() for key, value in original.items()}
        disease_id = _normalize_disease_id(row.get("database id", ""))
        hpo_id = row.get("hpo id", "")
        aspect = row.get("aspect", "")
        if not disease_id or not hpo_id or (aspect and aspect != "P"):
            continue
        batch.append((
            disease_id, row.get("disease name", ""), row.get("qualifier", ""),
            hpo_id, term_names.get(hpo_id, ""), row.get("reference", ""),
            row.get("evidence", ""), row.get("onset", ""), row.get("frequency", ""),
            row.get("sex", ""), row.get("modifier", ""), aspect,
            row.get("biocuration", ""),
        ))
        if len(batch) >= 2000:
            connection.executemany(_INSERT_HPO, batch)
            count += len(batch)
            batch = []
    if batch:
        connection.executemany(_INSERT_HPO, batch)
        count += len(batch)
    return count


def _read_hpo_term_names(stream):
    terms = {}
    current_id = ""
    current_name = ""
    obsolete = False

    def commit():
        if current_id and current_name and not obsolete:
            terms[current_id] = current_name

    for raw_line in stream:
        line = raw_line.rstrip("\r\n")
        if line == "[Term]":
            commit()
            current_id = ""
            current_name = ""
            obsolete = False
        elif line.startswith("id: HP:"):
            current_id = line[4:].strip()
        elif line.startswith("name: "):
            current_name = line[6:].strip()
        elif line == "is_obsolete: true":
            obsolete = True
    commit()
    return terms


def _import_g2p_records(connection, g2p_stream):
    if g2p_stream is None:
        return 0
    reader = _comment_aware_dict_reader(
        g2p_stream, header_hints=("gene symbol", "molecular mechanism")
    )
    fields = {_normal_field(field) for field in (reader.fieldnames or [])}
    if "gene symbol" not in fields or "molecular mechanism" not in fields:
        raise ValueError("G2P download does not contain the expected columns")
    count = 0
    batch = []
    for original in reader:
        row = {_normal_field(key): str(value or "").strip() for key, value in original.items()}
        gene_symbol = _row_value(row, "gene symbol", "gene")
        g2p_id = _row_value(row, "g2p id", "stable id", "stable identifier")
        if not gene_symbol or not g2p_id:
            continue
        hgnc_id = _row_value(row, "hgnc id", "gene hgnc id", "hgnc")
        disease_mim = _normalize_disease_id(_row_value(
            row, "disease mim", "disease omim", "omim disease"
        ))
        disease_curie = _normalize_disease_id(_row_value(
            row, "disease mondo", "mondo id", "disease mondo id"
        ))
        batch.append((
            g2p_id, _normalize_hgnc(hgnc_id), gene_symbol, disease_curie,
            disease_mim, _row_value(row, "disease name", "disease"),
            _row_value(row, "allelic requirement", "genotype"),
            _row_value(row, "confidence"), _row_value(row, "molecular mechanism", "mechanism"),
            _row_value(row, "molecular mechanism categorisation", "mechanism categorisation"),
            _row_value(row, "molecular mechanism support", "mechanism support"),
            _row_value(row, "variant consequence", "variant consequences"),
            _row_value(row, "publications", "publication"),
            _row_value(row, "date of last review", "last reviewed", "last updated"),
            f"https://www.ebi.ac.uk/gene2phenotype/lgd/{g2p_id}",
        ))
        if len(batch) >= 1000:
            connection.executemany(_INSERT_G2P, batch)
            count += len(batch)
            batch = []
    if batch:
        connection.executemany(_INSERT_G2P, batch)
        count += len(batch)
    return count


def _import_clingen_dosage(connection, dosage_stream):
    if dosage_stream is None:
        return 0
    reader = _comment_aware_dict_reader(
        dosage_stream, delimiter="\t",
        header_hints=("gene symbol", "haploinsufficiency score", "triplosensitivity score"),
    )
    fields = {_normal_field(field) for field in (reader.fieldnames or [])}
    required = {"gene symbol", "haploinsufficiency score", "triplosensitivity score"}
    if not required.issubset(fields):
        raise ValueError("ClinGen dosage download does not contain the expected columns")
    count = 0
    batch = []
    for original in reader:
        row = {_normal_field(key): str(value or "").strip() for key, value in original.items()}
        gene_symbol = row.get("gene symbol", "")
        if not gene_symbol:
            continue
        hi_pmids = _prefixed_values(row, "haploinsufficiency pmid")
        ts_pmids = _prefixed_values(row, "triplosensitivity pmid")
        batch.append((
            gene_symbol, row.get("gene id", ""), row.get("cytoband", ""),
            row.get("genomic location", ""), row.get("haploinsufficiency score", ""),
            row.get("haploinsufficiency description", ""), ";".join(hi_pmids),
            _normalize_disease_id(row.get("haploinsufficiency disease id", "")),
            row.get("triplosensitivity score", ""),
            row.get("triplosensitivity description", ""), ";".join(ts_pmids),
            _normalize_disease_id(row.get("triplosensitivity disease id", "")),
            row.get("date last evaluated", ""),
            f"https://search.clinicalgenome.org/kb/gene-dosage/{gene_symbol}",
        ))
        if len(batch) >= 1000:
            connection.executemany(_INSERT_CLINGEN_DOSAGE, batch)
            count += len(batch)
            batch = []
    if batch:
        connection.executemany(_INSERT_CLINGEN_DOSAGE, batch)
        count += len(batch)
    return count


def _import_orphadata(connection, orphadata_stream):
    if orphadata_stream is None:
        return 0, 0
    alias_count = 0
    code_count = 0
    alias_batch = []
    code_batch = []
    for _event, disorder in ElementTree.iterparse(orphadata_stream, events=("end",)):
        if _xml_local_name(disorder.tag) != "Disorder":
            continue
        orpha_code = _xml_text(disorder, "./OrphaCode")
        if not orpha_code:
            disorder.clear()
            continue
        orpha_id = f"ORPHA:{orpha_code}"
        disease_name = _xml_text(disorder, "./Name")
        aliases = [(orpha_id, "Exact ORPHA identifier")]
        icd_records = []
        for reference in disorder.findall("./ExternalReferenceList/ExternalReference"):
            source = _xml_text(reference, "./Source").upper()
            code = _xml_text(reference, "./Reference")
            relation = _xml_text(reference, "./DisorderMappingRelation/Name")
            if not source or not code:
                continue
            if source in {"MONDO", "OMIM"} and _is_exact_mapping(relation):
                aliases.append((_normalize_disease_id(f"{source}:{code}"), relation))
            if source not in {"ICD-10", "ICD-11"}:
                continue
            source_url = _xml_text(reference, "./DisorderMappingICDRefUrl")
            if source == "ICD-10" and not source_url:
                source_url = f"https://icd.who.int/browse10/2019/en#/{code}"
            icd_records.append((
                orpha_id, disease_name, source, code, relation,
                _xml_text(reference, "./DisorderMappingICDRelation/Name"),
                _xml_text(reference, "./DisorderMappingValidationStatus/Name"),
                source_url, _xml_text(reference, "./DisorderMappingICDRefUri"),
            ))
        alias_batch.extend(
            (identifier, orpha_id, relation) for identifier, relation in aliases
        )
        code_batch.extend(icd_records)
        if len(alias_batch) >= 2000:
            connection.executemany(_INSERT_ORPHA_ALIAS, alias_batch)
            alias_count += len(alias_batch)
            alias_batch = []
        if len(code_batch) >= 2000:
            connection.executemany(_INSERT_DISEASE_CODE, code_batch)
            code_count += len(code_batch)
            code_batch = []
        disorder.clear()
    if alias_batch:
        connection.executemany(_INSERT_ORPHA_ALIAS, alias_batch)
        alias_count += len(alias_batch)
    if code_batch:
        connection.executemany(_INSERT_DISEASE_CODE, code_batch)
        code_count += len(code_batch)
    return alias_count, code_count


def _xml_text(element, path):
    child = element.find(path)
    return str(child.text or "").strip() if child is not None else ""


def _xml_local_name(tag):
    return str(tag).rsplit("}", 1)[-1]


def _is_exact_mapping(relation):
    relation = str(relation or "").strip().lower()
    return relation == "e" or relation.startswith("e (") or "exact mapping" in relation


def _prefixed_values(row, prefix):
    return [
        value for key, value in sorted(row.items())
        if key.startswith(prefix) and value
    ]


def _comment_aware_dict_reader(stream, delimiter=",", header_hints=()):
    iterator = iter(stream)
    header = None
    for raw_line in iterator:
        candidate = raw_line.lstrip("\ufeff").rstrip("\r\n")
        if not candidate:
            continue
        if candidate.startswith("#"):
            possible_header = candidate[1:]
            normalized_header = {_normal_field(field) for field in possible_header.split(delimiter)}
            if delimiter not in possible_header or not set(header_hints).issubset(normalized_header):
                continue
            candidate = possible_header
        elif header_hints:
            normalized_header = {_normal_field(field) for field in candidate.split(delimiter)}
            if not set(header_hints).issubset(normalized_header):
                continue
        header = candidate + "\n"
        break
    if header is None:
        raise ValueError("Knowledge source is empty")
    return csv.DictReader(chain([header], iterator), delimiter=delimiter)


def _normal_field(value):
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def _row_value(row, *names):
    for name in names:
        value = row.get(_normal_field(name), "")
        if value:
            return value
    return ""


def _normalize_disease_id(value):
    value = str(value or "").strip()
    if not value:
        return ""
    prefix, separator, identifier = value.partition(":")
    if not separator:
        return f"OMIM:{value}" if value.isdigit() else value
    prefix = prefix.upper()
    if prefix == "MIM":
        prefix = "OMIM"
    elif prefix == "ORPHANET":
        prefix = "ORPHA"
    return f"{prefix}:{identifier}"


def query_gene(gene_symbol, hgnc_id="", database=None):
    database = Path(database or cache_path())
    status = cache_status(database)
    if status["status"] != "ready":
        return {"gene": gene_symbol, "hgnc_id": hgnc_id, "associations": [], "cache": status}
    normalized_hgnc = _normalize_hgnc(hgnc_id)
    where = "gene_curie = ?" if normalized_hgnc else "gene_symbol = ? COLLATE NOCASE"
    parameter = normalized_hgnc or str(gene_symbol).strip()
    with sqlite3.connect(str(database)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM assertions WHERE " + where
            + " ORDER BY disease_title COLLATE NOCASE, submitter_title COLLATE NOCASE",
            (parameter,),
        ).fetchall()
        if normalized_hgnc and not rows:
            rows = connection.execute(
                "SELECT * FROM assertions WHERE gene_symbol = ? COLLATE NOCASE "
                "ORDER BY disease_title COLLATE NOCASE, submitter_title COLLATE NOCASE",
                (str(gene_symbol).strip(),),
            ).fetchall()
        associations = _aggregate_assertions(rows)
        _enrich_associations(
            connection, associations, str(gene_symbol).strip(), normalized_hgnc
        )
        gene_constraint = _query_gnomad_constraint(connection, gene_symbol)
        dosage_sensitivity = _query_clingen_dosage(connection, gene_symbol)
    return {
        "gene": gene_symbol, "hgnc_id": normalized_hgnc,
        "associations": associations, "association_count": len(associations),
        "assertion_count": sum(len(item["assertions"]) for item in associations),
        "gene_constraint": gene_constraint,
        "dosage_sensitivity": dosage_sensitivity,
        "cache": status,
    }


def _query_gnomad_constraint(connection, gene_symbol):
    refreshing = constraint_is_refreshing(gene_symbol)
    try:
        row = connection.execute(
            "SELECT * FROM gnomad_constraints WHERE gene_symbol = ? COLLATE NOCASE",
            (str(gene_symbol or "").strip(),),
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if row is None:
        return {"status": "missing", "refreshing": refreshing}
    stale = True
    try:
        updated = datetime.strptime(row["updated_at"], "%Y-%m-%dT%H:%M:%SZ")
        stale = datetime.now(timezone.utc).replace(tzinfo=None) - updated > CONSTRAINT_MAX_AGE
    except (TypeError, ValueError):
        pass
    result = {
        "status": "ready" if row["available"] else "unavailable",
        "refreshing": refreshing, "stale": stale,
        "source": "gnomAD v4.1.2", "source_url": row["source_url"],
        "gene_id": row["gene_id"], "transcript_id": row["transcript_id"],
        "updated_at": row["updated_at"],
    }
    if row["available"]:
        result.update({
            "pli": row["pli"], "loeuf": row["loeuf"], "lof_oe": row["lof_oe"],
            "lof_observed": row["lof_observed"], "lof_expected": row["lof_expected"],
            "lof_z": row["lof_z"], "missense_z": row["missense_z"],
            "missense_oe": row["missense_oe"],
            "missense_observed": row["missense_observed"],
            "missense_expected": row["missense_expected"],
        })
    return result


def _query_clingen_dosage(connection, gene_symbol):
    try:
        row = connection.execute(
            "SELECT * FROM clingen_dosage WHERE gene_symbol = ? COLLATE NOCASE",
            (str(gene_symbol or "").strip(),),
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if row is None:
        return {"status": "unavailable", "source": "ClinGen Dosage Sensitivity"}
    return {
        "status": "ready", "source": "ClinGen Dosage Sensitivity",
        "gene_id": row["gene_id"], "cytoband": row["cytoband"],
        "genomic_location": row["genomic_location"],
        "haploinsufficiency": {
            "score": row["hi_score"], "description": row["hi_description"],
            "pmids": _split_values(row["hi_pmids"]),
            "disease_id": row["hi_disease_id"],
        },
        "triplosensitivity": {
            "score": row["ts_score"], "description": row["ts_description"],
            "pmids": _split_values(row["ts_pmids"]),
            "disease_id": row["ts_disease_id"],
        },
        "last_evaluated": row["last_evaluated"], "source_url": row["report_url"],
    }


def _split_values(value):
    return [item.strip() for item in str(value or "").split(";") if item.strip()]


def _assertion_values(row):
    try:
        version = int(row.get("version_number") or 0)
    except ValueError:
        version = 0
    return (
        row.get("sgc_id", ""), version, row.get("gene_curie", ""),
        row.get("gene_symbol", ""), row.get("disease_curie", ""),
        row.get("disease_title", ""), row.get("disease_original_curie", ""),
        row.get("disease_original_title", ""), row.get("classification_title", ""),
        row.get("moi_curie", ""), row.get("moi_title", ""),
        row.get("submitter_title", ""), row.get("submitted_as_date", ""),
        row.get("submitted_as_public_report_url", ""), row.get("submitted_as_pmids", ""),
        row.get("submitted_as_assertion_criteria_url", ""), row.get("submitted_run_date", ""),
    )


def _normalize_hgnc(value):
    value = str(value or "").strip()
    if not value:
        return ""
    return "HGNC:" + value.split(":")[-1]


def _classification_rank(value):
    return _CLASSIFICATION_RANK.get(str(value or "").strip().lower(), 99)


def _enrich_associations(connection, associations, gene_symbol, hgnc_id):
    try:
        where = "gene_curie = ?" if hgnc_id else "gene_symbol = ? COLLATE NOCASE"
        gene_value = hgnc_id or gene_symbol
        g2p_rows = connection.execute(
            f"SELECT * FROM g2p_records WHERE {where}", (gene_value,)
        ).fetchall()
        if hgnc_id and not g2p_rows:
            g2p_rows = connection.execute(
                "SELECT * FROM g2p_records WHERE gene_symbol = ? COLLATE NOCASE",
                (gene_symbol,),
            ).fetchall()
    except sqlite3.OperationalError:
        g2p_rows = []
    for association in associations:
        disease_ids = {
            _normalize_disease_id(identifier) for identifier in [
                association.get("disease_id", ""),
                *association.get("original_disease_ids", []),
            ] if identifier
        }
        association["phenotypic_features"] = _query_hpo_features(connection, disease_ids)
        association["phenotypic_feature_count"] = len(association["phenotypic_features"])
        association["icd_codes"] = _query_disease_codes(connection, disease_ids)
        matching_g2p = [
            row for row in g2p_rows
            if disease_ids.intersection({row["disease_curie"], row["disease_mim"]} - {""})
        ]
        association["molecular_mechanism"] = _mechanism_summary(matching_g2p)


def _query_disease_codes(connection, disease_ids):
    if not disease_ids:
        return []
    placeholders = ",".join("?" for _ in disease_ids)
    try:
        rows = connection.execute(
            "SELECT DISTINCT codes.* FROM orpha_aliases aliases "
            "JOIN disease_codes codes ON codes.orpha_id = aliases.orpha_id "
            f"WHERE aliases.identifier IN ({placeholders}) "
            "ORDER BY codes.system, codes.code",
            tuple(sorted(disease_ids)),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [{
        "system": row["system"], "code": row["code"],
        "disease_name": row["disease_name"],
        "mapping_relation": row["mapping_relation"],
        "mapping_kind": _mapping_relation_kind(row["mapping_relation"]),
        "icd_relation": row["icd_relation"],
        "validation_status": row["validation_status"],
        "source": "Orphadata", "source_url": row["source_url"],
        "source_uri": row["source_uri"], "orpha_id": row["orpha_id"],
    } for row in rows]


def _mapping_relation_kind(relation):
    value = str(relation or "").strip().upper()
    if value == "E" or value.startswith("E ("):
        return "exact"
    if value.startswith("NTBT"):
        return "narrower-to-broader"
    if value.startswith("BTNT"):
        return "broader-to-narrower"
    return "undetermined"


def _query_hpo_features(connection, disease_ids):
    if not disease_ids:
        return []
    placeholders = ",".join("?" for _ in disease_ids)
    try:
        rows = connection.execute(
            f"SELECT * FROM hpo_features WHERE disease_curie IN ({placeholders}) "
            "ORDER BY hpo_name COLLATE NOCASE, hpo_id, reference",
            tuple(sorted(disease_ids)),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    grouped = {}
    for row in rows:
        feature = grouped.setdefault(row["hpo_id"], {
            "id": row["hpo_id"], "name": row["hpo_name"] or row["hpo_id"],
            "negative": True, "frequencies": set(), "onsets": set(),
            "annotations": [],
        })
        qualifier = str(row["qualifier"] or "").strip().upper()
        if qualifier != "NOT":
            feature["negative"] = False
        if row["frequency"]:
            feature["frequencies"].add(row["frequency"])
        if row["onset"]:
            feature["onsets"].add(row["onset"])
        feature["annotations"].append({
            "disease_id": row["disease_curie"], "qualifier": qualifier,
            "reference": row["reference"], "evidence": row["evidence"],
            "sex": row["sex"], "modifier": row["modifier"],
            "biocuration": row["biocuration"],
        })
    result = []
    for feature in grouped.values():
        feature["frequencies"] = sorted(feature["frequencies"])
        feature["onsets"] = sorted(feature["onsets"])
        result.append(feature)
    return sorted(result, key=lambda item: (item["negative"], item["name"].casefold()))


def _mechanism_summary(rows):
    records = []
    mechanisms = set()
    for row in rows:
        mechanism = _normalize_mechanism(row["mechanism"])
        confidence = str(row["confidence"] or "").strip().lower()
        accepted = confidence in _G2P_ACCEPTED_CONFIDENCE
        if accepted and mechanism != "unknown":
            mechanisms.add(mechanism)
        records.append({
            "id": row["g2p_id"], "mechanism": mechanism,
            "category": row["mechanism_category"], "support": row["mechanism_support"],
            "confidence": row["confidence"], "accepted": accepted,
            "allelic_requirement": row["allelic_requirement"],
            "variant_consequence": row["variant_consequence"],
            "publications": row["publications"], "last_reviewed": row["last_reviewed"],
            "url": row["record_url"],
        })
    status = (
        "conflicting" if len(mechanisms) > 1 else
        "supported" if mechanisms else
        "uncertain" if records else "unknown"
    )
    return {
        "status": status,
        "value": next(iter(mechanisms)) if len(mechanisms) == 1 else "",
        "source": "Gene2Phenotype" if records else "",
        "records": records,
    }


def _normalize_mechanism(value):
    value = " ".join(str(value or "").strip().lower().replace("_", " ").split())
    if not value or value in {"unknown", "undetermined", "not known", "not specified"}:
        return "unknown"
    aliases = {
        "loss of function": "loss of function",
        "gain of function": "gain of function",
        "dominant negative": "dominant negative",
    }
    return aliases.get(value, value)


def _aggregate_assertions(rows):
    grouped = {}
    for row in rows:
        key = row["disease_curie"] or row["disease_title"].strip().casefold()
        association = grouped.setdefault(key, {
            "disease_id": row["disease_curie"], "disease": row["disease_title"],
            "original_disease_ids": set(), "inheritance": set(),
            "strongest_classification": "", "assertions": [],
        })
        if row["disease_original_curie"]:
            association["original_disease_ids"].add(row["disease_original_curie"])
        if row["moi_title"]:
            association["inheritance"].add(row["moi_title"])
        classification = row["classification_title"]
        if not association["strongest_classification"] or _classification_rank(classification) < _classification_rank(association["strongest_classification"]):
            association["strongest_classification"] = classification
        association["assertions"].append({
            "id": row["sgc_id"], "version": row["version_number"],
            "source": row["submitter_title"], "classification": classification,
            "inheritance": row["moi_title"], "submitted_at": row["submitted_as_date"],
            "report_url": row["public_report_url"], "pmids": row["pmids"],
            "criteria_url": row["assertion_criteria_url"],
        })
    result = []
    for association in grouped.values():
        association["original_disease_ids"] = sorted(association["original_disease_ids"])
        association["inheritance"] = sorted(association["inheritance"])
        association["assertions"].sort(
            key=lambda item: (_classification_rank(item["classification"]), item["source"].lower())
        )
        result.append(association)
    result.sort(key=lambda item: (
        _classification_rank(item["strongest_classification"]), item["disease"].lower()
    ))
    return result
