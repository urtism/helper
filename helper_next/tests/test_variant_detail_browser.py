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
          if(path.includes('/priority-evidence'))return {status:"complete",attempted:5,total:5,outcomes:{FOUND:5}};
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
        const originalColumns=viewer.columnOrder.filter(key=>key!=='acmg_classification');
        localStorage.setItem('helper-variant-column-order-v7',JSON.stringify(originalColumns));
        assert(viewer.loadColumnOrder().includes('acmg_classification'),'New column migrates into saved layouts');
        assert(JSON.stringify(viewer.loadColumnOrder().filter(key=>key!=='acmg_classification'))===JSON.stringify(originalColumns),'Migration retains existing column order');
        const tableItem=workspace.items.find(item=>item.variant_id===1);
        tableItem.acmg_classifications=[{classification:'LIKELY_PATHOGENIC',identity:{disease:'MONDO:1',transcript:'TX.1',inheritance:['AUTOSOMAL_DOMINANT']}}];
        viewer.renderWorkspace();
        await new Promise(resolve=>setTimeout(resolve,0));
        let detailCalls=0;
        const originalLoadDetail=viewer.loadDetail.bind(viewer);
        viewer.loadDetail=(...args)=>{detailCalls++;return originalLoadDetail(...args);};
        const classButton=()=>viewer.shadowRoot.querySelector('.table-acmg-classification[data-variant-id="1"]');
        assert(classButton().textContent==='LP','Table displays only the short HELPER class');
        classButton().click();
        await new Promise(resolve=>setTimeout(resolve,0));
        await new Promise(resolve=>setTimeout(resolve,0));
        assert(detailCalls===1,'Class click does not also trigger the row click');
        let acmg=viewer.shadowRoot.querySelector('.acmg-disclosure');
        assert(acmg.open && viewer.shadowRoot.activeElement===acmg.querySelector('summary'),'Class click opens and focuses ACMG');
        const openedPanel=viewer.shadowRoot.querySelector('.detail-panel');
        acmg.open=false;
        classButton().click();
        assert(acmg.open && viewer.shadowRoot.querySelector('.detail-panel')===openedPanel,'Existing detail opens ACMG without rebuilding');
        await viewer.loadDetail(workspace,1);
        await new Promise(resolve=>setTimeout(resolve,0));
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
        workspace.detail.classificationsError=null;
        workspace.detail.classifications=[
          {classification:'BENIGN',identity:{gene:'HGNC:1',disease:'MONDO:1',transcript:'TX.1',inheritance:[]}},
          {classification:'VUS',identity:{gene:'HGNC:1',disease:'MONDO:2',transcript:'TX.1',inheritance:[]}},
          {classification:'BENIGN',identity:{gene:'HGNC:1',disease:'MONDO:3',transcript:'TX.1',inheritance:[]}}];
        viewer.updateTableClassifications(workspace);
        assert(classButton().textContent==='VUSB','Distinct classes are shown once without arbitrarily choosing a phenotype');
        assert(viewer.shadowRoot.querySelector('.variant-viewport')===table,'Updating classification preserves the table');
        assert(viewer.shadowRoot.activeElement===focused && panel.scrollTop===scrollTop,'Updating table class retains detail focus and scroll');
        tableItem.acmg_classifications=[];
        assert(viewer.variantCellNode(workspace,tableItem,'acmg_classification').querySelector('button').textContent==='—','Unknown is distinct from VUS');
        viewer.transcriptCards=originalTranscriptCards;
        viewer.toggleVariantSort(workspace,'gene');
        const replacement=viewer.shadowRoot.querySelector('.detail-panel');
        assert([...replacement.children].find(item=>item.dataset.disclosureKey==='Transcripts').open,'Sorting preserves transcript disclosure');
        document.body.dataset.result='PASS';
      }catch(error){document.body.dataset.result='FAIL';document.body.append(String(error.stack));}
    </script>'''.replace('ASSET', json.dumps(asset.as_uri())).replace('PAYLOAD', json.dumps(dict(page=page, detail=detail))))
    result = subprocess.run([chrome, '--headless=new', '--no-sandbox', '--disable-gpu',
        '--disable-background-networking', '--disable-dev-shm-usage', '--no-first-run',
        '--run-all-compositor-stages-before-draw', '--disable-renderer-backgrounding',
        '--disable-background-timer-throttling',
        '--allow-file-access-from-files', '--host-resolver-rules=MAP * ~NOTFOUND',
        f'--user-data-dir={tmp_path / "chrome"}', '--virtual-time-budget=5000', '--dump-dom', html.as_uri()],
        capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr[-1500:]
    assert 'data-result="PASS"' in result.stdout, result.stdout[-6000:]


def test_acmg_navigation_reuses_results_and_inflight_requests_in_browser(tmp_path, monkeypatch):
    chrome = shutil.which("google-chrome")
    if chrome is None:
        pytest.skip("Chrome unavailable")
    database, sample, _ = query_store(tmp_path)
    install(tmp_path, monkeypatch, [at(1)])
    monkeypatch.setattr(api, "_entry", lambda identifier: {"database": database})
    monkeypatch.setattr(api, "_entry_database", lambda entry: database)
    page = query.list_variants(database, sample, load_all=True)
    details = {variant: api.sample_variant_detail("RUN", sample, variant, compact=True) for variant in (1, 2)}
    asset = Path(__file__).resolve().parents[1] / "src/helper_variants/web/static/variant-browser.js"
    html = tmp_path / "acmg-loading.html"
    html.write_text('''<!doctype html><meta charset="utf-8"><body><script type="module">
      import {VariantBrowser} from ASSET;
      const payload=PAYLOAD;
      const assert=(ok,message)=>{if(!ok)throw Error(message);};
      try {
        const viewer=new VariantBrowser(); viewer.activated=true; viewer.selectedRun='RUN';
        viewer.loadLiftover=viewer.loadCarriers=viewer.loadGnomadFrequency=()=>{};
        let evaluations=0, detailReads=0, release;
        const delayed=new Promise(resolve=>{release=resolve;});
        window.fetch=async(path,options)=>{
          assert(path==='/api/acmg-calculator/classification/automatic','Only the automatic endpoint is requested');
          const id=JSON.parse(options.body).variant_id; evaluations++;
          if(evaluations===1)await delayed;
          assert(!options.signal.aborted,'Changing variants must not abort shared ACMG work');
          return {ok:true,json:async()=>({items:[],automatic:[],mains:[],context_ready:true})};
        };
        viewer.request=async path=>{
          if(path.includes('/priority-evidence'))return {status:'complete',attempted:5,total:5,outcomes:{FOUND:5}};
          if(path.includes('/variants?'))return structuredClone(payload.page);
          const id=path.match(/\\/variants\\/(\\d+)\\?compact=true/);
          if(id){detailReads++;return structuredClone(payload.details[id[1]]);}
          if(path.includes('/knowledge/gene-phenotypes/'))return {associations:[],cache:{status:'ready'}};
          throw Error('Unexpected request: '+path);
        };
        document.body.append(viewer);
        const sheet=viewer.shadowRoot.querySelector('link');
        if(!sheet.sheet)await new Promise((resolve,reject)=>{sheet.onload=resolve;sheet.onerror=reject;});
        await viewer.openSample({sample_id:1,display_name:'Synthetic sample',variant_count:5},false);
        const workspace=viewer.workspaces.get(viewer.activeWorkspace);
        await viewer.loadDetail(workspace,1);
        assert(evaluations===1,'First variant starts exactly one request');
        await viewer.loadDetail(workspace,2);
        await viewer.loadClassifications(workspace,2);
        await viewer.loadDetail(workspace,1);
        const repeated=viewer.loadClassifications(workspace,1);
        assert(evaluations===2,'Returning during an in-flight request shares it');
        release();await repeated;
        const reads=detailReads;
        await viewer.loadDetail(workspace,1);
        await viewer.loadDetail(workspace,1,{section:'ACMG'});
        assert(detailReads===reads && evaluations===2,'Reclicking a loaded variant retains the detail and ACMG');
        viewer.toggleVariantSort(workspace,'gene');
        await viewer.loadGenePhenotypes(workspace,1);
        await viewer.loadClassifications(workspace,1);
        assert(evaluations===2,'Sorting and source-section refreshes reuse ACMG results');
        workspace.detail.metadata={...workspace.detail.metadata,gnomad_enrichment:{retrieved_at:'updated'}};
        await viewer.loadClassifications(workspace,1);
        assert(evaluations===2,'Population cache metadata does not invalidate ACMG');
        const identity={gene:'HGNC:1',disease:'MONDO:1',transcript:'TX.1',inheritance:[]};
        workspace.detail.classifications=[{identity,classification:'BENIGN'}];viewer.updateTableClassifications(workspace);
        await viewer.loadDetail(workspace,2);await viewer.loadClassifications(workspace,2);
        await viewer.loadDetail(workspace,1);await viewer.loadClassifications(workspace,1);
        assert(evaluations===2 && workspace.detail.classifications[0].classification==='BENIGN','Navigation retains manual saves without extra requests');
        workspace.detail.acmg_revision='changed biological source';
        await viewer.loadClassifications(workspace,1);
        assert(evaluations===3,'A genuine input revision permits one new request');
        document.body.dataset.result='PASS';
      }catch(error){document.body.dataset.result='FAIL';document.body.append(String(error.stack));}
    </script>'''.replace('ASSET', json.dumps(asset.as_uri())).replace('PAYLOAD', json.dumps(dict(page=page, details=details))))
    result = subprocess.run([chrome, '--headless=new', '--no-sandbox', '--disable-gpu',
        '--disable-background-networking', '--disable-dev-shm-usage', '--no-first-run',
        '--run-all-compositor-stages-before-draw', '--disable-renderer-backgrounding', '--disable-background-timer-throttling',
        '--allow-file-access-from-files', '--host-resolver-rules=MAP * ~NOTFOUND',
        f'--user-data-dir={tmp_path / "chrome"}', '--virtual-time-budget=5000', '--dump-dom', html.as_uri()],
        capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr[-1500:]
    assert 'data-result="PASS"' in result.stdout, result.stdout[-6000:]
