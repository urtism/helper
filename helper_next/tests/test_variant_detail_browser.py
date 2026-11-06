"""Real component: compact decoding and updates preserve the reader's view."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from helper_next.api import variants as api
from helper_variants import query
from test_clinvar_integration import install, at
from test_variant_query import query_store


def test_detail_updates_preserve_table_sections_and_focus_in_browser(tmp_path, monkeypatch):
    chrome = shutil.which("google-chrome")
    if chrome is None:
        pytest.skip("Chrome unavailable")
    database, sample, _ = query_store(tmp_path)
    install(tmp_path, monkeypatch, [at(1)])
    monkeypatch.setattr(api, "_entry", lambda identifier: {"database": database})
    monkeypatch.setattr(api, "_entry_database", lambda entry: database)
    page = query.list_variants(database, sample, load_all=True)
    detail = api.sample_variant_detail("RUN", sample, 1, compact=True)
    asset = Path(__file__).resolve().parents[1] / "src/helper_variants/web/static/variant-browser.js"
    html = tmp_path / "detail.html"
    html.write_text('''<!doctype html><meta charset="utf-8"><body><script type="module">
      import {VariantBrowser} from ASSET;
      const payload=PAYLOAD;
      const assert=(ok,message)=>{if(!ok)throw Error(message);};
      try {
        const viewer=new VariantBrowser(); viewer.activated=true; viewer.selectedRun='RUN';
        viewer.loadLiftover=viewer.loadCarriers=viewer.loadGenePhenotypes=viewer.loadGnomadFrequency=()=>{};
        viewer.request=async path=>{
          if(path.includes('/priority-evidence?'))return {attempted:5,outcomes:{FOUND:5},next_after_variant_id:null};
          if(path.includes('/variants?'))return structuredClone(payload.page);
          if(path.includes('/variants/1?compact=true'))return structuredClone(payload.detail);
          if(path.endsWith('/carriers'))return {same_run:[],historical:[]};
          if(path.endsWith('/liftover'))return {status:'mapped',target:{reference_build:'GRCh37',chromosome:'1',position:1,reference:'A',alternate:'G'}};
          if(path.endsWith('/gnomad-frequency'))return {availability:'UNAVAILABLE',retrieval_status:'ERROR',message:'Fixture unavailable'};
          if(path.includes('/knowledge/gene-phenotypes/'))return {associations:[],cache:{status:'ready'}};
          throw Error('Unexpected request: '+path);
        };
        document.body.append(viewer);
        const stylesheet=viewer.shadowRoot.querySelector('link');
        if(!stylesheet.sheet)await new Promise((resolve,reject)=>{stylesheet.onload=resolve;stylesheet.onerror=reject;});
        await viewer.openSample({sample_id:1,display_name:'Synthetic sample',variant_count:5},false);
        const workspace=viewer.workspaces.get(viewer.activeWorkspace);
        await viewer.loadDetail(workspace,1);
        assert(workspace.detail.annotations.length===2,'Compact detail restores all transcript annotations');
        assert(typeof workspace.detail.annotations[0].release_resources==='object','Release provenance expanded');
        const table=viewer.shadowRoot.querySelector('.variant-viewport');
        const panel=viewer.shadowRoot.querySelector('.detail-panel');
        const section=title=>[...panel.children].find(item=>item.dataset.disclosureKey===title);
        const clinvar=section('ClinVar');const transcripts=section('Transcripts');
        clinvar.open=true;transcripts.open=true;section('Variant carriers').open=true;
        section('Variant details').open=false;
        const focused=clinvar.querySelector('summary'); focused.focus();
        panel.style.maxHeight='250px';panel.style.minHeight='0';panel.scrollTop=80;
        const scrollTop=panel.scrollTop;
        assert(scrollTop>0,'Fixture has a scrollable detail panel');
        const originalTranscriptCards=viewer.transcriptCards;
        viewer.transcriptCards=()=>{throw Error('A source update cannot rebuild transcript cards');};
        await VariantBrowser.prototype.loadCarriers.call(viewer,workspace,1);
        await VariantBrowser.prototype.loadGenePhenotypes.call(viewer,workspace,1);
        await VariantBrowser.prototype.loadGnomadFrequency.call(viewer,workspace,1);
        await VariantBrowser.prototype.loadLiftover.call(viewer,workspace,1);
        assert(viewer.shadowRoot.querySelector('.variant-viewport')===table,'Table DOM retained across source updates');
        assert(viewer.shadowRoot.querySelector('.detail-panel')===panel,'Detail container retained');
        assert(section('ClinVar')===clinvar && section('Transcripts')===transcripts,'Unchanged sections retain their DOM');
        assert(clinvar.open && transcripts.open && section('Variant carriers').open,'Open sections stay open');
        assert(!section('Variant details').open,'A manually collapsed section stays collapsed');
        assert(viewer.shadowRoot.activeElement===focused,'Focus survives background updates');
        assert(panel.scrollTop===scrollTop,'Detail scroll position survives background updates');
        assert(!section('Variant carriers').textContent.includes('Searching indexed runs'),'Only carrier content updates');
        assert(panel.querySelector('.detail-identity').textContent.includes('GRCh37'),'Projected identity updates');
        viewer.transcriptCards=originalTranscriptCards;
        viewer.toggleVariantSort(workspace,'gene');
        const replacement=viewer.shadowRoot.querySelector('.detail-panel');
        assert([...replacement.children].find(item=>item.dataset.disclosureKey==='Transcripts').open,'Sorting preserves transcript disclosure');
        document.body.dataset.result='PASS';
      }catch(error){document.body.dataset.result='FAIL';document.body.append(String(error.stack));}
    </script>'''.replace('ASSET', json.dumps(asset.as_uri())).replace('PAYLOAD', json.dumps(dict(page=page, detail=detail))))
    result = subprocess.run([chrome, '--headless=new', '--no-sandbox', '--disable-gpu',
        '--disable-background-networking', '--disable-dev-shm-usage', '--no-first-run',
        '--allow-file-access-from-files', '--host-resolver-rules=MAP * ~NOTFOUND',
        f'--user-data-dir={tmp_path / "chrome"}', '--virtual-time-budget=5000', '--dump-dom', html.as_uri()],
        capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr[-1500:]
    assert 'data-result="PASS"' in result.stdout, result.stdout[-6000:]
