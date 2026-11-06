"""Real browser rendering with the existing component/CSS; no network."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from helper_variants import gnomad_frequency as g
from test_gnomad_frequency import ALLELE, official


def test_compact_frequency_table_populations_states_and_cached_detail(tmp_path):
    chrome=shutil.which('google-chrome')
    if chrome is None:
        pytest.skip('Chrome unavailable')
    response=official()['data']
    frequency=g._parse_response({'data':{'variant':response['v0_all']}},g.DATASETS['GRCh38'],ALLELE,'')
    frequency['subsets']={'non_ukb':g._parse_response({'data':{'variant':response['v0_non_ukb']}},g.DATASETS['GRCh38'],ALLELE,'')}
    frequency['datasets']['genomes']['filters']=['RF']
    frequency['datasets']['genomes']['filter']='RF'
    frequency['datasets']['joint']['filter']='EXOMES_FILTERED'
    asset=Path(__file__).resolve().parents[1]/'src/helper_variants/web/static/variant-browser.js'
    html=tmp_path/'gnomad-browser.html'
    html.write_text('''<!doctype html><meta charset="utf-8"><body><script type="module">
    import {VariantBrowser} from ASSET;
    const frequency=PAYLOAD;
    const assert=(ok,text)=>{if(!ok)throw Error(text);};
    try {
      const viewer=new VariantBrowser();viewer.activated=true;
      document.body.append(viewer);
      const root=viewer.shadowRoot;
      const stylesheet=root.querySelector('link');
      if (!stylesheet.sheet) await new Promise((resolve,reject)=>{stylesheet.onload=resolve;stylesheet.onerror=reject;});
      const host=document.createElement('div');host.style.width='420px';
      root.querySelector('.variant-app').replaceChildren(host);
      const card=viewer.gnomadFrequencyCard({gnomadFrequency:frequency});host.append(card);
      const main=card.querySelector('.gnomad-frequency-table');
      assert(main.tBodies[0].rows.length===5,'Exactly five data rows');
      assert(main.tHead.rows[0].cells.length===4,'Three dataset columns');
      assert(card.querySelectorAll('details').length===1,'Single population disclosure');
      const disclosure=card.querySelector('details');
      assert(!disclosure.open,'Population disclosure closed by default');
      assert(card.querySelectorAll('h5').length===1,'Single source title');
      assert(card.querySelectorAll('.detail-cards').length===0,'No per-dataset cards');
      const column=label=>Array.from(main.tHead.rows[0].cells).findIndex(cell=>cell.textContent===label);
      assert(main.rows[4].cells[column('Exomes')].textContent==='0.0165172','Official Grpmax FAF95, with sufficient precision');
      assert(main.rows[1].cells[column('Genomes')].textContent==='RF','Original genome filter');
      assert(main.rows[1].cells[column('Joint')].textContent==='EXOMES_FILTERED','Original joint filter');
      assert(main.rows[1].cells[column('Genomes')].dataset.filter==='other','Discreet non-PASS state');
      assert(getComputedStyle(main.rows[2].cells[1]).textAlign==='right','Right-aligned numerical cells');
      const bounds=main.rows[2].cells[1].getBoundingClientRect();
      assert(Math.abs(bounds.right-main.rows[3].cells[1].getBoundingClientRect().right)<1,'Aligned columns');
      assert(card.scrollWidth<=host.clientWidth+1,'No horizontal overflow');
      assert(card.getBoundingClientRect().height<=210,'Compact panel height');
      disclosure.querySelector('summary').click();
      assert(disclosure.open,'Opens on click');
      const select=disclosure.querySelector('select');
      assert(select.options.length===6,'Three datasets and separate non-UKB subset');
      let populationTable=disclosure.querySelector('table');
      assert(populationTable.tHead.rows[0].cells.length===6,'Six default population columns');
      assert(populationTable.textContent.includes(viewer.populationName('afr')),'Real ancestry groups');
      assert(!populationTable.textContent.includes(viewer.populationName('afr_XX')),'Strata separate from principal groups');
      assert(populationTable.rows[1].cells[4].textContent==='—','Missing population FAF remains null');
      const stratum=disclosure.querySelectorAll('select')[1];stratum.value='XX';stratum.dispatchEvent(new Event('change'));
      assert(populationTable.textContent.includes(viewer.populationName('afr_XX')),'XX data accessible in same disclosure');
      select.value='non_ukb:joint';select.dispatchEvent(new Event('change'));
      assert(populationTable.textContent.includes('No population data'),'Missing non-UKB joint not constructed');
      assert(disclosure.querySelectorAll('details').length===0,'No nested population panels');
      disclosure.querySelector('summary').click();assert(!disclosure.open,'Closes on click');
      for(const width of [360,420,600]){
        host.style.width=width+'px';
        assert(card.scrollWidth<=host.clientWidth+1,'No overflow at '+width);
      }
      const absent=structuredClone(frequency);absent.datasets.exomes={presence:'NOT_OBSERVED',ac:null,an:null,af:null};
      const missing=viewer.gnomadFrequencyCard({gnomadFrequency:absent});
      assert(missing.querySelector('tbody').rows[0].cells[column('Exomes')].textContent==='No variant','Presence is distinct from filter');
      assert(missing.querySelector('tbody').rows[1].cells[column('Exomes')].textContent==='— / —','Null counts do not become zero');
      absent.region_coverage={chromosome:'2',start:975,stop:1026,status:'ADEQUATE',
        datasets:{genomes:{status:'ADEQUATE',mean_min:30,over_20_min:.95,source:'gnomAD v3 genome coverage'}}};
      const coveredMissing=viewer.gnomadFrequencyCard({gnomadFrequency:absent});
      assert(coveredMissing.textContent.includes('Surrounding coverage'),'Regional coverage visible in existing card');
      assert(coveredMissing.textContent.includes('genomes: adequate'),'Coverage status per dataset');
      assert(coveredMissing.textContent.includes('absence unverified'),'Coverage does not claim absence');
      assert(coveredMissing.querySelector('tbody').rows.length===5,'Coverage does not add frequency rows');
      host.append(coveredMissing);
      for(const width of [360,420,600]){
        host.style.width=width+'px';
        assert(coveredMissing.scrollWidth<=host.clientWidth+1,'Coverage note wraps at '+width);
      }
      assert(viewer.frequencyNumber(0)==='0'&&viewer.frequencyNumber(null)==='—','Zero differs from missing');
      assert(viewer.frequencyNumber(.000002702).includes('e-6'),'Small frequencies use scientific notation');
      const duplicate=viewer.populationFrequencyContent([{database:'gnomAD',fields:[]}],{gnomadFrequency:frequency});
      assert(duplicate.querySelectorAll('.frequency-group').length===1,'No duplicate VCF gnomAD panel');
      let frequencyReads=0;
      viewer.loadCarriers=viewer.loadGenePhenotypes=viewer.loadLiftover=()=>{};
      viewer.loadGnomadFrequency=()=>{frequencyReads++;};viewer.renderWorkspace=()=>{};
      viewer.request=async()=>({gnomad_frequency:{...frequency,availability:'AVAILABLE'}});
      const workspace={key:'offline',sample:{sample_id:1},runId:'RUN',items:[]};
      await viewer.loadDetail(workspace,1);
      assert(frequencyReads===0,'Cached detail does not request the frequency endpoint');
      viewer.request=async()=>({gnomad_frequency:{...frequency,availability:'AVAILABLE',region_coverage_pending:true}});
      await viewer.loadDetail(workspace,2);
      assert(frequencyReads===1,'Old cached negative result retrieves missing regional coverage');
      viewer.request=async()=>({gnomad_frequency:{...frequency,availability:'AVAILABLE',non_ukb_pending:true}});
      await viewer.loadDetail(workspace,2);
      assert(frequencyReads===2,'Priority-only data loads the optional subset on detail');
      let priorityRefreshes=0;viewer.refreshVariantPriorities=()=>{priorityRefreshes++;};
      viewer.request=async()=>({cache:'miss',retrieval_status:'NOT_FOUND',region_coverage:absent.region_coverage});
      await VariantBrowser.prototype.loadGnomadFrequency.call(viewer,workspace,2);
      assert(priorityRefreshes===1,'New coverage of a missing allele refreshes priority explanations');
      viewer.request=async()=>({cache:'miss',status:'observed',priority_evidence_changed:false});
      await VariantBrowser.prototype.loadGnomadFrequency.call(viewer,workspace,2);
      assert(priorityRefreshes===1,'Optional subset acquisition preserves the completed Priority list');
      document.body.dataset.result='PASS';
      document.body.dataset.panelHeight=card.getBoundingClientRect().height.toFixed(1);
    } catch(error){document.body.dataset.result='FAIL';document.body.append(String(error.stack));}
    </script>'''.replace('ASSET',json.dumps(asset.as_uri())).replace('PAYLOAD',json.dumps(frequency)))
    result=subprocess.run([chrome,'--headless=new','--no-sandbox','--disable-gpu','--disable-background-networking',
        '--disable-dev-shm-usage','--no-first-run','--allow-file-access-from-files',
        '--host-resolver-rules=MAP * ~NOTFOUND',f'--user-data-dir={tmp_path/"chrome-profile"}',
        '--virtual-time-budget=5000','--dump-dom',html.as_uri()],capture_output=True,text=True,timeout=45)
    assert result.returncode==0,result.stderr[-1500:]
    assert 'data-result="PASS"' in result.stdout,result.stdout[-5000:]
