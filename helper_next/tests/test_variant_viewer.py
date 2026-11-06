from pathlib import Path
import ast
import shutil
import subprocess

import pytest

from helper_next.api.app import create_app


STATIC = Path(__file__).resolve().parents[1] / "src"


def test_igv_custom_track_rounds_fractional_query_coordinates():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to exercise the IGV track configuration")
    script = r"""
      const fs = require('node:fs');
      const assert = require('node:assert/strict');
      const source = fs.readFileSync(process.argv[1], 'utf8');
      const method = source.slice(source.indexOf('  igvTrackConfig(track, workspace) {'),
        source.indexOf('  igvChromosome(workspace) {'));
      const viewer = Function(`return ({${method}})`)();
      const config = viewer.igvTrackConfig({id: 'gnomad-regional', source_type: 'custom',
        url: '/igv-gnomad?chr=$CHR&start=$START&end=$END'}, {});
      assert.equal(config.source.url({chr: 'chr1', start: 98.25, end: 120.75}),
        '/igv-gnomad?chr=chr1&start=98&end=121');
      assert.equal(config.source.url({chr: 'chr1', start: -0.5, end: 120.1}),
        '/igv-gnomad?chr=chr1&start=0&end=121');
      const url = new URL(config.source.url({chr: 'chr1', start: 100.5,
        end: 100.5 + config.visibilityWindow}), 'http://localhost');
      assert.ok(Number(url.searchParams.get('end')) - Number(url.searchParams.get('start')) <= 100000);
    """
    subprocess.run(
        [node, "-e", script, str(STATIC / "helper_variants/web/static/variant-browser.js")],
        check=True, capture_output=True, text=True,
    )


def test_population_frequency_header_shows_maximum_or_not_found():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to exercise population frequency display")
    script = r"""
      const fs = require('node:fs');
      const assert = require('node:assert/strict');
      const source = fs.readFileSync(process.argv[1], 'utf8');
      const labelsStart = source.indexOf('const POPULATION_LABELS = {');
      const labelsEnd = source.indexOf('\n};', labelsStart) + 2;
      const labels = source.slice(labelsStart, labelsEnd);
      const status = source.slice(source.indexOf('  populationFrequencyStatus(detail, annotations) {'),
        source.indexOf('  gnomadFrequencyCard(detail) {'));
      const number = source.slice(source.indexOf('  frequencyNumber(rawValue) {'),
        source.indexOf('  frequencyPercent(rawValue) {'));
      const nameStart = source.indexOf('  populationName(populationId) {');
      const readableStart = source.indexOf('\n  readableFieldName(', nameStart);
      const populationName = source.slice(nameStart, readableStart);
      const readableFieldName = source.slice(
        readableStart + 1, source.indexOf('\n  referenceToolConfiguration(', readableStart));
      const viewer = Function(`${labels}; return ({${status}, ${number}, ${populationName}, ${readableFieldName}})`)();
      assert.equal(viewer.populationFrequencyStatus({}, [
        {population_af: 0.02, metadata: {fields: {GNOMADG_NFE_AF: "0.12", MAX_AF_POPS: "NFE"}}},
        {population_af: 0.04, metadata: {fields: {AFR_AF: "0.09"}}},
      ]), `Max AF: ${viewer.frequencyNumber(0.12)} (gnomAD · Non-Finnish European)`);
      assert.equal(viewer.populationFrequencyStatus({}, [
        {metadata: {fields: {AFR_AF: "0.15", EAS_AF: "0.1"}}},
      ]), `Max AF: ${viewer.frequencyNumber(0.15)} (1000G · African)`);
      assert.equal(viewer.populationFrequencyStatus({gnomadFrequency: {
        af: 0.05, populations: [{id: "afr", af: 0.2}],
      }}, []), `Max AF: ${viewer.frequencyNumber(0.2)} (gnomAD · African)`);
      assert.equal(viewer.populationFrequencyStatus({}, []), "Not found");
    """
    subprocess.run(
        [node, "-e", script, str(STATIC / "helper_variants/web/static/variant-browser.js")],
        check=True, capture_output=True, text=True,
    )


def test_gnomad_population_identifiers_are_rendered_as_full_names():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to exercise population name display")
    script = r"""
      const fs = require('node:fs');
      const assert = require('node:assert/strict');
      const source = fs.readFileSync(process.argv[1], 'utf8');
      const labelsStart = source.indexOf('const POPULATION_LABELS = {');
      const labelsEnd = source.indexOf('\n};', labelsStart) + 2;
      const labels = source.slice(labelsStart, labelsEnd);
      const nameStart = source.indexOf('  populationName(populationId) {');
      const readableStart = source.indexOf('\n  readableFieldName(', nameStart);
      const populationName = source.slice(nameStart, readableStart);
      const readableFieldName = source.slice(
        readableStart + 1, source.indexOf('\n  referenceToolConfiguration(', readableStart));
      const viewer = Function(`${labels}; return ({${populationName}, ${readableFieldName}})`)();
      assert.equal(viewer.populationName('afr'), 'African');
      assert.equal(viewer.populationName('nfe_XX'), 'Non-Finnish European (XX)');
      assert.equal(viewer.populationName('gnomadg_mid'), 'Middle Eastern');
    """
    subprocess.run(
        [node, "-e", script, str(STATIC / "helper_variants/web/static/variant-browser.js")],
        check=True, capture_output=True, text=True,
    )


def test_helper_mounts_standalone_variant_assets_and_only_hosts_the_component():
    app = create_app()
    mounts = {route.path: route.name for route in app.routes if hasattr(route, "name")}
    index = (STATIC / "helper_next/web/static/index.html").read_text()

    assert mounts["/variant-module"] == "variant-module"
    assert '<variant-browser api-base="/api/variants"></variant-browser>' in index
    assert "allow-archived-import" not in index
    assert 'src="/variant-module/variant-browser.js' in index
    assert 'data-section="variants"' in index
    assert "variant-viewport" not in index


def test_viewer_is_a_configurable_shadow_dom_web_component_with_virtual_rows():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()

    assert 'customElements.define("variant-browser"' in source
    assert 'this.attachShadow({mode: "open"})' in source
    assert 'this.getAttribute("api-base")' in source
    assert 'this.getAttribute("route-prefix")' in source
    assert 'const PAGE_SIZE = 200;' in source
    assert "Math.floor(offset / ROW_HEIGHT)" in source
    assert "workspace.items.slice(start, end)" in source
    assert "workspace.pageController?.abort()" in source
    assert "workspace.detailController?.abort()" in source


def test_priority_score_opens_an_explainable_bottom_panel():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()
    stylesheet = (STATIC / "helper_variants/web/static/variant-browser.css").read_text()

    assert '{key: "priority", label: "Priority"' in source
    assert "item.priority" in source
    assert "priorityExplanationPanel(workspace)" in source
    assert "priorityItem.priority = detail.priority" in source
    assert 'String(item.variant_id) === String(variantId)' in source
    assert '{signal: workspace.detailController.signal, cache: "no-store"}' in source
    assert "priority.formula" in source
    assert "priority.components" in source
    assert "Experimental review priority; it is not an ACMG/AMP classification" in source
    assert ".priority-explanation-panel" in stylesheet
    assert "bottom: 0" in stylesheet


def test_viewer_keeps_independent_workspaces_and_restorable_urls():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()
    app_source = (STATIC / "helper_next/web/static/app.js").read_text()

    assert "this.workspaces = new Map()" in source
    assert "this.workspaces.set(key" in source
    assert 'new URLSearchParams({run: runId})' in source
    assert 'params.set("sample"' in source
    assert 'window.addEventListener("hashchange"' in source
    assert 'variants: "Variant Browser"' in app_source
    assert "sectionFromHash()" in app_source


def test_viewer_opens_read_evidence_in_a_reusable_igv_workspace_tab():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()
    stylesheet = (STATIC / "helper_variants/web/static/variant-browser.css").read_text()

    assert 'node("button", "Inspect reads", "igv-open")' in source
    assert 'kind: "igv"' in source
    assert '`IGV · ${workspace.sample.display_name}`' in source
    assert 'view: "igv", variantId: detail.variant_id' in source
    assert 'igv-manifest' in source
    assert 'this.igvTrackConfig(track, workspace)' in source
    assert 'igv-evidence-summary' in source
    assert 'track.type === "variant"' in source
    assert "createBrowser" in source
    assert "workspace.igvBrowser.search" in source
    assert "removeBrowser" in source
    assert ".igv-panel" in stylesheet


def test_igv_overlays_are_clamped_and_match_the_variant_browser_ui():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()
    stylesheet = (STATIC / "helper_variants/web/static/variant-browser.css").read_text()
    igv_theme = (STATIC / "helper_variants/web/static/igv-theme.css").read_text()

    assert "installIgvOverlayManagement(workspace)" in source
    assert "installIgvTheme(workspace)" in source
    assert "workspace.igvNodes.viewer.shadowRoot" in source
    assert 'link.dataset.helperIgvTheme = "true"' in source
    assert "IGV_THEME_URL" in source
    assert "clampIgvOverlays(workspace)" in source
    assert "decorateIgvOverlay(overlay)" in source
    assert 'window.addEventListener("resize", schedule)' in source
    assert 'window.addEventListener("scroll", schedule, true)' in source
    assert "removeIgvOverlayManagement(workspace)" in source
    assert ".igv-panel {" in stylesheet and "overflow: visible" in stylesheet
    assert ".igv-ui-popover" in igv_theme
    assert ".igv-track-label-popover" in igv_theme
    assert ".igv-menu-popup" in igv_theme
    assert "max-height: calc(100vh - 24px)" in igv_theme
    assert "box-shadow: 0 12px 32px rgba(31, 46, 61, .2)" in igv_theme


def test_igv_track_menu_loads_reference_population_and_split_read_tracks_on_demand():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()
    stylesheet = (STATIC / "helper_variants/web/static/variant-browser.css").read_text()

    assert 'node("details", undefined, "igv-track-picker")' in source
    assert "initializeIgvTrackSelection(workspace)" in source
    assert "renderIgvTrackMenu(workspace)" in source
    assert "toggleIgvTrack(workspace, track, visible)" in source
    assert "workspace.igvBrowser.loadTrack" in source
    assert "workspace.igvBrowser.removeTrack" in source
    assert 'track.mode === "split-reads"' in source
    assert 'groupBy: "chimeric"' in source
    assert "showSoftClips: true" in source
    assert 'track.source_type === "custom"' in source
    assert 'sourceType: "custom"' in source
    assert ".igv-track-menu" in stylesheet
    assert ".igv-track-option" in stylesheet


def test_viewer_shows_runs_as_compact_rows_without_duplicate_overview():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()

    assert "Run-local, indexed variant review" not in source
    assert 'id="refresh-runs"' not in source
    assert 'class="toolbar"' not in source
    assert 'run-row run-table-header' in source
    assert '["Run", "Date", "Samples", "Panel", "Pipeline", "Reference", "Status", ""]' in source
    assert 'node("button", "ⓘ", "icon-button")' in source
    assert 'infoButton.title = "Tools and versions"' in source
    assert 'id="run-overview"' not in source
    assert 'id="sample-search"' in source
    assert "renderRunOverview" not in source
    assert "this.refreshRuns(true)" in source
    assert "const select = () => this.activateRun(run)" in source
    assert 'if (run.index_status === "complete")' in source
    assert "this.selectRun(run.history_id)" in source


def test_viewer_uses_collapsible_runs_and_expandable_sample_sidebar():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()

    assert 'id="run-drawer" class="run-drawer"' in source
    assert '<aside id="sample-panel" class="sample-panel">' in source
    assert 'id="sample-panel-toggle"' in source
    assert 'layout.classList.toggle("samples-collapsed", collapsed)' in source
    assert 'node("details", undefined, "sample-card")' in source
    assert 'details.append(node("summary", sample.display_name))' in source
    assert '["Family", analysisType === "family" ? analysisId : ""]' in source
    assert '["Tissue / specimen", metadata.specimen_type || sample.specimen_type]' in source
    assert '["Variants", sample.variant_count]' in source


def test_viewer_opens_evidence_source_registry_from_topbar_info_button():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()
    stylesheet = (STATIC / "helper_variants/web/static/variant-browser.css").read_text()
    index = (STATIC / "helper_next/web/static/index.html").read_text()
    app_source = (STATIC / "helper_next/web/static/app.js").read_text()
    app_stylesheet = (STATIC / "helper_next/web/static/styles.css").read_text()

    assert 'id="source-registry" class="source-registry"' not in source
    assert 'id="variant-source-info"' in index
    assert 'class="topbar-title-row"' in index
    assert 'variantSourceInfo.hidden = sectionId !== "variants"' in app_source
    assert 'variant-browser")?.openSourceRegistryPanel()' in app_source
    assert 'openSourceRegistryPanel()' in source
    assert 'node("section", undefined, "source-registry-dialog")' in source
    assert 'dialog.setAttribute("aria-modal", "true")' in source
    assert 'if (event.key === "Escape") closeDialog()' in source
    assert 'this.request("/knowledge/sources")' in source
    assert '["Source", "Use", "Release / version", "Source updated", "Local snapshot", "State"]' in source
    assert 'this.sourceRegistryDate(source.data_updated_at, "Not captured")' in source
    assert 'this.sourceRegistryDate(source.synchronized_at' in source
    assert 'sourceRegistryStatusLabel(status)' in source
    assert 'sourceRegistryStatusDescription(status)' in source
    assert 'status.title = statusDescription' in source
    assert 'status.tabIndex = 0' in source
    assert 'It is not a real-time connection to the source.' in source
    assert '.source-registry-dialog {' in stylesheet
    assert '.source-registry-status.synchronized' in stylesheet
    assert '.variant-source-info[hidden]' in app_stylesheet


def test_variant_columns_are_reorderable_and_include_vep_fields():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()

    expected_order = [
        'key: "filter_alert"', 'key: "genotypes"',
        'key: "gene"', 'key: "hgvsc"', 'key: "hgvsp"',
        'key: "population_af"',
        'key: "clinvar_local"', 'key: "consequence"', 'key: "exon_intron"',
        'key: "depth"', 'key: "allele_fraction"', 'key: "transcript"',
    ]
    positions = [source.index(item) for item in expected_order]
    assert positions == sorted(positions)
    assert '{key: "clinvar_local", label: "ClinVar"' in source
    assert 'label: "Clinical (VCF)"' not in source
    assert 'label: "AF_max"' in source
    assert 'label: "Exon / intron"' in source
    assert "dragHandle.draggable = true" in source
    assert "cell.draggable = true" not in source
    assert 'resizeHandle.addEventListener("pointerdown"' in source
    assert 'node("span", "↔", "column-resize-handle")' in source
    assert 'cell.classList.add("sortable-column-header")' in source
    assert 'cell.addEventListener("drop"' in source
    assert "localStorage.setItem(COLUMN_STORAGE_KEY" in source
    assert "localStorage.setItem(COLUMN_WIDTH_STORAGE_KEY" in source
    assert 'node("span", "▲", "filter-alert")' in source
    assert 'normalized !== "PASS"' in source
    assert '{key: "variant"' not in source
    assert '{key: "filter_status"' not in source
    assert '{key: "quality"' not in source


def test_priority_columns_are_click_sortable_across_server_pages():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()
    stylesheet = (STATIC / "helper_variants/web/static/variant-browser.css").read_text()

    assert '["priority", {firstDirection: "desc", description: "by review priority; highest score first"}]' in source
    assert 'sort: {key: "priority", direction: "desc"}' in source
    assert '["gene", {firstDirection: "asc", description: "alphabetically"}]' in source
    assert '["population_af", {firstDirection: "asc", description: "by AF_max; missing AF is the lowest value"}]' in source
    assert '["clinical_significance", {firstDirection:' not in source
    assert '["consequence", {firstDirection: "asc", description: "alphabetically"}]' in source
    assert 'params.set("sort_by", workspace.sort.key)' in source
    assert 'params.set("sort_direction", workspace.sort.direction)' in source
    assert 'this.toggleVariantSort(workspace, key)' in source
    assert 'cell.setAttribute("aria-sort"' in source
    assert 'direction === "desc" ? "▼" : "▲"' in source
    assert '.column-sort-button {' in stylesheet
    assert ".sortable-column-header" in stylesheet
    assert ".column-resize-handle::before" in stylesheet


def test_priority_filters_support_multiple_classes_and_numeric_range():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()
    stylesheet = (STATIC / "helper_variants/web/static/variant-browser.css").read_text()

    assert '"Class", "priorityClass", ["P1", "P2", "P3", "P4"]' in source
    assert '[["minPriority", "From", filters.minPriority], ["maxPriority", "To", filters.maxPriority]]' in source
    assert 'Minimum priority cannot exceed maximum priority.' in source
    assert ".priority-filter-body" in stylesheet
    assert ".priority-range" in stylesheet


def test_priority_panel_normalizes_locus_and_shows_hgvs():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()

    assert "priorityVariantIdentity(item = {})" in source
    assert 'String(item.chromosome || "").replace(/^chr/i, "")' in source
    assert 'this.compactHgvs(item.hgvsc, "c.")' in source
    assert 'this.compactHgvs(item.hgvsp, "p.")' in source
    assert 'node("p", this.priorityVariantIdentity(item))' in source
    assert "chr${item.chromosome}" not in source


def test_variant_detail_loads_assembly_matched_gnomad_genome_frequency():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()
    stylesheet = (STATIC / "helper_variants/web/static/variant-browser.css").read_text()

    assert "/gnomad-frequency`" in source
    assert 'dataset: "gnomad_r2_1", version: "2.1.1"' in source
    assert 'dataset: "gnomad_r4", version: "4.1.1"' in source
    assert "gnomadFrequencyCard(detail)" in source
    assert "refreshVariantPriorities(workspace)" in source
    assert '["observed", "not_observed_covered"].includes(frequency.status)' in source
    assert '`Max AF: ${this.frequencyNumber(maximum.frequency)}${source}`' in source
    assert 'if (!candidates.length) return "Not found";' in source
    assert 'gnomad-populations' in source
    assert 'node("strong", "Population details", "gene-knowledge-label")' in source
    assert 'const products = ["joint", "exomes", "genomes"]' in source
    assert 'this.populationName(population.id)' in source
    assert 'Additional VEP, gnomAD and 1000 Genomes data' in source
    assert ".gnomad-populations > summary::before" in stylesheet
    assert 'gnomad-frequency-table' in stylesheet
    assert ".frequency-direct { grid-column: 1 / -1; }" in stylesheet


def test_gene_context_action_opens_a_filtered_workspace_tab():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()

    assert 'cell.addEventListener("contextmenu"' in source
    assert "this.openGeneWorkspace(workspace, item.gene)" in source
    assert "? `${workspace.gene} · ${workspace.sample.display_name}`" in source


def test_filter_panel_supports_clinical_inheritance_and_removable_gene_panels():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()
    stylesheet = (STATIC / "helper_variants/web/static/variant-browser.css").read_text()

    assert '"ClinVar", "clinicalSignificance"' in source
    assert '"compound", "recessive", "dominant", "x_linked", "y_linked", "mitochondrial"' in source
    assert 'mitochondrial: "Maternal (mitochondrial)"' in source
    assert 'node("h5", "Family evidence")' in source
    assert '"de_novo", "father_only", "mother_only", "both_parents", "parental_compound"' in source
    assert 'de_novo: "De novo (absent in both parents)"' in source
    assert 'father_only: "Present only in father"' in source
    assert 'mother_only: "Present only in mother"' in source
    assert 'both_parents: "Present in both parents"' in source
    assert 'parental_compound: "Parental compound (one variant per parent)"' in source
    assert "familyPedigreeFilter(workspace, filters.familyPattern || [])" in source
    assert "pedigreeMemberControl(member, selected)" in source
    assert 'hidden.name = "familyPattern"' in source
    assert 'present: "must carry the variant"' in source
    assert 'absent: "must not carry the variant"' in source
    assert 'node("button", "🗑", "panelapp-source-remove")' in source
    assert "removePanelSource(workspace, textarea, sourceHost, source)" in source
    assert 'population.name = "populationFrequency"' in source
    assert '"Maximum across populations"' in source
    assert 'likely_pathogenic: "Likely pathogenic"' in source
    assert 'uncertain_significance: "VUS"' in source
    assert 'likely_benign: "Likely benign"' in source
    assert '__not_reported__: "Not reported"' in source
    assert "Up to 5,000 HGNC gene symbols" not in source
    assert '"Zygosity", "zygosity"' not in source
    assert 'params.set("zygosities"' not in source
    assert ".sample-evidence-section { display: grid; grid-template-rows: auto minmax(0, 1fr)" in stylesheet
    assert ".evidence-grid { align-items: stretch; gap: 6px; grid-template-columns: minmax(105px, 1fr) minmax(78px, 88px); height: 100%" in stylesheet
    assert ".filter-site-status { grid-template-rows: auto auto minmax(0, 1fr); height: 100%" in stylesheet
    assert ".filter-site-status .filter-choices { height: 100%; margin-top: 1px; max-height: none" in stylesheet
    assert ".sample-evidence-section, .family-evidence-section { box-sizing: border-box; height: 270px; max-height: 270px; }" in stylesheet
    assert ".call-threshold-grid { display: grid" in stylesheet
    assert ".call-threshold-grid { display: grid; gap: 5px; grid-template-columns: minmax(0, 1fr)" in stylesheet
    for field in (
        '"minDepth", "DP"', '"minVaf", "VAF"', '"minQuality", "QUAL"',
    ):
        assert field in source
    assert '["exclude", "Exclude selected FILTER flags"]' in source
    assert '"FILTER flags", "filterStatus"' in source
    assert "grid-template-columns: minmax(105px, .7fr) minmax(88px, .5fr) repeat(3, minmax(105px, 1fr))" in stylesheet
    assert ".priority-class-choices { grid-template-columns: minmax(0, 1fr)" in stylesheet
    assert 'lowerGrid.append(sampleEvidence, familyEvidence, genePanel)' in source
    assert ".filter-lower-grid { display: grid" in stylesheet
    assert "grid-template-columns: minmax(205px, .65fr) minmax(430px, 1.7fr) minmax(250px, 1fr)" in stylesheet
    assert ".family-evidence-layout" in stylesheet
    assert ".pedigree-diagram" in stylesheet
    assert "isFamilyAnalysis(workspace)" in source
    assert 'lowerGrid.classList.add("without-family")' in source
    assert ".filter-lower-grid.without-family" in stylesheet
    assert ".workspace-grid:not(.detail-closed) .filter-lower-grid { grid-template-columns: 1fr; }" in stylesheet
    assert ".workspace-grid:not(.detail-closed) .interpretation-grid { grid-template-columns: minmax(100px, .7fr) minmax(82px, .5fr) repeat(3, minmax(95px, 1fr)); }" in stylesheet
    assert ".workspace-grid:not(.detail-closed) .evidence-grid { grid-template-columns: minmax(105px, 1fr) minmax(78px, 88px); }" in stylesheet


def test_filter_typography_uses_one_consistent_scale():
    stylesheet = (STATIC / "helper_variants/web/static/variant-browser.css").read_text()

    assert "--filter-control-size: 10px" in stylesheet
    assert "--filter-label-size: 11px" in stylesheet
    assert "--filter-note-size: 10px" in stylesheet
    assert "--filter-section-title-size: 12px" in stylesheet
    assert ".priority-class-choices label { font-size: var(--filter-control-size)" in stylesheet
    assert ".priority-range label { color: #526174; display: grid; font-size: var(--filter-control-size)" in stylesheet
    assert ".call-threshold-control > span { font-size: var(--filter-control-size)" in stylesheet
    assert ".pedigree-member-role { color: #6a7683; font-size: var(--filter-note-size)" in stylesheet


def test_priority_explanations_use_readable_text_sizes():
    stylesheet = (STATIC / "helper_variants/web/static/variant-browser.css").read_text()

    assert ".priority-component p { color: #42566b; font-size: 12px" in stylesheet
    assert ".priority-component small { color: #667385; display: block; font-size: 11px" in stylesheet
    assert ".priority-explanation-footer span { color: #45596e; font-size: 11.5px; }" in stylesheet
    assert ".priority-explanation-footer small { color: #6a7685; font-size: 11px; }" in stylesheet


def test_variant_hgvs_is_compact_and_detail_panel_can_be_closed():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()
    stylesheet = (STATIC / "helper_variants/web/static/variant-browser.css").read_text()

    assert 'this.compactHgvs(item[key], "c.")' in source
    assert 'this.compactHgvs(item[key], "p.")' in source
    assert 'compact.replace(/%3D/gi, "=")' in source
    assert 'const displayDetail = !workspace.loading && workspace.detail;' in source
    assert 'workspace-grid${displayDetail ? "" : " detail-closed"}' in source
    assert 'node("button", "×", "detail-close")' in source
    assert "workspace.detail = null" in source
    assert "variantDetailAnnotationLabel(annotations = [])" in source
    assert "annotations.find(item => item.canonical)" in source
    assert 'const coding = [gene, hgvsc].filter(Boolean).join(":")' in source
    assert 'hgvsp ? `(${hgvsp})` : ""' in source
    assert '"detail-identity"' in source
    assert '"detail-annotation"' in source
    assert "variantDetailIdentityRow(locus, annotationLabel, options = {})" in source
    assert '"detail-build-badge"' in source
    assert "HGVSc and HGVSp are transcript-level descriptions" in source
    assert ".detail-identity-row.projected" in stylesheet


def test_variant_detail_uses_collapsible_interpretation_sections():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()
    stylesheet = (STATIC / "helper_variants/web/static/variant-browser.css").read_text()

    for title in (
        '"Variant details"', '"Gene–phenotype"', '"Family"',
        '"Population frequencies"', '"Damage predictions"', '"Transcripts"',
    ):
        assert title in source
    assert 'node("details", undefined, `detail-disclosure' in source
    assert '["Reference reads", call.reference_depth]' in source
    assert '["Genotype quality (GQ)", call.genotype_quality]' in source
    assert 'annotation.metadata?.fields' in source
    assert 'disabled: onlyCase' in source
    assert "minmax(580px, 46%)" in stylesheet
    assert '["VCF ID",' not in source
    assert '["dbSNP", this.databaseIdentifierLinks("dbsnp", databaseIds.dbsnp)]' in source
    assert 'this.externalDatabaseLabel("ClinVar", clinvarSearchUrl' in source
    assert "assemblyCoordinateSummary(detail)" in source
    assert "loadLiftover(workspace, variantId)" in source
    assert '"GRCh37 / hg19"' in source
    assert '"GRCh38 / hg38"' in source
    assert ".assembly-coordinate-card.projected" in stylesheet
    assert "https://www.ncbi.nlm.nih.gov/variation/services/" in source
    assert "https://www.ncbi.nlm.nih.gov/variation/docs/" not in source
    assert "clinvarSearchUrl(dbsnpIdentifiers = [])" in source
    assert "clinvar/?term=${encodeURIComponent(rsid)}" in source
    assert '["ClinGen Allele Registry", this.databaseIdentifierLinks("clingen", databaseIds.clingen)]' in source
    assert "https://www.ncbi.nlm.nih.gov/snp/" in source
    assert "https://www.ncbi.nlm.nih.gov/clinvar/variation/" in source
    assert "https://reg.clinicalgenome.org/" in source
    assert ".variant-summary-grid" in stylesheet
    assert ".database-label-link" in stylesheet
    for resource in (
        'name: "ClinGen"', 'name: "GenCC"', 'name: "OMIM"',
        'name: "Orphanet"', 'name: "Gene2Phenotype"', 'name: "PanelApp"',
        'name: "DECIPHER"', 'name: "Monarch"', 'name: "Human Phenotype Ontology"',
        'name: "GeneReviews"', 'name: "Open Targets"',
        'name: "Clinical Genomic Database"', 'name: "MalaCards"',
    ):
        assert resource in source
    assert "genePhenotypeGenes(annotations)" in source
    assert "loadGenePhenotypes(workspace, variantId" in source
    assert 'this.clinvarSourceInformation(clinvarEvidence)' in source
    assert "clinvarEvidenceContent(clinvarEvidence, databaseIds, clinvarSearchUrl)" in source
    assert "clinvarReviewStatuses(statuses = [])" in source
    assert '"View all submissions and full details on ClinVar ↗"' not in source
    assert "Germline submissions with at least 1 review star, across all conditions." not in source
    assert '"clinvar-review-stars"' in source
    assert 'heading.append(classifications)' in source
    assert "clinvarClassificationLabels(evidence = {})" in source
    assert 'evidence.submission_classification_breakdown' in source
    assert "const classifications = evidence.classifications || [];" in source
    assert 'classifications.join(" · ")' in source
    assert 'node("div", undefined, "clinvar-identifiers")' in source
    assert source.index('heading.append(classifications)') < source.index('"clinvar-identifiers"')
    assert 'Current aggregate record on ClinVar' not in source
    assert 'Review status reflects the level of review reported by ClinVar' not in source
    assert ".clinvar-classification.pathogenic" in stylesheet
    assert ".clinvar-conflict-warning" in stylesheet
    assert ".clinvar-identifiers .database-identifier-link { font-size: 14px; font-weight: 700; }" in stylesheet
    assert "--detail-section-title-size: 12px" in stylesheet
    assert "--detail-label-size: 11px" in stylesheet
    assert "--detail-metadata-size: 10px" in stylesheet
    assert "...detail, variant_id: variantId, carriers: null" in source
    assert "/knowledge/gene-phenotypes/" in source
    assert "genePhenotypeAssertionUrl(assertion, gene)" in source
    assert "genePhenotypeSourcePriority(sourceName)" in source
    assert "genePhenotypeEvidenceAssertions(association)" in source
    assert 'classification: "Evidence not imported"' in source
    assert "https://www.omim.org/entry/" in source
    assert '"Supporting databases"' in source
    assert 'node("span", "Supporting databases", "gene-knowledge-label")' in source
    assert 'node("details", undefined, "gene-evidence-sources")' in source
    assert 'node("small", `${assertions.length} source${assertions.length === 1 ? "" : "s"}`)' in source
    assert ".gene-evidence-sources[open] > summary::before" in stylesheet
    assert 'node("button", "i", "gene-evidence-information-button")' in source
    assert 'informationText.setAttribute("role", "tooltip")' in source
    assert ".gene-evidence-information:focus-within .gene-evidence-information-text" in stylesheet
    assert "geneDiseaseMechanism(association.molecular_mechanism, constraint, dosage)" in source
    assert 'node("details", undefined, "gene-disease-mechanisms")' in source
    assert '"gnomAD constraint"' in source
    assert '"ClinGen dosage sensitivity"' in source
    assert '["lof_oe", "lof"]' in source
    assert '["missense_oe", "mis"]' in source
    assert 'constraint.transcripts || [constraint]' in source
    assert 'gnomad-constraint-table' in stylesheet
    assert 'geneConstraintMetricLabel(label, help)' in source
    assert 'it does not establish LoF, GoF or DN disease mechanisms' in source
    assert '"constraint-metric-information-button"' in source
    assert 'tooltip.setAttribute("role", "tooltip")' in source
    assert ".constraint-metric-information:focus-within" in stylesheet
    assert ".gene-mechanism-metrics dt:nth-of-type(even) .constraint-metric-information-text" in stylesheet
    assert '"pLoF observed"' not in source
    assert '"Missense observed"' not in source
    assert ".gene-disease-mechanisms[open] > summary::before" in stylesheet
    assert "geneDiseasePhenotypicFeatures(association)" in source
    assert 'node("span", "Phenotypic features", "gene-knowledge-label")' in source
    assert '"Conflicting G2P records"' in source
    assert '`confidence: ${record.confidence}`' in source
    assert '`allelic requirement: ${record.allelic_requirement}`' in source
    assert '`consequence: ${record.variant_consequence}`' in source
    assert '`support: ${record.support}`' in source
    assert ".gene-phenotypic-feature-list" in stylesheet
    assert "geneDiseaseIdentifiers(association)" in source
    assert "geneDiseaseCode(code = {})" in source
    assert "(association.icd_codes || []).forEach" in source
    assert '`${system}: ${value}`' in source
    assert "https://monarchinitiative.org/disease/MONDO:" in source
    assert "https://www.omim.org/entry/" in source
    assert "https://www.orpha.net/en/disease/detail/" in source
    assert 'node("span", "Inheritance", "gene-inheritance-label")' in source
    assert ".gene-disease-identifier.mondo" in stylesheet
    assert ".gene-disease-identifier.icd10" in stylesheet
    assert ".gene-disease-identifier.icd11" in stylesheet
    assert ".gene-inheritance-value" in stylesheet
    assert '"gene-evidence-source-row"' in source
    assert '"gene-evidence-source-link"' in source
    assert '"No phenotype association was found in the local knowledge cache."' in source
    assert "association.strongest_classification" in source
    assert "geneDiseaseInheritance(association.inheritance)" in source
    assert "geneAssociationEvidenceSummary(association, constraint, dosage)" in source
    assert 'node("strong", "Evidence summary")' in source
    assert '"G2P is disease-specific; ClinGen dosage and gnomAD constraint are gene-level context."' in source
    assert ".gene-association-summary-tooltip" in stylesheet
    assert "assertion.report_url" in source
    assert ".gene-evidence-source-row" in stylesheet
    assert ".gene-evidence-source-link" in stylesheet
    assert ".gene-phenotype-association" in stylesheet
    assert '["Caller", call.caller]' not in source
    assert '["Genotype", call.genotype], ["Genotype quality (GQ)", call.genotype_quality]' in source
    assert '["Variant allele fraction (VAF)", call.allele_fraction]' in source
    assert 'PL: "Genotype likelihoods (PL)"' in source
    assert 'new Set(["GT", "DP", "AD", "ADF", "ADR", "AF", "GQ", "FS", "SOR"])' in source
    assert 'parts.join(" · ")' in source
    assert "const thresholds = {FS: isIndel ? 200 : 60, SOR: isIndel ? 10 : 3}" in source
    assert "metric-pass" not in stylesheet
    assert 'node("span", "▲", "metric-warning-icon")' in source
    assert "numericValue > threshold" in source
    assert "`${label} · max ${threshold}`" not in source
    assert "this.transcriptCards(annotations)" in source
    assert '["Gene", annotation.gene]' in source
    assert '["Transcript", annotation.transcript]' in source
    assert '["HGVSc", this.compactHgvs(annotation.hgvsc, "c.")]' in source
    assert '["HGVSp", this.compactHgvs(annotation.hgvsp, "p.")]' in source
    assert '["ClinVar", annotation.clinical_significance]' in source
    assert '["Exon / intron", annotation.exon_intron]' in source
    assert '["Canonical", annotation.canonical ? "yes" : "no"]' in source
    assert ".detail-cards dl.transcript-card" in stylesheet
    assert ".transcript-card dd:last-of-type" not in stylesheet
    assert "grid-template-columns: 145px minmax(0, 1fr)" in stylesheet
    assert 'const order = ["VEP summary", "gnomAD", "1000 Genomes", "ExAC", "ESP", "TOPMed", "ALFA", "Other"]' in source
    assert 'node("h6", "Additional FORMAT info", "additional-format-heading")' in source
    assert 'node("section", undefined, "frequency-group frequency-summary")' in source
    assert 'normalized === "AF_MAX" ? "Max AF" : "Population"' in source
    assert ".frequency-summary { grid-column: 1 / -1; }" in stylesheet
    assert 'EAS: "East Asian"' in source
    assert 'NFE: "Non-Finnish European"' in source
    assert 'code.replace(/^GNOMAD[EG]_/, "")' in source
    assert 'gnomad: {dataset: "gnomad_r2_1", version: "2.1.1"}' in source
    assert 'gnomad: {dataset: "gnomad_r4", version: "4.1.1"}' in source
    assert 'referenceToolConfiguration(referenceBuild)' in source
    assert 'externalVariantTool(detail, toolName)' in source
    assert 'return null;' in source
    assert 'link.target = "_blank"' in source
    assert 'node("small", `v${externalTool.version}`, "frequency-tool-version")' in source
    assert 'node("span", "↗", "external-link-icon")' in source
    assert ".frequency-external-link" in stylesheet
    assert ".frequency-group dl { grid-template-columns: 125px" in stylesheet
    assert ".frequency-group dt { font-size: var(--detail-secondary-size); }" in stylesheet
    assert '"Not found"' in source
    frequency_disclosure = source[source.index('"Population frequencies"') - 160:
                                  source.index('"Population frequencies"') + 240]
    assert "disabled:" not in frequency_disclosure
    assert "grid-template-columns: 170px minmax(0, 1fr) 170px minmax(0, 1fr)" in stylesheet
    assert ".sample-evidence-grid dt { white-space: nowrap; }" in stylesheet
    assert '"Variant carriers"' in source
    assert '"Historical indexed runs"' in source
    assert "carrierIsHomozygous(carrier)" in source
    assert 'this.carrierZygosityGroup(workspace, "Homozygous"' in source
    assert 'this.carrierZygosityGroup(workspace, "Heterozygous"' in source
    assert "homozygous) ·" in source
    assert ".carrier-zygosity-group" in stylesheet
    assert ".carrier-sample strong { font-size: var(--detail-secondary-size)" in stylesheet
    assert "this.openCarrierSample(workspace, carrier, historical)" in source
    assert "Open ${carrier.display_name} at this variant" in source
    assert "await this.loadDetail(targetWorkspace, carrier.variant_id)" in source
    assert "await this.focusVariantInWorkspace(targetWorkspace, carrier.variant_id)" in source
    assert "async focusVariantInWorkspace(workspace, variantId)" in source
    assert 'new URLSearchParams({limit: "1", variant_id: String(variantId)})' in source
    assert "workspace.items = [item, ...workspace.items.filter" in source
    assert 'node("span", "●", "selected-variant-marker")' in source
    assert 'row.setAttribute("aria-current", "true")' in source
    assert "`${carrier.history_id}:${carrier.sample_id}`" in source
    assert "`${workspace.runId}:${carrier.sample_id}`" in source
    assert "/carriers`" in source
    assert ".variant-row.selected {" in stylesheet
    assert "inset 4px 0 #176b86" in stylesheet
    assert ".selected-variant-marker" in stylesheet


def test_damage_predictions_cover_pipeline_predictors_and_splicing_plugins():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()

    for predictor in (
        "SIFT", "POLYPHEN", "LRT", "MUTATIONTASTER", "MUTATIONASSESSOR",
        "FATHMM", "PROVEAN", "VEST4", "METASVM", "METALR", "M[-_]?CAP",
        "REVEL", "MUTPRED", "MVP", "MPC", "PRIMATEAI", "DEOGEN2", "ALOFT",
        "CADD", "DANN", "EIGEN", "GENOCANYON", "LINSIGHT", "FITCONS",
        "SPLICEAI", "GENESPLICER", "MAXENTSCAN", "SPLICEREGION",
        "GERP", "PHYLOP", "PHASTCONS", "SIPHY", "BSTATISTIC",
    ):
        assert predictor in source
    assert "this.annotationMetadataFields(" in source
    assert "[proteinImpact, generalImpact, splicing, conservation]" in source


def test_viewer_can_create_one_archived_run_from_multiple_vcfs():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()

    assert 'id="add-archived-run"' in source
    assert 'this.hasAttribute("allow-archived-import")' in source
    assert "step=postprocessing&pickerId=" in source
    assert "Select one or more VCF files" in source
    assert 'this.request("/archived-runs"' in source
    assert "The VCF files are linked without copying them" in source


def test_variant_package_limits_helper_runtime_imports_to_existing_ga2_reader():
    package = STATIC / "helper_variants"
    dependencies = []
    for path in package.glob("*.py"):
        for statement in ast.walk(ast.parse(path.read_text())):
            if isinstance(statement, ast.ImportFrom) and (statement.module or "").startswith("helper_next"):
                dependencies.append((path.name, statement.module, tuple(alias.name for alias in statement.names)))
            elif isinstance(statement, ast.Import):
                assert not any(alias.name.startswith("helper_next") for alias in statement.names)
    # ClinVar reuses ga2; gnomAD trusts submitted alleles without a local FASTA reader.
    # CACHE-06 administrative readers reuse existing stores.
    assert set(dependencies) == {
        ("clinvar_local.py", "helper_next.core", ("biological_identity",)),
        ("source_registry.py", "helper_next.core.acmg_mechanism_store", ("MechanismStore",)),
        ("source_registry.py", "helper_next.core.acmg_transcripts", ("TranscriptReferenceProvider", "VERSION")),
        ("source_registry.py", "helper_next.core.acmg_reference", ("reference_record",)),
        ("source_registry.py", "helper_next.core", ("reference_validation",)),
        ("source_registry.py", "helper_next.core.project", ("get_project_paths",)),
    }
