"""Real shell/navigation with offline API fixtures and the shipped JS modules."""
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest


def test_data_sources_navigation_details_and_manual_check(tmp_path):
    chrome = shutil.which("google-chrome")
    if not chrome:
        pytest.skip("Chrome unavailable")
    static = Path(__file__).resolve().parents[1] / "src/helper_next/web/static"
    html = (static / "index.html").read_text()
    html = re.sub(r'<script type="module".*?</script>', "", html)
    html = re.sub(r'href="/static/styles.css[^"]*"', 'href="' + (static / "styles.css").as_uri() + '"', html)
    script = r'''
    <script type="module">
    const assert = (value, label) => { if (!value) throw Error(label); };
    const waitFor = async predicate => {
      for (let i=0; i<150; i++) { if (predicate()) return; await new Promise(resolve => setTimeout(resolve, 20)); }
      throw Error('Timed out waiting for UI');
    };
    let checks = 0, reads = 0, updates = 0, updateReads = 0, postpones = 0, confirmation = '', accept = false;
    window.confirm = message => { confirmation = message; return accept; };
    const source = {source_id: 'clinvar', name: 'ClinVar', storage_type: 'SQLite locale',
      installed: true, status: 'installed', version: null, snapshot_id: 'composite-sha256:fixture',
      last_updated: '2026-10-29T12:00:00Z', last_checked: null, update_available: null,
      update_supported: true, details: {backup: {snapshot_id: 'previous'}, note: '<img src=x onerror=alert(1)>'},
      check: {status: 'idle'}, source_url: 'https://www.ncbi.nlm.nih.gov/clinvar/'};
    const vcep = {...source, source_id: 'clingen_vcep_variants',
      name: 'ClinGen — VCEP Variant Classifications', installed: false, status: 'missing',
      snapshot_id: null, last_updated: null, update_supported: false,
      source_url: 'https://erepo.clinicalgenome.org/evrepo/', details: {note:'CACHE-07'}};
    window.fetch = async (url, options={}) => {
      let result = {runs: [], panels: [], pipelines: [], tools: []};
      if (url === '/api/project') result = {root:'/fixture', scripts:[], tool_config_files:[], pipelines:[], gene_panel_designs:[]};
      if (url === '/api/data-sources') result = {sources: [source, vcep]};
      if (url === '/api/data-sources/clinvar/check') {
        assert(options.method === 'POST', 'Only explicit POST starts checks');
        checks++;
        source.check = {status:'running'};
        result = source.check;
      }
      if (url === '/api/data-sources/clinvar/postpone') {
        assert(options.method === 'POST', 'Explicit postpone');
        postpones++;
        source.postpone = {silenced:true, remind_after:'2026-11-09T12:00:00Z'};
        source.notification = false;
        result = source.postpone;
      }
      if (url === '/api/data-sources/clinvar/update') {
        const approved = JSON.parse(options.body);
        assert(options.method === 'POST' && approved.confirmed === true, 'Explicit update confirmation');
        assert(approved.snapshot_id === source.snapshot_id && approved.update_id === source.check.update_id, 'Approval bound to current files');
        updates++;
        source.update = {status:'running', phase:'DOWNLOADING', progress:{filename:'variant_summary.txt.gz',bytes:100,total_bytes:200}};
        source.can_update = source.can_postpone = false;
        result = source.update;
      }
      if (url === '/api/data-sources/clinvar') {
        reads++;
        if (checks && reads >= 2) {
          source.check = {status:'complete', update_id:'ncbi-md5:fixture', files:{
            'variant_summary.txt.gz':{remote_md5:'11111111111111111111111111111111'},
            'submission_summary.txt.gz':{remote_md5:'22222222222222222222222222222222'}}};
          source.update_available = true;
          source.can_update = source.can_postpone = !updates;
          source.notification = !source.postpone?.silenced;
          source.last_checked = '2026-11-02T12:00:00Z';
        }
        if (updates && ++updateReads >= 2) {
          source.details.backup.snapshot_id = source.snapshot_id;
          source.snapshot_id = 'composite-sha256:new';
          source.update = {status:'completed', phase:'COMPLETED'};
          source.update_available = null;
          source.notification = false;
        }
        result = source;
      }
      return {ok:true, json:async()=>structuredClone(result)};
    };
    try {
      await import(APP);
      assert(checks === 0, 'No automatic remote checks');
      document.querySelector('[data-section="data-sources"]').click();
      await waitFor(() => document.querySelectorAll('#data-sources-body tr').length === 2);
      assert(document.querySelector('#data-sources').classList.contains('active'), 'Main menu navigation');
      assert(!document.querySelector('#variants').classList.contains('active'), 'Independent of Variant Browser');
      assert(document.querySelector('#section-title').textContent === 'Data Sources', 'Section title');
      const rows = document.querySelectorAll('#data-sources-body tr');
      assert(rows[1].textContent.includes('Non installato'), 'Real VCEP status');
      assert(rows[1].querySelectorAll('button').length === 1, 'No fake VCEP checker');
      rows[1].querySelector('button').click();
      assert(document.querySelector('#data-sources-detail-fields a').href === vcep.source_url, 'Official ERepo link');
      rows[0].querySelector('button').click();
      assert(document.querySelector('#data-sources-detail-fields').textContent.includes('previous'), 'Backup details');
      assert(!document.querySelector('#data-sources-detail img'), 'Metadata rendered as text');
      rows[0].querySelectorAll('button')[1].click();
      await waitFor(() => checks === 1);
      assert(document.querySelector('#data-sources-body tr').querySelectorAll('button')[1].disabled, 'Duplicate UI requests disabled');
      document.querySelector('[data-section="pipeline"]').click();
      assert(document.querySelector('#pipeline').classList.contains('active'), 'Navigation remains responsive');
      document.querySelector('[data-section="data-sources"]').click();
      await waitFor(() => document.querySelector('#data-sources-body tr').textContent.includes('Disponibile'));
      assert(checks === 1, 'Polling never starts a new remote check');
      assert(!document.querySelector('#data-sources-body tr').querySelectorAll('button')[1].disabled, 'Check can be retried');
      const action = name => [...document.querySelector('#data-sources-body tr').querySelectorAll('button')].find(button => button.textContent === name);
      assert(action('Aggiorna') && action('Posticipa'), 'Supervised actions only after detecting change');
      action('Aggiorna').click();
      await waitFor(() => confirmation !== '');
      assert(confirmation.includes(source.snapshot_id) && confirmation.includes('11111111111111111111111111111111') &&
        confirmation.includes('22222222222222222222222222222222') && confirmation.includes('BACKUP') && confirmation.includes('prioritizzazione'), 'Concrete confirmation');
      assert(updates === 0, 'Cancel never downloads');
      await waitFor(() => !action('Posticipa').disabled);
      action('Posticipa').click();
      await waitFor(() => document.querySelector('#data-sources-body tr').textContent.includes('posticipato'));
      assert(postpones === 1 && updates === 0 && document.querySelector('#data-sources-notice').hidden, 'Persistent postpone notice');
      assert(action('Aggiorna'), 'Postpone keeps manual update available');
      await waitFor(() => !action('Aggiorna').disabled);
      accept = true;
      action('Aggiorna').click();
      await waitFor(() => document.querySelector('#data-sources-body tr').textContent.includes('Download'));
      assert(document.querySelector('#data-sources-body tr').textContent.includes('100 byte / 200'), 'Measured byte progress');
      document.querySelector('[data-section="pipeline"]').click();
      document.querySelector('[data-section="data-sources"]').click();
      await waitFor(() => document.querySelector('#data-sources-body tr').textContent.includes('Aggiornamento completato'));
      assert(updates === 1 && checks === 1, 'Leaving the panel does not duplicate operations');
      assert(document.querySelector('#data-sources-body tr').textContent.includes('composite-sha256:new'), 'Installed snapshot visible');
      document.body.dataset.result = 'PASS';
    } catch (error) {
      document.body.dataset.result = 'FAIL';
      document.body.append(String(error.stack));
    }
    </script>
    '''.replace("APP", json.dumps((static / "app.js").as_uri()))
    page = tmp_path / "data-sources.html"
    page.write_text(html.replace("</body>", script + "</body>"))
    result = subprocess.run([
        chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-background-networking",
        "--disable-dev-shm-usage", "--no-first-run", "--allow-file-access-from-files",
        "--host-resolver-rules=MAP * ~NOTFOUND", "--user-data-dir=" + str(tmp_path / "chrome"),
        "--window-size=1440,1100", "--virtual-time-budget=6000", "--dump-dom", page.as_uri(),
    ], capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr[-2000:]
    assert 'data-result="PASS"' in result.stdout, result.stdout[-6000:]
