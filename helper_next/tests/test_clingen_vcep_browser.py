"""Real Variant Browser component and local API fixtures; network disabled."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from helper_next.api import variants as api
from helper_variants import query, store
from test_variant_query import query_store
from test_clingen_vcep_integration import dataset


def test_vcep_assertions_ambiguity_retraction_and_snapshot_change_in_browser(tmp_path, monkeypatch):
    chrome = shutil.which("google-chrome")
    if chrome is None:
        pytest.skip("Chrome unavailable")
    path, sample, _ = query_store(tmp_path)
    with store.connect(path) as db:
        db.execute("UPDATE annotations SET metadata_json='{}',hgvsc='' WHERE variant_id=1")
    monkeypatch.setattr(api, "_entry", lambda identifier: {"database": path})
    monkeypatch.setattr(api, "_entry_database", lambda entry: path)
    dataset(tmp_path)
    first = api.sample_variant_detail("RUN", sample, 1)
    page = query.list_variants(path, sample)
    dataset(tmp_path, revision=2)
    second = api.sample_variant_detail("RUN", sample, 1)
    asset = Path(__file__).resolve().parents[1] / "src/helper_variants/web/static/variant-browser.js"
    html = tmp_path / "vcep-browser.html"
    html.write_text('''<!doctype html><meta charset="utf-8"><body><script type="module">
      import {VariantBrowser} from ASSET;
      const payload = PAYLOAD;
      const assert = (ok, message) => { if (!ok) throw Error(message); };
      try {
        const viewer = new VariantBrowser();
        viewer.activated = true;
        viewer.runs = [{history_id:"RUN", run_id:"Offline fixture"}];
        viewer.selectedRun = "RUN";
        viewer.loadLiftover = viewer.loadGnomadFrequency = viewer.loadCarriers = viewer.loadGenePhenotypes = () => {};
        let current = payload.first, detailReads = 0;
        viewer.request = async path => {
          if (path.includes('/filter-options')) return {};
          if (path.includes('/variants/1?compact=true')) { detailReads++; return structuredClone(current); }
          if (path.includes('/variants?')) return structuredClone(payload.page);
          throw Error('Unexpected request: ' + path);
        };
        document.body.append(viewer);
        await viewer.openSample({sample_id:1, display_name:'Offline sample'}, false);
        const workspace = viewer.workspaces.get(viewer.activeWorkspace);
        await viewer.loadDetail(workspace, 1);
        const section = () => viewer.shadowRoot.querySelector('.vcep-disclosure');
        assert(section().querySelector('summary strong').textContent === 'ClinGen VCEP — Expert Panel Classifications', 'Distinct source section');
        const info = section().querySelector('.clinvar-source-information');
        assert(info.querySelector('button').getAttribute('aria-label') === 'About the ClinGen VCEP snapshot', 'VCEP snapshot info icon');
        assert(info.querySelector('[role=tooltip]').textContent.includes('Snapshot updated:'), 'VCEP snapshot update date is in the tooltip');
        assert(viewer.shadowRoot.querySelector('.clinvar-disclosure'), 'Existing ClinVar disclosure retained');
        assert(section().querySelectorAll('.vcep-assertion').length === 3, 'All disease/panel assertions');
        assert(section().querySelectorAll('[data-retracted=true]').length === 1, 'Retraction flag');
        const assertion = section().querySelector('.vcep-assertion');
        assert(assertion.querySelector('.clinvar-evidence-heading strong').textContent === 'Classification', 'Classification heading matches ClinVar');
        assert(assertion.querySelector('.clinvar-classification').textContent, 'Classification is displayed as a ClinVar-style badge');
        const fields = [...assertion.querySelectorAll('dt')].map(field => field.textContent);
        assert(fields.includes('Condition') && fields.includes('MOI'), 'Condition and mode of inheritance are labeled');
        assert(assertion.querySelector('.vcep-met-codes .vcep-met-code').textContent.includes('PS3_Strong'), 'Met codes are displayed as badges');
        const text = section().textContent;
        for (const expected of ['Disease 0','Disease 1','Disease 2','MONDO:0000001','Autosomal dominant inheritance',
          'Panel 0','Panel 1','Panel 2','2.1.0','RETRACTED','Unknown — active status not established',
          'Applied Evidence Codes (Met)','Applied Evidence Codes (Not Met)','PS3_Strong','PM2_Supporting',
          'External panel interpretation']) {
          assert(text.includes(expected), 'Visible source fact: ' + expected);
        }
        for (const removed of ['External expert panel classifications and declared criteria',
          'Matching', 'Match methods', 'Reference status', 'Snapshot', 'Clinical context',
          'UNVERIFIED', 'NOT_APPLICABLE']) {
          assert(!section().querySelector('.detail-content').textContent.includes(removed), 'Technical provenance removed: ' + removed);
        }
        assert(!section().querySelector('script'), 'Source narrative rendered as text');
        assert(!section().querySelector('input,select,button:not(.gene-evidence-information-button)'), 'No ACMG criterion activation controls');
        assert([...section().querySelectorAll('a')].some(a => a.href.includes('/evrepo/ui/classification/')), 'Official ERepo link');
        const oldUUID = payload.first.clingen_vcep_evidence.assertions[0].classification_id;
        current = payload.second;
        await viewer.loadDetail(workspace, 1);
        assert(detailReads === 2, 'Reopening fetches current snapshot');
        assert(!section().textContent.includes(payload.second.clingen_vcep_evidence.snapshot_id), 'Snapshot ID remains in tooltip-free display');
        assert(!section().textContent.includes(oldUUID), 'Old UUID references discarded');
        const ambiguous = viewer.vcepEvidenceContent({...payload.first.clingen_vcep_evidence,
          matching_status:'AMBIGUOUS', assertions:[], candidate_assertions:payload.first.clingen_vcep_evidence.assertions});
        assert(ambiguous.textContent.includes('unconfirmed candidates') && ambiguous.textContent.includes('No candidate is selected'), 'Ambiguity explained');
        for (const state of ['NOT_FOUND','UNSUPPORTED','ERROR']) {
          const content = viewer.vcepEvidenceContent({matching_status:state});
          assert(!content.querySelector('.vcep-assertion'), 'No fabricated assertion for ' + state);
          assert(!content.querySelector('.detail-cards'), 'No matching/provenance block for ' + state);
        }
        assert(viewer.vcepEvidenceStatus({matching_status:'NOT_FOUND'}) === 'Not found', 'VCEP header uses concise not-found status');

        current = structuredClone(payload.second);
        current.clingen_vcep_evidence = {matching_status:'NOT_FOUND'};
        current.clinvar_evidence = {matching_status:'NOT_FOUND'};
        await viewer.loadDetail(workspace, 1);
        assert(section().classList.contains('disabled'), 'Not-found VCEP section is disabled');
        assert(section().querySelector('summary').getAttribute('aria-disabled') === 'true', 'Not-found VCEP header is not interactive');
        const clinvarSection = viewer.shadowRoot.querySelector('.clinvar-disclosure');
        assert(clinvarSection.classList.contains('disabled'), 'Not-found ClinVar section is disabled');
        assert(clinvarSection.querySelector('summary').getAttribute('aria-disabled') === 'true', 'Not-found ClinVar header is not interactive');
        document.body.dataset.result = 'PASS';
      } catch(error) { document.body.dataset.result = 'FAIL'; document.body.append(String(error.stack)); }
      </script>'''.replace("ASSET", json.dumps(asset.as_uri())).replace("PAYLOAD", json.dumps(dict(first=first, second=second, page=page)).replace("</", "<\\/")))
    result = subprocess.run([
        chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-background-networking",
        "--disable-dev-shm-usage", "--no-first-run", "--allow-file-access-from-files",
        "--host-resolver-rules=MAP * ~NOTFOUND", f"--user-data-dir={tmp_path / 'chrome-profile'}",
        "--virtual-time-budget=3000", "--dump-dom", html.as_uri(),
    ], capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr[-1500:]
    assert 'data-result="PASS"' in result.stdout, result.stdout[-6000:]
