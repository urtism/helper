"""ClinVar Local -> existing HELPER evidence payload, scoped to one operation."""
import json
import logging
import re
import sqlite3

from helper_variants.clinvar_local import ClinVarLocal, ClinVarLocalError, clinvar_url


_ERRORS = (ClinVarLocalError, OSError, sqlite3.Error, ValueError, KeyError, TypeError)


def table_classifications(evidence):
    """Class labels visible in the local ClinVar column, for server-side filtering."""
    if evidence.get("matching_status") != "FOUND":
        return set()
    breakdown = evidence.get("submission_classification_breakdown") or []
    if "submission_classification_breakdown" in evidence:
        labels = [row["label"] for row in breakdown if row.get("label") and row.get("count", 0) > 0]
    else:
        labels = [] if evidence.get("has_conflict") else evidence.get("classifications", [])
    return {part.strip().lower().replace("_", " ") for label in labels for part in label.split("/")
            if part.strip() and part.strip().lower().replace("_", " ") != "not provided"}


class LocalEvidence:
    """Pin CURRENT for a request/batch; never retain a reader in application caches."""

    def __init__(self, database=None):
        self.database = database
        self.reader = None
        self.manifest = {}
        self.error = None

    def __enter__(self):
        try:
            self.reader = ClinVarLocal(self.database)
            self.manifest = self.reader.release()
            if not self.manifest.get("snapshot_id"):
                raise ClinVarLocalError("Missing ClinVar snapshot identifier")
        except _ERRORS as exc:
            self._failed(exc)
        return self

    def __exit__(self, *args):
        if self.reader is not None:
            self.reader.close()
            self.reader = None

    def _failed(self, exc):
        self.error = str(exc)
        logging.getLogger(__name__).warning("ClinVar Local unavailable: %s", exc)

    @property
    def snapshot_id(self):
        return self.manifest.get("snapshot_id")

    def batch(self, alleles, *, record=None):
        alleles = [tuple(allele) if isinstance(allele, list) else allele for allele in alleles]
        if self.error is None:
            try:
                # Deduplicate input as well as the reader's genomic SQL keys.
                unique = list(dict.fromkeys(alleles))
                lookups = self.reader.lookup_batch(unique, record=record)
                ids = sorted({hit["matches"][0]["variation_id"] for hit in lookups
                              if hit["status"] == "FOUND"})
                variants, classes = {}, {}
                # Batch aggregates/RCV references too; individual SCVs stay in detail.
                for start in range(0, len(ids), 500):
                    chunk = ids[start:start + 500]
                    marks = ",".join("?" for _ in chunk)
                    for row in self.reader.connection.execute(
                        "SELECT * FROM variants WHERE variation_id IN (" + marks + ")", chunk
                    ):
                        variants[row["variation_id"]] = dict(row)
                    for row in self.reader.connection.execute(
                        "SELECT * FROM classifications WHERE variation_id IN (" + marks + ") "
                        "ORDER BY variation_id,scope,kind,rcv", chunk
                    ):
                        classes.setdefault(row["variation_id"], []).append(dict(row))
                mapped = {allele: self._adapt(hit, variants, classes)
                          for allele, hit in zip(unique, lookups)}
                counted_items = [item for item in mapped.values() if item["matching_status"] == "FOUND"]
                try:
                    display_counts = self.reader.submission_classification_counts_batch(
                        [item["variation_id"] for item in counted_items]
                    )
                except _ERRORS as exc:
                    # Display counts are optional; keep the source aggregate authoritative.
                    display_counts = {}
                    logging.getLogger(__name__).warning("ClinVar submission counts unavailable: %s", exc)
                for item in counted_items:
                    item["submission_classification_breakdown"] = display_counts.get(item["variation_id"], [])
                return [mapped[allele] for allele in alleles]
            except _ERRORS as exc:
                self._failed(exc)
        return [self._adapt(dict(status="ERROR", reason=self.error, matches=[]), {}, {})
                for allele in alleles]

    def _adapt(self, hit, variants, classes):
        state = hit["status"]
        result = dict(
            source="ClinVar Local", status={"FOUND": "available", "NOT_FOUND": "not_found"}.get(state, "unavailable"),
            availability="AVAILABLE" if state == "FOUND" else state,
            freshness="NOT_APPLICABLE", matching_status=state, match_reason=hit.get("reason"),
            match_method=hit.get("match_method"), allele_identity=hit.get("allele_identity", []),
            matches=hit.get("matches", []), snapshot_id=self.snapshot_id,
            provenance=self.manifest, identifiers=[], classifications=[], review_statuses=[],
            conditions=[], condition_ids=[], rcv_accessions=[], has_conflict=False, conflicts=[],
            last_evaluated=[], origins=[], classification_breakdown=[],
            clinical_status="NOT_FOUND" if state == "NOT_FOUND" else "NOT_EVALUABLE",
        )
        if self.error:
            result["last_error"] = self.error
        if state != "FOUND":
            return result
        identifier = hit["matches"][0]["variation_id"]
        variant = variants[identifier]
        result.update(variation_id=identifier, allele_id=variant["allele_id"],
                      identifiers=[str(identifier)], source_url=clinvar_url(identifier),
                      submitter_count=variant["number_submitters"],
                      origins=[variant["origins"]] if variant["origins"] else [])
        unaligned = json.loads(variant["details_json"]).get("unaligned_condition_source")
        if unaligned:
            result["unaligned_condition_source"] = unaligned
            for field, key in (("PhenotypeList", "conditions"), ("PhenotypeIDS", "condition_ids")):
                if unaligned.get(field) not in (None, "", "-", "na"):
                    result[key].append(unaligned[field])
        for row in classes.get(identifier, []):
            if row["scope"] == "condition_reference":
                result["rcv_accessions"].append(row["rcv"])
                for field, key in (("condition_name", "conditions"), ("condition_ids", "condition_ids")):
                    if row[field] and row[field] not in result[key]:
                        result[key].append(row[field])
                continue
            kind = row["kind"]
            key = {"germline": "classifications", "oncogenicity": "oncogenicity",
                   "somatic_clinical_impact": "somatic_clinical_impact"}[kind]
            review_key = {"germline": "review_statuses", "oncogenicity": "oncogenicity_review_statuses",
                          "somatic_clinical_impact": "somatic_review_statuses"}[kind]
            result[key] = [row["classification"]] if row["classification"] else []
            result[review_key] = ([dict(label=row["review_status"], stars=row["stars"])]
                                  if row["review_status"] else [])
            if kind == "germline":
                result.update(has_conflict=bool(row["has_conflict"]),
                              conflicts=[row["classification"]] if row["has_conflict"] else [],
                              last_evaluated=[row["last_evaluated"]] if row["last_evaluated"] else [],
                              contributing_scvs=re.findall(r"SCV\d+(?:\.\d+)?", row["contributing_scvs"] or ""))
        result["clinical_status"] = "CLASSIFIED" if result["classifications"] else "NO_GERMLINE_CLASSIFICATION"
        return result

    def submissions(self, evidence, *, limit=100, offset=0):
        """Page individual interpretations, without turning SCVs into an aggregate."""
        if evidence["matching_status"] != "FOUND" or self.error:
            return evidence
        try:
            identifier = evidence["variation_id"]
            rows = self.reader.submissions(identifier, limit=limit, offset=offset)
            counts = self.reader.submission_counts(identifier)
            contributors = set(evidence.get("contributing_scvs") or [])
            for row in rows:
                # Exact version when VS has it; accession-only lists explicitly lack it.
                row["contributes_to_germline_aggregate"] = (
                    row["scv"] in contributors or row["scv_accession"] in contributors
                ) if contributors else None
            evidence.update(submissions=rows, submission_count=counts["submissions"],
                            submission_classification_breakdown=self.reader.submission_classification_counts(identifier),
                            reviewed_submission_classification_breakdown=self.reader.submission_classification_counts(identifier, min_stars=1),
                            submission_interpretation_count=counts["interpretation_rows"],
                            submissions_offset=offset, submissions_limit=limit,
                            submissions_next_offset=offset + limit
                            if offset + len(rows) < counts["interpretation_rows"] else None)
        except _ERRORS as exc:
            # A missing optional page must not alter the aggregate used for priority.
            evidence["submissions_error"] = str(exc)
            logging.getLogger(__name__).warning("ClinVar Local submissions unavailable: %s", exc)
        return evidence
