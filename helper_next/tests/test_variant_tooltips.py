"""Shared tooltip presentation and exact gene/disease display labels."""
import io
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess

import pytest

from helper_variants import gene_phenotype
from test_gene_phenotype import HEADER


def test_acmg_evidence_revision_ignores_unrelated_genes_and_cache_accesses(tmp_path, monkeypatch):
    from helper_next.core.acmg_automatic_store import gene_revision
    database = tmp_path / "knowledge.sqlite3"
    rows = (
        'SGC-1,1,HGNC:1,GENE1,MONDO:1,First phenotype,,,Strong,HP:1,AD,Source,2025-01-01,,,,2025-01-02\n'
        'SGC-2,1,HGNC:2,GENE2,MONDO:2,Other phenotype,,,Strong,HP:1,AR,Source,2025-01-01,,,,2025-01-02\n'
    )
    gene_phenotype.build_cache(io.StringIO(HEADER + rows), database)
    monkeypatch.setenv("HELPER_GENE_PHENOTYPE_DB", str(database))
    original = gene_revision("GENE1", "HGNC:1")
    with sqlite3.connect(database) as db:
        db.execute("UPDATE assertions SET disease_title='Unrelated update' WHERE gene_curie='HGNC:2'")
        db.execute("UPDATE metadata SET value='2099-01-01T00:00:00Z' WHERE key='updated_at'")
    assert gene_revision("GENE1", "HGNC:1") == original
    with sqlite3.connect(database) as db:
        db.execute("UPDATE assertions SET moi_title='AR' WHERE gene_curie='HGNC:1'")
    assert gene_revision("GENE1", "HGNC:1") != original


def test_classification_labels_keep_gene_disease_pairs_separate(tmp_path, monkeypatch):
    database = tmp_path / "knowledge.sqlite3"
    rows = (
        'SGC-1,1,HGNC:1,GENE1,MONDO:1,First phenotype,,,Strong,HP:1,AD,Source,2025-01-01,,,,2025-01-02\n'
        'SGC-2,1,HGNC:2,GENE2,MONDO:1,Other gene phenotype,,,Strong,HP:1,AR,Source,2025-01-01,,,,2025-01-02\n'
    )
    gene_phenotype.build_cache(io.StringIO(HEADER + rows), database)
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO g2p_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            "G2P:1", "HGNC:1", "GENE1", "MONDO:2", "OMIM:2", "Second phenotype",
            "biallelic", "strong", "", "", "", "", "", "", ""))
    identities = [dict(gene="HGNC:1", disease=disease) for disease in ("MONDO:1", "MONDO:2", "OMIM:2", "MONDO:3")]
    labels = gene_phenotype.classification_labels(iter(identities), database)
    assert labels == {
        ("HGNC:1", "MONDO:1"): dict(gene_label="GENE1", disease_label="First phenotype"),
        ("HGNC:1", "MONDO:2"): dict(gene_label="GENE1", disease_label="Second phenotype"),
        ("HGNC:1", "OMIM:2"): dict(gene_label="GENE1", disease_label="Second phenotype"),
    }
    missing = tmp_path / "missing.sqlite3"
    assert gene_phenotype.classification_labels(identities, missing) == {}
    assert not missing.exists()

    # Table enrichment adds labels without loading or evaluating a worksheet.
    from helper_next.api import variants
    from helper_next.core import acmg_classification_store as saved
    from helper_variants import store
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    index = tmp_path / "variants.sqlite3"
    with store.connect(index, "run") as db:
        store.register_sample(db, "sample", "Sample")
    identity = dict(sample="sample", assembly="GRCh38", chromosome="1", position=1,
                    reference="A", alternate="G", gene="HGNC:1", disease="MONDO:1",
                    transcript="TX.1", inheritance=["AUTOSOMAL_DOMINANT"])
    saved.save(run_dir, identity, "signature", dict(classification="BENIGN", total_points=0, requires_review=False,
        criteria=[dict(code="BA1", strength="STAND_ALONE", note="Worksheet-only note")]))
    monkeypatch.setenv("HELPER_GENE_PHENOTYPE_DB", str(database))
    items = [dict(reference_build="hg38", chromosome="1", position=1, reference="A", alternate="G")]
    variants._attach_classification_summaries(dict(database=index, record=dict(run_dir=run_dir)), 1, items)
    assert items[0]["acmg_classifications"][0]["disease_label"] == "First phenotype"
    assert items[0]["acmg_classifications"][0]["gene_label"] == "GENE1"
    assert items[0]["acmg_classifications"][0]["applied_criteria"] == [dict(code="BA1", strength="STAND_ALONE")]


def test_variant_tooltips_in_browser(tmp_path):
    chrome = shutil.which("google-chrome")
    if chrome is None:
        pytest.skip("Chrome unavailable")
    asset = Path(__file__).resolve().parents[1] / "src/helper_variants/web/static/variant-browser.js"
    html = tmp_path / "tooltips.html"
    html.write_text('''<!doctype html><meta charset="utf-8"><body><script type="module">
      import {VariantBrowser} from ASSET;
      const assert=(ok,message)=>{if(!ok)throw Error(message);};
      const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
      try {
        const viewer=new VariantBrowser(); viewer.activated=true; document.body.append(viewer);
        const root=viewer.shadowRoot, stylesheet=root.querySelector('link');
        if(!stylesheet.sheet)await new Promise((resolve,reject)=>{stylesheet.onload=resolve;stylesheet.onerror=reject;});
        const area=document.createElement('div'); root.append(area);
        const identity={gene:'HGNC:1',disease:'MONDO:1',transcript:'TX.1',inheritance:['AUTOSOMAL_DOMINANT']};
        const item={variant_id:1,gene:'GENE1',acmg_classifications:[
          {identity,classification:'LIKELY_PATHOGENIC',gene_label:'GENE1',disease_label:'First phenotype',
            applied_criteria:[{code:'PVS1',strength:'VERY_STRONG'},{code:'PM2',strength:'SUPPORTING'}]},
          {identity:{...identity,disease:'MONDO:2',inheritance:['AUTOSOMAL_RECESSIVE']},classification:'BENIGN',gene_label:'GENE1',disease_label:'Second phenotype',
            applied_criteria:[{code:'BA1',strength:'STAND_ALONE'}]},
          {identity:{...identity,transcript:'TX.2',inheritance:['X_LINKED']},classification:'VUS',gene_label:'GENE1',disease_label:'First phenotype',
            assessment:{criteria:[{code:'PVS1',strength:'MODERATE'},{code:'PP3',strength:'STRONG'}]}},
          {identity:{...identity,gene:'HGNC:2',inheritance:['SEMIDOMINANT']},classification:'PATHOGENIC',gene_label:'GENE2',disease_label:'Third phenotype'}]};
        const cell=viewer.variantCellNode({},item,'acmg_classification'); area.append(cell);
        const button=cell.querySelector('button'), source=cell.querySelector('[role="tooltip"]');
        assert(button.textContent==='PLPVUSB','Short classes stay separate from tooltip text');
        assert(getComputedStyle(source).display==='none','Rich source does not affect table layout');
        button.focus();
        const tooltip=root.querySelector('.variant-tooltip');
        assert(!tooltip.hidden && tooltip.matches(':popover-open'),'Keyboard focus opens the shared floating surface');
        assert(tooltip.textContent.includes('GENE1 (TX.1)'),'Header identifies gene and exact transcript');
        assert(tooltip.textContent.includes('First phenotype (AD) · LP (PVS1, PM2_supp)'),'Inheritance replaces MONDO and applied criteria follow the class');
        assert(!tooltip.textContent.includes('MONDO:'),'MONDO identifiers are omitted');
        assert(tooltip.textContent.includes('Second phenotype (AR) · B (BA1)'),'Each phenotype keeps its own class and criteria');
        assert(tooltip.textContent.includes('GENE1 (TX.2)') && tooltip.textContent.includes('(XL) · VUS (PVS1_mod, PP3_str)'),'Automatic criteria retain their applied strengths and transcript');
        assert(tooltip.textContent.includes('GENE2 (TX.1)') && tooltip.textContent.includes('(SD) · P'),'Genes remain separate');
        assert(button.getAttribute('aria-describedby')===tooltip.id,'Tooltip is associated with its trigger');
        const referenceStyle=getComputedStyle(tooltip);
        const appearance=[referenceStyle.backgroundColor,referenceStyle.color,referenceStyle.fontSize,referenceStyle.padding,referenceStyle.borderRadius].join('|');
        button.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
        assert(tooltip.hidden && !button.hasAttribute('aria-describedby'),'Escape dismisses and restores accessibility attributes');
        const hint=document.createElement('button'); hint.title='Native hint\\nSecond line'; hint.innerHTML='<span>Hover</span>'; area.append(hint);
        hint.dispatchEvent(new PointerEvent('pointerover',{bubbles:true})); await pause(230);
        assert(!tooltip.hidden && tooltip.textContent==='Native hint\\nSecond line','Native titles use the shared surface');
        assert(!hint.hasAttribute('title'),'Native duplicate is suppressed');
        hint.firstChild.dispatchEvent(new PointerEvent('pointerover',{bubbles:true}));
        assert(!tooltip.hidden,'Moving across trigger children keeps the tooltip visible');
        const current=getComputedStyle(tooltip);
        assert([current.backgroundColor,current.color,current.fontSize,current.padding,current.borderRadius].join('|')===appearance,'Native and rich tooltips share all visual styles');
        hint.dispatchEvent(new PointerEvent('pointerout',{bubbles:true})); await pause(160);
        assert(tooltip.hidden && hint.title==='Native hint\\nSecond line','Leaving restores the original title');
        const rich=viewer.geneAssociationEvidenceSummary({disease:'Example'}); area.append(rich);
        rich.querySelector('button').focus();
        assert(!tooltip.hidden && tooltip.textContent.includes('Evidence summary'),'Existing evidence summaries use the same surface');
        const link=document.createElement('a'); link.href='https://example.test'; link.textContent='Source';
        rich.querySelector('[role="tooltip"]').append(link);
        hint.focus(); rich.querySelector('button').focus();
        assert(tooltip.querySelector('a')?.href==='https://example.test/','Rich source links are retained');
        rich.querySelector('button').dispatchEvent(new PointerEvent('pointerout',{bubbles:true,relatedTarget:area}));
        area.dispatchEvent(new PointerEvent('pointerover',{bubbles:true}));
        tooltip.querySelector('a').dispatchEvent(new PointerEvent('pointerover',{bubbles:true})); await pause(160);
        assert(!tooltip.hidden,'Moving across the gap to a source link keeps the tooltip open');
        tooltip.dispatchEvent(new Event('scroll',{composed:true}));
        assert(!tooltip.hidden,'Long tooltip contents can be scrolled');
        rich.remove(); await pause(0); assert(tooltip.hidden,'Removed triggers cannot leave stale tooltips');
        area.style.cssText='position:fixed;bottom:0;right:0;width:90px;height:30px;overflow:hidden';
        button.focus();
        const box=tooltip.getBoundingClientRect();
        assert(box.left>=0 && box.top>=0 && box.right<=innerWidth && box.bottom<=innerHeight,'Tooltip stays inside the viewport at clipped table edges');
        area.scrollTop=5; area.dispatchEvent(new Event('scroll')); assert(tooltip.hidden,'Scrolling dismisses stale positions');
        const fallback=viewer.tableClassificationTooltip({}, {variant_id:2,gene:'GENE1',transcript:'TX.3'});
        assert(fallback.textContent.includes('GENE1 (TX.3)') && fallback.textContent.includes('Non valutata'),'Unassessed stays distinct from VUS');
        const unnamed=viewer.tableClassificationTooltip({}, {variant_id:2,acmg_classifications:[{identity,classification:'VUS'}]});
        assert(!unnamed.textContent.includes('MONDO:') && unnamed.textContent.includes('Fenotipo non disponibile (AD) · VUS'),'Missing names do not reintroduce MONDO or fabricate applied criteria');
        viewer.remove();
        document.body.dataset.result='PASS';
      }catch(error){document.body.dataset.result='FAIL';document.body.append(String(error.stack));}
    </script>'''.replace('ASSET', json.dumps(asset.as_uri())))
    result = subprocess.run([chrome, '--headless=new', '--no-sandbox', '--disable-gpu',
        '--disable-background-networking', '--disable-dev-shm-usage', '--no-first-run',
        '--allow-file-access-from-files', '--host-resolver-rules=MAP * ~NOTFOUND',
        f'--user-data-dir={tmp_path / "chrome"}', '--virtual-time-budget=5000', '--dump-dom', html.as_uri()],
        capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr[-1500:]
    assert 'data-result="PASS"' in result.stdout, result.stdout[-6000:]
