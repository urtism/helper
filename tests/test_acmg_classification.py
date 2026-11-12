"""Point thresholds, clinical-context isolation and bounded manual persistence."""
import copy
import json
import os
import sqlite3

import pytest
from fastapi import HTTPException

from helper_next.api import acmg_calculator as api
from helper_next.core import acmg_classification as scoring
from helper_next.core import acmg_classification_store as saved
from helper_next.core import acmg_pvs1_store
from helper_next.core.acmg_digest import digest
from test_pvs1_store import indexed  # Shared synthetic run, no molecular references.


def criterion(code, strength="SUPPORTING", **kwargs):
    return dict(code=code, strength=strength, **kwargs)


@pytest.mark.parametrize("points,expected", [(0, "VUS"), (5, "VUS"), (6, "LIKELY_PATHOGENIC"),
    (9, "LIKELY_PATHOGENIC"), (10, "PATHOGENIC"), (-1, "LIKELY_BENIGN"),
    (-6, "LIKELY_BENIGN"), (-7, "BENIGN")])
def test_published_point_boundaries(points, expected):
    # Independent criteria with no reserved/overlapping pair, including mixed directions.
    positive = [criterion("PS3", "STRONG"), criterion("PM3", "MODERATE"), criterion("PM1", "MODERATE"),
                criterion("PP1", "SUPPORTING"), criterion("PP4", "SUPPORTING")]
    negative = [criterion("BS1", "STRONG"), criterion("BP3", "MODERATE"), criterion("BP7", "SUPPORTING")]
    pool = positive if points >= 0 else negative
    remaining, chosen = abs(points), []
    for row in pool:
        weight = scoring.POINTS[row["strength"]]
        if weight <= remaining:
            chosen.append(row); remaining -= weight
    if points == 0:
        chosen = [criterion("PP4"), criterion("BP7")]
    assert remaining == 0
    result = scoring.combine(chosen)
    assert result["total_points"] == points and result["classification"] == expected


def test_empty_is_unassessed_and_ba1_is_standalone_without_fake_points():
    assert scoring.combine([])["classification"] == "NOT_EVALUATED"
    result = scoring.combine([criterion("BA1", "STAND_ALONE")])
    assert result["classification"] == "BENIGN" and result["total_points"] == 0
    conflict = scoring.combine([criterion("BA1", "STAND_ALONE"), criterion("PP4")])
    assert conflict["requires_review"] and conflict["classification"] == "VUS"


@pytest.mark.parametrize("strength,points", list(scoring.POINTS.items()))
def test_symmetric_strength_weights(strength, points):
    assert scoring.combine([criterion("PVS1", strength)])["total_points"] == points
    assert scoring.combine([criterion("BS3", strength)])["total_points"] == -points


@pytest.mark.parametrize("criteria", [[criterion("PP5")], [criterion("BP6")], [criterion("PVS1", "NONE")],
    [criterion("BA1", "VERY_STRONG")], [criterion("PP1"), criterion("PP1")],
    [criterion("PVS1", origin="PVS1_SAVED", pvs1_revision=True)], [criterion("PP1", origin={})],
    [criterion("PP1", source="x" * 1001)], None])
def test_invalid_and_duplicate_evidence_is_rejected(criteria):
    with pytest.raises(ValueError): scoring.combine(criteria)


def test_correlated_evidence_requires_review_and_pm2_defaults_to_supporting():
    for pair in [("PS2", "PM6"), ("PS1", "PM5"), ("PVS1", "PM4"), ("BA1", "BS1")]:
        rows = [criterion(code, "STAND_ALONE" if code == "BA1" else "STRONG") for code in pair]
        assert scoring.combine(rows)["requires_review"]
    rows = [criterion("PVS1", "VERY_STRONG"), criterion("PP3")]
    assert scoring.combine(rows, splice=True)["requires_review"]
    assert not scoring.combine(rows, splice=False)["requires_review"]
    assert next(item for item in scoring.catalog() if item["code"] == "PM2")["default_strength"] == "SUPPORTING"


def identity(**changes):
    return dict(sample="stable", assembly="GRCh38", chromosome="1", position=1100, reference="C", alternate="T",
                transcript="TX.1", gene="HGNC:1", disease="MONDO:1", inheritance=["AUTOSOMAL_DOMINANT"], **changes)


def test_no_database_is_created_by_reading(tmp_path):
    assert saved.latest(tmp_path, identity()) is None and saved.summaries(tmp_path, identity()) == []
    assert saved.batch_summaries(tmp_path, [identity()]) == {}
    assert not acmg_pvs1_store.path(tmp_path).exists()


def test_table_batch_reads_only_latest_heads_and_keeps_contexts_separate(tmp_path):
    context = identity()
    other_disease = {**context, "disease": "MONDO:2"}
    other_sample = {**context, "sample": "another-sample"}
    saved.save(tmp_path, context, "s1", scoring.combine([criterion("PVS1", "VERY_STRONG")]))
    saved.save(tmp_path, context, "s1", scoring.combine([criterion("BA1", "STAND_ALONE")]), expected_revision=1)
    saved.save(tmp_path, other_disease, "s1", scoring.combine([criterion("PP1", note="Private worksheet note", source="Worksheet source")]))
    saved.save(tmp_path, other_sample, "s1", scoring.combine([criterion("PP1")]))
    # Cross the SQL batching boundary; absent alleles cannot inherit another class.
    contexts = [context] + [{**context, "position": position} for position in range(2000, 2410)]
    summaries = saved.batch_summaries(tmp_path, contexts)
    assert set(summaries) == {saved.variant_key(context)}
    records = summaries[saved.variant_key(context)]
    assert {(row["identity"]["disease"], row["classification"], row["revision"]) for row in records} == {
        ("MONDO:1", "BENIGN", 2), ("MONDO:2", "VUS", 1)}
    assert all("assessment" not in row and "criteria" not in row for row in records)
    assert {row["identity"]["disease"]: row["applied_criteria"] for row in records} == {
        "MONDO:1": [dict(code="BA1", strength="STAND_ALONE")],
        "MONDO:2": [dict(code="PP1", strength="SUPPORTING")]}


def test_table_enrichment_uses_stable_sample_and_normalized_allele(selected, monkeypatch):
    from helper_next.api import variants
    run_dir, database, payload = selected
    selection = api.load_classification(payload)
    api.save_classification({**payload, "signature": selection["signature"], "criteria": [criterion("BA1", "STAND_ALONE")]})
    monkeypatch.setattr(api, "calculate_pvs1", lambda *a, **k: pytest.fail("No table PVS1 calculation"))
    monkeypatch.setattr(api, "analyze_transcripts", lambda *a, **k: pytest.fail("No table sequence analysis"))
    item = dict(variant_id=1, reference_build="hg38", chromosome="1", position=1100, reference="C", alternate="T")
    items = [item, {**item, "variant_id": 2, "alternate": "G"}]
    variants._attach_classification_summaries({"record": {"run_dir": run_dir}, "database": database}, 1, items)
    assert len(items[0]["acmg_classifications"]) == 1
    assert items[0]["acmg_classifications"][0]["classification"] == "BENIGN"
    assert items[1]["acmg_classifications"] == []
    variants._attach_classification_summaries({"record": {"run_dir": run_dir}, "database": database}, 99, items)
    assert all(item["acmg_classifications"] == [] for item in items)


def test_revisions_conflicts_and_indexed_heads(tmp_path):
    context, assessment = identity(), scoring.combine([criterion("PVS1", "VERY_STRONG")])
    first = saved.save(tmp_path, context, "s1", assessment)
    assert saved.save(tmp_path, context, "s1", assessment) == first
    with pytest.raises(ValueError, match="altra scheda"):
        saved.save(tmp_path, context, "s1", assessment, "changed", 0)
    for revision in range(1, 35):
        record = saved.save(tmp_path, context, "s1", assessment, str(revision), revision)
    assert record["revision"] == 35 and len(saved.summaries(tmp_path, context)) == 1
    assert "assessment" not in saved.summaries(tmp_path, context)[0]
    with sqlite3.connect(acmg_pvs1_store.path(tmp_path)) as db:
        plan = db.execute("EXPLAIN QUERY PLAN SELECT * FROM classification_heads WHERE variant_key=?", ("k",)).fetchall()
    assert any("classification_variant" in row[3] for row in plan) and all("SCAN" not in row[3] for row in plan)


@pytest.mark.parametrize("field,value", [("sample", "other"), ("assembly", "GRCh37"), ("chromosome", "2"),
    ("position", 1101), ("reference", "G"), ("alternate", "A"), ("transcript", "TX.2"),
    ("gene", "HGNC:2"), ("disease", "MONDO:2"), ("inheritance", ["AUTOSOMAL_RECESSIVE"])])
def test_all_clinical_identity_fields_are_isolated(tmp_path, field, value):
    context = identity()
    saved.save(tmp_path, context, "s1", scoring.combine([criterion("PP1")]))
    assert saved.latest(tmp_path, {**context, field: value}) is None


@pytest.fixture
def selected(indexed, monkeypatch):
    run_dir, db, payload = indexed
    monkeypatch.setenv("HELPER_GENE_PHENOTYPE_DB", str(run_dir / "missing.sqlite"))
    context = {"gene": {"identifier": "HGNC:1", "label": "Synthetic"},
               "disease": {"identifier": "MONDO:1", "label": "Synthetic"}, "inheritance_modes": ["AUTOSOMAL_DOMINANT"]}
    context_id = "context-" + digest(dict(annotation_id=payload["annotation_id"], gene="HGNC:1", disease="MONDO:1"))["value"][:24]
    return run_dir, db, {**payload, "context_id": context_id, "interpretation_context": context}


def test_api_computes_server_score_without_running_biology(selected, monkeypatch):
    run_dir, db, payload = selected
    monkeypatch.setattr(api, "calculate_pvs1", lambda *a, **k: pytest.fail("No PVS1 evaluation"))
    monkeypatch.setattr(api, "analyze_transcripts", lambda *a, **k: pytest.fail("No reference analysis"))
    monkeypatch.setattr(api.acmg_context, "build", lambda *a, **k: pytest.fail("No full context rebuild"))
    loaded = api.load_classification(payload)
    assert loaded["saved"] is None and not acmg_pvs1_store.path(run_dir).exists()
    request = {**payload, "signature": loaded["signature"], "criteria": [criterion("PVS1", "VERY_STRONG"), criterion("PM3", "MODERATE")],
               "classification": "BENIGN", "total_points": -999}
    record = api.save_classification(request)["saved"]
    assert record["assessment"]["classification"] == "PATHOGENIC" and record["assessment"]["total_points"] == 10
    assert api.load_classification(payload)["saved"]["revision"] == 1
    assert len(api.classification_summaries(payload)["items"]) == 1
    with pytest.raises(HTTPException): api.classification_summaries({**payload, "sample_id": 99})
    other = copy.deepcopy(payload)
    other["interpretation_context"]["inheritance_modes"] = ["AUTOSOMAL_RECESSIVE"]
    assert api.load_classification(other)["saved"] is None
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE annotations SET hgvsc='c.101C>T' WHERE id=7")
    assert api.load_classification(payload)["needs_review"]
    with pytest.raises(HTTPException):
        api.save_classification({**request, "expected_revision": 1})


def test_import_only_accepts_current_pvs1_for_exact_context(selected):
    run_dir, db, payload = selected
    run_dir, context, signature = api._saved_selection(payload)
    source = {"result": {"applied_strength": "STRONG", "status": "ACTIVE"}}
    acmg_pvs1_store.save(run_dir, context, signature, source)
    loaded = api.load_classification(payload)
    assert loaded["pvs1"]["strength"] == "STRONG"
    row = criterion("PVS1", "STRONG", origin="PVS1_SAVED", pvs1_revision=1)
    request = {**payload, "signature": loaded["signature"], "criteria": [row]}
    api.save_classification(request)
    with pytest.raises(HTTPException):
        api.save_classification({**request, "criteria": [{**row, "strength": "VERY_STRONG"}], "expected_revision": 1})
    acmg_pvs1_store.save(run_dir, context, signature, source, "new revision")
    assert api.load_classification(payload)["needs_review"]
    with pytest.raises(HTTPException): api.save_classification({**request, "expected_revision": 1})
    other = copy.deepcopy(payload)
    other["interpretation_context"]["inheritance_modes"] = ["AUTOSOMAL_RECESSIVE"]
    assert api.load_classification(other)["pvs1"] is None


def test_save_derives_splice_conflict_from_annotation(selected):
    run_dir, db, payload = selected
    with sqlite3.connect(db) as conn: conn.execute("UPDATE annotations SET consequence='splice_donor_variant' WHERE id=7")
    loaded = api.load_classification(payload)
    request = {**payload, "signature": loaded["signature"], "splice": False,
               "criteria": [criterion("PVS1", "VERY_STRONG"), criterion("PP3")]}
    assessment = api.save_classification(request)["saved"]["assessment"]
    assert assessment["requires_review"] and assessment["classification"] == "VUS"


@pytest.mark.skipif(os.environ.get("HELPER_TEST_CLASSIFICATION_BROWSER") != "1", reason="Opt in to Chrome worksheet check")
@pytest.mark.parametrize("viewport", [(1280, 900), (480, 900)])
def test_phenotype_worksheet_browser(tmp_path, viewport):
    from dataclasses import asdict
    from html.parser import HTMLParser
    from pathlib import Path
    import shutil
    import subprocess
    chrome = shutil.which("google-chrome")
    if not chrome: pytest.skip("Chrome unavailable")
    root = Path(__file__).resolve().parents[1]
    module = (root / "helper_next/src/helper_variants/web/static/variant-browser.js").as_uri()
    from test_pvs1_calculator import sample_fixture
    pvs1_sample = sample_fixture()
    pvs1_response = dict(input=asdict(pvs1_sample), result=asdict(api.calculate_pvs1(pvs1_sample)), evaluation_id="b" * 32, evaluation_signature="s1")
    script = r"""
      const until=async f=>{for(let n=0;n<250;n++){if(f())return;await new Promise(r=>setTimeout(r,10));}throw Error('Timed out');};
      const originalFetch=window.fetch.bind(window), requests=[],pvs1Requests=[], records=new Map();let stale=false,automaticPayload;
      const key=b=>JSON.stringify([b.transcript,b.interpretation_context.disease.identifier,b.interpretation_context.inheritance_modes]);
      const evaluate=criteria=>{
        const weights={SUPPORTING:1,MODERATE:2,STRONG:4,VERY_STRONG:8};
        const points=criteria.reduce((n,r)=>n+(r.code.startsWith('P')?1:-1)*(weights[r.strength]||0),0);
        const classification=!criteria.length?'NOT_EVALUATED':points>=10?'PATHOGENIC':points>=6?'LIKELY_PATHOGENIC':points<0?'LIKELY_BENIGN':'VUS';
        const labels={NOT_EVALUATED:'Non valutata',PATHOGENIC:'P',LIKELY_PATHOGENIC:'LP',VUS:'VUS',LIKELY_BENIGN:'LB'};
        return {criteria,classification,label:labels[classification],total_points:points,warnings:[],requires_review:false};
      };
      window.fetch=async(url,options={})=>{
        if(String(url)==='/api/acmg-calculator/pvs1/saved')return new Response('{"saved":null}',{status:200});
        if(String(url)==='/api/acmg-calculator/pvs1'){
          const b=JSON.parse(options.body);pvs1Requests.push(b);const result=structuredClone(__PVS1__);
          if(b.strength_override){result.strength_override={strength:b.strength_override,automatic_status:result.result.status};
            result.result.applied_strength=b.strength_override==='NONE'?null:b.strength_override;}
          return new Response(JSON.stringify(result),{status:200});
        }
        if(String(url).startsWith('/api/acmg-calculator/classification/')){
          const route=String(url).split('/').pop(),b=JSON.parse(options.body);requests.push({route,body:b});let result;
          if(route==='summaries')result={items:[]};
          if(route==='automatic')result=automaticPayload;
          if(route==='load')result={saved:records.get(key(b))||null,catalog:__CATALOG__,signature:'s1',needs_review:stale,
            pvs1:{strength:'VERY_STRONG',status:'ACTIVE',manual:false,revision:1,needs_review:false},splice:false,
            source_url:__SOURCE__,pm2_source_url:__PM2_SOURCE__};
          if(route==='preview')result=evaluate(b.criteria);
          if(route==='save'){
            const saved={revision:(records.get(key(b))?.revision||0)+1,note:b.note,assessment:evaluate(b.criteria),
              identity:{gene:'HGNC:1',disease:b.interpretation_context.disease.identifier,transcript:b.transcript,inheritance:b.interpretation_context.inheritance_modes},saved_at:'2026-11-11'};
            records.set(key(b),saved);result={saved};
          }
          return new Response(JSON.stringify(result),{status:200});
        }
        if(String(url).startsWith('/api/acmg'))throw Error('Molecular or legacy evaluation unexpectedly called');
        if(String(url).startsWith('/api/'))return new Response('{"runs":[],"items":[]}',{status:200});
        return originalFetch(url,options);
      };
      await import(__MODULE__);
      const {vusSubcategory}=await import(new URL('acmg-classification.js',__MODULE__).href);
      const tierResult=points=>({classification:'VUS',criteria:[{code:'PP4'}],total_points:points,requires_review:false});
      const tierBoundaries=[0,1,2,3,4,5].map(points=>vusSubcategory(tierResult(points)));
      const noTierForUnknown=vusSubcategory({...tierResult(0),criteria:[]})===null;
      const noTierForConflict=vusSubcategory({...tierResult(4),requires_review:true})===null;
      const noTierOutsideVus=vusSubcategory({...tierResult(6),classification:'LIKELY_PATHOGENIC'})===null&&vusSubcategory(tierResult(-1))===null;
      const host=document.querySelector('variant-browser'),shadow=host.shadowRoot;
      const annotations=[7,8].map((id,i)=>({id,gene:'SYNTH',transcript:`TX.${i+1}`,consequence:'stop_gained',metadata:{fields:{HGNC_ID:'HGNC:1'}}}));
      const workspace={key:'worksheet',runId:'run',sample:{sample_id:1},items:[],detail:{variant_id:1,reference_build:'GRCh38',chromosome:'1',position:1100,reference:'C',alternate:'T',
        calls:[],annotations,classifications:[],genePhenotypesLoading:false,
        genePhenotypes:[{gene:'SYNTH',cache:{status:'ready'},associations:['1','2'].map(id=>({disease:'Disease '+id,disease_id:'MONDO:'+id,strongest_classification:'Definitive',inheritance:['AD']}))}],
        interpretation_context:{annotations:annotations.map(an=>({annotation_id:an.id,transcript:an.transcript,gene_symbol:'SYNTH',
          contexts:['1','2'].map(id=>({id:'context-'+an.id+'-'+id,context:{gene:{identifier:'HGNC:1'},disease:{identifier:'MONDO:'+id},inheritance_modes:['AUTOSOMAL_DOMINANT','AUTOSOMAL_RECESSIVE']}}))}))}}};
      host.activeWorkspace=workspace.key;shadow.append(host.renderDetail(workspace));
      window.worksheetDebug=()=>({dialog:shadow.querySelector('#acmg-classification')?.innerText,requests:requests.slice(-3),summaries:workspace.detail.classifications});
      const geneSection=()=>[...shadow.querySelectorAll('.detail-panel > details')].find(item=>item.dataset.disclosureKey==='Gene–phenotype');
      const acmgSection=()=>[...shadow.querySelectorAll('.detail-panel > details')].find(item=>item.dataset.disclosureKey==='ACMG');
      acmgSection().open=true;
      const separateSection=!geneSection().querySelector('button[data-disease]')&&acmgSection().querySelectorAll('button[data-disease]').length===2;
      const initialHeader=acmgSection().querySelector('summary').innerText;
      const button=id=>[...shadow.querySelectorAll('button[data-disease]')].find(item=>item.dataset.disease==='MONDO:'+id);
      if(!button('1')||!button('2'))throw Error('Missing phenotype buttons');
      button('1').focus();button('1').click();await until(()=>shadow.querySelector('#acmg-classification'));
      const tx=()=>shadow.querySelector('#classification-transcript'),inheritance=()=>shadow.querySelector('#classification-inheritance');
      tx().value='7';tx().dispatchEvent(new Event('change'));inheritance().value='AUTOSOMAL_DOMINANT';inheritance().dispatchEvent(new Event('change'));
      await until(()=>shadow.querySelector('#classification-result')?.textContent==='Non valutata');
      await until(()=>shadow.querySelector('link[rel=stylesheet]')?.sheet);
      const initialAdvancedClosed=!shadow.querySelector('.classification-advanced').open;
      const switches=()=>[...shadow.querySelectorAll('[role="switch"][data-criterion-switch]')];
      const allCriteriaVisible=switches().length===26&&switches().every(item=>!item.checked);
      const pathogenic=shadow.querySelector('.classification-criteria-column[data-direction="PATHOGENIC"]');
      const benign=shadow.querySelector('.classification-criteria-column[data-direction="BENIGN"]');
      const groupedCriteria=pathogenic.querySelectorAll('[data-criterion]').length===15&&benign.querySelectorAll('[data-criterion]').length===11;
      const left=pathogenic.getBoundingClientRect(),right=benign.getBoundingClientRect();
      const responsiveColumns=window.innerWidth>850 ? right.left>left.right&&Math.abs(left.top-right.top)<2
        : Math.abs(left.left-right.left)<2&&right.top>left.bottom;
      const inactiveStrengthsDisabled=[...shadow.querySelectorAll('[data-criterion] select')].every(item=>item.disabled);
      const openCriterion=code=>shadow.querySelector(`[data-criterion="${code}"] .classification-criterion-name`).click();
      openCriterion('PS3');
      const criterionOpensWithoutActivation=shadow.querySelector('#classification-panel-PS3')&&!shadow.querySelector('[data-criterion-switch="PS3"]').checked;
      openCriterion('PS3');
      const noDuplicateCriterionTabs=shadow.querySelectorAll('#classification-tab-PS3').length===1;
      shadow.querySelector('[data-criterion-sheet-switch="PS3"]').click();
      await until(()=>shadow.querySelector('#classification-points')?.textContent==='+4 punti');
      const sheetStrength=shadow.querySelector('[aria-label="Strength PS3 nella scheda"]');sheetStrength.value='MODERATE';sheetStrength.dispatchEvent(new Event('change'));
      await until(()=>shadow.querySelector('#classification-points')?.textContent==='+2 punti');
      const sheetNote=shadow.querySelector('[aria-label="Nota PS3 nella scheda"]');sheetNote.value='Criterion tab draft';sheetNote.dispatchEvent(new Event('input'));
      shadow.querySelector('#classification-main-tab').click();openCriterion('BP4');
      const bp4Tab=shadow.querySelector('#classification-tab-BP4');bp4Tab.focus();bp4Tab.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true,cancelable:true}));
      const keyboardSwitchesCriterionTabs=shadow.querySelector('#classification-tab-PS3').getAttribute('aria-selected')==='true';
      const criterionDraftPreserved=shadow.querySelector('[aria-label="Nota PS3 nella scheda"]').value==='Criterion tab draft';
      shadow.querySelector('#classification-main-tab').click();
      const criterionEditsSynchronized=shadow.querySelector('[data-criterion-switch="PS3"]').checked&&shadow.querySelector('[aria-label="Strength PS3"]').value==='MODERATE'&&
        shadow.querySelector('[aria-label="Nota PS3"]').value==='Criterion tab draft';
      shadow.querySelector('[data-criterion-switch="PS3"]').click();
      await until(()=>shadow.querySelector('#classification-result')?.textContent==='Non valutata');
      shadow.querySelector('[aria-label="Chiudi scheda PS3"]').click();shadow.querySelector('[aria-label="Chiudi scheda BP4"]').click();
      const classificationDraftIntact=shadow.querySelector('[role="tablist"]').querySelectorAll('[role="tab"]').length===1&&!pvs1Requests.length;
      shadow.querySelector('#classification-import-pvs1').click();
      await until(()=>shadow.querySelector('#classification-points')?.textContent==='+8 punti');
      const add=code=>{const control=shadow.querySelector(`[data-criterion-switch="${code}"]`);if(!control.checked)control.click();};
      const pvs1Metadata=shadow.querySelector('[data-criterion="PVS1"] details');pvs1Metadata.open=true;
      const pvs1Note=shadow.querySelector('[aria-label="Nota PVS1"]');pvs1Note.value='toggle note';pvs1Note.dispatchEvent(new Event('input'));
      shadow.querySelector('[data-criterion-switch="PVS1"]').click();
      await until(()=>shadow.querySelector('#classification-result')?.textContent==='Non valutata');
      const offRemovesEvidence=requests.filter(item=>item.route==='preview').at(-1).body.criteria.length===0;
      add('PVS1');await until(()=>shadow.querySelector('#classification-points')?.textContent==='+8 punti');
      const toggledEvidence=requests.filter(item=>item.route==='preview').at(-1).body.criteria[0];
      const togglePreservesDetails=toggledEvidence.origin==='PVS1_SAVED'&&toggledEvidence.pvs1_revision===1&&toggledEvidence.note==='toggle note'&&
        shadow.querySelector('[data-criterion="PVS1"] details').open&&shadow.querySelector('[aria-label="Nota PVS1"]').value==='toggle note';
      add('PM2');await until(()=>shadow.querySelector('#classification-points')?.textContent==='+9 punti');
      const pm2Supporting=shadow.querySelector('[data-criterion="PM2"] select').value==='SUPPORTING';
      const pvs1=shadow.querySelector('[aria-label="Strength PVS1"]');pvs1.value='STRONG';pvs1.dispatchEvent(new Event('change'));
      await until(()=>shadow.querySelector('#classification-points')?.textContent==='+5 punti');
      const manualOrigin=requests.filter(r=>r.route==='preview').at(-1).body.criteria.find(r=>r.code==='PVS1').origin;
      const changed=shadow.querySelector('[aria-label="Strength PVS1"]');changed.value='VERY_STRONG';changed.dispatchEvent(new Event('change'));
      await until(()=>shadow.querySelector('#classification-points')?.textContent==='+9 punti');
      add('PP4');await until(()=>shadow.querySelector('#classification-result')?.textContent==='P');
      const advanced=shadow.querySelector('.classification-advanced');advanced.open=true;
      const note=shadow.querySelector('[aria-label="Nota della classificazione"]');note.value='Synthetic note';note.dispatchEvent(new Event('input'));
      const draftBadge=button('1').textContent;
      openCriterion('PS3');shadow.querySelector('#classification-main-tab').click();
      shadow.querySelector('#classification-save').click();
      const tabsLockedWhileSaving=[...shadow.querySelector('[role="tablist"]').querySelectorAll('button')].every(item=>item.disabled);
      await until(()=>shadow.querySelector('#classification-save-status')?.textContent.startsWith('Salvata ·'));
      const savedBadge=button('1').textContent,otherBadge=button('2').textContent;
      const savedHeader=acmgSection().querySelector('summary .acmg-classifications').innerText;
      const headerUsesClinvarStyle=!!acmgSection().querySelector('summary .clinvar-classification.pathogenic');
      const dialog=shadow.querySelector('#acmg-classification'),rectangle=dialog.getBoundingClientRect();
      const overflow=dialog.scrollWidth>dialog.clientWidth+2;
      const focusables=[...dialog.querySelectorAll('button,select,input,textarea,summary,a[href]')].filter(n=>!n.disabled&&n.getClientRects().length);
      focusables.at(-1).focus();document.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',bubbles:true,cancelable:true}));
      const focusTrapped=shadow.activeElement===focusables[0];
      document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
      const focusReturned=shadow.activeElement===button('1');
      button('1').click();await until(()=>shadow.querySelector('#classification-save-status')?.textContent.startsWith('Salvata ·'));
      const restored=shadow.querySelector('[aria-label="Nota della classificazione"]').value;
      inheritance().value='AUTOSOMAL_RECESSIVE';inheritance().dispatchEvent(new Event('change'));
      await until(()=>shadow.querySelector('#classification-result')?.textContent==='Non valutata');
      const recessiveRows=shadow.querySelectorAll('[data-criterion][data-active="true"]').length;
      inheritance().value='AUTOSOMAL_DOMINANT';inheritance().dispatchEvent(new Event('change'));
      await until(()=>shadow.querySelector('#classification-result')?.textContent==='P');
      tx().value='8';tx().dispatchEvent(new Event('change'));inheritance().value='AUTOSOMAL_DOMINANT';inheritance().dispatchEvent(new Event('change'));
      await until(()=>shadow.querySelector('#classification-result')?.textContent==='Non valutata');
      add('BS3');await until(()=>shadow.querySelector('#classification-points')?.textContent==='−4 punti'||shadow.querySelector('#classification-points')?.textContent==='-4 punti');
      shadow.querySelector('#classification-save').click();await until(()=>shadow.querySelector('#classification-save-status')?.textContent.startsWith('Salvata ·'));
      const multipleBadge=button('1').textContent;
      const multiHeader=acmgSection().querySelector('summary .acmg-classifications').innerText;
      const sectionStayedOpen=acmgSection().open;
      const fallbackWorkspace=structuredClone(workspace);fallbackWorkspace.detail.genePhenotypes=[];
      const fallback=host.renderDetail(fallbackWorkspace,'ACMG');
      const fallbackAssociations=fallback.querySelectorAll('button[data-disease]').length;
      document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
      stale=true;button('1').click();await until(()=>shadow.querySelector('#classification-transcript'));
      const requiresTranscriptSelection=tx().value==='';
      tx().value='7';tx().dispatchEvent(new Event('change'));inheritance().value='AUTOSOMAL_DOMINANT';inheritance().dispatchEvent(new Event('change'));
      await until(()=>shadow.querySelector('#classification-save-status')?.textContent.includes('Dati aggiornati'));
      document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
      stale=false;records.clear();
      const autoWorkspace=structuredClone(workspace);autoWorkspace.key='automatic-main';autoWorkspace.detail.classifications=[];
      autoWorkspace.detail.interpretation_context.annotations.forEach(item=>item.contexts.forEach(choice=>choice.context.inheritance_modes=['AUTOSOMAL_DOMINANT']));
      const autoContext=autoWorkspace.detail.interpretation_context.annotations.find(item=>item.annotation_id===7);
      const automaticCriterion={code:'PVS1',strength:'VERY_STRONG',origin:'PVS1_AUTO',pvs1_evaluation_id:'a'.repeat(32),source:'HELPER PVS1 automatico'};
      automaticPayload={items:[],context_ready:true,contexts:autoWorkspace.detail.interpretation_context,
        mains:[{gene:'SYNTH',annotation_id:7,transcript:'TX.1'}],automatic:[{annotation_id:7,context_id:autoContext.contexts[0].id,
          automatic:true,identity:{gene:'HGNC:1',disease:'MONDO:1',transcript:'TX.1',inheritance:['AUTOSOMAL_DOMINANT']},
          assessment:evaluate([automaticCriterion]),pvs1:{status:'ACTIVE',reason:'Synthetic predicted LoF',applied_strength:'VERY_STRONG'}}]};
      host.activeWorkspace=autoWorkspace.key;shadow.querySelector('.detail-panel').replaceWith(host.renderDetail(autoWorkspace));
      await host.loadClassifications(autoWorkspace,1);acmgSection().open=true;
      const automaticBadge=button('1').textContent,automaticOrigin=button('1').dataset.origin;
      const automaticHeader=acmgSection().querySelector('summary').innerText;
      const savesBeforeAutomaticEditing=requests.filter(r=>r.route==='save').length;
      button('1').click();await until(()=>shadow.querySelector('#classification-result')?.textContent==='LP');
      const automaticMainSelection=tx().value==='7'&&inheritance().value==='AUTOSOMAL_DOMINANT';
      const automaticPrefilled=shadow.querySelector('[data-criterion="PVS1"] select').value==='VERY_STRONG'&&shadow.querySelector('#classification-save-status').textContent.includes('automaticamente');
      const automaticStrength=shadow.querySelector('[aria-label="Strength PVS1"]');automaticStrength.value='STRONG';automaticStrength.dispatchEvent(new Event('change'));
      await until(()=>shadow.querySelector('#classification-points')?.textContent==='+4 punti');
      const automaticChangedToManual=requests.filter(r=>r.route==='preview').at(-1).body.criteria[0].origin==='MANUAL'&&
        !requests.filter(r=>r.route==='preview').at(-1).body.criteria[0].pvs1_evaluation_id;
      const vusHighInformative=shadow.querySelector('#classification-vus-subcategory').textContent.includes('VUS (high)')&&
        !shadow.querySelector('#classification-vus-subcategory').hidden&&shadow.querySelector('#classification-result').textContent==='VUS';
      shadow.querySelector('#classification-import-pvs1').click();
      await until(()=>shadow.querySelector('#classification-points')?.textContent==='+8 punti');
      const noVusTierForLp=shadow.querySelector('#classification-vus-subcategory').hidden;
      const automaticRestored=requests.filter(r=>r.route==='preview').at(-1).body.criteria[0].origin==='PVS1_AUTO';
      const strengthAgain=shadow.querySelector('[aria-label="Strength PVS1"]');strengthAgain.value='STRONG';strengthAgain.dispatchEvent(new Event('change'));
      await until(()=>shadow.querySelector('#classification-points')?.textContent==='+4 punti');
      shadow.querySelector('#classification-save').click();await until(()=>shadow.querySelector('#classification-save-status')?.textContent.startsWith('Salvata ·'));
      const manualWinsAutomatic=button('1').dataset.origin==='SAVED'&&button('1').textContent==='VUS';
      document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
      button('1').click();await until(()=>shadow.querySelector('#classification-save-status')?.textContent.startsWith('Salvata ·'));
      const manualRestoredOverAutomatic=shadow.querySelector('[aria-label="Strength PVS1"]').value==='STRONG';
      openCriterion('PVS1');await until(()=>shadow.querySelector('#new-acmg-summary'));
      const pvs1EmbeddedWithoutModal=shadow.querySelectorAll('[role="dialog"]').length===1&&shadow.querySelector('#new-acmg-calculator').closest('#classification-panel-PVS1');
      const pvs1SelectionLocked=shadow.querySelector('#new-acmg-transcript').disabled&&shadow.querySelector('#new-acmg-context').disabled&&
        pvs1Requests.at(-1).annotation_id===7&&pvs1Requests.at(-1).inheritance==='AUTOSOMAL_DOMINANT';
      shadow.querySelector('#classification-main-tab').click();openCriterion('PVS1');
      const pvs1OpenedOnce=pvs1Requests.length===1&&shadow.querySelector('#classification-points').textContent==='+4 punti';
      const evaluatorStrength=shadow.querySelector('#new-acmg-strength');evaluatorStrength.value='MODERATE';evaluatorStrength.dispatchEvent(new Event('change'));
      await until(()=>pvs1Requests.length===2&&!shadow.querySelector('#new-acmg-apply').disabled);
      shadow.querySelector('#new-acmg-apply').click();await until(()=>shadow.querySelector('#classification-points')?.textContent==='+2 punti');
      const pvs1AppliedToClassification=shadow.querySelector('#classification-main-tab').getAttribute('aria-selected')==='true'&&
        shadow.querySelector('[aria-label="Strength PVS1"]').value==='MODERATE'&&requests.filter(r=>r.route==='preview').at(-1).body.criteria[0].origin==='MANUAL';
      tx().value='8';tx().dispatchEvent(new Event('change'));
      await until(()=>shadow.querySelector('#classification-result')?.textContent==='Non valutata');
      const tabsResetForNewContext=shadow.querySelector('[role="tablist"]').querySelectorAll('[role="tab"]').length===1&&!shadow.querySelector('#new-acmg-calculator');
      return {separateSection,initialHeader,savedHeader,headerUsesClinvarStyle,multiHeader,sectionStayedOpen,fallbackAssociations,
        criterionOpensWithoutActivation,noDuplicateCriterionTabs,keyboardSwitchesCriterionTabs,criterionDraftPreserved,criterionEditsSynchronized,classificationDraftIntact,
        tabsLockedWhileSaving,
        pvs1EmbeddedWithoutModal:Boolean(pvs1EmbeddedWithoutModal),pvs1SelectionLocked,pvs1OpenedOnce,pvs1AppliedToClassification,tabsResetForNewContext,
        allCriteriaVisible,groupedCriteria,responsiveColumns,inactiveStrengthsDisabled,offRemovesEvidence,togglePreservesDetails,
        tierBoundaries,noTierForUnknown,noTierForConflict,noTierOutsideVus,vusHighInformative,noVusTierForLp,
        automaticBadge,automaticOrigin,automaticHeader,savesBeforeAutomaticEditing,automaticMainSelection,automaticPrefilled,automaticChangedToManual,automaticRestored,manualWinsAutomatic,manualRestoredOverAutomatic,
        initialAdvancedClosed,pm2Supporting,manualOrigin,draftBadge,savedBadge,otherBadge,overflow,focusTrapped,focusReturned,restored,recessiveRows,multipleBadge,requiresTranscriptSelection,
        withinViewport:rectangle.left>=0&&rectangle.right<=window.innerWidth,saves:requests.filter(r=>r.route==='save').length};
    """.replace('__MODULE__', json.dumps(module)).replace('__CATALOG__', json.dumps(scoring.catalog())).replace('__SOURCE__', json.dumps(scoring.SOURCE)).replace('__PM2_SOURCE__', json.dumps(scoring.PM2_SOURCE)).replace('__PVS1__', json.dumps(pvs1_response))
    page = tmp_path / "classification.html"
    page.write_text('<!doctype html><variant-browser></variant-browser><pre id="check"></pre><script type="module">'
                    '(async()=>{' + script + '})().then(r=>document.querySelector("#check").textContent=JSON.stringify(r))'
                    '.catch(e=>document.querySelector("#check").textContent=JSON.stringify({error:e.stack,debug:window.worksheetDebug?.()}));</script>')
    result = subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--disable-background-networking",
        f"--window-size={viewport[0]},{viewport[1]}", "--force-device-scale-factor=1", "--allow-file-access-from-files",
        "--user-data-dir=" + str(tmp_path / "chrome"), "--dump-dom", "--virtual-time-budget=15000", page.as_uri()], capture_output=True, text=True, timeout=35)
    class Parser(HTMLParser):
        def __init__(self): super().__init__(); self.collect = False; self.value = ""
        def handle_starttag(self, tag, attrs):
            if tag == "pre" and dict(attrs).get("id") == "check": self.collect = True
        def handle_endtag(self, tag):
            if tag == "pre": self.collect = False
        def handle_data(self, text):
            if self.collect: self.value += text
    parser = Parser(); parser.feed(result.stdout)
    assert parser.value, result.stderr[-2000:]
    output = json.loads(parser.value)
    assert "error" not in output, json.dumps(output, ensure_ascii=False)
    assert output["initialAdvancedClosed"] and output["pm2Supporting"] and output["manualOrigin"] == "MANUAL"
    assert output["allCriteriaVisible"] and output["groupedCriteria"] and output["responsiveColumns"] and output["inactiveStrengthsDisabled"]
    assert output["offRemovesEvidence"] and output["togglePreservesDetails"]
    assert output["criterionOpensWithoutActivation"] and output["noDuplicateCriterionTabs"] and output["keyboardSwitchesCriterionTabs"]
    assert output["criterionDraftPreserved"] and output["criterionEditsSynchronized"] and output["classificationDraftIntact"]
    assert output["tabsLockedWhileSaving"]
    assert output["pvs1EmbeddedWithoutModal"] and output["pvs1SelectionLocked"] and output["pvs1OpenedOnce"]
    assert output["pvs1AppliedToClassification"] and output["tabsResetForNewContext"]
    assert output["separateSection"] and "Non valutata" in output["initialHeader"]
    assert output["headerUsesClinvarStyle"] and "P" in output["savedHeader"] and "Non valutata" in output["savedHeader"]
    assert "P" in output["multiHeader"] and "LB" in output["multiHeader"]
    assert output["sectionStayedOpen"] and output["fallbackAssociations"] == 2
    assert output["draftBadge"] == "Non valutata" and output["savedBadge"] == "P" and output["otherBadge"] == "Non valutata"
    assert output["focusTrapped"] and output["focusReturned"] and output["withinViewport"] and not output["overflow"]
    assert output["restored"] == "Synthetic note" and output["recessiveRows"] == 0
    assert output["multipleBadge"] == "2 classificazioni" and output["requiresTranscriptSelection"] and output["saves"] == 3
    assert output["automaticBadge"] == "LP" and output["automaticOrigin"] == "AUTOMATIC"
    assert "LP" in output["automaticHeader"] and output["savesBeforeAutomaticEditing"] == 2
    assert output["automaticMainSelection"] and output["automaticPrefilled"] and output["automaticChangedToManual"] and output["automaticRestored"]
    assert output["manualWinsAutomatic"] and output["manualRestoredOverAutomatic"]
    assert output["tierBoundaries"] == ["low", "low", "mid", "mid", "high", "high"]
    assert output["noTierForUnknown"] and output["noTierForConflict"] and output["noTierOutsideVus"]
    assert output["vusHighInformative"] and output["noVusTierForLp"]
