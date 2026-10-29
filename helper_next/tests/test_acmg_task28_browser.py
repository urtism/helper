"""Real Chrome renderer checks with explicitly synthetic engine-response fixtures."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(os.environ.get("HELPER_TEST_TASK28_BROWSER") != "1", reason="Opt-in local Chrome renderer verification")
def test_pvs1_policy_states_warnings_provenance_and_unchanged_automatic_result(tmp_path):
    chrome = shutil.which("google-chrome")
    if not chrome:
        pytest.skip("Chrome required")
    module = Path(__file__).resolve().parents[1] / "src/helper_variants/web/static/acmg-task22.js"
    script = r'''
import {mountTask22} from MODULE_URI;
const outcome = document.querySelector('#outcome');
try {
  for (const state of ['ACTIVE', 'INACTIVE', 'EXPLORATORY']) {
    const exploratory = state === 'EXPLORATORY';
    const evaluation = {criterion:'PVS1', status:state, active:state==='ACTIVE',
      calculated_strength:state==='INACTIVE'?null:'MODERATE', applied_strength:state==='ACTIVE'?'MODERATE':null,
      classification_eligible:state==='ACTIVE', mechanism:'LOSS_OF_FUNCTION', mechanism_confidence:'INFERRED',
      mechanism_scope:exploratory?'GENE_LEVEL':'DISEASE_SPECIFIC', mechanism_basis:'SYNTHETIC_FIXTURE',
      warnings:state==='INACTIVE'?[]:['Synthetic inferred mechanism warning: clinical review required.'],
      reason:'Synthetic engine rationale', requires_review:state!=='INACTIVE', source_evidence_json:'[{"evidence_id":"fixture","source":"synthetic"}]',
      decision_trace:['SYNTHETIC_MECHANISM_GATE', 'SYNTHETIC_TECHNICAL_BRANCH']};
    const row = {criterion_id:'PVS1', activation_status:state, pvs1_evaluation:evaluation,
      assigned_strength:state==='ACTIVE'?{direction:'PATHOGENIC',level:'MODERATE'}:null,
      rule:{protocol:{protocol:'CLINGEN_GENERAL'},version:'1.0.0',original_definition:'Synthetic fixture only',rule_id:'synthetic'},
      input_evidence_used:['fixture'], compared_values:[{name:'synthetic observed',value:12}],applied_thresholds:[{name:'synthetic threshold',value:50}],
      rationale:'Synthetic engine rationale',warnings:evaluation.warnings,missing_evidence:[],exclusion_reasons:[],execution:{execution_id:'synthetic'}};
    const selection={protocol:'CLINGEN_GENERAL',version:'1.0.0'};
    const result={id:'synthetic-result',kind:'criteria_evaluation',document:{corrections:[],engine_result:{
      protocol:selection,limitations:['Synthetic UI fixture'],criteria:[row],requirements:{requirements:[]}}}};
    const before=JSON.stringify(result);
    globalThis.fetch=async path=>({ok:true,json:async()=>String(path).endsWith('/criteria/evaluate')?result:
      String(path).endsWith('/criteria/artifacts')?{}:{history:[]}});
    const host=document.createElement('section'),status=document.createElement('p'); document.body.append(host,status);
    await mountTask22(host,{id:'synthetic-workspace',document:{original_vcf_evidence:{},normalized_evidence:{snapshot:{context:{transcripts:[]},evidence:[]}}}},
      {protocols:[{selection}],scientific_profiles:[],tree_overrides:[],contract_schema:{$defs:{}},capabilities:{research_execution_enabled:true}},status);
    const run=[...host.querySelectorAll('button')].find(b=>b.textContent==='Evaluate selected variant');
    await run.onclick();
    if(!host.textContent.includes(`PVS1 ${state}`))throw Error('Missing state '+state);
    if(exploratory&&(!host.querySelector('.pvs1-exploratory')||!host.textContent.includes('strength none')))throw Error('Exploratory not distinguished');
    if(state!=='INACTIVE'&&!host.textContent.includes(evaluation.warnings[0]))throw Error('Warning absent from summary');
    const inspect=[...host.querySelectorAll('button')].find(b=>b.textContent==='PVS1');await inspect.onclick();
    if(!host.textContent.includes('SYNTHETIC_MECHANISM_GATE')||!host.textContent.includes('"source": "synthetic"'))throw Error('Trace/provenance unavailable');
    if(JSON.stringify(result)!==before)throw Error('Renderer mutated automatic engine result');
    host.remove();status.remove();
  }
  outcome.textContent='PASS: ACTIVE INACTIVE EXPLORATORY, persistent warnings, provenance, trace, automatic result preserved';
} catch(error) {outcome.textContent='FAIL: '+error.stack;}
'''.replace("MODULE_URI", json.dumps(module.as_uri()))
    page = tmp_path / "task28.html"
    page.write_text('<!doctype html><pre id="outcome">RUNNING</pre><script type="module">' + script + '</script>')
    result = subprocess.run([chrome, '--headless=new', '--no-sandbox', '--no-first-run', '--disable-gpu',
        '--disable-dev-shm-usage', '--allow-file-access-from-files', '--virtual-time-budget=10000', '--dump-dom',
        '--user-data-dir=' + str(tmp_path / 'chrome'), page.as_uri()], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr[-2000:]
    assert '<pre id="outcome">PASS:' in result.stdout, result.stdout[-4000:]
