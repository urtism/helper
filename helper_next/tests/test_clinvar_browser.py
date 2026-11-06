"""Opt-in real Chrome check of the shipped component, with offline API fixtures."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from helper_next.api import variants as api
from helper_variants import query
from test_clinvar_integration import at, install
from test_clinvar_local import submission
from test_variant_query import query_store


def test_snapshot_change_replaces_complete_list_without_mixing_cached_rows():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable")
    asset = Path(__file__).resolve().parents[1] / "src/helper_variants/web/static/variant-browser.js"
    script = r'''
      const fs = require('node:fs');
      const assert = require('node:assert/strict');
      const source = fs.readFileSync(process.argv[1], 'utf8');
      const method = source.slice(source.indexOf('  async loadPage(workspace) {'),
        source.indexOf('  activeFilterCount(workspace) {')).replace('  emptyFilters()', ', emptyFilters()');
      const viewer = Function('PAGE_SIZE', `return ({${method}})`)(200);
      viewer.renderWorkspace = () => {};
      viewer.updateFilteredVariants = workspace => { workspace.items = workspace.allItems; };
      viewer.preparePriorityEvidence = async () => {};
      let snapshot = 'A';
      const calls = [];
      viewer.request = async (url, options) => {
        calls.push(url);
        assert.equal(options.cache, 'no-store');
        return {clinvar_snapshot_id: snapshot, clinvar_status: 'AVAILABLE',
          items: [{variant_id: snapshot === 'A' ? 1 : 2}], next_cursor: null};
      };
      (async () => {
        const workspace = {items: [], runId: 'RUN', sample: {sample_id: 1}};
        await viewer.loadPage(workspace);
        assert.deepEqual(workspace.items.map(row => row.variant_id), [1]);
        snapshot = 'B';
        workspace.initialized = false;
        await viewer.loadPage(workspace);
        assert.equal(calls.length, 2);
        assert.ok(calls.every(url => url.includes('load_all=true') && !url.includes('cursor=')));
        assert.deepEqual(workspace.items.map(row => row.variant_id), [2]);
        assert.equal(workspace.clinvarSnapshot, 'B');
        assert.equal(workspace.loading, false);
      })().catch(error => { console.error(error); process.exitCode = 1; });
    '''
    result = subprocess.run([node, "-e", script, str(asset)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(os.environ.get("HELPER_TEST_CLINVAR_BROWSER") != "1", reason="Chrome opt-in")
def test_local_evidence_submissions_and_snapshot_change_in_real_browser(tmp_path, monkeypatch):
    chrome = shutil.which("google-chrome")
    if chrome is None:
        pytest.skip("Chrome unavailable")
    install(tmp_path, monkeypatch, [at(1, ClinicalSignificance="Conflicting classifications of pathogenicity",
        ReviewStatus="criteria provided, conflicting classifications")],
        [submission(SCV=f"SCV{i:09d}.1", ClinicalSignificance="Pathogenic" if i <= 70 else "Benign") for i in range(1, 102)])
    path, sample, _ = query_store(tmp_path)
    monkeypatch.setattr(api, "_entry", lambda identifier: {"database": path})
    monkeypatch.setattr(api, "_entry_database", lambda entry: path)
    first = query.list_variants(path, sample, limit=200)
    detail = api.sample_variant_detail("RUN", sample, 1)
    more = api.sample_variant_submissions("RUN", sample, 1, limit=500, offset=100)
    install(tmp_path, monkeypatch, [at(1, ClinicalSignificance="Benign")])
    second = query.list_variants(path, sample, limit=200)
    asset = Path(__file__).resolve().parents[1] / "src/helper_variants/web/static/variant-browser.js"
    payload = json.dumps(dict(first=first, second=second, detail=detail, more=more))
    html = tmp_path / "browser.html"
    html.write_text('''<!doctype html><meta charset="utf-8"><body><script type="module">
      import {VariantBrowser} from ASSET;
      const payload = PAYLOAD;
      const assert = (ok, message) => { if (!ok) throw Error(message); };
      try {
        const viewer = new VariantBrowser();
        viewer.activated = true;
        viewer.runs = [{history_id: "RUN", run_id: "Synthetic offline run"}];
        viewer.selectedRun = "RUN";
        viewer.loadLiftover = viewer.loadGnomadFrequency = viewer.loadCarriers = viewer.loadGenePhenotypes = () => {};
        let changed = false;
        const calls = [];
        viewer.request = async path => {
          calls.push(path);
          if (path.includes("/priority-evidence?")) return {attempted: 5, outcomes: {FOUND: 5}, next_after_variant_id: null};
          if (path.includes("/filter-options")) return {};
          if (path.includes("/clinvar-submissions?")) return structuredClone(payload.more);
          if (path.includes("/variants/1?compact=true")) return structuredClone(payload.detail);
          if (path.includes("/variants?")) return structuredClone(changed ? payload.second : payload.first);
          throw Error("Unexpected request: " + path);
        };
        document.body.append(viewer);
        await viewer.openSample({sample_id: 1, display_name: "Synthetic sample"}, false);
        const workspace = viewer.workspaces.get(viewer.activeWorkspace);
        await viewer.loadDetail(workspace, 1);
        const text = () => viewer.shadowRoot.textContent;
        const section = viewer.shadowRoot.querySelector('.clinvar-disclosure');
        const summary = section.querySelector('summary');
        assert(summary.querySelector('strong').textContent === 'ClinVar', "Concise source heading");
        assert(summary.textContent.includes('Conflicting classifications'), "Conflict in header");
        assert(summary.textContent.includes('★☆☆☆'), "Review stars in header");
        assert(!section.textContent.includes(payload.first.clinvar_snapshot_id), "Technical snapshot ID hidden");
        assert(!section.textContent.includes('Source:') && !section.textContent.includes('Matching:'), "Technical provenance hidden");
        const info = summary.querySelector('button');
        const tooltip = summary.querySelector('[role=tooltip]');
        assert(tooltip.textContent.includes('Local ClinVar snapshot'), "Local provenance in tooltip");
        assert(tooltip.textContent.includes('Snapshot updated:') && !tooltip.textContent.includes('Not available'), "Snapshot date");
        assert(!tooltip.textContent.includes('ClinVar version:'), "No invented release version");
        const wasOpen = section.open;
        info.click();
        assert(section.open === wasOpen, "Info control does not toggle disclosure");
        info.focus();
        assert(getComputedStyle(tooltip).visibility === 'visible', "Tooltip accessible on keyboard focus");
        const badges = section.querySelector('.clinvar-classifications').textContent;
        assert(badges.includes('Pathogenic (70)') && badges.includes('Benign (31)'), "Complete classification counts beyond page");
        assert(!badges.includes('submission'), "Compact detail counts");
        assert(!badges.includes('Conflicting'), "Actual classifications in expanded content");
        assert(!text().includes("Original VCF ClinVar annotation"), "VCF evidence menu removed");
        assert(text().includes("SCV000000001.1"), "Individual SCV");
        assert(text().includes("Hereditary spastic paraplegia 48"), "Conditions");
        const localItem = payload.first.items.find(row => row.variant_id === 1);
        assert(viewer.variantCell(localItem, 'clinvar_local') === 'P(70) B(31)', "Compact table conflict counts");
        assert(viewer.variantCell({clinvar_evidence: {matching_status: 'NOT_FOUND'}}, 'clinvar_local') === '—', "Absent snapshot allele is a dash");
        assert(viewer.clinvarEvidenceStatus({matching_status: 'NOT_FOUND'}) === 'Not found', "ClinVar header uses concise not-found status");
        for (const [label, short] of [['Pathogenic', 'P'], ['Likely pathogenic', 'LP'], ['Uncertain significance', 'VUS'], ['Likely benign', 'LB'], ['Benign', 'B'], ['Pathogenic/Likely pathogenic', 'P/LP']]) {
          assert(viewer.clinvarTableStatus({matching_status: 'FOUND', classifications: [label]}) === short, `Abbreviation for ${label}`);
        }
        assert(viewer.clinvarTableStatus({matching_status: 'FOUND', classifications: ['not provided']}) === '—', "Uninformative classification hidden");
        const benignCounts = {matching_status: 'FOUND', classifications: ['Benign/Likely benign'], submission_classification_breakdown: [
          {label: 'Benign', count: 5}, {label: 'Likely benign', count: 2}, {label: 'not provided', count: 10}]};
        assert(viewer.clinvarTableStatus(benignCounts) === 'B(5) LB(2)', "Benign classes separated using submission counts");
        assert(viewer.clinvarTableStatus({matching_status: 'FOUND', classifications: ['Pathogenic'], submission_classification_breakdown: [{label: 'Pathogenic', count: 4}]}) === 'P(4)', "Single-class submission count");
        const reviewedOnly = viewer.clinvarEvidenceContent({matching_status: 'FOUND', classifications: ['Pathogenic'],
          submission_classification_breakdown: [{label: 'Pathogenic', count: 4}, {label: 'Benign', count: 2}],
          reviewed_submission_classification_breakdown: [{label: 'Pathogenic', count: 1}]});
        assert(reviewedOnly.querySelector('.clinvar-classifications').textContent === 'Pathogenic (1)', "Only reviewed submission classifications in detail");
        const zeroStars = viewer.clinvarEvidenceContent({matching_status: 'FOUND', classifications: ['Pathogenic'], reviewed_submission_classification_breakdown: []});
        assert(!zeroStars.querySelector('.clinvar-classification'), "No aggregate fallback when reviewed submissions absent");
        assert(viewer.columnOrder.includes('clinvar_local') && !viewer.columnOrder.includes('clinical_significance'), "Only local ClinVar column");
        assert(viewer.columnHeader(workspace, 'clinvar_local').textContent.trim().startsWith('ClinVar'), "ClinVar column title");
        const submissionsMenu = section.querySelector('.clinvar-submissions-disclosure');
        assert(submissionsMenu && !submissionsMenu.open, "Submission disclosure initially collapsed");
        assert(!calls.some(path => path.includes('/clinvar-submissions?')), "No extra pages while collapsed");
        submissionsMenu.open = true;
        for (let i = 0; i < 20 && workspace.detail.clinvar_evidence.submissions.length < 101; i++) {
          await new Promise(resolve => setTimeout(resolve, 10));
        }
        assert(submissionsMenu.querySelectorAll('.clinvar-submission-preview').length === 101, "All submissions, including subsequent pages");
        const scroller = submissionsMenu.querySelector('.clinvar-submissions-scroll');
        const cards = [...scroller.children];
        assert(getComputedStyle(scroller).overflowY === 'auto', "Independent submission scroll");
        assert(scroller.clientHeight === 278 && scroller.scrollHeight > scroller.clientHeight, "Compact three-card viewport");
        assert(cards[2].offsetTop + cards[2].offsetHeight - cards[0].offsetTop <= scroller.clientHeight, "First three cards fit");
        const phenotype = cards[0].querySelector('p').getBoundingClientRect();
        const evaluated = cards[0].querySelector('small').getBoundingClientRect();
        assert(evaluated.top - phenotype.bottom <= 3, "No expanded gap before evaluation date");
        assert(evaluated.bottom <= cards[0].getBoundingClientRect().bottom, "Evaluation date fits in compact card");
        scroller.scrollTop = scroller.scrollHeight;
        assert(scroller.scrollTop > 0 && cards.at(-1).textContent.includes('SCV000000101.1'), "Last submission accessible by scrolling");
        const full = [...section.querySelectorAll('a')].find(a => a.textContent.includes('View all submissions'));
        assert(!full, "No duplicate ClinVar footer link");
        const mainLink = section.querySelector('.clinvar-identifiers a');
        assert(mainLink && mainLink.href === 'https://www.ncbi.nlm.nih.gov/clinvar/variation/2/', "Main ClinVar record link");
        assert(getComputedStyle(mainLink).fontSize === '14px', "Prominent ClinVar link");
        assert(!section.textContent.includes('Germline submissions with at least 1 review star, across all conditions.'), "Removed classification explanation");
        const versionInfo = viewer.clinvarSourceInformation({snapshot_id: 'test', provenance: {clinvar_version: '2026-10', imported_at: '2026-10-29T12:00:00Z'}});
        assert(versionInfo.textContent.includes('ClinVar version: 2026-10'), "Declared version displayed");
        const noBreakdown = viewer.clinvarEvidenceContent({has_conflict: true, classifications: ['Conflicting classifications of pathogenicity']});
        assert(!noBreakdown.querySelector('.clinvar-classification'), "No invented conflicting breakdown");
        const noGermline = viewer.clinvarEvidenceContent({clinical_status: 'NO_GERMLINE_CLASSIFICATION', matching_status: 'FOUND', oncogenicity: ['Oncogenic']});
        assert(noGermline.textContent.includes('No germline classification') && noGermline.textContent.includes('Oncogenic'), "Separate somatic evidence");
        changed = true;
        workspace.cursor = 'old-snapshot-page';
        await viewer.loadPage(workspace);
        assert(workspace.clinvarSnapshot === payload.second.clinvar_snapshot_id, "New snapshot active");
        assert(JSON.stringify(workspace.items.map(row => row.variant_id)) === JSON.stringify(payload.second.items.map(row => row.variant_id)), "Old ordering discarded");
        assert(calls.at(-1).includes("/variants?") && !calls.at(-1).includes("cursor="), "Restart from first page after snapshot change");
        document.body.dataset.result = "PASS";
      } catch (error) { document.body.dataset.result = "FAIL"; document.body.append(String(error.stack)); }
      </script>'''.replace("ASSET", json.dumps(asset.as_uri())).replace("PAYLOAD", payload))
    result = subprocess.run([
        chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-background-networking",
        "--disable-dev-shm-usage", "--no-first-run", "--allow-file-access-from-files",
        "--host-resolver-rules=MAP * ~NOTFOUND", f"--user-data-dir={tmp_path / 'chrome-profile'}",
        "--virtual-time-budget=3000", "--dump-dom", html.as_uri(),
    ], capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr[-1000:]
    assert 'data-result="PASS"' in result.stdout, result.stdout[-5000:]
