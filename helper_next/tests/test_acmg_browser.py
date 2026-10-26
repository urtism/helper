"""Opt-in browser workflow with mocked ACMG API; no scientific service required."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest

from helper_next.core.acmg_workbench import CRITERIA, criterion_rows


@pytest.mark.skipif(os.environ.get("HELPER_TEST_ACMG_BROWSER") != "1", reason="Explicit Chrome browser test opt-in required")
def test_criterion_inspection_review_rerun_and_profile_comparison(tmp_path):
    websocket = pytest.importorskip("websocket")
    chrome = shutil.which("google-chrome")
    if not chrome:
        pytest.skip("Google Chrome required for optional browser smoke test")
    port = int(os.environ.get("HELPER_TEST_BROWSER_PORT", "8793"))
    debug_port = int(os.environ.get("HELPER_TEST_BROWSER_DEBUG_PORT", "9293"))
    with socket.socket() as reservation:
        reservation.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        reservation.bind(("127.0.0.1", port))
    root = Path(__file__).resolve().parents[2]
    log = (tmp_path / "services.log").open("w")
    processes = []
    connection = None
    def wait_json(url):
        for _ in range(80):
            try:
                with urlopen(url, timeout=1) as response:
                    return json.load(response)
            except OSError:
                time.sleep(.1)
        raise AssertionError("Local browser test service did not start")
    try:
        processes.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "helper_next.api.app:create_app", "--factory", "--host", "127.0.0.1", "--port", str(port)], cwd=root, stdout=log, stderr=log))
        wait_json("http://127.0.0.1:{}/api/health".format(port))
        processes.append(subprocess.Popen([chrome, "--headless=new", "--no-sandbox", "--no-first-run", "--no-proxy-server", "--disable-dev-shm-usage", "--disable-background-networking", "--remote-debugging-port=" + str(debug_port), "--remote-allow-origins=http://localhost:" + str(debug_port), "--user-data-dir=" + str(tmp_path / "chrome"), "http://127.0.0.1:{}/".format(port)], stdout=log, stderr=log))
        for _ in range(80):
            pages = wait_json("http://127.0.0.1:{}/json/list".format(debug_port))
            page = next((p for p in pages if p.get("type") == "page" and p.get("url", "").startswith("http://127.0.0.1:")), None)
            if page:
                break
            time.sleep(.1)
        assert page, "No HELPER browser tab was created"
        connection = websocket.create_connection(page["webSocketDebuggerUrl"], origin="http://localhost:" + str(debug_port), timeout=30)
        sequence = 0
        def cdp(method, params):
            nonlocal sequence
            sequence += 1
            connection.send(json.dumps({"id": sequence, "method": method, "params": params}))
            while True:
                response = json.loads(connection.recv())
                if response.get("id") == sequence:
                    assert "error" not in response, response
                    return response["result"]
        for _ in range(100):
            loaded = cdp("Runtime.evaluate", {"expression": "Boolean(customElements.get('variant-browser'))", "returnByValue": True})
            if loaded.get("result", {}).get("value") is True:
                break
            time.sleep(.1)
        else:
            page_state = cdp("Runtime.evaluate", {"expression": "JSON.stringify({url:location.href,text:document.body?.innerText.slice(0,1000)})", "returnByValue": True})
            raise AssertionError("Variant browser module did not load: " + str(page_state))
        raw = [{"code": code, "status": "MANUAL_REVIEW_REQUIRED" if code == "PM2" else "INSUFFICIENT_EVIDENCE",
                "activation": "ENABLED", "strength": None, "reason_code": "METHOD_DISCORDANCE" if code == "PM2" else "SYNTHETIC_UI_FIXTURE",
                "explanation": "Synthetic UI fixture, no clinical interpretation", "rules": [], "provenance": {}} for code in CRITERIA]
        raw[6]["population_upper_ci"] = [{"binomial_upper95": "0.00003999991265", "poisson_upper95": "0.00004000054402", "threshold": "0.00004", "method_discordance": True, "primary_candidate_met": True, "sensitivity_candidate_met": False}]
        result = {"result_id": "synthetic", "criterion_results": raw, "classification": {"status": "NOT_CLASSIFIED", "category": None, "included_criteria": [], "effective_strengths": []}}
        fixture = {"engine_result": {"result": result, "evidence_completeness": "INCOMPLETE"}, "rows": criterion_rows(result)}
        script = r'''(async () => {
          const until = async f => {for(let i=0;i<150;i++){if(f())return;await new Promise(r=>setTimeout(r,50));}throw Error('UI wait timed out');};
          await customElements.whenDefined('variant-browser');
          await until(()=>{document.querySelector('[data-section="variants"]').click();return document.querySelector('#variants').classList.contains('active');});
          const browser=document.querySelector('variant-browser');
          const profile={profile_id:'synthetic-base',version:'1',strategy:'CLINGEN_GUIDED',release_status:'EXPERIMENTAL',applicability:{specificity:'NONE'},classification_method:'ACMG_2015_COMBINATORIAL'};
          const config={base_profile:{profile_id:profile.profile_id,version:'1'},specializations:[],strategy:'CLINGEN_GUIDED'};
          const detail={id:1,reference_build:'GRCh38',chromosome:'14',position:100,reference:'A',alternate:'G',annotations:[{id:1,gene:'MYH7',transcript:'ENST1.1',annotator:'SYNTHETIC'}]};
          const packet={snapshot:{variant:{identity:{assembly:'GRCh38',chromosome:'14',position:100,reference:'A',alternate:'G'},normalization:{reference_validated:true},annotations:[],transcript_selection:{transcript:{accession:'ENST1',version:'1'}}},context:{gene:{namespace:'HGNC',identifier:'HGNC:7577'},disease:{namespace:'MONDO',identifier:'MONDO:0005045'},transcripts:[]},evidence:[]},missing_evidence:[]};
          const choice={id:'ctx-one',context:{gene:packet.snapshot.context.gene,disease:{...packet.snapshot.context.disease,label:'Example disease'},inheritance_modes:[]},origin:{source:'SYNTHETIC HELPER cache'},fingerprint:{value:'0'.repeat(64)}};
          detail.interpretation_context={schema_version:'helper-interpretation-context-v1',annotations:[{annotation_id:1,transcript:'ENST1.1',gene:choice.context.gene,status:'READY',contexts:[choice,{...choice,id:'ctx-two',context:{...choice.context,disease:{namespace:'MONDO',identifier:'MONDO:9999999',label:'Other disease'}}}]}]};
          const workspace={id:'mock-workspace',created_at:'2026-10-21',document:{selected_annotation_id:1,context_resolution:choice,original_vcf_evidence:detail,normalized_evidence:packet}};
          const history=[], requests=[]; let counter=0, singleProfile=false, researchEnabled=true;
          const original=window.fetch.bind(window);
          window.fetch=async (url,options={})=>{
            if(!String(url).startsWith('/api/acmg'))return original(url,options);
            const path=String(url).slice('/api/acmg'.length), body=options.body?JSON.parse(options.body):null;
            requests.push({path,body}); let value;
            if(path==='/task22/discovery')return new Response(JSON.stringify({detail:{code:'UNSUPPORTED_TASK22_API',message:'Legacy fixture has no Task 22 API'}}),{status:409,headers:{'Content-Type':'application/json'}});
            if(path==='/discovery')value={capabilities:{research_execution_enabled:researchEnabled},schemas:{},criteria:{criteria:[]}};
            else if(path==='/workspaces'&&body)value=workspace;
            else if(path.startsWith('/workspaces?'))value={workspaces:[]};
            else if(path.endsWith('/profiles'))value={profiles:singleProfile?[profile]:[profile,{...profile,profile_id:'synthetic-other'}]};
            else if(path.endsWith('/interpret')){value={id:'result-'+(++counter),kind:'interpretation',created_at:'2026-10-21',document:{...FIXTURE,packet,configuration:config,parent_id:body.parent_id,corrections:body.corrections}};history.push(value);}
            else if(path.endsWith('/reviews')){value={kind:'review',document:{...body,interpretation_id:path.split('/')[2]}};history.push(value);}
            else if(path.endsWith('/compare')){value={id:'compare-1',kind:'comparison',document:{packet,engine_result:{branches:[{configuration:config,result:FIXTURE.engine_result.result},{configuration:config,result:FIXTURE.engine_result.result}],comparisons:[],not_comparable:[]}}};history.push(value);}
            else value={workspace,history};
            return new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}});
          };
          const {openAcmgWorkbench}=await import('/variant-module/acmg-workbench.js');
          await openAcmgWorkbench(browser,{detail,runId:'mock-source',sample:{sample_id:1}});
          const dialog=browser.shadowRoot.querySelector('.acmg-workbench');
          await until(()=>dialog.querySelector('link').sheet);
          const form=dialog.querySelector('form.acmg-config'), inputs=form.querySelectorAll('input'), selects=form.querySelectorAll('select');
          if(![...inputs].every(i=>i.readOnly)||inputs[1].value!=='HGNC:7577'||inputs[3].value!=='')throw Error('Identifiers must come from HELPER; ambiguous disease must remain unselected');
          if([...inputs].some(i=>i.checkVisibility()))throw Error('Automatic IDs should stay inside collapsed details');
          const diseaseContext=form.querySelector('.acmg-disease-context');
          if(!diseaseContext.checkVisibility())throw Error('Ambiguous disease choice must remain visible');
          diseaseContext.value='ctx-one';diseaseContext.dispatchEvent(new Event('change'));
          if(inputs[3].value!=='MONDO:0005045')throw Error('Disease identifier was not filled automatically');
          form.requestSubmit();
          await until(()=>dialog.querySelector('.acmg-profile-selectors select'));
          if(dialog.querySelector('.acmg-context').open)throw Error('Prepared context should collapse');
          const profiles=dialog.querySelectorAll('.acmg-profile-selectors select');
          const run=[...dialog.querySelectorAll('button')].find(b=>b.textContent==='Classify variant');
          if(!run.disabled)throw Error('Multiple profiles require an explicit choice');
          if(!dialog.querySelector('.acmg-execution-status').textContent.includes('Select a classification profile'))throw Error('Missing profile blocker should be explained');
          if(profiles[1].checkVisibility())throw Error('Empty specialization selector should be hidden');
          profiles[0].value='0';profiles[0].dispatchEvent(new Event('change'));
          if(!dialog.querySelector('.acmg-execution-status').hidden)throw Error('Blocker should clear after selecting a profile');
          run.click();
          await until(()=>dialog.querySelector('.acmg-table-scroll button'));
          const count=dialog.querySelectorAll('.acmg-table-scroll tr').length-1;
          if(dialog.querySelectorAll('.acmg-table-scroll th').length!==6)throw Error('Default criterion table should have six columns');
          const technical=dialog.querySelector('input[type=checkbox]');technical.checked=true;technical.dispatchEvent(new Event('change'));
          if(dialog.querySelectorAll('.acmg-table-scroll th').length!==16)throw Error('Full criterion table should remain available');
          technical.checked=false;technical.dispatchEvent(new Event('change'));
          [...dialog.querySelectorAll('.acmg-table-scroll button')].find(b=>b.textContent==='PM2').click();
          const inspector=dialog.querySelector('.acmg-inspector');
          if(!inspector.textContent.includes('0.00003999991265')||!inspector.textContent.includes('0.00004000054402'))throw Error('Precision lost');
          if(!inspector.textContent.includes('METHOD_DISCORDANCE'))throw Error('Safeguard missing');
          const review=dialog.querySelector('.acmg-review');
          if(review.parentElement.open)throw Error('Review form should open only on request');
          review.parentElement.open=true;review.querySelector('select').value='CONTEST';review.querySelector('textarea').value='Synthetic disagreement';review.requestSubmit();
          await until(()=>requests.some(r=>r.path.endsWith('/reviews')));await until(()=>!dialog.querySelector('.acmg-review'));
          run.click();await until(()=>history.filter(h=>h.kind==='interpretation').length===2);
          await until(()=>dialog.querySelector('a[href$="/export/rerun"]'));
          const comparator=dialog.querySelector('[aria-label="Comparison profile"]');
          if(comparator.checkVisibility())throw Error('Comparison should stay in advanced tools');
          comparator.closest('details').parentElement.open=true;comparator.closest('details').open=true;
          comparator.value='1';comparator.dispatchEvent(new Event('change'));[...dialog.querySelectorAll('button')].find(b=>b.textContent==='Compare Standard vs VCEP').click();
          await until(()=>dialog.querySelector('.acmg-comparison'));
          const prepared=requests.find(r=>r.path==='/workspaces'&&r.body).body;
          const outcome={automatic_ids:prepared.context_id==='ctx-one'&&!('context' in prepared),criteria:count,review:requests.find(r=>r.path.endsWith('/reviews')).body.decision,rerun:requests.filter(r=>r.path.endsWith('/interpret'))[1].body.parent_id,branches:dialog.querySelector('.acmg-comparison').children.length,exports:dialog.querySelectorAll('a[download]').length};
          [...dialog.querySelectorAll('button')].find(b=>b.textContent.includes('interpretation · result-1')).click();
          [...dialog.querySelectorAll('details')].forEach(d=>d.open=false);dialog.scrollTop=0;
          window.acmgUniqueContext=async()=>{
            singleProfile=true;
            detail.interpretation_context.annotations[0].contexts=[choice];
            await openAcmgWorkbench(browser,{detail,runId:'mock-unique-source',sample:{sample_id:1}});
            const form=browser.shadowRoot.querySelector('form.acmg-config');
            if([...form.querySelectorAll('select,input')].some(i=>i.checkVisibility()))throw Error('Unambiguous automatic context should need no fields');
            if(form.querySelector('button[type=submit]').disabled)throw Error('Unique HELPER context should be ready to continue');
            const runs=history.filter(h=>h.kind==='interpretation').length;
            form.requestSubmit();await until(()=>browser.shadowRoot.querySelector('.acmg-profile-selectors select'));
            const dialog=browser.shadowRoot.querySelector('.acmg-workbench');
            if(dialog.querySelector('[aria-label="Classification profile"]').value!=='0')throw Error('Single usable profile should be selected automatically');
            if([...dialog.querySelectorAll('button')].find(b=>b.textContent==='Classify variant').disabled)throw Error('Classification should be ready for the unique profile');
            if(history.filter(h=>h.kind==='interpretation').length!==runs)throw Error('Classification must wait for the user');
            researchEnabled=false;
            await openAcmgWorkbench(browser,{detail,runId:'mock-research-disabled',sample:{sample_id:1}});
            browser.shadowRoot.querySelector('form.acmg-config').requestSubmit();
            await until(()=>browser.shadowRoot.querySelector('.acmg-profile-selectors select'));
            let blocked=browser.shadowRoot.querySelector('.acmg-workbench');
            if(![...blocked.querySelectorAll('button')].find(b=>b.textContent==='Classify variant').disabled)throw Error('Disabled research must block classification');
            if(!blocked.querySelector('.acmg-execution-status').checkVisibility()||!blocked.querySelector('.acmg-execution-status').textContent.includes('Research interpretation is disabled'))throw Error('Disabled research should have a visible explanation');
            researchEnabled=true;packet.snapshot.evidence.push({});packet.snapshot.variant.normalization.reference_validated=false;
            await openAcmgWorkbench(browser,{detail,runId:'mock-reference-missing',sample:{sample_id:1}});
            browser.shadowRoot.querySelector('form.acmg-config').requestSubmit();
            await until(()=>browser.shadowRoot.querySelector('.acmg-profile-selectors select'));
            blocked=browser.shadowRoot.querySelector('.acmg-workbench');
            if(![...blocked.querySelectorAll('button')].find(b=>b.textContent==='Classify variant').disabled)throw Error('Missing reference must still block classification');
            if(!blocked.querySelector('.acmg-execution-status').textContent.includes('PACKET_NORMALIZATION_REQUIRED'))throw Error('Reference blocker should be explained');
          };
          return outcome;
        })()'''.replace("FIXTURE", json.dumps(fixture))
        response = cdp("Runtime.evaluate", {"expression": script, "awaitPromise": True, "returnByValue": True})
        assert "exceptionDetails" not in response, response.get("exceptionDetails", {}).get("exception", {}).get("description", response)
        assert response["result"]["value"] == {"automatic_ids": True, "criteria": 28, "review": "CONTEST", "rerun": "result-1", "branches": 2, "exports": 3}
        cdp("Emulation.setDeviceMetricsOverride", {"width": 1280, "height": 1000, "deviceScaleFactor": 1, "mobile": False})
        if os.environ.get("HELPER_TEST_ACMG_SCREENSHOT"):
            import base64
            screenshot = cdp("Page.captureScreenshot", {"format": "png"})
            Path(os.environ["HELPER_TEST_ACMG_SCREENSHOT"]).write_bytes(base64.b64decode(screenshot["data"]))
        cdp("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
        responsive = cdp("Runtime.evaluate", {"expression": "(()=>{const d=document.querySelector('variant-browser').shadowRoot.querySelector('.acmg-workbench');return d.scrollWidth<=d.clientWidth+1;})()", "returnByValue": True})
        assert responsive["result"]["value"], "Workbench content overflows on a narrow screen"
        unique = cdp("Runtime.evaluate", {"expression": "window.acmgUniqueContext()", "awaitPromise": True, "returnByValue": True})
        assert "exceptionDetails" not in unique, unique
    finally:
        if connection:
            connection.close()
        for process in reversed(processes):
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        log.close()
