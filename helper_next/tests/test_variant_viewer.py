from pathlib import Path

from helper_next.api.app import create_app


STATIC = Path(__file__).resolve().parents[1] / "src"


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
    assert "this.refreshRuns(false)" in source
    assert "this.refreshRuns(true)" not in source
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


def test_variant_columns_are_reorderable_and_include_vep_fields():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()

    expected_order = [
        'key: "filter_alert"', 'key: "genotypes"',
        'key: "gene"', 'key: "hgvsc"', 'key: "hgvsp"',
        'key: "population_af"',
        'key: "clinical_significance"', 'key: "consequence"', 'key: "exon_intron"',
        'key: "depth"', 'key: "allele_fraction"', 'key: "transcript"',
    ]
    positions = [source.index(item) for item in expected_order]
    assert positions == sorted(positions)
    assert 'label: "Clinical"' in source
    assert 'label: "AF_max"' in source
    assert 'label: "Exon / intron"' in source
    assert "dragHandle.draggable = true" in source
    assert "cell.draggable = true" not in source
    assert 'resizeHandle.addEventListener("pointerdown"' in source
    assert 'cell.addEventListener("drop"' in source
    assert "localStorage.setItem(COLUMN_STORAGE_KEY" in source
    assert "localStorage.setItem(COLUMN_WIDTH_STORAGE_KEY" in source
    assert 'node("span", "▲", "filter-alert")' in source
    assert 'normalized !== "PASS"' in source
    assert '{key: "variant"' not in source
    assert '{key: "filter_status"' not in source
    assert '{key: "quality"' not in source


def test_gene_context_action_opens_a_filtered_workspace_tab():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()

    assert 'cell.addEventListener("contextmenu"' in source
    assert "this.openGeneWorkspace(workspace, item.gene)" in source
    assert 'if (workspace.gene) params.set("gene", workspace.gene)' in source
    assert "? `${workspace.gene} · ${workspace.sample.display_name}`" in source


def test_filter_panel_supports_clinical_inheritance_and_removable_gene_panels():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()
    stylesheet = (STATIC / "helper_variants/web/static/variant-browser.css").read_text()

    assert '"Clinical", "clinicalSignificance"' in source
    assert '"compound", "recessive", "dominant", "x_linked", "y_linked"' in source
    assert 'params.set("inheritance_candidates"' in source
    assert 'node("button", "🗑", "panelapp-source-remove")' in source
    assert "removePanelSource(workspace, textarea, sourceHost, source)" in source
    assert 'population.name = "populationFrequency"' in source
    assert '"Maximum across populations"' in source
    assert 'likely_pathogenic: "Likely pathogenic"' in source
    assert 'uncertain_significance: "VUS"' in source
    assert 'likely_benign: "Likely benign"' in source
    assert '__not_reported__: "Not reported"' in source
    assert "Up to 5,000 HGNC gene symbols" not in source
    assert ".filter-evidence { grid-template-columns: 1fr; }" in stylesheet
    assert ".interpretation-grid { grid-template-columns: repeat(4" in stylesheet
    assert 'lowerGrid.append(sampleEvidence, genePanel)' in source
    assert ".filter-lower-grid { display: grid" in stylesheet
    assert "grid-template-columns: minmax(0, 2fr) minmax(260px, 1fr)" in stylesheet
    assert ".workspace-grid:not(.detail-closed) .filter-lower-grid { grid-template-columns: 1fr; }" in stylesheet
    assert ".workspace-grid:not(.detail-closed) .evidence-grid { grid-template-columns: repeat(3" in stylesheet


def test_variant_hgvs_is_compact_and_detail_panel_can_be_closed():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()

    assert 'this.compactHgvs(item[key], "c.")' in source
    assert 'this.compactHgvs(item[key], "p.")' in source
    assert 'compact.replace(/%3D/gi, "=")' in source
    assert 'workspace-grid${workspace.detail ? "" : " detail-closed"}' in source
    assert 'node("button", "×", "detail-close")' in source
    assert "workspace.detail = null" in source
    assert "variantDetailAnnotationLabel(annotations = [])" in source
    assert "annotations.find(item => item.canonical)" in source
    assert 'const coding = [gene, hgvsc].filter(Boolean).join(":")' in source
    assert 'hgvsp ? `(${hgvsp})` : ""' in source
    assert '"detail-identity"' in source
    assert '"detail-annotation"' in source


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
    assert '"ClinVar evidence"' in source
    assert "clinvarEvidenceContent(clinvarEvidence, databaseIds, clinvarSearchUrl)" in source
    assert "clinvarReviewStatuses(statuses = [])" in source
    assert '"ClinVar contains conflicting classifications.' in source
    assert '"clinvar-review-stars"' in source
    assert 'heading.append(classifications)' in source
    assert "clinvarClassificationLabels(evidence = {})" in source
    assert '`${item.label} (${Number(item.count)})`' in source
    assert "const classifications = evidence.classifications || [];" in source
    assert 'classifications.join(" · ")' in source
    assert 'node("div", undefined, "clinvar-identifiers")' in source
    assert source.index('heading.append(classifications)') < source.index('"clinvar-identifiers"')
    assert 'Current aggregate record on ClinVar' not in source
    assert 'Review status reflects the level of review reported by ClinVar' not in source
    assert ".clinvar-classification.pathogenic" in stylesheet
    assert ".clinvar-conflict-warning" in stylesheet
    assert ".clinvar-identifiers .database-identifier-link { font-size: var(--detail-compact-size); }" in stylesheet
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
    assert '["pLoF o/e", observedExpected(' in source
    assert '["Missense o/e", observedExpected(' in source
    assert 'geneConstraintMetricLabel(label, help)' in source
    assert 'gnomAD v4.1 recommends <0.45' in source
    assert '>3.09 is a widely used historical threshold' in source
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
    assert 'const summaryClass = group.database === "VEP summary"' in source
    assert ".frequency-summary { grid-column: 1 / -1; }" in stylesheet
    assert 'EAS: "East Asia"' in source
    assert 'NFE: "Non-Finnish European"' in source
    assert 'code.replace(/^GNOMAD[EG]_/, "")' in source
    assert 'gnomad: {dataset: "gnomad_r2_1", version: "2.1"}' in source
    assert 'gnomad: {dataset: "gnomad_r4", version: "4"}' in source
    assert 'referenceToolConfiguration(referenceBuild)' in source
    assert 'externalVariantTool(detail, toolName)' in source
    assert 'return null;' in source
    assert 'link.target = "_blank"' in source
    assert 'node("small", `v${externalTool.version}`, "frequency-tool-version")' in source
    assert 'node("span", "↗", "external-link-icon")' in source
    assert ".frequency-external-link" in stylesheet
    assert ".frequency-group dl { grid-template-columns: 185px" in stylesheet
    assert ".frequency-group dt { font-size: var(--detail-secondary-size); white-space: nowrap; }" in stylesheet
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
    assert "/carriers`" in source


def test_viewer_can_create_one_archived_run_from_multiple_vcfs():
    source = (STATIC / "helper_variants/web/static/variant-browser.js").read_text()

    assert 'id="add-archived-run"' in source
    assert 'this.hasAttribute("allow-archived-import")' in source
    assert "step=postprocessing&pickerId=" in source
    assert "Select one or more VCF files" in source
    assert 'this.request("/archived-runs"' in source
    assert "The VCF files are linked without copying them" in source


def test_variant_package_has_no_helper_runtime_imports():
    package = STATIC / "helper_variants"
    python_sources = "\n".join(path.read_text() for path in package.glob("*.py"))
    assert "import helper_next" not in python_sources
    assert "from helper_next" not in python_sources
