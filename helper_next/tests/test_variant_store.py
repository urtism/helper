import sqlite3

import pytest

from helper_variants import store as variant_store


def populated_store(tmp_path, kind="run"):
    path = tmp_path / (kind + ".sqlite3")
    with variant_store.connect(path, kind) as db:
        run_id = variant_store.register_run(db, "RUN-1", "GRCh38", "/runs/RUN-1")
        subject_id = variant_store.register_subject(db, "SUBJECT-1")
        sample_id = variant_store.register_sample(
            db, "SAMPLE-1", "Proband", subject_id, "blood"
        )
        analysis_id = variant_store.register_analysis(
            db, "RUN-1:SAMPLE-1", run_id, sample_id, "proband", {"caller": "GATK"}, {"mean_dp": 120}
        )
    return path, analysis_id


def test_initializes_versioned_run_and_cohort_stores(tmp_path):
    for kind in ("run", "cohort"):
        path = tmp_path / kind / "variants.sqlite3"
        with variant_store.connect(path, kind) as db:
            assert variant_store.store_info(db)["store_kind"] == kind
            assert variant_store.store_info(db)["schema_version"] == variant_store.SCHEMA_VERSION
            assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            assert db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_rejects_wrong_store_kind_and_unknown_database(tmp_path):
    path, _ = populated_store(tmp_path)
    with pytest.raises(ValueError, match="not 'cohort'"):
        with variant_store.connect(path, "cohort"):
            pass

    unknown = tmp_path / "unknown.sqlite3"
    sqlite3.connect(str(unknown)).close()
    with pytest.raises(ValueError, match="not a Helper variant database"):
        with variant_store.connect(unknown):
            pass


def test_registration_is_idempotent_and_keeps_builds_separate(tmp_path):
    path, analysis_id = populated_store(tmp_path)
    with variant_store.connect(path) as db:
        first = variant_store.get_or_create_variant(db, "GRCh38", "1", 100, "a", "g", "SNV")
        duplicate = variant_store.get_or_create_variant(db, "GRCh38", "1", 100, "A", "G", "SNV")
        other_build = variant_store.get_or_create_variant(db, "GRCh37", "1", 100, "A", "G", "SNV")
        call = variant_store.record_call(db, analysis_id, first, "GATK", "0/1", depth=80)
        repeated_call = variant_store.record_call(db, analysis_id, first, "GATK", "0/1", depth=80)

        assert first == duplicate
        assert first != other_build
        assert call == repeated_call
        assert db.execute("SELECT COUNT(*) FROM variants").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 1

        with pytest.raises(ValueError, match="conflicting duplicate call"):
            variant_store.record_call(db, analysis_id, first, "GATK", "1/1", depth=80)


def test_annotation_releases_are_immutable_parallel_history(tmp_path):
    path, _ = populated_store(tmp_path, "cohort")
    with variant_store.connect(path) as db:
        variant_id = variant_store.get_or_create_variant(db, "GRCh38", "7", 140453136, "A", "T")
        old_release = variant_store.register_annotation_release(
            db, "vep-2025", "VEP", "GRCh38", "113", {"clinvar": "2025-01"}
        )
        new_release = variant_store.register_annotation_release(
            db, "vep-2026", "VEP", "GRCh38", "116", {"clinvar": "2026-09"}
        )
        old_annotation = variant_store.record_annotation(
            db, variant_id, old_release, gene="BRAF", transcript="ENST1",
            consequence="missense_variant", clinical_significance="VUS"
        )
        repeated = variant_store.record_annotation(
            db, variant_id, old_release, gene="BRAF", transcript="ENST1",
            consequence="missense_variant", clinical_significance="VUS"
        )
        new_annotation = variant_store.record_annotation(
            db, variant_id, new_release, gene="BRAF", transcript="ENST1",
            consequence="missense_variant", clinical_significance="pathogenic"
        )

        assert old_annotation == repeated
        assert old_annotation != new_annotation
        assert db.execute("SELECT COUNT(*) FROM annotations").fetchone()[0] == 2

        with pytest.raises(ValueError, match="conflicting annotation"):
            variant_store.record_annotation(
                db, variant_id, old_release, gene="BRAF", transcript="ENST1",
                consequence="missense_variant", clinical_significance="pathogenic"
            )


def test_foreign_keys_prevent_orphan_calls(tmp_path):
    path, _ = populated_store(tmp_path)
    with variant_store.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError):
            variant_store.record_call(db, 999, 999, "caller")


def test_stable_keys_cannot_be_silently_reassigned(tmp_path):
    path, _ = populated_store(tmp_path)
    with variant_store.connect(path) as db:
        with pytest.raises(ValueError, match="another reference build"):
            variant_store.register_run(db, "RUN-1", "GRCh37")
        run_2 = variant_store.register_run(db, "RUN-2", "GRCh38")
        sample_2 = variant_store.register_sample(db, "SAMPLE-2", "Sibling")
        with pytest.raises(ValueError, match="another run or sample"):
            variant_store.register_analysis(db, "RUN-1:SAMPLE-1", run_2, sample_2)
        subject_2 = variant_store.register_subject(db, "SUBJECT-2")
        with pytest.raises(ValueError, match="another subject"):
            variant_store.register_sample(db, "SAMPLE-1", "Proband", subject_2)
