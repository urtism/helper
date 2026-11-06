"""Complete sample loading: acquire evidence, score globally, then display once."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import sqlite3
import subprocess
import threading

import pytest

from helper_next.api import variants as api
from helper_next.core import acmg_reference
from helper_variants import clinvar_local, gene_phenotype, gnomad_enrichment, gnomad_frequency, query, store
from test_clinvar_local import build, summary
from test_gnomad_frequency import official, provider
from test_variant_query import query_store


def test_clinvar_checks_indels_without_hashing_reference(tmp_path, monkeypatch):
    database, _ = build(tmp_path, [summary(
        Chromosome="1", ChromosomeAccession="NC_000001.11", PositionVCF="1",
        ReferenceAlleleVCF="CA", AlternateAlleleVCF="C",
    )])
    fasta = tmp_path / "reference.fa"
    fasta.write_text(">1\nCAAAAAGTACGT\n")
    Path(str(fasta) + ".fai").write_text("1\t12\t3\t12\t13\n")
    record = {"run_config": {"reference_fasta": str(fasta), "reference_version": "test"}}
    monkeypatch.setattr(acmg_reference, "reference_checksum",
                        lambda *args: pytest.fail("Sample loading must not hash the FASTA"))
    with clinvar_local.ClinVarLocal(database) as reader:
        found = reader.lookup("GRCh38", "1", 4, "AA", "A", record=record)
        assert found["status"] == "FOUND"
        assert found["allele_identity"][0]["identity"]["position"] == 1
        provenance = found["allele_identity"][0]["reference_provenance"]
        assert provenance["ref_status"] == "VERIFIED"
        assert provenance["digest"] is None
        assert provenance["identifier"] is None
        assert provenance["checksum_status"] == "NOT_CHECKED"
        assert reader.lookup("GRCh38", "1", 4, "GA", "G", record=record)["status"] == "UNRESOLVED"


@pytest.mark.parametrize("sort_by", ["priority", "gene", "population_af", "clinical_significance", "consequence"])
def test_load_all_preserves_full_order_filters_and_pagination_contract(tmp_path, sort_by):
    database, sample, _ = query_store(tmp_path)
    expected = []
    cursor = None
    while True:
        page = query.list_variants(database, sample, limit=2, cursor=cursor, sort_by=sort_by)
        expected.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    loaded = query.list_variants(database, sample, load_all=True, limit=1, sort_by=sort_by)
    assert [{key: value for key, value in item.items() if key != "filter_data"}
            for item in loaded["items"]] == expected
    assert loaded["next_cursor"] is None
    assert len(loaded["items"]) == 5
    filtered = query.list_variants(database, sample, load_all=True, limit=1,
                                   sort_by=sort_by, genes="GENE1")
    assert {item["position"] for item in filtered["items"]} == {1, 2}
    with pytest.raises(query.VariantQueryError, match="cursor"):
        query.list_variants(database, sample, load_all=True, cursor="old-page")


def test_load_all_exceeds_page_cap_and_computes_every_priority(tmp_path):
    database, sample, _ = query_store(tmp_path)
    with store.connect(database) as db:
        analysis = db.execute('SELECT id FROM analyses WHERE sample_id=?', (sample,)).fetchone()[0]
        for position in range(6, 607):
            variant = store.get_or_create_variant(db, "GRCh38", "1", position, "A", "G", "SNV")
            store.record_call(db, analysis, variant, "GATK", "0/1", depth=30)
    loaded = query.list_variants(database, sample, load_all=True, limit=1)
    assert len(loaded["items"]) == 606
    assert loaded["next_cursor"] is None
    assert len({item["variant_id"] for item in loaded["items"]}) == 606
    assert all(item["priority"]["components"] for item in loaded["items"])
    assert all(item["priority"]["ruleset"] for item in loaded["items"])


def test_prepare_sample_visits_all_alleles_once_and_scores_acquired_data(tmp_path, monkeypatch):
    monkeypatch.delenv("HELPER_GNOMAD_OFFLINE", raising=False)
    database, sample, other = query_store(tmp_path)
    with store.connect(database) as db:
        analysis = db.execute('SELECT id FROM analyses WHERE sample_id=?', (sample,)).fetchone()[0]
        store.record_call(db, analysis, 1, "SECOND_CALLER", "0/1", depth=40)
        other_analysis = db.execute('SELECT id FROM analyses WHERE sample_id=?', (other,)).fetchone()[0]
        unrelated = store.get_or_create_variant(db, "GRCh38", "1", 99, "C", "T", "SNV")
        store.record_call(db, other_analysis, unrelated, "GATK", "0/1", depth=30)
    template = official()
    for variant in template['data'].values():
        if variant and variant.get('joint'):
            variant['joint']['freq_comparison_stats'] = {}
    calls = provider(monkeypatch, template)
    before = query.list_variants(database, sample, load_all=True)
    for item in before["items"]:
        component = next(c for c in item["priority"]["components"] if c["key"] == "maf")
        assert component["evaluated"] == (item["position"] == 1)
        if item["position"] == 1:
            assert component["observed_af_source"]["dataset"] == "vep"
    after = 0
    batches = []
    while after is not None:
        batch = gnomad_enrichment.prepare_sample(database, sample, after_variant_id=after, limit=2)
        batches.append(batch)
        after = batch["next_after_variant_id"]
    assert [batch["attempted"] for batch in batches] == [2, 2, 1]
    assert [batch["outcomes"] for batch in batches] == [{"FOUND": 2}, {"FOUND": 2}, {"FOUND": 1}]
    assert sum(len(variables) for _, variables in calls) == 5
    loaded = query.list_variants(database, sample, load_all=True, limit=1)
    assert len(loaded["items"]) == 5
    for item in loaded["items"]:
        component = next(c for c in item["priority"]["components"] if c["key"] == "maf")
        assert component["evaluated"] and component["score"] == -10, json.dumps(component)
    with sqlite3.connect(database) as db:
        assert "gnomad_enrichment" not in json.loads(db.execute(
            'SELECT metadata_json FROM variants WHERE id=?', (unrelated,)).fetchone()[0])
        metadata = json.loads(db.execute('SELECT metadata_json FROM variants WHERE id=1').fetchone()[0])
        assert metadata["vcf_id"] == "rs123"
    monkeypatch.setattr(gnomad_frequency, "_request_graphql", lambda *args: pytest.fail("Already acquired"))
    assert gnomad_enrichment.prepare_sample(database, sample)["attempted"] == 5


def test_preparation_reports_failed_lookups_without_awarding_absence_points(tmp_path, monkeypatch):
    monkeypatch.delenv("HELPER_GNOMAD_OFFLINE", raising=False)
    database, sample, _ = query_store(tmp_path)
    def unavailable(*args):
        raise gnomad_frequency.GnomadFrequencyError("offline test")
    monkeypatch.setattr(gnomad_frequency, "_request_graphql", unavailable)
    result = gnomad_enrichment.prepare_sample(database, sample)
    assert result["attempted"] == 5 and result["next_after_variant_id"] is None
    assert result["outcomes"] == {"UNAVAILABLE": 5}
    for item in query.list_variants(database, sample, load_all=True)["items"]:
        component = next(c for c in item["priority"]["components"] if c["key"] == "maf")
        if item["position"] == 1:
            assert component["score"] == 5 and component["evaluated"]
            assert component["observed_af_source"]["dataset"] == "vep"
        else:
            assert component["score"] == 0 and not component["evaluated"]


@pytest.mark.parametrize("only_invalid", [False, True])
@pytest.mark.parametrize("sort_by", ["priority", "gene"])
def test_sample_loading_filters_unresolved_alleles_in_existing_indexes(tmp_path, monkeypatch, only_invalid, sort_by):
    database, sample, _ = query_store(tmp_path)
    invalid_alleles = [
        (0, "A", "G"), (-1, "A", "T"), (10, "", "G"), (11, "A", ""),
        (12, "*", "G"), (13, "A", "*"), (14, "A*", "G"), (15, "A", "G*"),
        (16, "N", "G"), (17, "A", "N"), (18, "A", "<DEL>"),
        (19, "A", "A]2:100]"), (20, "A", "."), (21, "A", "A"),
    ]
    with store.connect(database) as db:
        db.execute("PRAGMA ignore_check_constraints=ON")
        analysis = db.execute('SELECT id FROM analyses WHERE sample_id=?', (sample,)).fetchone()[0]
        # Use hg19 to exercise the supplied-projection path that raised on '*'.
        db.execute("UPDATE variants SET reference_build='GRCh37'")
        expected = [] if only_invalid else [1, 2, 3, 4, 5]
        if only_invalid:
            db.execute("UPDATE variants SET alternate='*'")
        for index, (position, reference, alternate) in enumerate(invalid_alleles):
            variant = store.get_or_create_variant(db, "GRCh37", "1", 1000 + index,
                                                   "C", "T", "SNV")
            # Simulate an existing index, including fields rejected by new writes.
            db.execute('UPDATE variants SET position=?,reference=?,alternate=? WHERE id=?',
                       (position, reference, alternate, variant))
            store.record_call(db, analysis, variant, "GATK", "0/1")
            if not only_invalid:
                valid_ref, valid_alt = [("AT", "A"), ("A", "AT"), ("ac", "gt")][index % 3]
                valid = store.get_or_create_variant(db, "GRCh37", "1", 200 + position, valid_ref, valid_alt)
                store.record_call(db, analysis, valid, "GATK", "0/1")
                expected.append(valid)

    # No remote projection is needed to test filtering and batch progression.
    monkeypatch.setenv("HELPER_GNOMAD_OFFLINE", "1")
    monkeypatch.setenv("HELPER_LIFTOVER_CACHE", str(tmp_path / "projection.sqlite3"))
    after = 0
    attempted = 0
    for _ in range(len(expected) + 1):
        result = gnomad_enrichment.prepare_sample(database, sample, after_variant_id=after, limit=2)
        attempted += result["attempted"]
        after = result["next_after_variant_id"]
        if after is None:
            break
    assert after is None
    assert attempted == len(expected)
    loaded = query.list_variants(database, sample, load_all=True, sort_by=sort_by)
    assert {item["variant_id"] for item in loaded["items"]} == set(expected)
    seen = []
    cursor = None
    while True:
        page = query.list_variants(database, sample, limit=2, cursor=cursor, sort_by=sort_by)
        seen.extend(item["variant_id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == [item["variant_id"] for item in loaded["items"]]


def test_preparation_api_and_all_variants_flag(tmp_path, monkeypatch):
    database, sample, _ = query_store(tmp_path)
    monkeypatch.setattr(api, "_entry", lambda identifier: {"database": database, "record": {}})
    monkeypatch.setattr(api, "_entry_database", lambda entry: database)
    monkeypatch.setattr(api.gene_phenotype, "prepare_priority_contexts", lambda: {"status": "ready"})
    provider(monkeypatch)
    result = api.prepare_sample_priority_evidence("RUN", sample, after_variant_id=0, limit=3)
    assert result["attempted"] == 3 and result["next_after_variant_id"] == 3
    loaded = api.sample_variants("RUN", sample, limit=1, load_all=True)
    assert len(loaded["items"]) == 5 and loaded["next_cursor"] is None
    with pytest.raises(api.HTTPException) as error:
        api.prepare_sample_priority_evidence("RUN", 999, after_variant_id=0, limit=3)
    assert error.value.status_code == 404


def test_remote_batches_return_progress_early_and_cached_batches_remain_large(tmp_path, monkeypatch):
    database, sample, _ = query_store(tmp_path)
    with store.connect(database) as db:
        analysis = db.execute('SELECT id FROM analyses WHERE sample_id=?', (sample,)).fetchone()[0]
        for position in range(6, 21):
            variant = store.get_or_create_variant(db, 'GRCh38', '1', position, 'A', 'G', 'SNV')
            store.record_call(db, analysis, variant, 'GATK', '0/1', depth=30)
    calls = provider(monkeypatch)
    first = gnomad_enrichment.prepare_sample(database, sample, limit=50)
    assert first['attempted'] == 5 and first['next_after_variant_id'] == 5
    after = first['next_after_variant_id']
    while after is not None:
        batch = gnomad_enrichment.prepare_sample(database, sample, after_variant_id=after, limit=50)
        assert batch['attempted'] == 5
        after = batch['next_after_variant_id']
    assert len(calls) == 4
    monkeypatch.setattr(gnomad_frequency, '_request_graphql', lambda *a: pytest.fail('Already acquired'))
    cached = gnomad_enrichment.prepare_sample(database, sample, limit=50)
    assert cached['attempted'] == 20 and cached['next_after_variant_id'] is None


def test_gene_disease_refresh_completes_before_population_acquisition(tmp_path, monkeypatch):
    database, sample, _ = query_store(tmp_path)
    events = []
    monkeypatch.setattr(gene_phenotype, "cache_status", lambda: {"status": "missing", "refreshing": False}
                        if not events else {"status": "ready", "stale": False, "refreshing": False})
    monkeypatch.setattr(gene_phenotype, "refresh_cache", lambda **kwargs: events.append("gene-disease"))
    calls = provider(monkeypatch)
    original = gnomad_frequency.lookup_variants
    def acquire(*args, **kwargs):
        assert events == ["gene-disease"]
        events.append("population")
        return original(*args, **kwargs)
    monkeypatch.setattr(gnomad_frequency, "lookup_variants", acquire)
    result = gnomad_enrichment.prepare_sample(database, sample, prepare_gene_context=True)
    assert result["gene_context"]["status"] == "ready"
    assert events == ["gene-disease", "population"] and calls
    assert not gene_phenotype.is_refreshing()


def test_failed_gene_refresh_keeps_installed_evidence_and_reports_failure(monkeypatch):
    monkeypatch.setattr(gene_phenotype, "cache_status", lambda: {"status": "ready", "stale": True, "refreshing": False})
    def unavailable(**kwargs):
        raise OSError("gene source unreachable")
    monkeypatch.setattr(gene_phenotype, "refresh_cache", unavailable)
    status = gene_phenotype.prepare_priority_contexts()
    assert status["status"] == "ready" and status["stale"]
    assert status["preparation_error"] == "gene source unreachable"
    assert not gene_phenotype.is_refreshing()


def test_current_gene_context_does_not_refresh_on_reopening(monkeypatch):
    monkeypatch.setattr(gene_phenotype, "cache_status", lambda: {"status": "ready", "stale": False, "refreshing": False})
    monkeypatch.setattr(gene_phenotype, "refresh_cache", lambda **kwargs: pytest.fail("Already available"))
    assert gene_phenotype.prepare_priority_contexts()["status"] == "ready"


def test_preparation_waits_for_running_gene_refresh(monkeypatch):
    monkeypatch.setattr(gene_phenotype, "cache_status", lambda: {
        "status": "ready", "stale": gene_phenotype.is_refreshing(), "refreshing": gene_phenotype.is_refreshing()})
    monkeypatch.setattr(gene_phenotype, "refresh_cache", lambda **kwargs: pytest.fail("Share the active update"))
    entered = threading.Event()
    original_wait = gene_phenotype._refresh_done.wait
    def wait(**kwargs):
        entered.set()
        return original_wait(**kwargs)
    monkeypatch.setattr(gene_phenotype._refresh_done, "wait", wait)
    assert gene_phenotype.begin_refresh()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            prepared = pool.submit(gene_phenotype.prepare_priority_contexts)
            assert entered.wait(timeout=2)
            assert not prepared.done()
            gene_phenotype.finish_refresh()
            assert prepared.result(timeout=2)["stale"] is False
    finally:
        gene_phenotype.finish_refresh()


def test_running_gene_refresh_blocks_provisional_priority(tmp_path, monkeypatch):
    database, sample, _ = query_store(tmp_path)
    monkeypatch.setattr(gene_phenotype, "prepare_priority_contexts", lambda: {"status": "ready", "refreshing": True})
    monkeypatch.setattr(gnomad_frequency, "lookup_variants", lambda *a, **kw: pytest.fail("Wait for required sources"))
    with pytest.raises(ValueError, match="still running"):
        gnomad_enrichment.prepare_sample(database, sample, prepare_gene_context=True)


def run_loading_js(script):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable")
    asset = Path(__file__).resolve().parents[1] / "src/helper_variants/web/static/variant-browser.js"
    setup = r'''
      const assert = require('node:assert/strict');
      const source = require('node:fs').readFileSync(process.argv[1], 'utf8');
      const sortDefinitions = source.slice(source.indexOf('const SORTABLE_VARIANT_COLUMNS = '),
        source.indexOf('const FORMAT_FIELD_LABELS = '));
      const browserClass = source.slice(source.indexOf('class VariantBrowser extends HTMLElement'),
        source.indexOf('\nif (!customElements.get('));
      const viewer = Function('HTMLElement', 'PAGE_SIZE',
        `${sortDefinitions}\n${browserClass}\nreturn Object.create(VariantBrowser.prototype);`)(class {}, 200);
      const workspace = {key: 'sample', runId: 'RUN', sample: {sample_id: 1, variant_count: 252},
        items: [{variant_id: 'OLD'}], cursor: null, initialized: false};
      viewer.activeWorkspace = 'sample';
      const rendered = [];
      viewer.renderWorkspace = () => rendered.push(workspace.items.length);
      const tick = () => new Promise(resolve => setImmediate(resolve));
    '''
    result = subprocess.run([node, "-e", setup + '\n(async () => {\n' + script +
                             '\n})().catch(error => {console.error(error);process.exitCode=1;});', str(asset)],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_browser_acquires_every_batch_before_loading_and_displays_all_rows_atomically():
    run_loading_js(r'''
      let release;
      const finalBatch = new Promise(resolve => { release = resolve; });
      const calls = [];
      viewer.request = async (url, options) => {
        calls.push(url);
        assert.equal(options.cache, 'no-store');
        assert.equal(workspace.items.length, 0, 'No provisional priority visible');
        if (url.includes('/priority-evidence?')) {
          assert.equal(options.method, 'POST');
          const after = Number(new URL(url, 'http://test').searchParams.get('after_variant_id'));
          if (after === 250) return finalBatch;
          return {attempted: 50, outcomes: {FOUND: 50}, next_after_variant_id: after + 50};
        }
        assert.ok(url.includes('load_all=true'));
        assert.ok(!url.includes('cursor='));
        return {items: Array.from({length: 252}, (_, i) => ({variant_id: i + 1,
          priority: {normalized_score: 25}})), next_cursor: null,
          clinvar_snapshot_id: 'A', clinvar_status: 'AVAILABLE'};
      };
      const loading = viewer.loadPage(workspace);
      await tick();
      assert.equal(calls.length, 6);
      assert.ok(calls.every(url => url.includes('/priority-evidence?')));
      assert.equal(workspace.items.length, 0);
      assert.equal(workspace.loading, true);
      release({attempted: 2, outcomes: {FOUND: 1, UNAVAILABLE: 1}, next_after_variant_id: null});
      await loading;
      assert.equal(calls.length, 7);
      assert.equal(workspace.items.length, 252);
      assert.equal(workspace.populationEvidenceUnavailable, 1);
      assert.equal(workspace.cursor, null);
      assert.equal(workspace.initialized, true);
      assert.equal(workspace.loading, false);
      assert.ok(rendered.every(count => count === 0 || count === 252));
    ''')


def test_cancelled_preparation_cannot_overwrite_new_load_or_clear_loading_state():
    run_loading_js(r'''
      let releaseOld, releaseNew;
      const oldBatch = new Promise(resolve => {releaseOld = resolve;});
      const newList = new Promise(resolve => {releaseNew = resolve;});
      let batches = 0;
      viewer.request = async url => {
        if (url.includes('/priority-evidence?')) {
          batches++;
          return batches === 1 ? oldBatch : {attempted: 0, outcomes: {}, next_after_variant_id: null};
        }
        return newList;
      };
      const oldLoad = viewer.loadPage(workspace);
      await tick();
      workspace.pageController.abort();
      workspace.loading = false;
      const newLoad = viewer.loadPage(workspace);
      await tick();
      releaseOld({attempted: 50, outcomes: {FOUND: 50}, next_after_variant_id: 50});
      await oldLoad;
      assert.equal(workspace.loading, true);
      assert.equal(workspace.items.length, 0);
      releaseNew({items: [{variant_id: 999}], next_cursor: null, clinvar_snapshot_id: 'B'});
      await newLoad;
      assert.deepEqual(workspace.items.map(item => item.variant_id), [999]);
      assert.equal(workspace.loading, false);
    ''')


def test_preparation_failure_never_displays_old_or_partially_scored_rows():
    run_loading_js(r'''
      viewer.request = async url => {
        assert.ok(url.includes('/priority-evidence?'), 'No list requested before acquisition completes');
        throw new Error('Acquisition failed');
      };
      await viewer.loadPage(workspace);
      assert.equal(workspace.items.length, 0);
      assert.equal(workspace.initialized, false);
      assert.equal(workspace.loading, false);
      assert.equal(workspace.error, 'Acquisition failed');
    ''')


def test_sorting_reuses_all_loaded_rows_scores_and_selected_detail_without_requests():
    run_loading_js(r'''
      workspace.items = [
        {variant_id: 1, gene: 'b', consequence: 'intron_variant', population_af: 0.1,
          priority: {normalized_score: 50, score: 20}},
        {variant_id: 2, gene: '', consequence: '', population_af: null,
          priority: {normalized_score: 50, score: 30}},
        {variant_id: 3, gene: 'A', consequence: 'missense_variant', population_af: 0,
          priority: {normalized_score: 80, score: 40}},
        {variant_id: 4, gene: 'a', consequence: 'intron_variant', population_af: 0.1,
          priority: {normalized_score: 50, score: 20}},
      ];
      workspace.initialized = true;
      workspace.detail = {variant_id: 3};
      const detail = workspace.detail;
      const priorities = new Map(workspace.items.map(item => [item.variant_id, item.priority]));
      viewer.request = () => assert.fail('Sorting must not request evidence or recalculate scores');
      viewer.restartFilteredWorkspace = () => assert.fail('Sorting must not restart loading');
      const ids = () => workspace.items.map(item => item.variant_id);
      for (const [column, first, second] of [
        ['priority', [3, 2, 1, 4], [1, 4, 2, 3]],
        ['gene', [3, 4, 1, 2], [1, 3, 4, 2]],
        ['population_af', [2, 3, 1, 4], [1, 4, 3, 2]],
        ['consequence', [1, 4, 3, 2], [3, 1, 4, 2]],
      ]) {
        workspace.scrollTop = 500;
        viewer.toggleVariantSort(workspace, column);
        assert.deepEqual(ids(), first);
        assert.equal(workspace.scrollTop, 0);
        viewer.toggleVariantSort(workspace, column);
        assert.deepEqual(ids(), second);
        assert.equal(workspace.detail, detail);
        assert.equal(workspace.initialized, true);
        assert.ok(workspace.items.every(item => item.priority === priorities.get(item.variant_id)));
      }
      workspace.items = Array.from({length: 606}, (_, index) => ({variant_id: index+1,
        population_af: (606-index) / 1000, priority: priorities.get(1)}));
      workspace.sort = null;
      viewer.toggleVariantSort(workspace, 'population_af');
      assert.equal(workspace.items.length, 606);
      assert.equal(workspace.items[0].variant_id, 606);
      assert.equal(workspace.items.at(-1).variant_id, 1);
    ''')


def test_reopening_loaded_sample_reuses_the_existing_table():
    run_loading_js(r'''
      workspace.key = 'RUN:1';
      workspace.initialized = true;
      workspace.items = [{variant_id: 9, priority: {normalized_score: 20}}];
      workspace.sort = {key: 'gene', direction: 'desc'};
      workspace.scrollTop = 500;
      const items = workspace.items;
      viewer.selectedRun = 'RUN';
      viewer.workspaces = new Map([[workspace.key, workspace]]);
      viewer.renderTabs = () => {};
      viewer.setRoute = () => {};
      viewer.request = () => assert.fail('Reopening must not fetch or recalculate');
      await viewer.openSample(workspace.sample);
      assert.equal(workspace.items, items);
      assert.equal(workspace.scrollTop, 500);
      assert.deepEqual(workspace.sort, {key: 'gene', direction: 'desc'});
    ''')


def test_sort_changes_during_loading_keep_the_same_acquisition_and_use_the_latest_order():
    run_loading_js(r'''
      let release;
      const pending = new Promise(resolve => {release = resolve;});
      let preparations = 0, reads = 0;
      viewer.request = async url => {
        if (url.includes('/priority-evidence?')) {
          preparations++;
          return pending;
        }
        reads++;
        return {items: [{variant_id: 1, gene: 'B'}, {variant_id: 2, gene: 'A'}], next_cursor: null};
      };
      const loading = viewer.loadPage(workspace);
      const controller = workspace.pageController;
      viewer.toggleVariantSort(workspace, 'gene');
      assert.equal(workspace.pageController, controller);
      assert.equal(controller.signal.aborted, false);
      assert.equal(workspace.loading, true);
      release({attempted: 2, outcomes: {FOUND: 2}, next_after_variant_id: null});
      await loading;
      assert.equal(preparations, 1);
      assert.equal(reads, 1);
      assert.deepEqual(workspace.items.map(item => item.variant_id), [2, 1]);
    ''')


def test_local_filters_match_query_filters_without_requests_or_score_changes(tmp_path):
    database, sample, mother = query_store(tmp_path)
    with store.connect(database) as db:
        db.execute("UPDATE samples SET metadata_json=? WHERE id=?", (
            json.dumps({"analysis_id": "FAM", "father": "FATHER", "mother": "S2"}), sample))
        db.execute("UPDATE samples SET metadata_json=? WHERE id=?", (json.dumps({"analysis_id": "FAM"}), mother))
        run = db.execute("SELECT id FROM runs LIMIT 1").fetchone()[0]
        father = store.register_sample(db, "FATHER", "FATHER", metadata={"analysis_id": "FAM"})
        father_analysis = store.register_analysis(db, "FATHER", run, father, "father")
        mother_analysis = db.execute("SELECT id FROM analyses WHERE sample_id=?", (mother,)).fetchone()[0]
        db.execute("UPDATE calls SET zygosity='het',quality=30")
        db.execute("UPDATE calls SET filter_status='LowQual;strand_bias' WHERE variant_id=2")
        db.execute("UPDATE calls SET filter_status='LOW_DP',quality=NULL WHERE variant_id=3")
        db.execute("UPDATE calls SET zygosity='hom_alt' WHERE variant_id=5")
        db.execute("UPDATE variants SET chromosome='chrX' WHERE id=3")
        db.execute("UPDATE variants SET chromosome='Y' WHERE id=4")
        db.execute("UPDATE variants SET chromosome='chrM' WHERE id=5")
        for variant in (2, 3):
            store.record_call(db, father_analysis, variant, "GATK", "0/1", zygosity="het")
        store.record_call(db, mother_analysis, 3, "GATK", "0/1", zygosity="het")
        release = db.execute("SELECT id FROM annotation_releases LIMIT 1").fetchone()[0]
        store.record_annotation(db, 4, release, gene="GENE1", transcript="TX4", consequence="missense_variant")
        store.record_call(db, mother_analysis, 4, "GATK", "0/1", zygosity="het")
    loaded = query.list_variants(database, sample, load_all=True)["items"]
    cases = [
        {}, {"genes": "GENE1"}, {"genes": "GENE1", "consequences": "intron_variant"},
        {"consequences": "missense_variant,intron_variant"},
        {"max_af": 0.0001}, {"max_af": 0.01, "include_missing_af": False},
        {"max_af": 0.001, "population_frequency": "AFR_AF", "include_missing_af": False},
        {"max_af": 0.001, "population_frequency": "EUR_AF", "include_missing_af": False},
        {"clinical_significances": "pathogenic"}, {"clinical_significances": "__not_reported__"},
        {"filter_mode": "pass"}, {"filter_mode": "selected", "filter_statuses": "LOW_QUAL"},
        {"filter_mode": "exclude", "filter_statuses": "STRAND_BIAS"},
        {"filter_mode": "selected", "filter_statuses": "LOW_DEPTH"},
        {"min_depth": 30}, {"min_vaf": 0.5}, {"min_quality": 20},
        {"min_priority": 20}, {"max_priority": 30}, {"priority_classes": "P1,P2"},
        *[{"inheritance_candidates": candidate} for candidate in (
            "compound", "dominant", "recessive", "x_linked,y_linked", "mitochondrial")],
        *[{"family_evidence": origin} for origin in (
            "de_novo", "father_only", "mother_only", "both_parents", "parental_compound", "father_only,both_parents")],
        {"family_pattern": f"{father}:present,{mother}:absent"},
        {"family_pattern": f"{sample}:present,{father}:absent,{mother}:absent"},
    ]
    field_names = dict(
        genes="genes", consequences="consequences", max_af="maxAf", include_missing_af="includeMissingAf",
        population_frequency="populationFrequency", clinical_significances="clinicalSignificances",
        filter_mode="filterMode", filter_statuses="filterStatuses", min_depth="minDepth", min_vaf="minVaf",
        min_quality="minQuality", min_priority="minPriority", max_priority="maxPriority",
        priority_classes="priorityClasses", inheritance_candidates="inheritanceCandidates",
        family_evidence="familyEvidence", family_pattern="familyPattern",
    )
    array_fields = {"genes", "consequences", "clinical_significances", "filter_statuses", "priority_classes",
                    "inheritance_candidates", "family_evidence", "family_pattern"}
    comparisons = []
    for options in cases:
        expected = query.list_variants(database, sample, **options)["items"]
        comparisons.append(dict(
            filters={field_names[key]: value.split(",") if key in array_fields else value
                     for key, value in options.items()},
            ids=sorted(item["variant_id"] for item in expected),
        ))
    run_loading_js("workspace.allItems = " + json.dumps(loaded) + ";\nconst cases = " + json.dumps(comparisons) + r''';
      workspace.initialized = true;
      const scores = new Map(workspace.allItems.map(item => [item.variant_id, item.priority]));
      viewer.request = () => assert.fail('Filters must not request or recalculate variants');
      for (const test of cases) {
        workspace.filters = {...viewer.emptyFilters(), ...test.filters};
        viewer.restartFilteredWorkspace(workspace);
        assert.deepEqual(workspace.items.map(item => item.variant_id).sort((a,b) => a-b), test.ids,
          JSON.stringify(test.filters));
        assert.ok(workspace.items.every(item => item.priority === scores.get(item.variant_id)));
      }
      viewer.resetFilters(workspace);
      assert.equal(workspace.items.length, workspace.allItems.length);
      assert.ok(workspace.items.every(item => item.priority === scores.get(item.variant_id)));
    ''')


def test_filters_changed_during_loading_do_not_restart_acquisition_or_hide_the_source_rows():
    run_loading_js(r'''
      let release;
      const pending = new Promise(resolve => {release = resolve;});
      let acquisitions = 0, reads = 0;
      viewer.request = async url => {
        if (url.includes('/priority-evidence?')) {acquisitions++; return pending;}
        reads++;
        const params = new URL(url, 'http://test').searchParams;
        assert.equal(params.has('genes'), false, 'Load the full sample regardless of active filters');
        return {items: [{variant_id: 1, gene: 'A'}, {variant_id: 2, gene: 'B'}], next_cursor: null};
      };
      workspace.filters = {...viewer.emptyFilters(), genes: ['A']};
      const loading = viewer.loadPage(workspace);
      const controller = workspace.pageController;
      workspace.filters.genes = ['B'];
      viewer.restartFilteredWorkspace(workspace);
      assert.equal(workspace.pageController, controller);
      assert.equal(controller.signal.aborted, false);
      release({attempted: 2, outcomes: {FOUND: 2}, next_after_variant_id: null});
      await loading;
      assert.equal(acquisitions, 1); assert.equal(reads, 1);
      assert.deepEqual(workspace.items.map(item => item.variant_id), [2]);
      viewer.resetFilters(workspace);
      assert.equal(workspace.items.length, 2);
      assert.equal(reads, 1);
    ''')


def test_gene_tabs_and_selected_details_reuse_the_complete_filtered_sample():
    run_loading_js(r'''
      workspace.allItems = [{variant_id: 1, gene: 'A'}, {variant_id: 2, gene: 'B'}];
      workspace.initialized = true;
      workspace.detail = {variant_id: 2};
      workspace.priorityExplanation = workspace.allItems[1];
      workspace.filters = {...viewer.emptyFilters(), genes: ['A']};
      viewer.request = () => assert.fail('Local filtering and derived gene tabs must reuse existing data');
      viewer.restartFilteredWorkspace(workspace);
      assert.equal(workspace.detail, null);
      assert.equal(workspace.priorityExplanation, null);
      viewer.workspaces = new Map([[workspace.key, workspace]]);
      viewer.renderTabs = () => {};
      viewer.setRoute = () => {};
      await viewer.openGeneWorkspace(workspace, 'B');
      const target = viewer.workspaces.get(viewer.activeWorkspace);
      assert.equal(target.allItems, workspace.allItems);
      assert.deepEqual(target.items.map(item => item.variant_id), [2]);
      viewer.resetFilters(target);
      assert.deepEqual(target.items.map(item => item.variant_id), [2], 'The gene tab stays locked to its gene');
      viewer.resetFilters(workspace);
      assert.equal(workspace.items.length, 2);
    ''')


def test_explicit_evidence_refresh_replaces_source_rows_and_keeps_active_filters():
    run_loading_js(r'''
      let reads = 0, acquisitions = 0;
      viewer.request = async url => {
        if (url.includes('/priority-evidence?')) {
          acquisitions++;
          return {attempted: 2, outcomes: {FOUND: 2}, next_after_variant_id: null};
        }
        reads++;
        return {items: [{variant_id: reads, gene: 'A'}, {variant_id: 100+reads, gene: 'B'}], next_cursor: null};
      };
      workspace.filters = {...viewer.emptyFilters(), genes: ['A']};
      await viewer.loadPage(workspace);
      assert.deepEqual(workspace.items.map(item => item.variant_id), [1]);
      viewer.refreshVariantPriorities(workspace);
      assert.equal(workspace.allItems, null, 'Old rows cannot reappear during a real refresh');
      await tick();
      assert.deepEqual(workspace.items.map(item => item.variant_id), [2]);
      assert.equal(acquisitions, 2); assert.equal(reads, 2);
      viewer.resetFilters(workspace);
      assert.deepEqual(workspace.items.map(item => item.variant_id), [2, 102]);
    ''')


def test_local_clinvar_filters_match_the_installed_snapshot(tmp_path, monkeypatch):
    local_database, _ = build(tmp_path, [summary(
        Chromosome="1", ChromosomeAccession="NC_000001.11", PositionVCF="1",
        ReferenceAlleleVCF="A", AlternateAlleleVCF="G",
    )])
    monkeypatch.setenv("HELPER_CLINVAR_LOCAL_DB", str(local_database))
    database, sample, _ = query_store(tmp_path)
    items = query.list_variants(database, sample, load_all=True)["items"]
    found = next(item for item in items if item["variant_id"] == 1)
    assert found["filter_data"]["clinical_significances"] == ["pathogenic"]
    cases = []
    for label in ("pathogenic", "benign", "__not_reported__", "pathogenic,__not_reported__"):
        cases.append(dict(labels=label.split(","), ids=sorted(item["variant_id"] for item in
            query.list_variants(database, sample, clinical_significances=label)["items"])))
    run_loading_js("workspace.allItems=" + json.dumps(items) + "; const cases=" + json.dumps(cases) + r''';
      workspace.initialized = true;
      viewer.request = () => assert.fail('ClinVar filtering must reuse the loaded snapshot');
      for (const test of cases) {
        workspace.filters = {...viewer.emptyFilters(), clinicalSignificances: test.labels};
        viewer.restartFilteredWorkspace(workspace);
        assert.deepEqual(workspace.items.map(item => item.variant_id).sort((a,b) => a-b), test.ids);
      }
    ''')


def test_real_browser_shows_complete_sample_only_after_evidence_acquisition(tmp_path):
    chrome = shutil.which("google-chrome")
    if chrome is None:
        pytest.skip("Chrome unavailable")
    database, sample, _ = query_store(tmp_path)
    item = query.list_variants(database, sample)["items"][0]
    asset = Path(__file__).resolve().parents[1] / "src/helper_variants/web/static/variant-browser.js"
    html = tmp_path / "sample-loading.html"
    html.write_text('''<!doctype html><meta charset="utf-8"><body><script type="module">
      import {VariantBrowser} from ASSET;
      const assert = (ok, message) => {if (!ok) throw Error(message);};
      try {
        const viewer = new VariantBrowser(); viewer.activated = true;
        document.body.append(viewer); viewer.selectedRun = 'RUN';
        const root = viewer.shadowRoot;
        const style = root.querySelector('link');
        if (!style.sheet) await new Promise((resolve, reject) => {style.onload=resolve;style.onerror=reject;});
        const items = Array.from({length: 606}, (_, index) => ({...ITEM, variant_id: index+1, filter_data: undefined,
          population_af: index / 1000, gene: index % 2 ? 'GENE2' : 'GENE1'}));
        let release;
        const firstBatch = new Promise(resolve => {release = resolve;});
        let reads = 0, preparations = 0;
        viewer.request = async (url, options) => {
          if (url.includes('/priority-evidence?')) {
            preparations++;
            assert(options.method === 'POST', 'Explicit evidence acquisition');
            const after = Number(new URL(url, 'http://test').searchParams.get('after_variant_id'));
            if (after === 0) return firstBatch;
            return {attempted: Math.min(50, 606-after), outcomes: {FOUND: Math.min(50, 606-after)},
              next_after_variant_id: after < 600 ? after+50 : null};
          }
          assert(url.includes('load_all=true'), 'Request the complete sample');
          reads++;
          return {items, next_cursor: null, clinvar_status: 'AVAILABLE', clinvar_snapshot_id: 'TEST'};
        };
        const opening = viewer.openSample({sample_id: 1, display_name: 'Synthetic sample', variant_count: 606}, false);
        await Promise.resolve();
        const workspace = viewer.workspaces.get(viewer.activeWorkspace);
        assert(workspace.items.length === 0 && reads === 0, 'No scores before acquisition finishes');
        assert(!root.querySelector('.variant-row'), 'No provisional row visible');
        assert(root.textContent.includes('Preparing gene-disease and population evidence'), 'Preparation state visible');
        release({attempted: 50, outcomes: {FOUND: 50}, next_after_variant_id: 50});
        await opening;
        await new Promise(resolve => requestAnimationFrame(resolve));
        assert(workspace.items.length === 606, 'All variants loaded beyond page cap');
        assert(workspace.cursor === null && reads === 1, 'No deferred pages');
        assert(root.textContent.includes('606 loaded / 606'), 'Complete sample count');
        assert(root.textContent.includes('All variants loaded · Priority calculated'), 'Calculation completed before display');
        const visible = root.querySelectorAll('.variant-row').length;
        assert(visible > 0 && visible < 606, 'Virtual rendering with all data loaded');
        assert(!root.textContent.includes('Load next page'), 'No manual pagination');
        const prepared = preparations;
        const scores = new Map(workspace.items.map(item => [item.variant_id, item.priority]));
        for (const key of ['gene', 'consequence', 'priority', 'population_af']) {
          root.querySelector(`[data-column="${key}"] .column-sort-button`).click();
          assert(workspace.items.length === 606 && !workspace.loading, 'Sorting keeps the complete table visible');
          assert(reads === 1 && preparations === prepared, 'Header click uses calculated rows without requests');
        }
        assert(workspace.items[0].variant_id === 1, 'AF ascending uses all rows');
        root.querySelector('[data-column="population_af"] .column-sort-button').click();
        assert(workspace.items[0].variant_id === 606, 'AF descending uses all rows');
        assert(workspace.items.every(item => item.priority === scores.get(item.variant_id)), 'Scores remain unchanged');
        root.querySelector('.workspace-tab button').click();
        await viewer.openSample(workspace.sample, false);
        assert(reads === 1 && preparations === prepared, 'Tab activation and reopening reuse the loaded table');
        workspace.filterOptions = {consequences: [], clinical_significances: [],
          population_frequencies: ['MAX_AF'], filter_statuses: []};
        root.querySelector('.filter-toggle').click();
        let form = root.querySelector('.variant-filter-panel');
        form.querySelector('[name="genes"]').value = 'GENE2';
        form.requestSubmit();
        assert(workspace.items.length === 303 && workspace.allItems.length === 606, 'Gene filter preserves the full sample');
        assert(workspace.items.every(item => item.gene === 'GENE2'), 'Gene filter selects matching variants');
        assert(workspace.items[0].variant_id === 606, 'Filter preserves current AF ordering');
        form = root.querySelector('.variant-filter-panel');
        form.querySelector('[name="genes"]').value = 'UNKNOWN_GENE';
        form.requestSubmit();
        assert(workspace.items.length === 0, 'A filter can produce an empty table');
        [...root.querySelectorAll('.variant-filter-panel button')].find(button => button.textContent === 'Clear filters').click();
        assert(workspace.items.length === 606 && workspace.items[0].variant_id === 606, 'Clearing restores all calculated variants and ordering');
        assert(reads === 1 && preparations === prepared, 'Applying and clearing filters make no requests');
        assert(workspace.items.every(item => item.priority === scores.get(item.variant_id)), 'Filtering preserves the score objects');
        await new Promise(resolve => requestAnimationFrame(resolve));
        assert(root.querySelectorAll('.variant-row').length < 606, 'Virtual rendering remains active after sorting');
        document.body.dataset.result = 'PASS';
      } catch (error) {document.body.dataset.result='FAIL';document.body.append(String(error.stack));}
    </script>'''.replace('ASSET', json.dumps(asset.as_uri())).replace('ITEM', json.dumps(item)))
    result = subprocess.run([
        chrome, '--headless=new', '--no-sandbox', '--disable-gpu', '--disable-background-networking',
        '--disable-dev-shm-usage', '--no-first-run', '--allow-file-access-from-files',
        '--host-resolver-rules=MAP * ~NOTFOUND', f'--user-data-dir={tmp_path / "chrome-profile"}',
        '--virtual-time-budget=5000', '--dump-dom', html.as_uri(),
    ], capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr[-1500:]
    assert 'data-result="PASS"' in result.stdout, result.stdout[-5000:]
