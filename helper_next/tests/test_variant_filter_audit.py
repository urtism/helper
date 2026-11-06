"""Check local filter inputs against variant fields, including missing values."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from helper_variants import query
from test_sample_priority_loading import run_loading_js
from test_variant_query import query_store
from test_population_frequency_v2 import payload, product


def audit_variants():
    specifications = [
        (1, "BRCA1", "missense_variant", "1", "het", 0.02, 20, 0.25, 40, 80, "P1", ["LOW_DP"], ["pathogenic", "likely pathogenic"], [1, 2], "father_only"),
        (2, "TP53", "stop_gained&splice_region_variant", "chrX", "hom_alt", 0, 10, 0.5, 100, 50, "P2", ["PASS"], [], [1], "de_novo"),
        (3, "BRCA1", "synonymous_variant", "MT", "het", None, None, None, None, 25, "P3", ["STRAND_BIAS"], ["benign"], [1, 2, 3], "both_parents"),
        (4, "BRCA1", "intron_variant", "Y", "unknown", 0, 0, 0, 0, 0, "P4", ["."], [], [1, 3], "mother_only"),
    ]
    result = []
    for ident, gene, consequence, chrom, zygosity, af, depth, vaf, qual, score, band, flags, clinical, carriers, origin in specifications:
        annotation = dict(gene=gene, consequence=consequence,
                          population_frequencies={"AFR_AF": [0.0001, 0.02, None, 0][ident - 1],
                                                  "EUR_AF": [0.03, 0, None, 0][ident - 1]},
                          compound=ident == 1, parental_compound=ident == 1)
        annotations = [annotation]
        if ident == 1:
            annotations.append(dict(gene="BRCA2", consequence="intron_variant", population_frequencies={}))
        result.append(dict(
            variant_id=ident, gene=gene, consequence=consequence, chromosome=chrom, zygosities=[zygosity],
            population_af=af, depth=depth, allele_fraction=vaf, quality=qual, genotype_quality=999,
            priority=dict(band=band, normalized_score=score, score=100-score), filter_status=flags,
            clinical_significance="benign" if ident == 1 else "pathogenic",
            filter_data=dict(annotations=annotations, clinical_significances=clinical,
                             family_carriers=carriers, family_evidence=[origin]),
        ))
    return result


def audit_cases():
    return [
        ({"genes": ["brca1"]}, [1, 3, 4]), ({"genes": ["BRCA2"]}, [1]),
        ({"genes": ["BRCA1"], "consequences": ["intron_variant"]}, [4]),
        ({"genes": ["BRCA2"], "consequences": ["missense_variant"]}, []),
        ({"consequences": ["missense_variant", "splice_region_variant"]}, [1, 2]),
        ({"maxAf": "0.01", "includeMissingAf": False}, [2, 4]),
        ({"maxAf": "0.01"}, [2, 3, 4]),
        ({"maxAf": "0.001", "populationFrequency": "AFR_AF", "includeMissingAf": False}, [1, 4]),
        ({"maxAf": "0.001", "populationFrequency": "EUR_AF", "includeMissingAf": False}, [2, 4]),
        ({"priorityClasses": ["P1", "P3"]}, [1, 3]),
        ({"minPriority": "50"}, [1, 2]), ({"maxPriority": "25"}, [3, 4]),
        ({"minPriority": "25", "maxPriority": "50"}, [2, 3]),
        ({"minPriority": "0", "maxPriority": "0"}, [4]),
        ({"clinicalSignificances": ["pathogenic"]}, [1]),
        ({"clinicalSignificances": ["likely_pathogenic"]}, [1]),
        ({"clinicalSignificances": ["benign"]}, [3]),
        ({"clinicalSignificances": ["__not_reported__"]}, [2, 4]),
        ({"clinicalSignificances": ["pathogenic", "__not_reported__"]}, [1, 2, 4]),
        *[({"inheritanceCandidates": [candidate]}, ids) for candidate, ids in (
            ("compound", [1]), ("dominant", [1, 3]), ("recessive", [2]),
            ("x_linked", [2]), ("y_linked", [4]), ("mitochondrial", [3]))],
        *[({"familyEvidence": [origin]}, ids) for origin, ids in (
            ("father_only", [1]), ("mother_only", [4]), ("both_parents", [3]),
            ("de_novo", [2]), ("parental_compound", [1]))],
        ({"familyPattern": ["2:present", "3:absent"]}, [1]),
        ({"familyPattern": ["1:present", "2:absent", "3:absent"]}, [2]),
        ({"filterMode": "pass"}, [2, 4]),
        ({"filterMode": "selected", "filterStatuses": ["LOW_DEPTH"]}, [1]),
        ({"filterMode": "exclude", "filterStatuses": ["STRAND_BIAS"]}, [1, 2, 4]),
        ({"filterMode": "all", "filterStatuses": ["STRAND_BIAS"]}, [1, 2, 3, 4]),
        ({"minDepth": "20"}, [1]), ({"minVaf": "0.5"}, [2]), ({"minQuality": "50"}, [2]),
        ({"minDepth": "0", "minVaf": "0", "minQuality": "0"}, [1, 2, 4]),
        ({"genes": ["BRCA1"], "consequences": ["missense_variant"], "maxAf": "0.001",
          "populationFrequency": "AFR_AF", "priorityClasses": ["P1"], "minPriority": "80", "maxPriority": "80",
          "familyEvidence": ["father_only"], "inheritanceCandidates": ["compound"],
          "familyPattern": ["2:present", "3:absent"], "minDepth": "20", "minVaf": "0.25", "minQuality": "40",
          "filterMode": "selected", "filterStatuses": ["LOW_DEPTH"], "clinicalSignificances": ["pathogenic"]}, [1]),
    ]


def test_every_filter_uses_its_variant_fields_and_combines_with_other_filters():
    run_loading_js("workspace.allItems=" + json.dumps(audit_variants()) + "; const cases=" + json.dumps(audit_cases()) + r''';
      workspace.initialized = true;
      viewer.request = () => assert.fail('Audit filters must not make requests');
      const original = JSON.stringify(workspace.allItems);
      for (const [filters, expected] of cases) {
        workspace.filters = {...viewer.emptyFilters(), ...filters};
        viewer.restartFilteredWorkspace(workspace);
        assert.deepEqual(workspace.items.map(item => item.variant_id).sort(), expected, JSON.stringify(filters));
        assert.equal(JSON.stringify(workspace.allItems), original, 'Filters cannot change their source fields');
      }
    ''')


def test_maximum_af_filters_the_enriched_value_displayed_in_the_variant(tmp_path, monkeypatch):
    database, sample, _ = query_store(tmp_path)
    monkeypatch.setattr(query.gnomad_frequency, "cached_contexts", lambda alleles, **kwargs: [
        {"population_frequency_evidence": payload({"joint": product(0.2)})}
        if allele[2] == 1 else {} for allele in alleles
    ])
    items = query.list_variants(database, sample, load_all=True)["items"]
    first = next(item for item in items if item["variant_id"] == 1)
    assert first["population_af"] == 0.2
    assert first["filter_data"]["annotations"][0]["population_frequencies"]["MAX_AF"] == 0.001
    run_loading_js("workspace.allItems=" + json.dumps(items) + r''';
      workspace.initialized = true;
      viewer.request = () => assert.fail('Filtering must stay local');
      workspace.filters = {...viewer.emptyFilters(), maxAf: '0.01'};
      viewer.restartFilteredWorkspace(workspace);
      assert.deepEqual(workspace.items.map(item => item.variant_id).sort(), [2,3,4,5]);
      workspace.filters.includeMissingAf = false;
      viewer.restartFilteredWorkspace(workspace);
      assert.equal(workspace.items.length, 0);
      workspace.filters = {...viewer.emptyFilters(), maxAf: '0.001', populationFrequency: 'AFR_AF', includeMissingAf: false};
      viewer.restartFilteredWorkspace(workspace);
      assert.deepEqual(workspace.items.map(item => item.variant_id), [1], 'A named population uses its own INFO field');
    ''')


@pytest.mark.parametrize("raw", [None, "", " ", ".", "N/A", "NaN", "Infinity", "0.001bad", [], False, -0.1, 1.1])
def test_invalid_af_is_missing_and_never_becomes_a_rare_zero(raw):
    run_loading_js("const raw=" + json.dumps(raw) + r''';
      workspace.initialized = true;
      workspace.allItems = [{variant_id: 1, population_af: raw,
        filter_data: {annotations: [{gene: 'G', population_frequencies: {AFR_AF: raw}}]}}];
      viewer.request = () => assert.fail('No lookup during filtering');
      for (const populationFrequency of ['MAX_AF', 'AFR_AF']) {
        workspace.filters = {...viewer.emptyFilters(), populationFrequency, maxAf: '0.01', includeMissingAf: false};
        viewer.restartFilteredWorkspace(workspace);
        assert.equal(workspace.items.length, 0, 'An invalid AF must not pass a rarity threshold');
        workspace.filters.includeMissingAf = true;
        viewer.restartFilteredWorkspace(workspace);
        assert.equal(workspace.items.length, 1, 'The missing-AF option controls invalid/missing frequencies');
      }
    ''')


@pytest.mark.parametrize("filter_name,field", [
    ("minDepth", "depth"), ("minVaf", "allele_fraction"), ("minQuality", "quality"),
    ("minPriority", "normalized_score"), ("maxPriority", "normalized_score"),
])
def test_thresholds_use_their_own_field_and_reject_missing_or_invalid_numbers(filter_name, field):
    run_loading_js("const filterName=" + json.dumps(filter_name) + ";const field=" + json.dumps(field) + r''';
      workspace.initialized = true;
      viewer.request = () => assert.fail('Thresholds must not request data');
      for (const value of [null, undefined, '', ' ', '.', 'N/A', NaN, Infinity, '3junk', [], false]) {
        workspace.allItems = [{variant_id: 1, depth: 50, allele_fraction: 0.5, quality: 50,
          priority: {band: 'P1', normalized_score: 90}}];
        if (field === 'normalized_score') workspace.allItems[0].priority.normalized_score = value;
        else workspace.allItems[0][field] = value;
        workspace.filters = {...viewer.emptyFilters(), [filterName]: filterName === 'maxPriority' ? '100' : '0'};
        viewer.restartFilteredWorkspace(workspace);
        assert.equal(workspace.items.length, 0, `${filterName} must reject ${String(value)}`);
      }
    ''')


def test_filter_flags_normalize_spaces_case_and_aliases_without_reading_genotype_quality():
    run_loading_js(r'''
      workspace.initialized = true;
      workspace.allItems = [
        {variant_id: 1, filter_status: [' PASS ']},
        {variant_id: 2, filter_status: [' lowqual ; strand_bias ']},
        {variant_id: 3, filter_status: [' LOW_AD,low_dp ']},
        {variant_id: 4, filter_status: ['.'], genotype_quality: 0},
      ];
      viewer.request = () => assert.fail('FILTER selection must stay local');
      for (const [filterStatuses, expected] of [
        [['LOW_QUAL'], [2]], [['STRAND_BIAS'], [2]], [['LOW_DEPTH'], [3]],
        [['LOW_ALTERNATE_DEPTH'], [3]], [['LOW_DP'], [3]],
      ]) {
        workspace.filters = {...viewer.emptyFilters(), filterMode: 'selected', filterStatuses};
        viewer.restartFilteredWorkspace(workspace);
        assert.deepEqual(workspace.items.map(item => item.variant_id), expected);
      }
      workspace.filters = {...viewer.emptyFilters(), filterMode: 'pass'};
      viewer.restartFilteredWorkspace(workspace);
      assert.deepEqual(workspace.items.map(item => item.variant_id), [1,4]);
    ''')


def test_real_browser_all_filter_controls_use_the_variant_fields(tmp_path):
    chrome = shutil.which("google-chrome")
    if chrome is None:
        pytest.skip("Chrome unavailable")
    database, sample, _ = query_store(tmp_path)
    base = query.list_variants(database, sample)["items"][0]
    asset = Path(__file__).resolve().parents[1] / "src/helper_variants/web/static/variant-browser.js"
    html = tmp_path / "filter-audit.html"
    html.write_text('''<!doctype html><meta charset="utf-8"><body><script type="module">
      import {VariantBrowser} from ASSET;
      const assert = (ok, message) => {if (!ok) throw Error(message);};
      try {
        const viewer = new VariantBrowser(); viewer.activated = true;
        document.body.append(viewer); viewer.selectedRun = 'RUN';
        const root = viewer.shadowRoot, style = root.querySelector('link');
        if (!style.sheet) await new Promise((resolve,reject) => {style.onload=resolve;style.onerror=reject;});
        const fields = FIELDS, cases = CASES, base = BASE;
        const items = fields.map(item => ({...base, ...item, priority: {...base.priority, ...item.priority}}));
        const sample = {sample_id: 1, display_name: 'PROBAND', metadata: {
          analysis_type: 'family', analysis_id: 'FAMILY', father: 'FATHER', mother: 'MOTHER', relationship: 'proband'}};
        viewer.samples = [sample, ...['FATHER', 'MOTHER'].map((name,index) => ({sample_id: index+2,
          display_name: name, metadata: {analysis_id: 'FAMILY', relationship: name.toLowerCase()}}))];
        const workspace = {key: 'RUN:1', runId: 'RUN', sample, items, allItems: items,
          initialized: true, loading: false, filters: viewer.emptyFilters(), filtersOpen: true,
          sort: {key: 'gene', direction: 'asc'}, filterOptions: {
            consequences: [...new Set(fields.flatMap(item => item.filter_data.annotations.flatMap(row => row.consequence.split('&'))))],
            population_frequencies: ['MAX_AF', 'AFR_AF', 'EUR_AF'],
            clinical_significances: ['pathogenic', 'likely_pathogenic', 'benign', '__not_reported__'],
            filter_statuses: ['LOW_DEPTH', 'STRAND_BIAS'],
          }};
        viewer.workspaces.set(workspace.key, workspace); viewer.activeWorkspace = workspace.key;
        let requests = 0;
        viewer.request = () => {requests++; throw Error('Filtering made a request');};
        viewer.renderTabs(); viewer.renderWorkspace();
        const original = JSON.stringify(items);
        const names = {consequences: 'consequence', clinicalSignificances: 'clinicalSignificance',
          priorityClasses: 'priorityClass', inheritanceCandidates: 'inheritanceCandidate', filterStatuses: 'filterStatus'};
        for (const [filters, expected] of cases) {
          viewer.resetFilters(workspace);
          const form = root.querySelector('.variant-filter-panel');
          for (const [key,value] of Object.entries(filters)) {
            const controls = [...form.querySelectorAll(`[name="${names[key] || key}"]`)];
            assert(controls.length, `Missing control ${key}`);
            if (key === 'genes') controls[0].value = value.join(',');
            else if (key === 'familyPattern') {
              for (const pattern of value) {
                const [member,state] = pattern.split(':');
                const hidden = controls.find(input => input.value.split(':')[0] === member);
                const button = hidden.parentElement.querySelector('button');
                button.click(); if (state === 'absent') button.click();
              }
            } else if (Array.isArray(value)) controls.forEach(input => {input.checked = value.includes(input.value);});
            else if (typeof value === 'boolean') controls[0].checked = value;
            else controls[0].value = value;
          }
          assert(form.checkValidity(), `Invalid form ${JSON.stringify(filters)}`);
          form.requestSubmit();
          const actual = workspace.items.map(item => item.variant_id).sort((a,b) => a-b);
          assert(JSON.stringify(actual) === JSON.stringify(expected), `${JSON.stringify(filters)}: ${actual} expected ${expected}`);
          assert(!workspace.loading && requests === 0, 'Filters must not load or recalculate data');
          assert(JSON.stringify(workspace.allItems) === original, 'Variant source fields must stay unchanged');
        }
        document.body.dataset.result = 'PASS';
      } catch (error) {document.body.dataset.result='FAIL';document.body.append(String(error.stack));}
    </script>'''.replace('ASSET', json.dumps(asset.as_uri())).replace('FIELDS', json.dumps(audit_variants()))
                    .replace('CASES', json.dumps(audit_cases())).replace('BASE', json.dumps(base)))
    result = subprocess.run([
        chrome, '--headless=new', '--no-sandbox', '--disable-gpu', '--disable-background-networking',
        '--disable-dev-shm-usage', '--no-first-run', '--allow-file-access-from-files',
        '--host-resolver-rules=MAP * ~NOTFOUND', f'--user-data-dir={tmp_path / "chrome-profile"}',
        '--virtual-time-budget=8000', '--dump-dom', html.as_uri(),
    ], capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr[-1500:]
    assert 'data-result="PASS"' in result.stdout, result.stdout[-5000:]
