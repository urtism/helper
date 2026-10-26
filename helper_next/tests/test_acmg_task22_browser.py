"""One optional real-engine browser smoke test, without HTTP mocks."""
import json
import os
import shutil
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest

from test_acmg_task22 import workspace


@pytest.mark.skipif(os.environ.get("HELPER_TEST_TASK22_BROWSER") != "1", reason="Opt-in local Chrome and real Task 22 engine")
def test_real_engine_matrix_graph_and_node_inspector(workspace, tmp_path):
    websocket = pytest.importorskip("websocket")
    chrome = shutil.which("google-chrome")
    if not chrome:
        pytest.skip("Chrome required")
    port, debug = 8813, 9313
    processes, connection = [], None
    def get(url):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with urlopen(url, timeout=1) as response:
                    return json.load(response)
            except OSError:
                time.sleep(.1)
        raise AssertionError("Local browser service not available")
    log = (tmp_path / "services.log").open("w")
    try:
        processes.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "helper_next.api.app:create_app", "--factory", "--host", "127.0.0.1", "--port", str(port)], stdout=log, stderr=log))
        get(f"http://127.0.0.1:{port}/api/health")
        processes.append(subprocess.Popen([chrome, "--headless=new", "--no-sandbox", "--no-first-run", "--no-proxy-server", "--disable-dev-shm-usage", "--disable-background-networking", f"--remote-debugging-port={debug}", f"--remote-allow-origins=http://localhost:{debug}", "--user-data-dir=" + str(tmp_path / "chrome"), f"http://127.0.0.1:{port}/"], stdout=log, stderr=log))
        pages = get(f"http://127.0.0.1:{debug}/json/list")
        page = next(p for p in pages if p["type"] == "page")
        connection = websocket.create_connection(page["webSocketDebuggerUrl"], origin=f"http://localhost:{debug}", timeout=60)
        sequence = 0
        def evaluate(expression, await_promise=False):
            nonlocal sequence
            sequence += 1
            connection.send(json.dumps({"id": sequence, "method": "Runtime.evaluate", "params": {"expression": expression, "awaitPromise": await_promise, "returnByValue": True}}))
            while True:
                message = json.loads(connection.recv())
                if message.get("id") == sequence:
                    return message
        for _ in range(100):
            loaded = evaluate("Boolean(customElements.get('variant-browser'))")
            if loaded.get("result", {}).get("result", {}).get("value") is True:
                break
            time.sleep(.1)
        else:
            raise AssertionError("Variant browser did not load")
        vcf = ('##fileformat=VCFv4.2\n'
               '##INFO=<ID=CSQ,Number=.,Type=String,Description="Format: SYMBOL|Allele|Feature|Consequence|HGVSc|REVEL">\n'
               '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\n'
               '1\t100\t.\tA\tG\t60\tPASS\tCSQ=DEMO|G|ENST000001.1|missense_variant|c.1A>G|0.73\tGT:DP\t0/1:30\n')
        script = r"""(async () => {
          let stage='initial';
          const until = async f => { for(let i=0;i<500;i++){if(await f())return;await new Promise(r=>setTimeout(r,40));}throw Error('UI timed out: '+stage+' · '+document.querySelector('variant-browser').shadowRoot.querySelector('.acmg-workbench .status')?.textContent); };
          const json=async (url,body)=>{const r=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const v=await r.json();if(!r.ok)throw Error(JSON.stringify(v));return v;};
          await customElements.whenDefined('variant-browser');
          const browser=document.querySelector('variant-browser');
          document.querySelector('[data-section="variants"]').click();
          const upload=await fetch('/api/variants/external-sources?assembly=GRCh38',{method:'POST',headers:{'X-VCF-Filename':'task23.vcf'},body:VCF_DATA});
          const source=await upload.json();if(!upload.ok)throw Error(JSON.stringify(source));
          const samples=await json(`/api/variants/runs/${source.source_id}/samples`), sample=samples.samples[0];
          const variants=await json(`/api/variants/runs/${source.source_id}/samples/${sample.sample_id}/variants`);
          const detail=await json(`/api/variants/runs/${source.source_id}/samples/${sample.sample_id}/variants/${variants.items[0].variant_id}`);
          await browser.selectRun(source.source_id,sample.sample_id);
          const variantWorkspace=browser.workspaces.get(browser.activeWorkspace);
          if(variantWorkspace.items.length!==1)throw Error('Standalone VCF not shown in shared variant table');
          variantWorkspace.detail={...detail,variant_id:detail.id};browser.renderWorkspace();
          browser.shadowRoot.querySelector('.acmg-open').click();
          await until(()=>browser.shadowRoot.querySelector('.acmg-workbench'));
          const dialog=browser.shadowRoot.querySelector('.acmg-workbench');
          const runButton=()=>[...dialog.querySelectorAll('button')].find(b=>b.textContent==='Evaluate selected variant');
          stage='discovery'; await until(()=>!dialog.querySelector('.status').textContent.includes('Connecting')&&dialog.querySelector('.status').textContent.includes('Ready'));
          const manual=dialog.querySelector('[aria-label="Use manual interpretation context"]');manual.closest('details').open=true;manual.checked=true;manual.dispatchEvent(new Event('change'));
          dialog.querySelector('[aria-label="Manual gene namespace"]').value=CONTEXT.gene.namespace;
          dialog.querySelector('[aria-label="Manual stable gene identifier"]').value=CONTEXT.gene.identifier;
          dialog.querySelector('[aria-label="Manual disease namespace"]').value=CONTEXT.disease.namespace;
          dialog.querySelector('[aria-label="Manual disease identifier"]').value=CONTEXT.disease.identifier;
          dialog.querySelector('form.acmg-config').requestSubmit();
          await until(()=>[...dialog.querySelectorAll('button')].some(b=>b.textContent==='Evaluate selected variant'));
          const w={id:localStorage.getItem(`helper-acmg:${source.source_id}:${sample.sample_id}:${detail.id}`)};
          [...dialog.querySelectorAll('button')].find(b=>b.textContent==='Evaluate selected variant').click();
          stage='first matrix';await until(()=>dialog.querySelectorAll('.acmg-table-scroll tr').length===29&&!runButton().disabled);
          const inspect=async code=>{
            stage='inspect '+code;
            [...dialog.querySelectorAll('.acmg-table-scroll button')].find(b=>b.textContent===code).click();
            await until(()=>dialog.querySelector('.acmg-inspector h4')?.textContent.startsWith(code)&&dialog.querySelector('.acmg-decision-graph svg')&&!runButton().disabled);
            const svg=dialog.querySelector('.acmg-decision-graph svg'), old=svg.getAttribute('viewBox');
            [...dialog.querySelectorAll('button')].find(b=>b.textContent==='Zoom +').click();
            if(svg.getAttribute('viewBox')===old)throw Error('Zoom did not change viewBox');
            svg.querySelector('g[role=button]').dispatchEvent(new MouseEvent('click',{bubbles:true}));
            await until(()=>dialog.querySelector('.acmg-node-inspector h5')&&!runButton().disabled);
            if(!dialog.querySelector('.acmg-node-inspector').textContent.includes('Scientific definition'))throw Error('Node inspector absent');
          };
          await inspect('PM2'); await inspect('PVS1');
          if(!dialog.textContent.includes('SKIPPED'))throw Error('Skipped nodes not represented');
          await inspect('PM2');
          const form=dialog.querySelector('form.acmg-review');
          form.querySelector('[aria-label="Reviewer identifier"]').value='synthetic-browser-reviewer';
          form.querySelector('[aria-label="Review rationale"]').value='Synthetic browser review';form.requestSubmit();
          await until(()=>dialog.querySelector('.acmg-inspector').textContent.includes('Synthetic browser review')&&!runButton().disabled);
          const choice=dialog.querySelector('[aria-label="Evidence to edit"]');choice.closest('details').open=true;choice.value='0';choice.dispatchEvent(new Event('change'));
          dialog.querySelector('input[aria-label="score"]').value='0.51';dialog.querySelector('[aria-label="Evidence correction reason"]').value='Synthetic browser correction';
          [...dialog.querySelectorAll('button')].find(b=>b.textContent==='Stage evidence change').click();
          if(!dialog.textContent.includes('Synthetic browser correction'))throw Error('Typed correction was not staged');
          [...dialog.querySelectorAll('button')].find(b=>b.textContent==='Evaluate selected variant').click();
          await until(async()=>{const saved=await json(`/api/acmg/workspaces/${w.id}`);return saved.history.filter(e=>e.kind==='criteria_evaluation').length===2;});
          await until(()=>dialog.querySelectorAll('.acmg-table-scroll tr').length===29&&!runButton().disabled);
          const saved=await json(`/api/acmg/workspaces/${w.id}`), runs=saved.history.filter(e=>e.kind==='criteria_evaluation');
          if(runs[0].id===runs[1].id)throw Error('Rerun attempt identity reused');
          const exported=await json(`/api/acmg/results/${runs[1].id}/criteria/export/engine`);
          if(JSON.stringify(exported)!==JSON.stringify(runs[1].document.engine_result))throw Error('Export differs from original engine response');
          [...dialog.querySelectorAll('button')].find(b=>b.textContent==='Compare ACMG 2015 / ClinGen').click();
          await until(()=>[...dialog.querySelectorAll('h4')].some(h=>h.textContent==='Same validated evidence · ACMG 2015 / ClinGen'));
          if(dialog.querySelectorAll('.acmg-table-scroll tr').length!==29)throw Error('Comparison must show 28 criteria');
          return {rows:28,attempts:runs.length,comparison:true};
        })()""".replace("VCF_DATA", json.dumps(vcf)).replace("CONTEXT", json.dumps(workspace["document"]["normalized_evidence"]["snapshot"]["context"]))
        response = evaluate(script, True)
        assert "error" not in response, response
        assert "exceptionDetails" not in response.get("result", {}), response.get("result", {}).get("exceptionDetails", {}).get("exception", {}).get("description", response)
        assert response["result"]["result"]["value"]["rows"] == 28
        assert response["result"]["result"]["value"]["attempts"] == 2
        assert response["result"]["result"]["value"]["comparison"] is True
    finally:
        if connection:
            connection.close()
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        log.close()
