const ROW_HEIGHT = 36;
const PAGE_SIZE = 200;
const OVERSCAN = 8;
const STYLESHEET_URL = new URL("./variant-browser.css?v=20261006-38", import.meta.url).href;
const COLUMN_STORAGE_KEY = "helper-variant-column-order-v6";
const COLUMN_WIDTH_STORAGE_KEY = "helper-variant-column-widths-v4";
const VARIANT_COLUMNS = [
  {key: "filter_alert", label: "", width: 34},
  {key: "genotypes", label: "GT", width: 85},
  {key: "gene", label: "Gene", width: 110},
  {key: "hgvsc", label: "HGVSc", width: 160},
  {key: "hgvsp", label: "HGVSp", width: 160},
  {key: "population_af", label: "AF_max", width: 85},
  {key: "clinical_significance", label: "Clinical", width: 140},
  {key: "consequence", label: "Consequence", width: 180},
  {key: "exon_intron", label: "Exon / intron", width: 105},
  {key: "depth", label: "DP", width: 65},
  {key: "allele_fraction", label: "VAF", width: 75},
  {key: "transcript", label: "Transcript", width: 150},
];
const VARIANT_COLUMNS_BY_KEY = new Map(VARIANT_COLUMNS.map(column => [column.key, column]));
const FORMAT_FIELD_LABELS = {
  PS: "Phase set (PS)", PID: "Phase ID (PID)", PGT: "Phased genotype (PGT)",
  FT: "Sample filter (FT)", MIN_DP: "Minimum depth (MIN_DP)",
  RGQ: "Reference genotype quality (RGQ)", PL: "Genotype likelihoods (PL)",
  GL: "Log genotype likelihoods (GL)", GP: "Genotype probabilities (GP)",
  SB: "Strand-bias counts (SB)", SAC: "Strand allele counts (SAC)",
  F1R2: "F1R2 allele counts", F2R1: "F2R1 allele counts",
  RO: "Reference observations (RO)", AO: "Alternate observations (AO)",
  QR: "Reference quality sum (QR)", QA: "Alternate quality sum (QA)",
  MQ: "Mapping quality (MQ)", TLOD: "Tumor log odds (TLOD)",
  NLOD: "Normal log odds (NLOD)", FDP: "Filtered depth (FDP)",
  FS: "Fisher strand bias (FS)", SOR: "Strand odds ratio (SOR)",
};
const FORMAT_FIELD_ORDER = [
  "PS", "PID", "PGT", "MIN_DP", "FDP", "RO", "AO", "RGQ", "PL", "GL", "GP",
  "MQ", "FS", "SOR", "SB", "SAC", "F1R2", "F2R1", "QR", "QA", "TLOD", "NLOD", "FT",
];
const POPULATION_LABELS = {
  AF: "Overall", AFR: "African", AMR: "Admixed American", AMI: "Amish",
  ASJ: "Ashkenazi Jewish", EAS: "East Asia", FIN: "Finnish", MID: "Middle East",
  NFE: "Non-Finnish European", EUR: "Europe", SAS: "South Asia", OTH: "Other",
  REMAINING: "Remaining", AA: "African American", EA: "European American",
};

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function value(value, fallback = "—") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

class VariantBrowser extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this.apiBase = "/api/variants";
    this.routePrefix = "variants";
    this.runs = [];
    this.selectedRun = null;
    this.samples = [];
    this.workspaces = new Map();
    this.activeWorkspace = null;
    this.routeHandler = () => this.restoreRoute();
    this.activated = false;
    this.visibilityObserver = null;
    this.allowArchivedImport = false;
    this.columnOrder = this.loadColumnOrder();
    this.columnWidths = this.loadColumnWidths();
    this.draggedColumn = null;
    this.activePickerId = null;
    this.messageHandler = event => this.handleArchivedRunFiles(event);
  }

  connectedCallback() {
    this.apiBase = (this.getAttribute("api-base") || "/api/variants").replace(/\/$/, "");
    this.routePrefix = this.getAttribute("route-prefix") || "variants";
    this.allowArchivedImport = this.hasAttribute("allow-archived-import");
    const archiveAction = this.allowArchivedImport
      ? '<button id="add-archived-run" type="button">Add archived run</button>' : "";
    this.shadowRoot.innerHTML = `
      <link rel="stylesheet" href="${STYLESHEET_URL}">
      <div class="variant-app">
        <details id="run-drawer" class="run-drawer" open>
          <summary><span>Analysis runs</span><strong id="active-run-label">Select a run</strong></summary>
          <div class="run-drawer-body">
            <div class="run-browser-controls">
              ${archiveAction}
              <input id="run-search" type="search" placeholder="Search run, panel, pipeline…" aria-label="Search variant runs">
            </div>
            <div id="run-list" class="run-list"></div>
          </div>
        </details>
        <p id="status" class="status" aria-live="polite">Loading runs…</p>
        <div id="variant-layout" class="layout">
          <aside id="sample-panel" class="sample-panel">
            <button id="sample-panel-toggle" class="sample-panel-toggle" type="button" aria-expanded="true" title="Hide samples">
              <span class="sample-toggle-label">Samples</span><span class="sample-toggle-icon" aria-hidden="true">‹</span>
            </button>
            <div class="sample-panel-body">
              <div id="sample-toolbar" class="sample-toolbar" hidden>
                <div><span id="sample-count"></span></div>
                <input id="sample-search" type="search" placeholder="Search sample…" aria-label="Search samples in selected run">
              </div>
              <div id="sample-strip" class="sample-strip"></div>
            </div>
          </aside>
          <main class="content">
            <div id="workspace-tabs" class="workspace-tabs"></div>
            <div id="workspace" class="workspace-empty">Select an indexed run and open a sample.</div>
          </main>
        </div>
        <div id="dialog-layer"></div>
      </div>`;
    this.shadowRoot.querySelector("#run-search").addEventListener("input", () => this.renderRuns());
    this.shadowRoot.querySelector("#sample-search").addEventListener("input", () => this.renderSamples());
    this.shadowRoot.querySelector("#sample-panel-toggle").addEventListener("click", () => this.toggleSamplePanel());
    this.shadowRoot.querySelector("#add-archived-run")?.addEventListener("click", () => this.openArchivedRunPicker());
    window.addEventListener("hashchange", this.routeHandler);
    if (this.allowArchivedImport) window.addEventListener("message", this.messageHandler);
    if ("IntersectionObserver" in window) {
      this.visibilityObserver = new IntersectionObserver(entries => {
        if (entries.some(entry => entry.isIntersecting)) this.activate();
      });
      this.visibilityObserver.observe(this);
    } else {
      this.activate();
    }
  }

  disconnectedCallback() {
    window.removeEventListener("hashchange", this.routeHandler);
    if (this.allowArchivedImport) window.removeEventListener("message", this.messageHandler);
    this.visibilityObserver?.disconnect();
    for (const workspace of this.workspaces.values()) {
      workspace.pageController?.abort();
      workspace.detailController?.abort();
      workspace.carrierController?.abort();
      workspace.genePhenotypeController?.abort();
      window.clearTimeout(workspace.genePhenotypeTimer);
    }
  }

  activate() {
    if (this.activated) return;
    this.activated = true;
    this.visibilityObserver?.disconnect();
    this.refreshRuns(false);
  }

  async request(path, options) {
    const response = await fetch(`${this.apiBase}${path}`, options);
    let payload;
    try { payload = await response.json(); } catch { payload = {}; }
    if (!response.ok) throw new Error(payload.detail || `${response.status} ${response.statusText}`);
    return payload;
  }

  setStatus(message, error = false) {
    const status = this.shadowRoot.querySelector("#status");
    status.textContent = message || "";
    status.classList.toggle("error", error);
  }

  async refreshRuns(restore = false) {
    this.setStatus("Loading variant runs…");
    try {
      const payload = await this.request("/runs");
      this.runs = payload.runs || [];
      this.renderRuns();
      this.setStatus(`${this.runs.length} run${this.runs.length === 1 ? "" : "s"} available`);
      if (restore) await this.restoreRoute();
    } catch (error) {
      this.setStatus(error.message, true);
      this.shadowRoot.querySelector("#run-list").replaceChildren(
        node("p", "Variant runs could not be loaded.", "empty")
      );
    }
  }

  renderRuns() {
    const query = this.shadowRoot.querySelector("#run-search").value.trim().toLowerCase();
    const filtered = this.runs.filter(run => JSON.stringify(run).toLowerCase().includes(query));
    const list = this.shadowRoot.querySelector("#run-list");
    const header = node("div", undefined, "run-row run-table-header");
    ["Run", "Date", "Samples", "Panel", "Pipeline", "Reference", "Status", ""].forEach(label => {
      header.append(node("span", label));
    });
    const rows = filtered.map(run => {
      const row = node("div", undefined, `run-row${run.history_id === this.selectedRun ? " selected" : ""}`);
      row.tabIndex = 0;
      row.setAttribute("role", "button");
      row.setAttribute("aria-label", `Open run ${run.run_id || "unnamed"}`);
      const summary = run.summary;
      const values = [
        run.run_id || "Unnamed run", this.formatDate(run.created_at),
        summary?.sample_count ?? run.sample_count, run.panel, run.pipeline,
        run.reference_build || summary?.reference_build,
      ];
      values.forEach((fieldValue, index) => row.append(node(index === 0 ? "strong" : "span", value(fieldValue))));
      row.append(node("span", run.index_status, `badge ${run.index_status}`));
      const actions = node("div", undefined, "run-row-actions");
      if (run.index_status !== "complete") {
        const indexButton = node("button", "↻", "icon-button");
        indexButton.title = run.index_status === "indexing" || run.index_status === "pending" ? "Indexing" : "Create variant index";
        indexButton.setAttribute("aria-label", indexButton.title);
        indexButton.disabled = run.index_status === "indexing" || run.index_status === "pending";
        indexButton.addEventListener("click", event => {
          event.stopPropagation();
          this.startIndex(run);
        });
        actions.append(indexButton);
      }
      const infoButton = node("button", "ⓘ", "icon-button");
      infoButton.title = "Tools and versions";
      infoButton.setAttribute("aria-label", `Tools and versions for ${run.run_id || "run"}`);
      infoButton.addEventListener("click", event => {
        event.stopPropagation();
        this.openToolsPanel(run.history_id, run.run_id);
      });
      actions.append(infoButton);
      row.append(actions);
      const select = () => this.activateRun(run);
      row.addEventListener("click", select);
      row.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(); }
      });
      return row;
    });
    list.replaceChildren(...(rows.length ? [header, ...rows] : [node("p", "No matching runs.", "empty")]));
  }

  activateRun(run) {
    if (run.index_status === "complete") {
      this.selectRun(run.history_id);
    } else if (run.index_status === "indexing" || run.index_status === "pending") {
      this.setStatus(`Indexing ${run.run_id}…`);
      this.pollIndex(run.history_id);
    } else {
      this.startIndex(run);
    }
  }

  formatDate(raw) {
    if (!raw) return "";
    const parsed = new Date(raw);
    if (Number.isNaN(parsed.getTime())) return String(raw);
    return new Intl.DateTimeFormat(undefined, {dateStyle: "medium", timeStyle: "short"}).format(parsed);
  }

  openArchivedRunPicker() {
    const random = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    this.activePickerId = `archived-run-${random}`;
    const picker = this.getAttribute("file-picker-url") || "/static/file_picker.html";
    const separator = picker.includes("?") ? "&" : "?";
    const url = `${picker}${separator}step=postprocessing&pickerId=${encodeURIComponent(this.activePickerId)}`;
    const popup = window.open(url, "helper-archived-run-picker", "width=1050,height=720,resizable=yes,scrollbars=yes");
    if (!popup) this.setStatus("The file picker popup was blocked by the browser.", true);
    else this.setStatus("Select one or more VCF files for the archived run.");
  }

  handleArchivedRunFiles(event) {
    if (event.origin !== window.location.origin || !this.activePickerId) return;
    if (event.data?.type !== "helper-next-files-selected") return;
    const pickerId = this.activePickerId;
    this.activePickerId = null;
    const files = Array.isArray(event.data.files) ? event.data.files : [];
    this.renderArchivedRunDialog(pickerId, files);
  }

  renderArchivedRunDialog(pickerId, files) {
    const layer = this.shadowRoot.querySelector("#dialog-layer");
    const backdrop = node("div", undefined, "dialog-backdrop");
    const dialog = node("section", undefined, "archive-dialog");
    const heading = node("div", undefined, "dialog-heading");
    heading.append(node("div"), node("button", "×", "dialog-close"));
    heading.firstChild.append(node("h4", "Add archived run"), node("p", `${files.length} VCF file${files.length === 1 ? "" : "s"} selected`));
    heading.lastChild.setAttribute("aria-label", "Close archived run dialog");
    heading.lastChild.addEventListener("click", () => layer.replaceChildren());

    const fileList = node("ul", undefined, "selected-files");
    files.forEach(path => fileList.append(node("li", String(path).split(/[\\/]/).pop())));
    const form = node("form", undefined, "archive-form");
    form.innerHTML = `
      <label>Run name<input name="name" required placeholder="e.g. Run 2024-01"></label>
      <label>Reference build<select name="reference_build" required><option value="">Select…</option><option value="GRCh38">GRCh38</option><option value="GRCh37">GRCh37 / hg19</option></select></label>
      <label>Panel / notes<input name="panel" placeholder="Optional"></label>
      <p class="archive-note">The VCF files are linked without copying them. Keep the original files in their current location.</p>
      <p class="dialog-error" aria-live="polite"></p>
      <div class="dialog-actions"><button type="button" class="cancel-import">Cancel</button><button type="submit" class="primary">Create and index run</button></div>`;
    form.querySelector(".cancel-import").addEventListener("click", () => layer.replaceChildren());
    form.addEventListener("submit", event => this.createArchivedRun(event, pickerId, layer));
    dialog.append(heading, fileList, form);
    backdrop.append(dialog);
    backdrop.addEventListener("click", event => event.target === backdrop && layer.replaceChildren());
    layer.replaceChildren(backdrop);
    form.elements.name.focus();
  }

  async createArchivedRun(event, pickerId, layer) {
    event.preventDefault();
    const form = event.currentTarget;
    const submit = form.querySelector('button[type="submit"]');
    const errorNode = form.querySelector(".dialog-error");
    const data = new FormData(form);
    submit.disabled = true;
    errorNode.textContent = "";
    try {
      const payload = await this.request("/archived-runs", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          picker_id: pickerId, name: data.get("name"),
          reference_build: data.get("reference_build"), panel: data.get("panel"),
        }),
      });
      layer.replaceChildren();
      this.setStatus(`Indexing archived run ${payload.run_id}…`);
      await this.refreshRuns();
      this.pollIndex(payload.history_id);
    } catch (error) {
      errorNode.textContent = error.message;
      submit.disabled = false;
    }
  }

  async startIndex(run) {
    this.setStatus(`Starting index for ${run.run_id}…`);
    try {
      await this.request(`/runs/${encodeURIComponent(run.history_id)}/index`, {method: "POST"});
      run.index_status = "indexing";
      this.renderRuns();
      this.pollIndex(run.history_id);
    } catch (error) { this.setStatus(error.message, true); }
  }

  async pollIndex(historyId) {
    try {
      const status = await this.request(`/runs/${encodeURIComponent(historyId)}/index-status`);
      if (status.status === "indexing" || status.status === "pending") {
        window.setTimeout(() => this.pollIndex(historyId), 1500);
        return;
      }
      await this.refreshRuns();
      if (status.status === "complete") await this.selectRun(historyId);
      else this.setStatus(status.error || status.sources?.find(source => source.error)?.error || "Indexing failed", true);
    } catch (error) { this.setStatus(error.message, true); }
  }

  async selectRun(historyId, routeSampleId = null) {
    this.selectedRun = historyId;
    const selected = this.runs.find(run => run.history_id === historyId);
    this.shadowRoot.querySelector("#active-run-label").textContent = selected?.run_id || "Selected run";
    this.shadowRoot.querySelector("#run-drawer").open = false;
    this.renderRuns();
    this.setStatus("Loading samples…");
    try {
      const payload = await this.request(`/runs/${encodeURIComponent(historyId)}/samples`);
      this.samples = payload.samples || [];
      this.shadowRoot.querySelector("#sample-search").value = "";
      const currentWorkspace = this.workspaces.get(this.activeWorkspace);
      if (currentWorkspace?.runId !== historyId) {
        const sameRun = Array.from(this.workspaces.values()).filter(item => item.runId === historyId);
        this.activeWorkspace = sameRun.at(-1)?.key || null;
      }
      this.shadowRoot.querySelector("#sample-toolbar").hidden = false;
      this.shadowRoot.querySelector("#sample-count").textContent = `${this.samples.length} available`;
      this.renderSamples();
      this.renderTabs();
      this.renderWorkspace();
      this.setStatus(`${payload.run_id}: ${this.samples.length} sample${this.samples.length === 1 ? "" : "s"}`);
      if (routeSampleId !== null) {
        const sample = this.samples.find(item => item.sample_id === Number(routeSampleId));
        if (sample) await this.openSample(sample, false);
      } else {
        this.setRoute(historyId, null);
      }
    } catch (error) {
      this.samples = [];
      this.shadowRoot.querySelector("#sample-toolbar").hidden = true;
      this.renderSamples();
      this.setStatus(error.message, true);
    }
  }

  async openToolsPanel(identifier = this.selectedRun, runName = "") {
    if (!identifier) return;
    const layer = this.shadowRoot.querySelector("#dialog-layer");
    const backdrop = node("div", undefined, "dialog-backdrop");
    const dialog = node("section", undefined, "tools-dialog");
    const heading = node("div", undefined, "dialog-heading");
    heading.append(node("div"), node("button", "×", "dialog-close"));
    heading.firstChild.append(
      node("h4", "Analysis tools"),
      node("p", runName ? `${runName} · tools actually resolved for this run.` : "Tools actually resolved for this run."),
    );
    heading.lastChild.setAttribute("aria-label", "Close tools panel");
    heading.lastChild.addEventListener("click", () => layer.replaceChildren());
    const body = node("div", undefined, "tools-list");
    body.append(node("p", "Loading tools…", "loading"));
    dialog.append(heading, body);
    backdrop.append(dialog);
    backdrop.addEventListener("click", event => event.target === backdrop && layer.replaceChildren());
    layer.replaceChildren(backdrop);
    try {
      const payload = await this.request(`/runs/${encodeURIComponent(identifier)}/tools`);
      const cards = (payload.tools || []).map(tool => {
        const card = node("article", undefined, "tool-card");
        const toolHeading = node("div");
        toolHeading.append(node("strong", tool.name), node("span", tool.version || "version not recorded"));
        card.append(toolHeading);
        const uses = (tool.uses || []).map(use => `${use.step} · ${use.operation}`);
        if (uses.length) card.append(node("p", uses.join("; ")));
        return card;
      });
      body.replaceChildren(...(cards.length ? cards : [node("p", "No resolved tools were recorded for this run.", "empty")]));
    } catch (error) {
      body.replaceChildren(node("p", error.message, "inline-error"));
    }
  }

  toggleSamplePanel() {
    const panel = this.shadowRoot.querySelector("#sample-panel");
    const layout = this.shadowRoot.querySelector("#variant-layout");
    const toggle = this.shadowRoot.querySelector("#sample-panel-toggle");
    const icon = toggle.querySelector(".sample-toggle-icon");
    const collapsed = panel.classList.toggle("collapsed");
    layout.classList.toggle("samples-collapsed", collapsed);
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.title = collapsed ? "Show samples" : "Hide samples";
    icon.textContent = collapsed ? "›" : "‹";
  }

  renderSamples() {
    const strip = this.shadowRoot.querySelector("#sample-strip");
    const query = this.shadowRoot.querySelector("#sample-search").value.trim().toLowerCase();
    const filtered = this.samples.filter(sample => JSON.stringify(sample).toLowerCase().includes(query));
    const cards = filtered.map(sample => {
      const details = node("details", undefined, "sample-card");
      details.append(node("summary", sample.display_name));
      const body = node("div", undefined, "sample-card-body");
      const facts = node("dl");
      this.sampleFacts(sample).forEach(([label, fieldValue]) => {
        facts.append(node("dt", label), node("dd", value(fieldValue)));
      });
      const open = node("button", "Open sample", "open-sample");
      open.addEventListener("click", () => this.openSample(sample));
      body.append(facts, open);
      details.append(body);
      return details;
    });
    const emptyMessage = this.samples.length ? "No matching samples." : "No indexed samples in this run.";
    strip.replaceChildren(...(cards.length ? cards : [node("p", emptyMessage, "empty")]));
  }

  sampleFacts(sample) {
    const metadata = sample.metadata || {};
    const analysisType = metadata.analysis_type || "";
    const analysisId = metadata.analysis_id || metadata.sample_id || "";
    const fields = [
      ["ID", metadata.sample_id || metadata.analysis_id || sample.display_name],
      ["Family", analysisType === "family" ? analysisId : ""],
      ["Role", metadata.relationship || sample.role],
      ["Analysis", analysisType],
      ["Individual", metadata.individual_id],
      ["Sex", metadata.sex],
      ["Father", metadata.father],
      ["Mother", metadata.mother],
      ["Affected", metadata.affected],
      ["Control relation", metadata.control_relationship],
      ["Tissue / specimen", metadata.specimen_type || sample.specimen_type],
      ["Tumor purity", metadata.tumor_purity],
      ["Twin group", metadata.twin_group],
      ["Variants", sample.variant_count],
    ];
    return fields.filter(([, fieldValue]) => fieldValue !== null && fieldValue !== undefined && fieldValue !== "");
  }

  async openSample(sample, updateRoute = true) {
    const key = `${this.selectedRun}:${sample.sample_id}`;
    if (!this.workspaces.has(key)) {
      this.workspaces.set(key, {
        key, runId: this.selectedRun, sample, items: [], cursor: null,
        initialized: false, loading: false, error: "", detail: null,
        scrollTop: 0, scrollLeft: 0, filters: this.emptyFilters(), filtersOpen: false,
        filterOptions: null, filterOptionsLoading: false, panelAppSources: [],
        panelAppDraftSources: null, panelAppDraftGenes: null,
      });
    }
    this.activeWorkspace = key;
    this.renderTabs();
    this.renderWorkspace();
    if (updateRoute) this.setRoute(this.selectedRun, sample.sample_id);
    const workspace = this.workspaces.get(key);
    if (!workspace.initialized && !workspace.loading) await this.loadPage(workspace);
  }

  async openGeneWorkspace(sourceWorkspace, gene) {
    const normalizedGene = String(gene || "").trim();
    if (!normalizedGene) return;
    const key = `${sourceWorkspace.runId}:${sourceWorkspace.sample.sample_id}:gene:${normalizedGene.toUpperCase()}`;
    if (!this.workspaces.has(key)) {
      this.workspaces.set(key, {
        key, runId: sourceWorkspace.runId, sample: sourceWorkspace.sample, gene: normalizedGene,
        items: [], cursor: null, initialized: false, loading: false, error: "", detail: null,
        scrollTop: 0, scrollLeft: 0, filters: this.emptyFilters(), filtersOpen: false,
        filterOptions: null, filterOptionsLoading: false, panelAppSources: [],
        panelAppDraftSources: null, panelAppDraftGenes: null,
      });
    }
    this.activeWorkspace = key;
    this.renderTabs();
    this.renderWorkspace();
    this.setRoute(sourceWorkspace.runId, sourceWorkspace.sample.sample_id);
    const workspace = this.workspaces.get(key);
    if (!workspace.initialized && !workspace.loading) await this.loadPage(workspace);
  }

  closeWorkspace(key) {
    const workspace = this.workspaces.get(key);
    workspace?.pageController?.abort();
    workspace?.detailController?.abort();
    workspace?.carrierController?.abort();
    workspace?.genePhenotypeController?.abort();
    window.clearTimeout(workspace?.genePhenotypeTimer);
    this.workspaces.delete(key);
    if (this.activeWorkspace === key) {
      const sameRun = Array.from(this.workspaces.values()).filter(item => item.runId === this.selectedRun);
      this.activeWorkspace = sameRun.at(-1)?.key || null;
    }
    this.renderTabs();
    this.renderWorkspace();
    const active = this.workspaces.get(this.activeWorkspace);
    this.setRoute(active?.runId || this.selectedRun, active?.sample.sample_id || null);
  }

  renderTabs() {
    const tabs = this.shadowRoot.querySelector("#workspace-tabs");
    const elements = Array.from(this.workspaces.values())
      .filter(workspace => workspace.runId === this.selectedRun)
      .map(workspace => {
        const wrapper = node("div", undefined, `workspace-tab${workspace.key === this.activeWorkspace ? " active" : ""}`);
        const tabLabel = workspace.gene
          ? `${workspace.gene} · ${workspace.sample.display_name}` : workspace.sample.display_name;
        const select = node("button", tabLabel);
        select.addEventListener("click", () => {
          this.activeWorkspace = workspace.key;
          this.renderTabs();
          this.renderWorkspace();
          this.setRoute(workspace.runId, workspace.sample.sample_id);
        });
        const close = node("button", "×", "close-tab");
        close.setAttribute("aria-label", `Close ${tabLabel}`);
        close.addEventListener("click", () => this.closeWorkspace(workspace.key));
        wrapper.append(select, close);
        return wrapper;
      });
    tabs.replaceChildren(...elements);
  }

  async loadPage(workspace) {
    if (workspace.loading || (workspace.initialized && !workspace.cursor)) return;
    workspace.loading = true;
    workspace.error = "";
    workspace.pageController?.abort();
    workspace.pageController = new AbortController();
    this.renderWorkspace();
    const params = new URLSearchParams({limit: String(PAGE_SIZE)});
    if (workspace.cursor) params.set("cursor", workspace.cursor);
    if (workspace.gene) params.set("gene", workspace.gene);
    const filters = workspace.filters || this.emptyFilters();
    if (!workspace.gene && filters.genes.length) params.set("genes", filters.genes.join(","));
    if (filters.maxAf !== "") params.set("max_af", filters.maxAf);
    if (filters.populationFrequency !== "MAX_AF") params.set("population_frequency", filters.populationFrequency);
    if (!filters.includeMissingAf) params.set("include_missing_af", "false");
    if (filters.consequences.length) params.set("consequences", filters.consequences.join(","));
    if (filters.clinicalSignificances.length) params.set("clinical_significances", filters.clinicalSignificances.join(","));
    if (filters.inheritanceCandidates.length) params.set("inheritance_candidates", filters.inheritanceCandidates.join(","));
    if (filters.filterMode !== "all") params.set("filter_mode", filters.filterMode);
    if (filters.filterStatuses.length) params.set("filter_statuses", filters.filterStatuses.join(","));
    if (filters.zygosities.length) params.set("zygosities", filters.zygosities.join(","));
    if (filters.minDepth !== "") params.set("min_depth", filters.minDepth);
    if (filters.minVaf !== "") params.set("min_vaf", filters.minVaf);
    if (filters.minQuality !== "") params.set("min_quality", filters.minQuality);
    try {
      const payload = await this.request(
        `/runs/${encodeURIComponent(workspace.runId)}/samples/${workspace.sample.sample_id}/variants?${params}`,
        {signal: workspace.pageController.signal},
      );
      workspace.items.push(...(payload.items || []));
      workspace.cursor = payload.next_cursor;
      workspace.initialized = true;
    } catch (error) {
      if (error.name !== "AbortError") workspace.error = error.message;
    } finally {
      workspace.loading = false;
      if (workspace.key === this.activeWorkspace) this.renderWorkspace();
    }
  }

  emptyFilters() {
    return {
      genes: [], maxAf: "", populationFrequency: "MAX_AF", includeMissingAf: true, consequences: [],
      clinicalSignificances: [], inheritanceCandidates: [],
      filterMode: "all", filterStatuses: [], zygosities: [],
      minDepth: "", minVaf: "", minQuality: "",
    };
  }

  activeFilterCount(workspace) {
    const filters = workspace.filters || this.emptyFilters();
    return [filters.genes.length, filters.maxAf !== "", filters.consequences.length,
      filters.clinicalSignificances.length, filters.inheritanceCandidates.length,
      filters.filterMode !== "all", filters.zygosities.length, filters.minDepth !== "",
      filters.minVaf !== "", filters.minQuality !== ""].filter(Boolean).length;
  }

  async loadFilterOptions(workspace) {
    if (workspace.filterOptions || workspace.filterOptionsLoading) return;
    workspace.filterOptionsLoading = true;
    try {
      workspace.filterOptions = await this.request(
        `/runs/${encodeURIComponent(workspace.runId)}/samples/${workspace.sample.sample_id}/filter-options`,
      );
    } catch (error) {
      workspace.filterOptionsError = error.message;
    } finally {
      workspace.filterOptionsLoading = false;
      if (workspace.key === this.activeWorkspace && workspace.filtersOpen) this.renderWorkspace();
    }
  }

  filterChoiceGroup(title, name, options, selected) {
    const field = node("fieldset", undefined, "filter-field filter-choice-field");
    field.append(node("legend", title));
    const choices = node("div", undefined, "filter-choices");
    if (!options.length) choices.append(node("span", "No values available", "filter-empty"));
    options.forEach(option => {
      const label = node("label");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.name = name;
      input.value = option;
      input.checked = selected.includes(option);
      const displayLabels = {
        het: "Heterozygous", hom_alt: "Homozygous alternate", unknown: "Unknown",
        compound: "Possible compound het", recessive: "Recessive (hom-alt)",
        dominant: "Dominant (het)", x_linked: "X-linked", y_linked: "Y-linked",
        pathogenic: "Pathogenic", likely_pathogenic: "Likely pathogenic",
        uncertain_significance: "VUS", likely_benign: "Likely benign", benign: "Benign",
        __not_reported__: "Not reported",
      };
      label.append(input, document.createTextNode(displayLabels[option] || option.replaceAll("_", " ")));
      choices.append(label);
    });
    field.append(choices);
    return field;
  }

  renderFilterPanel(workspace) {
    const filters = workspace.filters || this.emptyFilters();
    const options = workspace.filterOptions || {
      consequences: [], clinical_significances: [], population_frequencies: ["MAX_AF"],
      filter_statuses: [], zygosities: [],
    };
    const form = node("form", undefined, "variant-filter-panel");
    form.addEventListener("submit", event => {
      event.preventDefault();
      this.applyFilters(workspace, form);
    });
    const heading = node("div", undefined, "filter-panel-heading");
    heading.append(
      node("div", undefined, "filter-panel-title"),
      node("span", "Filters are applied to the complete indexed sample, before pagination.", "filter-help"),
    );
    heading.firstChild.append(node("strong", "Variant filters"), node("small", "Combine criteria with AND"));
    form.append(heading);

    const interpretation = node("section", undefined, "filter-section");
    const interpretationHeading = node("div", undefined, "filter-section-heading");
    interpretationHeading.append(
      node("h5", "Variant interpretation"),
      node("p", "Prioritize variants by gene context, population frequency and predicted consequence."),
    );
    interpretation.append(interpretationHeading);
    const interpretationGrid = node("div", undefined, "filter-section-grid interpretation-grid");
    const genes = node("label", undefined, "filter-field filter-genes");
    const geneLabel = node("span", undefined, "filter-label-row");
    geneLabel.append(node("strong", workspace.gene ? `Gene locked to ${workspace.gene}` : "Genes"));
    const panelAppButton = node("button", "Browse gene panels", "panelapp-open");
    panelAppButton.type = "button";
    panelAppButton.disabled = Boolean(workspace.gene);
    geneLabel.append(panelAppButton);
    genes.append(geneLabel);
    const textarea = document.createElement("textarea");
    textarea.name = "genes";
    textarea.rows = 4;
    textarea.placeholder = "BRCA1, BRCA2, TP53\nOne symbol per line or comma-separated";
    textarea.value = workspace.gene
      ? workspace.gene : (workspace.panelAppDraftGenes ?? filters.genes).join("\n");
    textarea.disabled = Boolean(workspace.gene);
    const panelAppSources = node("div", undefined, "panelapp-sources");
    this.renderPanelAppSources(
      panelAppSources, workspace.panelAppDraftSources ?? workspace.panelAppSources ?? [],
      source => this.removePanelSource(workspace, textarea, panelAppSources, source),
    );
    genes.append(textarea, panelAppSources);
    panelAppButton.addEventListener("click", () => this.openPanelAppDialog(workspace, textarea, panelAppSources));
    const frequency = node("div", undefined, "filter-field");
    frequency.append(node("span", "Population frequency"));
    const population = document.createElement("select");
    population.name = "populationFrequency";
    const populationLabels = {
      MAX_AF: "Maximum across populations", AF: "Overall AF", AFR_AF: "African/African American",
      AMR_AF: "Admixed American", EAS_AF: "East Asian", EUR_AF: "European",
      NFE_AF: "Non-Finnish European", FIN_AF: "Finnish", SAS_AF: "South Asian",
      ASJ_AF: "Ashkenazi Jewish", AMI_AF: "Amish", MID_AF: "Middle Eastern", OTH_AF: "Other",
    };
    const populationOptions = options.population_frequencies?.length ? options.population_frequencies : ["MAX_AF"];
    populationOptions.forEach(field => {
      const option = document.createElement("option");
      option.value = field;
      option.textContent = populationLabels[field] || field.replaceAll("_", " ");
      option.selected = filters.populationFrequency === field;
      population.append(option);
    });
    const af = document.createElement("input");
    af.name = "maxAf"; af.type = "number"; af.min = "0"; af.max = "1"; af.step = "any";
    af.placeholder = "Maximum MAF, e.g. 0.01"; af.value = filters.maxAf;
    const missingLabel = node("label", undefined, "inline-check");
    const missing = document.createElement("input");
    missing.type = "checkbox"; missing.name = "includeMissingAf"; missing.checked = filters.includeMissingAf;
    missingLabel.append(missing, document.createTextNode("Keep variants with AF not reported"));
    frequency.append(population, af, missingLabel);
    interpretationGrid.append(frequency);

    interpretationGrid.append(this.filterChoiceGroup(
      "Consequence", "consequence", options.consequences, filters.consequences,
    ));
    interpretationGrid.append(this.filterChoiceGroup(
      "Clinical", "clinicalSignificance", options.clinical_significances, filters.clinicalSignificances,
    ));
    interpretationGrid.append(this.filterChoiceGroup(
      "Inheritance candidate", "inheritanceCandidate",
      ["compound", "recessive", "dominant", "x_linked", "y_linked"], filters.inheritanceCandidates,
    ));
    interpretation.append(interpretationGrid);
    form.append(interpretation);

    const sampleEvidence = node("section", undefined, "filter-section");
    const evidenceHeading = node("div", undefined, "filter-section-heading");
    evidenceHeading.append(
      node("h5", "Sample evidence"),
      node("p", "Filter using genotype and call-level evidence observed in this sample."),
    );
    sampleEvidence.append(evidenceHeading);
    const evidenceGrid = node("div", undefined, "filter-section-grid evidence-grid");
    evidenceGrid.append(this.filterChoiceGroup(
      "Zygosity", "zygosity", options.zygosities, filters.zygosities,
    ));

    const siteFilter = node("fieldset", undefined, "filter-field filter-site-status");
    siteFilter.append(node("legend", "VCF FILTER"));
    const mode = document.createElement("select");
    mode.name = "filterMode";
    [["all", "PASS and filtered"], ["pass", "PASS only"], ["selected", "Selected FILTER flags"]]
      .forEach(([optionValue, label]) => {
        const option = document.createElement("option");
        option.value = optionValue; option.textContent = label; option.selected = filters.filterMode === optionValue;
        mode.append(option);
      });
    siteFilter.append(mode, this.filterChoiceGroup(
      "Available flags", "filterStatus", options.filter_statuses, filters.filterStatuses,
    ).lastChild);
    evidenceGrid.append(siteFilter);

    const evidence = node("div", undefined, "filter-field filter-evidence");
    evidence.append(node("span", "Call thresholds"));
    [["minVaf", "Minimum VAF", filters.minVaf, "any"], ["minDepth", "Minimum DP", filters.minDepth, "1"],
      ["minQuality", "Minimum QUAL", filters.minQuality, "any"]].forEach(([name, placeholder, current, step]) => {
      const input = document.createElement("input");
      input.type = "number"; input.min = "0"; input.step = step; input.name = name;
      input.placeholder = placeholder; input.value = current;
      if (name === "minVaf") input.max = "1";
      evidence.append(input);
    });
    evidenceGrid.append(evidence);
    sampleEvidence.append(evidenceGrid);

    const genePanel = node("section", undefined, "filter-section gene-panel-section");
    const genePanelHeading = node("div", undefined, "filter-section-heading");
    genePanelHeading.append(
      node("h5", "Interesting gene panel"),
      node("p", "Paste gene symbols or import a curated panel."),
    );
    genePanel.append(genePanelHeading, genes);
    const lowerGrid = node("div", undefined, "filter-lower-grid");
    lowerGrid.append(sampleEvidence, genePanel);
    form.append(lowerGrid);
    if (workspace.filterOptionsLoading) form.append(node("p", "Loading available annotations and FILTER flags…", "filter-message"));
    if (workspace.filterOptionsError) form.append(node("p", workspace.filterOptionsError, "inline-error"));
    const actions = node("div", undefined, "filter-actions");
    const clear = node("button", "Clear filters");
    clear.type = "button";
    clear.addEventListener("click", () => this.resetFilters(workspace));
    const apply = node("button", "Apply filters", "primary");
    apply.type = "submit";
    actions.append(clear, apply);
    form.append(actions);
    return form;
  }

  renderPanelAppSources(host, sources, onRemove) {
    const badges = (sources || []).map(source => {
      const provider = source.source === "acmg" ? "ACMG SF" : "PanelApp";
      const badge = node("a", `${provider} · ${source.name} · ${source.evidence}`, "panelapp-source");
      badge.href = source.source_url || `https://panelapp.genomicsengland.co.uk/panels/${source.id}/`;
      badge.target = "_blank";
      badge.rel = "noopener noreferrer";
      badge.title = `${source.gene_count} genes imported from ${provider}`;
      const item = node("span", undefined, "panelapp-source-item");
      item.append(badge);
      if (onRemove) {
        const remove = node("button", "🗑", "panelapp-source-remove");
        remove.type = "button";
        remove.title = `Remove ${source.name}`;
        remove.setAttribute("aria-label", `Remove ${source.name}`);
        remove.addEventListener("click", () => onRemove(source));
        item.append(remove);
      }
      return item;
    });
    host.replaceChildren(...badges);
    host.hidden = !badges.length;
  }

  removePanelSource(workspace, textarea, sourceHost, source) {
    const sourceKey = item => `${item.source || "panelapp"}:${item.id}`;
    const current = workspace.panelAppDraftSources ?? workspace.panelAppSources ?? [];
    const remaining = current.filter(item => sourceKey(item) !== sourceKey(source));
    const retainedPanelGenes = new Set(remaining.flatMap(item => item.imported_genes || []));
    const removableGenes = new Set((source.imported_genes || []).filter(gene => !retainedPanelGenes.has(gene)));
    const genes = textarea.value.split(/[,;\s]+/).map(item => item.trim()).filter(Boolean)
      .filter(gene => !removableGenes.has(gene));
    textarea.value = genes.join("\n");
    workspace.panelAppDraftGenes = genes;
    workspace.panelAppDraftSources = remaining;
    this.renderPanelAppSources(
      sourceHost, remaining,
      item => this.removePanelSource(workspace, textarea, sourceHost, item),
    );
  }

  openPanelAppDialog(workspace, textarea, sourceHost) {
    const layer = this.shadowRoot.querySelector("#dialog-layer");
    const backdrop = node("div", undefined, "dialog-backdrop");
    const dialog = node("section", undefined, "panelapp-dialog");
    const closeDialog = () => backdrop.remove();
    const heading = node("div", undefined, "dialog-heading");
    const headingText = node("div");
    headingText.append(
      node("h4", "Gene panel catalogue"),
      node("p", "Browse local PanelApp data and versioned ACMG Secondary Findings lists."),
    );
    const close = node("button", "×", "dialog-close");
    close.type = "button";
    close.setAttribute("aria-label", "Close gene panel catalogue");
    close.addEventListener("click", closeDialog);
    heading.append(headingText, close);
    const searchForm = node("div", undefined, "panelapp-search");
    const searchInput = document.createElement("input");
    searchInput.type = "search";
    searchInput.placeholder = "Filter by panel, ID, indication or disease group";
    searchInput.setAttribute("aria-label", "Filter gene panels");
    const sourceSelect = document.createElement("select");
    sourceSelect.setAttribute("aria-label", "Filter panels by source");
    [["all", "All sources"], ["panelapp", "PanelApp"], ["acmg", "ACMG SF"]].forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value; option.textContent = label; sourceSelect.append(option);
    });
    const syncButton = node("button", "Sync PanelApp");
    syncButton.type = "button";
    searchForm.append(searchInput, sourceSelect, syncButton);
    const status = node("p", "Loading the local catalogue…", "panelapp-status");
    const results = node("div", undefined, "panelapp-results");
    const preview = node("div", undefined, "panelapp-preview");
    dialog.append(heading, searchForm, status, results, preview);
    backdrop.append(dialog);
    layer.replaceChildren(backdrop);
    backdrop.addEventListener("click", event => {
      if (event.target === backdrop) closeDialog();
    });
    let catalogue = [];
    let catalogueMetadata = {};
    const renderCatalogue = () => {
      const query = searchInput.value.trim().toLocaleLowerCase();
      const source = sourceSelect.value;
      const panels = catalogue.filter(panel => {
        if (source !== "all" && panel.source !== source) return false;
        if (!query) return true;
        const searchable = [panel.id, panel.name, panel.disease_group, panel.disease_sub_group,
          ...(panel.relevant_disorders || [])].join(" ").toLocaleLowerCase();
        return searchable.includes(query);
      });
      status.classList.remove("error");
      const syncNote = catalogueMetadata.synced_at
        ? ` PanelApp cache: ${new Date(catalogueMetadata.synced_at).toLocaleString()}.`
        : " PanelApp cache not yet available; use Sync PanelApp when the service permits.";
      status.textContent = `${panels.length} of ${catalogue.length} panels shown.${syncNote}`;
      if (catalogueMetadata.warning) status.textContent += ` ${catalogueMetadata.warning}`;
      results.replaceChildren(...panels.map(panel => {
        const card = node("button", undefined, "panelapp-result");
        card.type = "button";
        const title = node("span", undefined, "panelapp-result-title");
        const badges = node("span", undefined, "panelapp-result-badges");
        badges.append(node("span", panel.source === "acmg" ? "ACMG SF" : "PanelApp", `panel-source ${panel.source}`));
        if (panel.current) badges.append(node("span", "Current", "panel-current"));
        const identity = panel.source === "acmg" ? `v${panel.version} · ${panel.version_created}` : `ID ${panel.id} · v${panel.version}`;
        title.append(node("strong", panel.name), node("span", identity));
        const summary = node("small", [panel.disease_group, `${panel.gene_count} genes`].filter(Boolean).join(" · "));
        card.append(title, badges, summary);
        card.addEventListener("click", () => this.loadPanelAppPreview(
          workspace, panel, textarea, sourceHost, preview, status, closeDialog,
        ));
        return card;
      }));
      if (!panels.length) results.append(node("p", "No panels match the current filters.", "panelapp-empty"));
    };
    const loadCatalogue = async () => {
      try {
        const payload = await this.request("/knowledge/gene-panels");
        catalogue = payload.panels || [];
        catalogueMetadata = payload;
        renderCatalogue();
      } catch (error) {
        status.textContent = error.message;
        status.classList.add("error");
      }
    };
    searchInput.addEventListener("input", renderCatalogue);
    sourceSelect.addEventListener("change", renderCatalogue);
    syncButton.addEventListener("click", async () => {
      syncButton.disabled = true;
      status.classList.remove("error");
      status.textContent = "Synchronizing the PanelApp catalogue…";
      try {
        await this.request("/knowledge/gene-panels/sync", {method: "POST"});
        await loadCatalogue();
      } catch (error) {
        status.textContent = `${error.message} The existing local catalogue remains available.`;
        status.classList.add("error");
      } finally {
        syncButton.disabled = false;
      }
    });
    loadCatalogue();
    window.requestAnimationFrame(() => searchInput.focus());
  }

  async loadPanelAppPreview(workspace, panel, textarea, sourceHost, preview, status, closeDialog) {
    status.classList.remove("error");
    status.textContent = `Loading ${panel.name}…`;
    preview.replaceChildren();
    try {
      const detail = await this.request(`/knowledge/gene-panels/${encodeURIComponent(panel.source)}/${encodeURIComponent(panel.id)}`);
      const isAcmg = panel.source === "acmg";
      status.textContent = isAcmg ? "Review the version before importing." : "Review the evidence level before importing.";
      const card = node("section", undefined, "panelapp-preview-card");
      const title = node("div", undefined, "panelapp-preview-heading");
      const identity = isAcmg
        ? `ACMG SF version ${detail.version} · ${detail.current ? "current" : "previous"}`
        : `PanelApp ID ${detail.id} · version ${detail.version}`;
      title.append(node("strong", detail.name), node("span", identity));
      const counts = node("div", undefined, "panelapp-confidence-counts");
      const countGroups = isAcmg ? [["all", "All genes"]] : [["green", "Green"], ["amber", "Amber"], ["red", "Red"]];
      countGroups.forEach(([key, label]) => {
        counts.append(node("span", `${label}: ${detail.gene_counts?.[key] || 0}`, key));
      });
      const controls = node("div", undefined, "panelapp-import-controls");
      let evidence;
      if (!isAcmg) {
        const evidenceLabel = node("label", "Evidence level");
        evidence = document.createElement("select");
        [["green", "Green only"], ["green_amber", "Green + Amber"]].forEach(([entryValue, label]) => {
          const option = document.createElement("option");
          option.value = entryValue; option.textContent = label; evidence.append(option);
        });
        evidenceLabel.append(evidence);
        controls.append(evidenceLabel);
      }
      const modeLabel = node("label", "Import mode");
      const mode = document.createElement("select");
      [["replace", "Replace current list"], ["merge", "Merge with current list"]].forEach(([entryValue, label]) => {
        const option = document.createElement("option");
        option.value = entryValue; option.textContent = label; mode.append(option);
      });
      modeLabel.append(mode);
      const importButton = node("button", "Import genes", "primary");
      importButton.type = "button";
      importButton.addEventListener("click", () => {
        const imported = isAcmg ? [...(detail.genes?.all || [])] : [...(detail.genes?.green || [])];
        if (!isAcmg && evidence.value === "green_amber") imported.push(...(detail.genes?.amber || []));
        const current = textarea.value.split(/[,;\s]+/).map(item => item.trim()).filter(Boolean);
        const next = mode.value === "merge" ? Array.from(new Set([...current, ...imported])) : Array.from(new Set(imported));
        if (next.length > 5000) {
          status.textContent = "The combined list exceeds the 5,000 gene limit.";
          status.classList.add("error");
          return;
        }
        textarea.value = next.join("\n");
        const sourceKey = item => `${item.source || "panelapp"}:${item.id}`;
        const currentSources = workspace.panelAppDraftSources ?? workspace.panelAppSources ?? [];
        const priorSource = currentSources.find(item => sourceKey(item) === `${panel.source}:${detail.id}`);
        const currentGenes = new Set(current);
        const introducedGenes = mode.value === "replace"
          ? imported
          : [...(priorSource?.imported_genes || []), ...imported.filter(gene => !currentGenes.has(gene))];
        const source = {
          source: panel.source, id: detail.id, name: detail.name, version: detail.version,
          evidence: isAcmg ? `ACMG SF v${detail.version}` : (evidence.value === "green_amber" ? "Green + Amber" : "Green"),
          mode: mode.value, gene_count: imported.length, fetched_at: detail.fetched_at,
          source_url: detail.source_url, imported_genes: [...new Set(introducedGenes)],
        };
        workspace.panelAppDraftGenes = next;
        const existing = mode.value === "replace" ? [] : currentSources;
        workspace.panelAppDraftSources = [...existing.filter(item =>
          `${item.source || "panelapp"}:${item.id}` !== `${source.source}:${source.id}`), source];
        this.renderPanelAppSources(
          sourceHost, workspace.panelAppDraftSources,
          item => this.removePanelSource(workspace, textarea, sourceHost, item),
        );
        closeDialog();
      });
      controls.append(modeLabel, importButton);
      const notes = node("p", undefined, "panelapp-note");
      notes.textContent = isAcmg
        ? `Built-in ${detail.current ? "current" : "historical"} ACMG Secondary Findings snapshot (PMID ${detail.publication_pmid}).`
        : (Number(String(detail.version).split(".")[0]) < 1
          ? "This is a pre-version 1 panel; evidence ratings may not be final."
          : "Only gene entities are imported. STRs and genomic regions are excluded.");
      card.append(title, counts, controls, notes);
      preview.append(card);
    } catch (error) {
      status.textContent = error.message;
      status.classList.add("error");
    }
  }

  applyFilters(workspace, form) {
    const values = new FormData(form);
    const genes = String(values.get("genes") || "").split(/[,;\s]+/).map(item => item.trim()).filter(Boolean);
    const filterMode = String(values.get("filterMode") || "all");
    const filterStatuses = values.getAll("filterStatus").map(String);
    if (filterMode === "selected" && !filterStatuses.length) {
      workspace.error = "Select at least one FILTER flag, or choose another VCF FILTER mode.";
      this.renderWorkspace();
      return;
    }
    workspace.filters = {
      genes: Array.from(new Set(genes)).slice(0, 5000), maxAf: String(values.get("maxAf") || ""),
      populationFrequency: String(values.get("populationFrequency") || "MAX_AF"),
      includeMissingAf: values.has("includeMissingAf"),
      consequences: values.getAll("consequence").map(String),
      clinicalSignificances: values.getAll("clinicalSignificance").map(String),
      inheritanceCandidates: values.getAll("inheritanceCandidate").map(String),
      filterMode, filterStatuses,
      zygosities: values.getAll("zygosity").map(String), minDepth: String(values.get("minDepth") || ""),
      minVaf: String(values.get("minVaf") || ""), minQuality: String(values.get("minQuality") || ""),
    };
    workspace.panelAppSources = genes.length
      ? [...(workspace.panelAppDraftSources ?? workspace.panelAppSources ?? [])] : [];
    workspace.panelAppDraftSources = null;
    workspace.panelAppDraftGenes = null;
    this.restartFilteredWorkspace(workspace);
  }

  resetFilters(workspace) {
    workspace.filters = this.emptyFilters();
    workspace.panelAppSources = [];
    workspace.panelAppDraftSources = null;
    workspace.panelAppDraftGenes = null;
    this.restartFilteredWorkspace(workspace);
  }

  restartFilteredWorkspace(workspace) {
    workspace.pageController?.abort();
    workspace.items = []; workspace.cursor = null; workspace.initialized = false;
    workspace.loading = false; workspace.error = ""; workspace.detail = null; workspace.scrollTop = 0;
    this.renderWorkspace();
    this.loadPage(workspace);
  }

  loadColumnOrder() {
    const fallback = VARIANT_COLUMNS.map(column => column.key);
    try {
      const saved = JSON.parse(localStorage.getItem(COLUMN_STORAGE_KEY) || "[]");
      if (Array.isArray(saved) && saved.length === fallback.length
          && saved[0] === "filter_alert" && saved.every(key => VARIANT_COLUMNS_BY_KEY.has(key))) {
        return saved;
      }
    } catch {
      // Storage can be unavailable in embedded hosts; the default remains usable.
    }
    return fallback;
  }

  loadColumnWidths() {
    const fallback = Object.fromEntries(VARIANT_COLUMNS.map(column => [column.key, column.width]));
    try {
      const saved = JSON.parse(localStorage.getItem(COLUMN_WIDTH_STORAGE_KEY) || "{}");
      if (saved && typeof saved === "object" && !Array.isArray(saved)) {
        VARIANT_COLUMNS.forEach(column => {
          const width = Number(saved[column.key]);
          if (Number.isFinite(width)) fallback[column.key] = Math.min(600, Math.max(48, width));
        });
      }
    } catch {
      // Storage can be unavailable in embedded hosts; the default remains usable.
    }
    return fallback;
  }

  columnTemplate() {
    return this.columnOrder.map(key => `${this.columnWidths[key]}px`).join(" ");
  }

  columnTableWidth() {
    return this.columnOrder.reduce((total, key) => total + this.columnWidths[key], 0);
  }

  applyColumnLayout() {
    const template = this.columnTemplate();
    const width = `${this.columnTableWidth()}px`;
    this.shadowRoot.querySelectorAll(".variant-grid").forEach(grid => {
      grid.style.gridTemplateColumns = template;
      grid.style.minWidth = width;
    });
    const body = this.shadowRoot.querySelector(".virtual-body");
    if (body) body.style.minWidth = width;
  }

  columnHeader(key) {
    const definition = VARIANT_COLUMNS_BY_KEY.get(key);
    const cell = node("span", undefined, "column-header");
    if (key === "filter_alert") {
      cell.classList.add("filter-column-header");
      cell.setAttribute("aria-label", "Filter alert");
      return cell;
    }
    const label = node("span", definition.label, "column-label");
    const dragHandle = node("span", "⋮⋮", "column-drag-handle");
    const resizeHandle = node("span", undefined, "column-resize-handle");
    cell.dataset.column = key;
    dragHandle.draggable = true;
    dragHandle.title = `Drag to move ${definition.label}`;
    dragHandle.setAttribute("aria-label", `Drag to move ${definition.label}`);
    resizeHandle.title = `Resize ${definition.label}`;
    resizeHandle.setAttribute("aria-label", `Resize ${definition.label}`);
    dragHandle.addEventListener("dragstart", event => {
      this.draggedColumn = key;
      cell.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", key);
    });
    dragHandle.addEventListener("dragend", () => {
      this.draggedColumn = null;
      cell.classList.remove("dragging");
      this.shadowRoot.querySelectorAll(".column-header").forEach(item => item.classList.remove("drop-target"));
    });
    cell.addEventListener("dragover", event => {
      if (!this.draggedColumn || this.draggedColumn === key) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      cell.classList.add("drop-target");
    });
    cell.addEventListener("dragleave", () => cell.classList.remove("drop-target"));
    cell.addEventListener("drop", event => {
      event.preventDefault();
      cell.classList.remove("drop-target");
      const source = this.draggedColumn || event.dataTransfer.getData("text/plain");
      if (!VARIANT_COLUMNS_BY_KEY.has(source) || source === key) return;
      const next = this.columnOrder.filter(item => item !== source);
      let targetIndex = next.indexOf(key);
      const bounds = cell.getBoundingClientRect();
      if (event.clientX > bounds.left + bounds.width / 2) targetIndex += 1;
      next.splice(targetIndex, 0, source);
      this.columnOrder = next;
      try { localStorage.setItem(COLUMN_STORAGE_KEY, JSON.stringify(next)); } catch {}
      this.renderWorkspace();
    });
    resizeHandle.addEventListener("pointerdown", event => {
      event.preventDefault();
      event.stopPropagation();
      const startX = event.clientX;
      const startWidth = this.columnWidths[key];
      const resize = moveEvent => {
        this.columnWidths[key] = Math.min(600, Math.max(48, startWidth + moveEvent.clientX - startX));
        this.applyColumnLayout();
      };
      const stopResize = () => {
        window.removeEventListener("pointermove", resize);
        window.removeEventListener("pointerup", stopResize);
        try { localStorage.setItem(COLUMN_WIDTH_STORAGE_KEY, JSON.stringify(this.columnWidths)); } catch {}
      };
      window.addEventListener("pointermove", resize);
      window.addEventListener("pointerup", stopResize);
    });
    cell.append(label, dragHandle, resizeHandle);
    return cell;
  }

  compactHgvs(raw, marker) {
    if (raw === null || raw === undefined || raw === "") return raw;
    return String(raw).split(/([&,])/).map(part => {
      const markerIndex = part.indexOf(marker);
      const compact = markerIndex >= 0 ? part.slice(markerIndex) : part;
      return compact.replace(/%3D/gi, "=");
    }).join("");
  }

  variantCell(item, key) {
    if (key === "genotypes") {
      return Array.isArray(item[key]) ? item[key].join(", ") : item[key];
    }
    if (key === "filter_alert") return "";
    if (key === "hgvsc") return this.compactHgvs(item[key], "c.");
    if (key === "hgvsp") return this.compactHgvs(item[key], "p.");
    if (key === "allele_fraction" && item[key] !== null && item[key] !== undefined) {
      return Number(item[key]).toPrecision(3);
    }
    return item[key];
  }

  hasFilterAlert(item) {
    const filters = Array.isArray(item.filter_status) ? item.filter_status : [item.filter_status];
    return filters.some(filter => {
      const normalized = String(filter || "").trim().toUpperCase();
      return normalized && normalized !== "PASS" && normalized !== ".";
    });
  }

  variantCellNode(workspace, item, key) {
    const cell = node("span");
    if (key === "filter_alert") {
      cell.classList.add("filter-alert-cell");
      if (this.hasFilterAlert(item)) {
        const alert = node("span", "▲", "filter-alert");
        const filters = Array.isArray(item.filter_status) ? item.filter_status : [item.filter_status];
        alert.title = `Filtered: ${filters.filter(Boolean).join(", ")}`;
        alert.setAttribute("role", "img");
        alert.setAttribute("aria-label", "Filtered variant");
        cell.append(alert);
      }
      return cell;
    }
    if (key === "gene" && item.gene) {
      cell.classList.add("gene-cell");
      cell.title = `Right-click to open all ${item.gene} variants for this sample`;
      cell.addEventListener("contextmenu", event => {
        event.preventDefault();
        event.stopPropagation();
        this.openGeneWorkspace(workspace, item.gene);
      });
    }
    cell.append(document.createTextNode(value(this.variantCell(item, key))));
    return cell;
  }

  renderWorkspace() {
    const host = this.shadowRoot.querySelector("#workspace");
    const workspace = this.workspaces.get(this.activeWorkspace);
    if (!workspace) {
      host.className = "workspace-empty";
      host.textContent = "Select an indexed run and open a sample.";
      return;
    }
    host.className = `workspace-grid${workspace.detail ? "" : " detail-closed"}`;
    const tablePanel = node("section", undefined, "table-panel");
    const heading = node("div", undefined, "sample-heading");
    const headingActions = node("div", undefined, "sample-heading-actions");
    const filterButton = node("button", undefined, `filter-toggle${this.activeFilterCount(workspace) ? " active" : ""}`);
    filterButton.type = "button";
    filterButton.setAttribute("aria-label", "Open variant filters");
    filterButton.setAttribute("aria-expanded", String(Boolean(workspace.filtersOpen)));
    filterButton.title = "Filter variants";
    filterButton.innerHTML = '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M3 5h18l-7 8v5l-4 2v-7z"/></svg>';
    const activeFilters = this.activeFilterCount(workspace);
    if (activeFilters) filterButton.append(node("span", String(activeFilters), "filter-count"));
    filterButton.addEventListener("click", () => {
      workspace.filtersOpen = !workspace.filtersOpen;
      this.renderWorkspace();
      if (workspace.filtersOpen) this.loadFilterOptions(workspace);
    });
    headingActions.append(
      node("span", workspace.gene
        ? `${workspace.items.length} gene variants loaded`
        : `${workspace.items.length} loaded${activeFilters ? " · filtered" : ` / ${workspace.sample.variant_count}`}`, "loaded-count"),
      filterButton,
    );
    heading.append(
      node("div", undefined, "sample-title"),
      headingActions,
    );
    heading.firstChild.append(
      node("h4", workspace.gene || workspace.sample.display_name),
      node("p", workspace.gene
        ? `${workspace.sample.display_name} · all variants annotated in ${workspace.gene}`
        : `${workspace.sample.role || "sample"} · ${workspace.sample.specimen_type || "specimen not specified"}`),
    );
    tablePanel.append(heading);
    if (workspace.filtersOpen) tablePanel.append(this.renderFilterPanel(workspace));
    if (workspace.error) tablePanel.append(node("p", workspace.error, "inline-error"));
    const viewport = node("div", undefined, "variant-viewport");
    const header = node("div", undefined, "variant-grid grid-header");
    const gridTemplate = this.columnTemplate();
    const tableWidth = this.columnTableWidth();
    header.style.gridTemplateColumns = gridTemplate;
    header.style.minWidth = `${tableWidth}px`;
    this.columnOrder.forEach(key => header.append(this.columnHeader(key)));
    const body = node("div", undefined, "virtual-body");
    body.style.minWidth = `${tableWidth}px`;
    body.style.height = `${workspace.items.length * ROW_HEIGHT}px`;
    const layer = node("div", undefined, "row-layer");
    body.append(layer);
    viewport.append(header, body);
    const renderVisible = () => {
      const offset = Math.max(0, viewport.scrollTop - header.offsetHeight);
      const start = Math.max(0, Math.floor(offset / ROW_HEIGHT) - OVERSCAN);
      const count = Math.ceil(viewport.clientHeight / ROW_HEIGHT) + OVERSCAN * 2;
      const end = Math.min(workspace.items.length, start + count);
      layer.style.transform = `translateY(${start * ROW_HEIGHT}px)`;
      layer.replaceChildren(...workspace.items.slice(start, end).map(item => this.variantRow(workspace, item)));
      if (viewport.scrollTop + viewport.clientHeight >= viewport.scrollHeight - 240 && workspace.cursor && !workspace.loading) {
        this.loadPage(workspace);
      }
    };
    viewport.addEventListener("scroll", renderVisible, {passive: true});
    viewport.addEventListener("scroll", () => {
      workspace.scrollTop = viewport.scrollTop;
      workspace.scrollLeft = viewport.scrollLeft;
    }, {passive: true});
    tablePanel.append(viewport);
    const footer = node("div", undefined, "table-footer");
    if (workspace.loading) footer.append(node("span", "Loading variants…", "loading"));
    else if (workspace.cursor) {
      const more = node("button", "Load next page");
      more.addEventListener("click", () => this.loadPage(workspace));
      footer.append(more);
    } else if (workspace.initialized) footer.append(node("span", "All variants loaded", "complete-text"));
    tablePanel.append(footer);
    if (workspace.detail) host.replaceChildren(tablePanel, this.renderDetail(workspace));
    else host.replaceChildren(tablePanel);
    window.requestAnimationFrame(() => {
      viewport.scrollTop = workspace.scrollTop;
      viewport.scrollLeft = workspace.scrollLeft;
      renderVisible();
    });
  }

  variantRow(workspace, item) {
    const row = node("button", undefined, `variant-grid variant-row${workspace.detail?.variant_id === item.variant_id ? " selected" : ""}`);
    row.type = "button";
    row.style.gridTemplateColumns = this.columnTemplate();
    row.style.minWidth = `${this.columnTableWidth()}px`;
    this.columnOrder.forEach(key => row.append(this.variantCellNode(workspace, item, key)));
    row.addEventListener("click", () => this.loadDetail(workspace, item.variant_id));
    return row;
  }

  async loadDetail(workspace, variantId) {
    workspace.detailController?.abort();
    workspace.carrierController?.abort();
    workspace.genePhenotypeController?.abort();
    window.clearTimeout(workspace.genePhenotypeTimer);
    workspace.detailController = new AbortController();
    workspace.detail = {variant_id: variantId, loading: true};
    this.renderWorkspace();
    let loadCarriers = false;
    try {
      const detail = await this.request(
        `/runs/${encodeURIComponent(workspace.runId)}/samples/${workspace.sample.sample_id}/variants/${variantId}`,
        {signal: workspace.detailController.signal},
      );
      workspace.detail = {
        ...detail, variant_id: variantId, carriers: null, carriersLoading: true,
        genePhenotypes: [], genePhenotypesLoading: true,
      };
      loadCarriers = true;
    } catch (error) {
      if (error.name !== "AbortError") workspace.detail = {variant_id: variantId, error: error.message};
    }
    if (workspace.key === this.activeWorkspace) this.renderWorkspace();
    if (loadCarriers) {
      this.loadCarriers(workspace, variantId);
      this.loadGenePhenotypes(workspace, variantId);
    }
  }

  async loadCarriers(workspace, variantId) {
    workspace.carrierController = new AbortController();
    try {
      const carriers = await this.request(
        `/runs/${encodeURIComponent(workspace.runId)}/samples/${workspace.sample.sample_id}/variants/${variantId}/carriers`,
        {signal: workspace.carrierController.signal},
      );
      if (workspace.detail?.variant_id !== variantId) return;
      workspace.detail.carriers = carriers;
      workspace.detail.carriersLoading = false;
    } catch (error) {
      if (error.name === "AbortError" || workspace.detail?.variant_id !== variantId) return;
      workspace.detail.carriersError = error.message;
      workspace.detail.carriersLoading = false;
    }
    if (workspace.key === this.activeWorkspace) this.renderWorkspace();
  }

  async loadGenePhenotypes(workspace, variantId, attempt = 0) {
    if (attempt === 0) {
      workspace.genePhenotypeController?.abort();
      workspace.genePhenotypeController = new AbortController();
    }
    if (workspace.detail?.variant_id !== variantId) return;
    const genes = this.genePhenotypeGenes(workspace.detail.annotations || []);
    if (!genes.length) {
      workspace.detail.genePhenotypes = [];
      workspace.detail.genePhenotypesLoading = false;
      if (workspace.key === this.activeWorkspace) this.renderWorkspace();
      return;
    }
    try {
      const results = await Promise.all(genes.map(async gene => {
        const query = gene.hgnc ? `?hgnc_id=${encodeURIComponent(gene.hgnc)}` : "";
        try {
          return await this.request(
            `/knowledge/gene-phenotypes/${encodeURIComponent(gene.symbol)}${query}`,
            {signal: workspace.genePhenotypeController.signal},
          );
        } catch (error) {
          if (error.name === "AbortError") throw error;
          return {gene: gene.symbol, associations: [], error: error.message};
        }
      }));
      if (workspace.detail?.variant_id !== variantId) return;
      const waitingForCache = results.some(result => (
        result.cache?.status !== "ready" || result.cache?.stale || result.cache?.refreshing
      ));
      const waitingForConstraint = results.some(result => result.gene_constraint?.refreshing);
      workspace.detail.genePhenotypes = results;
      workspace.detail.genePhenotypesLoading = waitingForCache;
      if (workspace.key === this.activeWorkspace) this.renderWorkspace();
      if ((waitingForCache || waitingForConstraint) && attempt < 12) {
        workspace.genePhenotypeTimer = window.setTimeout(
          () => this.loadGenePhenotypes(workspace, variantId, attempt + 1),
          1500,
        );
      }
    } catch (error) {
      if (error.name === "AbortError" || workspace.detail?.variant_id !== variantId) return;
      workspace.detail.genePhenotypesError = error.message;
      workspace.detail.genePhenotypesLoading = false;
      if (workspace.key === this.activeWorkspace) this.renderWorkspace();
    }
  }

  renderDetail(workspace) {
    const panel = node("aside", undefined, "detail-panel");
    const heading = node("div", undefined, "detail-heading");
    const close = node("button", "×", "detail-close");
    close.type = "button";
    close.title = "Close variant detail";
    close.setAttribute("aria-label", "Close variant detail");
    close.addEventListener("click", () => {
      workspace.detailController?.abort();
      workspace.carrierController?.abort();
      workspace.genePhenotypeController?.abort();
      window.clearTimeout(workspace.genePhenotypeTimer);
      workspace.detailController = null;
      workspace.carrierController = null;
      workspace.genePhenotypeController = null;
      workspace.detail = null;
      this.renderWorkspace();
    });
    heading.append(node("h4", "Variant detail"), close);
    panel.append(heading);
    if (workspace.detail.loading) {
      panel.append(node("p", "Loading…", "loading"));
      return panel;
    }
    if (workspace.detail.error) {
      panel.append(node("p", workspace.detail.error, "inline-error"));
      return panel;
    }
    const detail = workspace.detail;
    const calls = detail.calls || [];
    const annotations = detail.annotations || [];
    const identity = node("div", undefined, "detail-identity");
    identity.append(node(
      "h4", `${detail.chromosome}:${detail.position} ${detail.reference}>${detail.alternate}`,
      "detail-locus",
    ));
    const annotationLabel = this.variantDetailAnnotationLabel(annotations);
    if (annotationLabel) identity.append(node("span", annotationLabel, "detail-annotation"));
    panel.append(identity);
    const sampleEvidence = this.sampleEvidenceContent(calls, detail);
    const databaseIds = detail.database_ids || {};
    const clinvarSearchUrl = this.clinvarSearchUrl(databaseIds.dbsnp);

    const variantContent = node("div", undefined, "detail-content");
    const variantSummary = node("div", undefined, "detail-cards variant-summary-grid");
    variantSummary.append(
      this.detailCard([
        ["Reference build", detail.reference_build], ["Chromosome", detail.chromosome],
        ["Position", detail.position], ["REF", detail.reference], ["ALT", detail.alternate],
        ["Type", detail.variant_type],
      ]),
      this.detailCard([
        ["dbSNP", this.databaseIdentifierLinks("dbsnp", databaseIds.dbsnp)],
        [
          clinvarSearchUrl
            ? this.externalDatabaseLabel("ClinVar", clinvarSearchUrl, `Search ClinVar by ${databaseIds.dbsnp[0]}`)
            : "ClinVar",
          this.databaseIdentifierLinks("clinvar", databaseIds.clinvar),
        ],
        ["ClinGen Allele Registry", this.databaseIdentifierLinks("clingen", databaseIds.clingen)],
      ]),
    );
    variantContent.append(
      node("h5", "Variant"),
      variantSummary,
      node("h5", "Sample evidence"),
      sampleEvidence,
    );
    panel.append(this.detailDisclosure("Variant details", variantContent, {
      open: true, status: `${calls.length} call${calls.length === 1 ? "" : "s"}`,
    }));

    const clinvarEvidence = detail.clinvar_evidence || {};
    panel.append(this.detailDisclosure(
      "ClinVar evidence",
      this.clinvarEvidenceContent(clinvarEvidence, databaseIds, clinvarSearchUrl),
      {
        open: Boolean(clinvarEvidence.has_conflict),
        status: this.clinvarEvidenceStatus(clinvarEvidence),
      },
    ));

    const genePhenotypeGenes = this.genePhenotypeGenes(annotations);
    const associationCount = (detail.genePhenotypes || [])
      .reduce((total, result) => total + (result.association_count || 0), 0);
    panel.append(this.detailDisclosure(
      "Gene–phenotype",
      this.genePhenotypeContent(
        genePhenotypeGenes,
        detail.genePhenotypes || [],
        detail.genePhenotypesLoading,
        detail.genePhenotypesError,
      ),
      {
        status: detail.genePhenotypesLoading
          ? "Loading associations…"
          : (genePhenotypeGenes.length
            ? `${genePhenotypeGenes.length} gene${genePhenotypeGenes.length === 1 ? "" : "s"} · ${associationCount} associations`
            : "No gene annotation"),
      },
    ));

    const sampleMetadata = workspace.sample.metadata || {};
    const analysisType = String(sampleMetadata.analysis_type || "").trim().toLowerCase();
    const onlyCase = !analysisType || ["only case", "only cases", "only_case"].includes(analysisType);
    const familyContent = node("div", undefined, "detail-content");
    familyContent.append(
      this.detailCard([
        ["Analysis", sampleMetadata.analysis_type], ["Family / group", sampleMetadata.analysis_id],
        ["Role", sampleMetadata.relationship || workspace.sample.role],
        ["Individual", sampleMetadata.individual_id], ["Sex", sampleMetadata.sex],
        ["Affected", sampleMetadata.affected], ["Father", sampleMetadata.father],
        ["Mother", sampleMetadata.mother],
      ]),
      node("p", "Pedigree and segregation data will be added in this section.", "detail-note"),
    );
    panel.append(this.detailDisclosure("Family", familyContent, {
      disabled: onlyCase,
      status: onlyCase ? "Not available for only-case analysis" : "Pedigree planned",
    }));

    panel.append(this.detailDisclosure(
      "Variant carriers",
      this.carrierContent(workspace, detail),
      {status: this.carrierStatus(workspace, detail)},
    ));

    const populationGroups = this.populationFrequencyGroups(annotations);
    const populationFieldCount = populationGroups.reduce((total, group) => total + group.fields.length, 0);
    panel.append(this.detailDisclosure(
      "Population frequencies",
      this.populationFrequencyContent(populationGroups, detail),
      {status: populationFieldCount ? `${populationFieldCount} fields` : "No data"},
    ));

    const predictionFacts = this.damagePredictionFields(annotations);
    panel.append(this.detailDisclosure(
      "Damage predictions",
      this.detailCards(predictionFacts.length ? [predictionFacts] : [], fields => fields),
      {status: predictionFacts.length ? `${predictionFacts.length} fields` : "No data"},
    ));

    panel.append(this.detailDisclosure(
      "Transcripts",
      this.transcriptCards(annotations),
      {status: `${annotations.length} transcript${annotations.length === 1 ? "" : "s"}`},
    ));
    return panel;
  }

  carrierStatus(workspace, detail) {
    if (detail.carriersLoading) return "Loading…";
    if (detail.carriersError) return "Unavailable";
    const sameRun = (detail.carriers?.same_run || [])
      .filter(carrier => carrier.sample_id !== workspace.sample.sample_id);
    const historical = detail.carriers?.historical || [];
    const sameRunHomozygous = sameRun.filter(carrier => this.carrierIsHomozygous(carrier)).length;
    const historicalHomozygous = historical.filter(carrier => this.carrierIsHomozygous(carrier)).length;
    return `${sameRun.length} current run (${sameRunHomozygous} homozygous) · `
      + `${historical.length} historical (${historicalHomozygous} homozygous)`;
  }

  carrierIsHomozygous(carrier) {
    return (carrier.genotypes || []).some(genotype => {
      const alleles = String(genotype).trim().split(/[\/|]/);
      return alleles.length > 1 && alleles[0] !== "0" && alleles[0] !== "."
        && alleles.every(allele => allele === alleles[0]);
    });
  }

  carrierContent(workspace, detail) {
    const content = node("div", undefined, "detail-content carrier-groups");
    if (detail.carriersLoading) {
      content.append(node("p", "Searching indexed runs…", "loading"));
      return content;
    }
    if (detail.carriersError) {
      content.append(node("p", detail.carriersError, "inline-error"));
      return content;
    }
    const sameRun = (detail.carriers?.same_run || [])
      .filter(carrier => carrier.sample_id !== workspace.sample.sample_id);
    const historical = detail.carriers?.historical || [];
    content.append(this.carrierGroup(workspace, "Current run", sameRun, false));
    content.append(this.carrierGroup(workspace, "Historical indexed runs", historical, true));
    return content;
  }

  carrierGroup(workspace, title, carriers, historical) {
    const group = node("section", undefined, "carrier-group");
    group.append(node("h5", title));
    if (!carriers.length) {
      group.append(node("p", "No other carriers found.", "empty"));
      return group;
    }
    const homozygous = carriers.filter(carrier => this.carrierIsHomozygous(carrier));
    const heterozygous = carriers.filter(carrier => !this.carrierIsHomozygous(carrier));
    group.append(
      this.carrierZygosityGroup(workspace, "Homozygous", homozygous, historical),
      this.carrierZygosityGroup(workspace, "Heterozygous", heterozygous, historical),
    );
    return group;
  }

  carrierZygosityGroup(workspace, title, carriers, historical) {
    const group = node("section", undefined, "carrier-zygosity-group");
    group.append(node("h6", `${title} (${carriers.length})`));
    if (!carriers.length) {
      group.append(node("p", "None", "carrier-empty"));
      return group;
    }
    carriers.forEach(carrier => {
      const button = node("button", undefined, "carrier-sample");
      const label = historical && carrier.run_id
        ? `${carrier.display_name} · ${carrier.run_id}` : carrier.display_name;
      const facts = [
        (carrier.genotypes || []).join(", "),
        carrier.depth !== null && carrier.depth !== undefined ? `DP ${carrier.depth}` : "",
        carrier.allele_fraction !== null && carrier.allele_fraction !== undefined
          ? `VAF ${Number(carrier.allele_fraction).toPrecision(3)}` : "",
      ].filter(Boolean).join(" · ");
      button.append(node("strong", label), node("small", facts || "Carrier"));
      button.title = `Open ${carrier.display_name}`;
      button.addEventListener("click", () => this.openCarrierSample(workspace, carrier, historical));
      group.append(button);
    });
    return group;
  }

  async openCarrierSample(workspace, carrier, historical) {
    if (historical) {
      await this.selectRun(carrier.history_id, carrier.sample_id);
      return;
    }
    const sample = this.samples.find(candidate => candidate.sample_id === carrier.sample_id);
    if (sample) await this.openSample(sample);
  }

  detailDisclosure(title, content, options = {}) {
    const details = node("details", undefined, `detail-disclosure${options.disabled ? " disabled" : ""}`);
    const summary = node("summary");
    summary.append(node("strong", title));
    if (options.status) summary.append(node("small", options.status));
    details.open = Boolean(options.open && !options.disabled);
    if (options.disabled) {
      summary.setAttribute("aria-disabled", "true");
      summary.addEventListener("click", event => event.preventDefault());
      summary.addEventListener("keydown", event => event.preventDefault());
    }
    details.append(summary, content);
    return details;
  }

  detailCard(fields) {
    const card = node("dl");
    fields.forEach(([label, fieldValue, presentation]) => {
      const term = node("dt");
      if (label instanceof Node) term.append(label);
      else term.textContent = label;
      const description = node("dd");
      if (fieldValue instanceof Node) description.append(fieldValue);
      else description.textContent = value(fieldValue);
      if (presentation?.title) description.title = presentation.title;
      if (presentation?.warning) {
        const warning = node("span", "▲", "metric-warning-icon");
        warning.setAttribute("role", "img");
        warning.setAttribute("aria-label", "Value above threshold; verify");
        warning.title = presentation.title || "Value above threshold; verify";
        description.append(warning);
      }
      card.append(term, description);
    });
    return card;
  }

  variantDetailAnnotationLabel(annotations = []) {
    const annotation = annotations.find(item => item.canonical)
      || annotations.find(item => item.gene || item.hgvsc || item.hgvsp);
    if (!annotation) return "";
    const gene = String(annotation.gene || "").trim();
    const hgvsc = String(this.compactHgvs(annotation.hgvsc, "c.") || "").trim();
    const hgvsp = String(this.compactHgvs(annotation.hgvsp, "p.") || "").trim();
    const coding = [gene, hgvsc].filter(Boolean).join(":");
    return [coding, hgvsp ? `(${hgvsp})` : ""].filter(Boolean).join(" ");
  }

  clinvarSearchUrl(dbsnpIdentifiers = []) {
    const rsid = dbsnpIdentifiers[0];
    return rsid
      ? `https://www.ncbi.nlm.nih.gov/clinvar/?term=${encodeURIComponent(rsid)}`
      : null;
  }

  clinvarEvidenceStatus(evidence = {}) {
    const review = (evidence.review_statuses || [])[0];
    const starCount = review ? Math.max(0, Math.min(4, Number(review.stars) || 0)) : 0;
    const stars = review ? `${"★".repeat(starCount)}${"☆".repeat(4 - starCount)}` : "";
    const classifications = evidence.classifications || [];
    if (evidence.has_conflict) return [stars, "Conflicting classifications"].filter(Boolean).join(" · ");
    if (classifications.length) {
      return [stars, classifications.join(" · ")].filter(Boolean).join(" · ");
    }
    if ((evidence.identifiers || []).length) return "Record linked";
    return "Not reported";
  }

  clinvarEvidenceContent(evidence = {}, databaseIds = {}, searchUrl = null) {
    const content = node("div", undefined, "detail-content clinvar-evidence-content");
    const identifiers = (evidence.identifiers || []).length
      ? evidence.identifiers : (databaseIds.clinvar || []);
    if (evidence.status === "not_reported" && !identifiers.length) {
      const message = node("p", "No ClinVar assertion was found in the indexed annotation.", "empty");
      content.append(message);
      if (searchUrl) {
        const link = node("a", "Search this variant in ClinVar ↗", "clinvar-source-link");
        link.href = searchUrl;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        content.append(link);
      }
      return content;
    }
    const heading = node("div", undefined, "clinvar-evidence-heading");
    heading.append(node("strong", "ClinVar classification"));
    const classificationLabels = this.clinvarClassificationLabels(evidence);
    if (classificationLabels.length) {
      const classifications = node("div", undefined, "clinvar-classifications");
      classificationLabels.forEach(classification => {
        classifications.append(node(
          "span", classification,
          `clinvar-classification ${this.clinvarClassificationClass(classification)}`,
        ));
      });
      heading.append(classifications);
    }
    content.append(heading);
    const identifierRow = node("div", undefined, "clinvar-identifiers");
    if (identifiers.length) {
      identifierRow.append(this.databaseIdentifierLinks("clinvar", identifiers));
    } else if (searchUrl) {
      const link = node("a", "Open ClinVar ↗", "clinvar-source-link");
      link.href = searchUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      identifierRow.append(link);
    }
    if (identifierRow.childNodes.length) content.append(identifierRow);
    if (evidence.has_conflict) {
      content.append(node(
        "p",
        "ClinVar contains conflicting classifications. Review the condition-specific submissions and their review status.",
        "clinvar-conflict-warning",
      ));
    }
    const fields = [];
    const review = this.clinvarReviewStatuses(evidence.review_statuses || []);
    if (review) fields.push(["Germline review", review]);
    if ((evidence.conditions || []).length) fields.push(["Conditions", evidence.conditions.join(" · ")]);
    if ((evidence.condition_ids || []).length) fields.push(["Condition identifiers", evidence.condition_ids.join(" · ")]);
    if ((evidence.conflicts || []).length) fields.push(["Conflicting submissions", evidence.conflicts.join(" · ")]);
    if ((evidence.origins || []).length) fields.push(["Allele origin", evidence.origins.join(" · ")]);
    if ((evidence.last_evaluated || []).length) fields.push(["Last evaluated", evidence.last_evaluated.join(" · ")]);
    if (evidence.submission_count != null || evidence.submitter_count != null) {
      const submissions = evidence.submission_count != null ? `${evidence.submission_count} submissions` : "";
      const submitters = evidence.submitter_count != null ? `${evidence.submitter_count} submitters` : "";
      fields.push(["Aggregate evidence", [submissions, submitters].filter(Boolean).join(" · ")]);
    }
    if (evidence.record_updated) fields.push(["Record updated", evidence.record_updated]);
    if (evidence.most_recent_submission) fields.push(["Most recent submission", evidence.most_recent_submission]);
    if ((evidence.rcv_accessions || []).length) {
      fields.push(["Condition records", this.databaseIdentifierLinks("clinvar", evidence.rcv_accessions)]);
    }
    if ((evidence.oncogenicity || []).length) fields.push(["Oncogenicity", evidence.oncogenicity.join(" · ")]);
    const oncReview = this.clinvarReviewStatuses(evidence.oncogenicity_review_statuses || []);
    if (oncReview) fields.push(["Oncogenicity review", oncReview]);
    if ((evidence.somatic_clinical_impact || []).length) {
      fields.push(["Somatic clinical impact", evidence.somatic_clinical_impact.join(" · ")]);
    }
    const somaticReview = this.clinvarReviewStatuses(evidence.somatic_review_statuses || []);
    if (somaticReview) fields.push(["Somatic review", somaticReview]);
    if (fields.length) content.append(this.detailCard(fields));
    if (evidence.retrieval_status === "unavailable") {
      content.append(node(
        "p", "Live ClinVar enrichment is temporarily unavailable; indexed VEP evidence is shown.",
        "clinvar-retrieval-note",
      ));
    }
    return content;
  }

  clinvarClassificationLabels(evidence = {}) {
    const breakdown = (evidence.classification_breakdown || [])
      .filter(item => item?.label && Number(item.count) > 0)
      .map(item => `${item.label} (${Number(item.count)})`);
    return breakdown.length ? breakdown : (evidence.classifications || []);
  }

  clinvarReviewStatuses(statuses = []) {
    if (!statuses.length) return null;
    const list = node("div", undefined, "clinvar-review-statuses");
    statuses.forEach(status => {
      const row = node("span", undefined, "clinvar-review-status");
      const stars = Math.max(0, Math.min(4, Number(status.stars) || 0));
      const rating = node("span", `${"★".repeat(stars)}${"☆".repeat(4 - stars)}`, "clinvar-review-stars");
      rating.setAttribute("aria-label", `${stars} of 4 ClinVar review stars`);
      row.append(rating, node("span", status.label));
      list.append(row);
    });
    return list;
  }

  clinvarClassificationClass(classification) {
    const value = String(classification || "").toLowerCase();
    if (value.includes("conflict")) return "conflicting";
    if (value.includes("pathogenic") && !value.includes("likely")) return "pathogenic";
    if (value.includes("likely pathogenic")) return "likely-pathogenic";
    if (value.includes("uncertain") || value.includes("vus")) return "uncertain";
    if (value.includes("likely benign")) return "likely-benign";
    if (value.includes("benign")) return "benign";
    return "other";
  }

  externalDatabaseLabel(label, url, title) {
    const link = node("a", undefined, "database-label-link");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.title = `${title} (new tab)`;
    link.setAttribute("aria-label", `${title} in a new tab`);
    link.append(node("span", label), node("span", "↗", "external-link-icon"));
    return link;
  }

  databaseIdentifierLinks(database, identifiers = []) {
    const container = node("span", undefined, "database-identifiers");
    if (!identifiers.length) {
      container.textContent = "—";
      return container;
    }
    identifiers.forEach(identifier => {
      const link = node("a", identifier, "database-identifier-link");
      if (database === "dbsnp") {
        link.href = `https://www.ncbi.nlm.nih.gov/snp/${encodeURIComponent(identifier)}`;
      } else if (database === "clinvar") {
        const directIdentifier = /^(?:VCV\d+(?:\.\d+)?|\d+)$/i.test(identifier);
        const rcvIdentifier = /^RCV\d+(?:\.\d+)?$/i.test(identifier);
        link.href = directIdentifier
          ? `https://www.ncbi.nlm.nih.gov/clinvar/variation/${encodeURIComponent(identifier)}/`
          : rcvIdentifier
            ? `https://www.ncbi.nlm.nih.gov/clinvar/${encodeURIComponent(identifier)}/`
            : `https://www.ncbi.nlm.nih.gov/clinvar/?term=${encodeURIComponent(identifier)}`;
      } else if (database === "clingen") {
        link.href = `https://reg.clinicalgenome.org/redmine/projects/registry/genboree_registry/by_caid?caid=${encodeURIComponent(identifier)}`;
      }
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.title = `Open ${identifier} in a new tab`;
      link.setAttribute("aria-label", `Open ${identifier} in a new tab`);
      link.append(node("span", "↗", "external-link-icon"));
      container.append(link);
    });
    return container;
  }

  genePhenotypeGenes(annotations) {
    const genes = new Map();
    annotations.forEach(annotation => {
      const symbol = String(annotation.gene || "").trim();
      if (!symbol || symbol === "-") return;
      const key = symbol.toUpperCase();
      if (!genes.has(key)) {
        genes.set(key, {symbol, hgnc: new Set(), ensembl: new Set(), entrez: new Set()});
      }
      const gene = genes.get(key);
      const fields = annotation.metadata?.fields || {};
      const hgncId = String(fields.HGNC_ID || fields.HGNC || "").trim();
      if (hgncId) gene.hgnc.add(`HGNC:${hgncId.replace(/^HGNC:/i, "")}`);
      Object.entries(fields).forEach(([fieldName, fieldValue]) => {
        if (!/^(Gene|Gene_ID|Ensembl_Gene_ID|EntrezGene)$/i.test(fieldName)) return;
        String(fieldValue || "").split(/[,&]/).forEach(identifier => {
          const normalized = identifier.trim();
          if (/^ENSG\d+(?:\.\d+)?$/i.test(normalized)) gene.ensembl.add(normalized.split(".")[0]);
          if (/^\d+$/.test(normalized)) gene.entrez.add(normalized);
        });
      });
    });
    return Array.from(genes.values(), gene => ({
      symbol: gene.symbol,
      hgnc: Array.from(gene.hgnc)[0] || "",
      ensembl: Array.from(gene.ensembl)[0] || "",
      entrez: Array.from(gene.entrez)[0] || "",
    })).sort((left, right) => left.symbol.localeCompare(right.symbol));
  }

  genePhenotypeResources(gene) {
    const symbol = encodeURIComponent(gene.symbol);
    const hgnc = encodeURIComponent(gene.hgnc);
    const resources = [
      {
        name: "ClinGen", description: "Curated gene–disease validity",
        url: `https://search.clinicalgenome.org/kb/gene-validity?page=1&search=${symbol}&size=25`,
        sourceMatchers: ["clingen", "clinical genome resource"],
      },
      {
        name: "GenCC", description: "Gene–disease validity submissions",
        url: gene.hgnc ? `https://thegencc.org/genes/${hgnc}/disease` : "https://thegencc.org/",
        aggregate: true,
      },
      {
        name: "OMIM", description: "Mendelian gene and phenotype catalogue",
        url: `https://www.omim.org/search?index=entry&search=${symbol}`,
        sourceMatchers: ["omim"],
      },
      {
        name: "Orphanet", description: "Rare disease associations",
        url: `https://www.orpha.net/en/disease/gene/${symbol}`,
        sourceMatchers: ["orphanet"],
      },
      {
        name: "Gene2Phenotype", description: "Expert-curated monogenic disease models",
        url: `https://www.ebi.ac.uk/gene2phenotype/search?query=${symbol}`,
        sourceMatchers: ["gene2phenotype", "gene2 phenotype", "g2p"],
      },
      {
        name: "PanelApp", description: "Diagnostic panels and phenotypes",
        url: `https://panelapp.genomicsengland.co.uk/panels/entities/${symbol}`,
        sourceMatchers: ["panelapp", "panel app", "genomics england"],
      },
      {
        name: "DECIPHER", description: "Clinical gene and phenotype evidence",
        url: `https://www.deciphergenomics.org/gene/${symbol}/overview/clinical-info`,
        sourceMatchers: ["decipher"],
      },
      {
        name: "Monarch", description: "Integrated genotype–phenotype knowledge",
        url: gene.hgnc ? `https://monarchinitiative.org/${hgnc}` : "",
      },
      {
        name: "Human Phenotype Ontology", description: "Gene-associated HPO phenotypes",
        url: gene.entrez ? `https://hpo.jax.org/browse/gene/${encodeURIComponent(gene.entrez)}` : "",
      },
      {
        name: "GeneReviews", description: "Clinical disease summaries",
        url: `https://www.ncbi.nlm.nih.gov/books/?term=${symbol}%20GeneReviews`,
      },
      {
        name: "Open Targets", description: "Target–disease associations",
        url: gene.ensembl
          ? `https://platform.opentargets.org/target/${encodeURIComponent(gene.ensembl)}/associations`
          : "",
      },
      {
        name: "Clinical Genomic Database", description: "Disease and clinical-actionability links",
        url: `https://research.nhgri.nih.gov/CGD/view/?g=${symbol}`,
        sourceMatchers: ["clinical genomic database", "cgd"],
      },
      {
        name: "MalaCards", description: "Aggregated human disease associations",
        url: `https://www.malacards.org/search/results?q=${symbol}`,
      },
    ];
    return resources.filter(resource => resource.url);
  }

  genePhenotypeSourceMatches(resource, sourceName) {
    const source = String(sourceName || "").trim().toLowerCase();
    return Boolean(source) && (resource.sourceMatchers || []).some(matcher => (
      source.includes(String(matcher).toLowerCase())
    ));
  }

  genePhenotypeAssertionUrl(assertion, gene) {
    const reportUrl = String(assertion.report_url || "").trim();
    if (/^https?:\/\//i.test(reportUrl)) return reportUrl;
    const resources = this.genePhenotypeResources(gene);
    const resource = resources.find(item => (
      !item.aggregate && this.genePhenotypeSourceMatches(item, assertion.source)
    ));
    return resource?.url || resources.find(item => item.aggregate)?.url || "https://thegencc.org/";
  }

  genePhenotypeSourcePriority(sourceName) {
    const source = String(sourceName || "").trim().toLowerCase();
    if (source.includes("clingen") || source.includes("clinical genome resource")) return 0;
    if (source.includes("omim")) return 1;
    if (source.includes("gene2phenotype") || source.includes("gene2 phenotype") || source === "g2p") return 2;
    if (source.includes("panelapp") || source.includes("panel app") || source.includes("genomics england")) return 3;
    if (source.includes("orphanet")) return 4;
    return 100;
  }

  genePhenotypeEvidenceAssertions(association) {
    const assertions = [...(association.assertions || [])];
    const omimId = (association.original_disease_ids || []).find(identifier => /^OMIM:\d+$/i.test(identifier));
    if (omimId && !assertions.some(assertion => /omim/i.test(assertion.source || ""))) {
      assertions.push({
        source: "OMIM",
        classification: "Evidence not imported",
        report_url: `https://www.omim.org/entry/${encodeURIComponent(omimId.split(":")[1])}`,
      });
    }
    return assertions.sort((left, right) => {
      const priority = this.genePhenotypeSourcePriority(left.source)
        - this.genePhenotypeSourcePriority(right.source);
      return priority || String(left.source || "").localeCompare(String(right.source || ""));
    });
  }

  genePhenotypeContent(genes, results = [], loading = false, error = "") {
    const content = node("div", undefined, "detail-content gene-phenotype-content");
    if (!genes.length) {
      content.append(node("p", "No gene annotation is available for this variant.", "empty"));
      return content;
    }
    genes.forEach(gene => {
      const section = node("section", undefined, "gene-phenotype-gene");
      const heading = node("div", undefined, "gene-phenotype-heading");
      heading.append(node("h5", gene.symbol));
      const identifiers = [gene.hgnc, gene.ensembl, gene.entrez && `NCBI Gene:${gene.entrez}`].filter(Boolean);
      if (identifiers.length) heading.append(node("small", identifiers.join(" · ")));
      const information = node("span", undefined, "gene-evidence-information");
      const informationButton = node("button", "i", "gene-evidence-information-button");
      informationButton.type = "button";
      informationButton.setAttribute("aria-label", "About external gene–disease evidence");
      const informationText = node(
        "span",
        "External evidence links are starting points for review; gene–disease validity and inheritance must be assessed in their original source.",
        "gene-evidence-information-text",
      );
      informationText.setAttribute("role", "tooltip");
      information.append(informationButton, informationText);
      heading.append(information);
      const result = results.find(item => String(item.gene).toUpperCase() === gene.symbol.toUpperCase());
      const resultError = result?.error || error;
      const resultReady = !resultError && result?.cache?.status === "ready";
      section.append(heading);
      if (resultError) section.append(node("p", resultError, "inline-error"));
      else if (!resultReady) {
        section.append(node(
          "p",
          loading ? "Preparing the local gene–phenotype knowledge cache…" : "Knowledge cache not available.",
          "loading",
        ));
      } else {
        section.append(this.genePhenotypeAssociations(
          result.associations || [], gene, result.gene_constraint, result.dosage_sensitivity,
        ));
      }
      if (result?.cache?.updated_at) {
        section.append(node("small", `Knowledge cache updated: ${result.cache.updated_at}`, "gene-cache-date"));
      }
      content.append(section);
    });
    return content;
  }

  geneDiseaseMechanism(mechanism = {}, constraint = {}, dosage = {}) {
    const details = node("details", undefined, "gene-disease-mechanisms");
    const summary = document.createElement("summary");
    const records = mechanism.records || [];
    const availableSources = [
      records.length ? "G2P" : "",
      constraint.status === "ready" ? "gnomAD" : "",
      dosage.status === "ready" ? "ClinGen" : "",
    ].filter(Boolean);
    summary.append(
      node("span", "Disease mechanism", "gene-knowledge-label"),
      node("small", availableSources.join(" · ") || (constraint.refreshing ? "Loading gnomAD…" : "No data")),
    );
    const content = node("div", undefined, "gene-mechanism-content");

    const g2p = node("section", undefined, "gene-mechanism-source");
    const g2pHeading = node("div", undefined, "gene-mechanism-source-heading");
    g2pHeading.append(node("strong", "Gene2Phenotype"), node("small", "Disease-specific mechanism"));
    const status = String(mechanism.status || "unknown");
    const value = status === "conflicting"
      ? "Conflicting G2P records"
      : status === "supported"
        ? String(mechanism.value || "Unknown")
        : status === "uncertain" ? "Low-confidence evidence only" : "Not available";
    g2pHeading.append(node("span", value, `gene-mechanism-value ${status}`));
    g2p.append(g2pHeading);
    if (records.length) {
      const recordList = node("div", undefined, "gene-mechanism-record-list");
      records.forEach(record => {
        const recordRow = node("div", undefined, "gene-mechanism-record");
        const link = node("a", `${record.mechanism || "Unknown"} · ${record.id || "G2P"} ↗`);
        link.href = record.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        const metadata = [
          record.confidence && `confidence: ${record.confidence}`,
          record.allelic_requirement && `allelic requirement: ${record.allelic_requirement}`,
          record.variant_consequence && `consequence: ${record.variant_consequence}`,
          record.category && `category: ${record.category}`,
          record.support && `support: ${record.support}`,
          record.publications && `publications: ${record.publications}`,
          record.last_reviewed && `reviewed: ${record.last_reviewed}`,
        ].filter(Boolean);
        recordRow.append(link);
        if (metadata.length) recordRow.append(node("small", metadata.join(" · ")));
        recordList.append(recordRow);
      });
      g2p.append(recordList);
    } else {
      g2p.append(node("p", "No matched disease-specific G2P record.", "empty"));
    }
    content.append(g2p, this.geneConstraintEvidence(constraint), this.geneDosageEvidence(dosage));
    details.append(summary, content);
    return details;
  }

  geneConstraintEvidence(constraint = {}) {
    const section = node("section", undefined, "gene-mechanism-source");
    const heading = node("div", undefined, "gene-mechanism-source-heading");
    heading.append(node("strong", "gnomAD constraint"), node("small", "Gene-level selection constraint"));
    if (constraint.source_url) {
      const link = node("a", `${constraint.source || "gnomAD"} ↗`, "gene-knowledge-source-link");
      link.href = constraint.source_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      heading.append(link);
    }
    section.append(heading);
    if (constraint.status !== "ready") {
      section.append(node(
        "p",
        constraint.refreshing ? "Retrieving gnomAD constraint data…" : "No gnomAD constraint data available.",
        constraint.refreshing ? "loading" : "empty",
      ));
      return section;
    }
    const observedExpected = (ratio, observed, expected) => {
      const format = rawValue => (
        rawValue === null || rawValue === undefined
          ? "—"
          : Number(rawValue).toLocaleString(undefined, {maximumFractionDigits: 3})
      );
      return `${format(ratio)} (${format(observed)}/${format(expected)})`;
    };
    const metrics = [
      ["LOEUF", constraint.loeuf,
        "Upper bound of the plausible pLoF observed/expected fraction. Lower values indicate stronger constraint. gnomAD v4.1 recommends <0.45 for pLoF-constrained genes."],
      ["pLI", constraint.pli,
        "Probability that a gene is loss-of-function intolerant. ≥0.9 indicates high intolerance; ≤0.1 indicates tolerance. gnomAD recommends preferring LOEUF."],
      ["pLoF o/e", observedExpected(
        constraint.lof_oe, constraint.lof_observed, constraint.lof_expected,
      ), "Observed/expected high-confidence pLoF variants; observed and expected counts are in parentheses. Values <1 indicate depletion. There is no standalone hard cutoff: use LOEUF (<0.45).", true],
      ["LoF Z-score", constraint.lof_z,
        "Standardized depletion of pLoF variants. Higher positive values indicate stronger constraint. gnomAD v4 has no recommended hard cutoff and Z-scores depend on sample size."],
      ["Missense o/e", observedExpected(
        constraint.missense_oe, constraint.missense_observed, constraint.missense_expected,
      ), "Observed/expected missense variants; observed and expected counts are in parentheses. Values <1 indicate depletion; there is no universal hard cutoff.", true],
      ["Missense Z-score", constraint.missense_z,
        "Standardized depletion of missense variants. Higher positive values indicate stronger constraint. >3.09 is a widely used historical threshold; gnomAD v4 Z-scores are sample-size sensitive."],
    ];
    const grid = node("dl", undefined, "gene-mechanism-metrics");
    metrics.forEach(([label, rawValue, help, formatted]) => {
      const value = formatted
        ? rawValue
        : rawValue === null || rawValue === undefined
          ? "—"
          : Number(rawValue).toLocaleString(undefined, {maximumFractionDigits: 3});
      grid.append(this.geneConstraintMetricLabel(label, help), node("dd", value));
    });
    section.append(
      node("p", "Constraint supports variant interpretation but is not a disease-mechanism assertion.", "gene-mechanism-note"),
      grid,
    );
    return section;
  }

  geneConstraintMetricLabel(label, help) {
    const term = node("dt");
    term.append(node("span", label));
    const information = node("span", undefined, "constraint-metric-information");
    const button = node("button", "i", "constraint-metric-information-button");
    button.type = "button";
    button.setAttribute("aria-label", `About ${label}`);
    const tooltip = node("span", help, "constraint-metric-information-text");
    tooltip.setAttribute("role", "tooltip");
    information.append(button, tooltip);
    term.append(information);
    return term;
  }

  geneDosageEvidence(dosage = {}) {
    const section = node("section", undefined, "gene-mechanism-source");
    const heading = node("div", undefined, "gene-mechanism-source-heading");
    heading.append(node("strong", "ClinGen dosage sensitivity"), node("small", "Gene-level dosage evidence"));
    if (dosage.source_url) {
      const link = node("a", "ClinGen ↗", "gene-knowledge-source-link");
      link.href = dosage.source_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      heading.append(link);
    }
    section.append(heading);
    if (dosage.status !== "ready") {
      section.append(node("p", "No ClinGen dosage sensitivity record available.", "empty"));
      return section;
    }
    const list = node("div", undefined, "gene-dosage-list");
    [
      ["Haploinsufficiency", dosage.haploinsufficiency || {}],
      ["Triplosensitivity", dosage.triplosensitivity || {}],
    ].forEach(([label, item]) => {
      const row = node("div", undefined, "gene-dosage-row");
      const title = node("div", undefined, "gene-dosage-title");
      title.append(node("strong", label), node("span", `Score ${item.score || "—"}`, "gene-dosage-score"));
      row.append(title, node("small", item.description || "No assessment description."));
      if (item.disease_id) row.append(this.geneDiseaseIdentifier(item.disease_id));
      if ((item.pmids || []).length) {
        const publications = node("div", undefined, "gene-dosage-publications");
        item.pmids.forEach(rawPmid => {
          const pmid = String(rawPmid).replace(/^PMID:/i, "");
          const link = node("a", `PMID:${pmid} ↗`);
          link.href = `https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(pmid)}/`;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          publications.append(link);
        });
        row.append(publications);
      }
      list.append(row);
    });
    section.append(list);
    if (dosage.last_evaluated) section.append(node("small", `Last evaluated: ${dosage.last_evaluated}`, "gene-cache-date"));
    return section;
  }

  geneDiseasePhenotypicFeatures(association) {
    const features = association.phenotypic_features || [];
    const details = node("details", undefined, "gene-phenotypic-features");
    const summary = document.createElement("summary");
    summary.append(
      node("span", "Phenotypic features", "gene-knowledge-label"),
      node("small", `${features.length} HPO term${features.length === 1 ? "" : "s"}`),
    );
    details.append(summary);
    if (!features.length) {
      details.append(node("p", "No disease-specific HPO annotations matched.", "empty"));
      return details;
    }
    const list = node("div", undefined, "gene-phenotypic-feature-list");
    features.forEach(feature => {
      const row = node("div", undefined, "gene-phenotypic-feature");
      const link = node("a", feature.name || feature.id);
      link.href = `https://hpo.jax.org/browse/term/${encodeURIComponent(feature.id)}`;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.title = `Open ${feature.id} in HPO`;
      const metadata = [feature.id];
      if ((feature.frequencies || []).length) metadata.push(`frequency ${feature.frequencies.join(" · ")}`);
      if ((feature.onsets || []).length) metadata.push(`onset ${feature.onsets.join(" · ")}`);
      row.append(link, node("small", metadata.join(" · ")));
      if (feature.negative) row.append(node("span", "Excluded", "gene-feature-negative"));
      list.append(row);
    });
    details.append(list);
    return details;
  }

  geneDiseaseIdentifier(identifier) {
    const value = String(identifier || "").trim();
    const mondo = value.match(/^MONDO:(\d+)$/i);
    const omim = value.match(/^(?:OMIM|MIM):(\d+)$/i);
    const orphanet = value.match(/^(?:ORPHA|ORPHANET):(\d+)$/i);
    let url = "";
    let source = "other";
    if (mondo) {
      url = `https://monarchinitiative.org/disease/MONDO:${mondo[1]}`;
      source = "mondo";
    } else if (omim) {
      url = `https://www.omim.org/entry/${omim[1]}`;
      source = "omim";
    } else if (orphanet) {
      url = `https://www.orpha.net/en/disease/detail/${orphanet[1]}`;
      source = "orphanet";
    }
    const element = node(url ? "a" : "span", undefined, `gene-disease-identifier ${source}`);
    element.append(node("span", value));
    if (url) {
      element.href = url;
      element.target = "_blank";
      element.rel = "noopener noreferrer";
      element.title = `Open ${value} in its source database`;
      element.setAttribute("aria-label", `Open ${value} in its source database (new tab)`);
      element.append(node("span", "↗", "external-link-icon"));
    }
    return element;
  }

  geneDiseaseIdentifiers(association) {
    const identifiers = Array.from(new Set([
      association.disease_id,
      ...(association.original_disease_ids || []),
    ].filter(Boolean)));
    const container = node("div", undefined, "gene-disease-identifiers");
    identifiers.forEach(identifier => container.append(this.geneDiseaseIdentifier(identifier)));
    (association.icd_codes || []).forEach(code => container.append(this.geneDiseaseCode(code)));
    return container;
  }

  geneDiseaseCode(code = {}) {
    const system = String(code.system || "ICD");
    const value = String(code.code || "");
    const sourceClass = system === "ICD-11" ? "icd11" : "icd10";
    const mappingClass = String(code.mapping_kind || "undetermined");
    const element = node(
      code.source_url ? "a" : "span", undefined,
      `gene-disease-identifier ${sourceClass} ${mappingClass}`,
    );
    element.append(node("span", `${system}: ${value}`));
    if (mappingClass !== "exact") {
      element.append(node("span", "≈", "gene-disease-mapping-indicator"));
    }
    const details = [
      code.mapping_relation,
      code.icd_relation,
      code.validation_status && `Status: ${code.validation_status}`,
      code.orpha_id && `Mapped from ${code.orpha_id}`,
      code.source && `Source: ${code.source}`,
    ].filter(Boolean);
    element.title = details.join(" · ");
    if (code.source_url) {
      element.href = code.source_url;
      element.target = "_blank";
      element.rel = "noopener noreferrer";
      element.setAttribute("aria-label", `Open ${system} code ${value} in its source database (new tab)`);
      element.append(node("span", "↗", "external-link-icon"));
    }
    return element;
  }

  geneDiseaseInheritance(values = []) {
    const row = node("div", undefined, "gene-disease-inheritance");
    row.append(node("span", "Inheritance", "gene-inheritance-label"));
    values.forEach(value => row.append(node("strong", value, "gene-inheritance-value")));
    return row;
  }

  genePhenotypeAssociations(associations, gene, constraint = {}, dosage = {}) {
    const container = node("div", undefined, "gene-phenotype-associations");
    if (!associations.length) {
      container.append(
        this.geneDiseaseMechanism({}, constraint, dosage),
        node("p", "No phenotype association was found in the local knowledge cache.", "empty"),
      );
      return container;
    }
    associations.forEach(association => {
      const card = node("article", undefined, "gene-phenotype-association");
      const heading = node("div", undefined, "gene-phenotype-association-heading");
      const headingTools = node("div", undefined, "gene-association-heading-tools");
      headingTools.append(
        node("span", association.strongest_classification || "Unclassified", "gene-evidence-badge"),
        this.geneAssociationEvidenceSummary(association, constraint, dosage),
      );
      heading.append(
        node("strong", association.disease || "Unnamed phenotype"),
        headingTools,
      );
      const identifiers = [association.disease_id, ...(association.original_disease_ids || [])].filter(Boolean);
      if (identifiers.length) card.append(heading, this.geneDiseaseIdentifiers(association));
      else card.append(heading);
      if ((association.inheritance || []).length) {
        card.append(this.geneDiseaseInheritance(association.inheritance));
      }
      card.append(
        this.geneDiseaseMechanism(association.molecular_mechanism, constraint, dosage),
        this.geneDiseasePhenotypicFeatures(association),
      );
      const assertions = this.genePhenotypeEvidenceAssertions(association);
      const sources = node("details", undefined, "gene-evidence-sources");
      const sourceSummary = document.createElement("summary");
      sourceSummary.append(
        node("span", "Supporting databases", "gene-knowledge-label"),
        node("small", `${assertions.length} source${assertions.length === 1 ? "" : "s"}`),
      );
      const sourceList = node("div", undefined, "gene-evidence-source-list");
      assertions.forEach(assertion => {
        const row = node("div", undefined, "gene-evidence-source-row");
        const source = node("a", undefined, "gene-evidence-source-link");
        source.href = this.genePhenotypeAssertionUrl(assertion, gene);
        source.target = "_blank";
        source.rel = "noopener noreferrer";
        source.title = `Open ${assertion.source || "source"} evidence (new tab)`;
        source.setAttribute("aria-label", `Open ${assertion.source || "source"} evidence in a new tab`);
        source.append(
          node("span", assertion.source || "Unspecified source"),
          node("span", "↗", "external-link-icon"),
        );
        row.append(
          source,
          node("span", assertion.classification || "Unclassified", "gene-evidence-badge"),
        );
        sourceList.append(row);
      });
      sources.append(sourceSummary, sourceList);
      card.append(sources);
      container.append(card);
    });
    return container;
  }

  geneAssociationEvidenceSummary(association = {}, constraint = {}, dosage = {}) {
    const information = node("span", undefined, "gene-association-summary");
    const button = node("button", "i", "gene-association-summary-button");
    button.type = "button";
    button.setAttribute("aria-label", `Evidence summary for ${association.disease || "this association"}`);
    const tooltip = node("span", undefined, "gene-association-summary-tooltip");
    tooltip.setAttribute("role", "tooltip");
    tooltip.append(node("strong", "Evidence summary"));
    const mechanism = association.molecular_mechanism || {};
    const mechanismValue = mechanism.status === "conflicting"
      ? "Conflicting G2P records"
      : mechanism.status === "supported"
        ? mechanism.value
        : mechanism.status === "uncertain" ? "Low-confidence evidence" : "Not available";
    const dosageParts = [];
    if (dosage.status === "ready") {
      dosageParts.push(`HI score ${dosage.haploinsufficiency?.score || "—"}`);
      dosageParts.push(`TS score ${dosage.triplosensitivity?.score || "—"}`);
    }
    const constraintParts = [];
    if (constraint.status === "ready") {
      if (constraint.loeuf !== null && constraint.loeuf !== undefined) constraintParts.push(`LOEUF ${constraint.loeuf}`);
      if (constraint.pli !== null && constraint.pli !== undefined) constraintParts.push(`pLI ${constraint.pli}`);
    }
    const rows = [
      ["Disease validity", association.strongest_classification || "Unclassified"],
      ["Inheritance", (association.inheritance || []).join(" · ") || "Not available"],
      ["G2P mechanism", mechanismValue || "Not available"],
      ["ClinGen dosage", dosageParts.join(" · ") || "Not available"],
      ["gnomAD constraint", constraintParts.join(" · ") || (constraint.refreshing ? "Loading…" : "Not available")],
    ];
    const grid = node("span", undefined, "gene-association-summary-grid");
    rows.forEach(([label, fieldValue]) => {
      grid.append(node("span", label, "gene-association-summary-label"), node("span", fieldValue));
    });
    tooltip.append(
      grid,
      node(
        "small",
        "G2P is disease-specific; ClinGen dosage and gnomAD constraint are gene-level context.",
      ),
    );
    information.append(button, tooltip);
    return information;
  }

  detailCards(items, fields) {
    const cards = node("div", undefined, "detail-cards");
    if (!items.length) {
      cards.append(node("p", "No data available.", "empty"));
      return cards;
    }
    items.forEach(item => cards.append(this.detailCard(fields(item))));
    return cards;
  }

  transcriptCards(annotations) {
    const cards = this.detailCards(annotations, annotation => [
      ["Gene", annotation.gene],
      ["Transcript", annotation.transcript],
      ["HGVSc", this.compactHgvs(annotation.hgvsc, "c.")],
      ["HGVSp", this.compactHgvs(annotation.hgvsp, "p.")],
      ["Consequence", annotation.consequence],
      ["Exon / intron", annotation.exon_intron],
      ["ClinVar", annotation.clinical_significance],
      ["Canonical", annotation.canonical ? "yes" : "no"],
    ]);
    cards.classList.add("transcript-cards");
    cards.querySelectorAll("dl").forEach(card => card.classList.add("transcript-card"));
    return cards;
  }

  sampleEvidenceContent(calls, detail) {
    const content = node("div", undefined, "detail-cards sample-evidence-grid");
    if (!calls.length) {
      content.append(node("p", "No data available.", "empty"));
      return content;
    }
    calls.forEach(call => {
      const callBlock = node("section", undefined, "sample-evidence-call");
      callBlock.append(this.detailCard(this.callDetailFields(call)));
      const additionalFormat = this.additionalFormatFields(call, detail);
      if (additionalFormat.length) {
        callBlock.append(
          node("h6", "Additional FORMAT info", "additional-format-heading"),
          this.detailCard(additionalFormat),
        );
      }
      content.append(callBlock);
    });
    return content;
  }

  callDetailFields(call) {
    return [
      ["Zygosity", call.zygosity], ["Total depth (DP)", call.depth],
      ["Reference reads", call.reference_depth], ["Alternate reads", call.alternate_depth],
      ["Variant allele fraction (VAF)", call.allele_fraction], ["Variant quality (QUAL)", call.quality],
      ["Phasing", call.phased ? "Phased" : "Unphased"], ["Site filter", call.filter_status],
    ];
  }

  additionalFormatFields(call, detail) {
    const format = call.metadata?.format || {};
    const coreFormatKeys = new Set(["GT", "DP", "AD", "ADF", "ADR", "AF", "GQ", "FS", "SOR"]);
    const additional = [
      ["Genotype", call.genotype], ["Genotype quality (GQ)", call.genotype_quality],
      ...this.strandBiasFields(format, detail),
    ];
    return additional.concat(Object.entries(format)
      .filter(([key, fieldValue]) => {
        const normalized = key.toUpperCase();
        if (coreFormatKeys.has(normalized) || fieldValue === "" || fieldValue === ".") return false;
        if (normalized === "RO" && String(fieldValue) === String(call.reference_depth)) return false;
        if (normalized === "AO" && String(fieldValue) === String(call.alternate_depth)) return false;
        if (normalized === "FT" && String(fieldValue) === String(call.filter_status)) return false;
        return true;
      })
      .sort(([left], [right]) => {
        const leftRank = FORMAT_FIELD_ORDER.indexOf(left.toUpperCase());
        const rightRank = FORMAT_FIELD_ORDER.indexOf(right.toUpperCase());
        return (leftRank < 0 ? 999 : leftRank) - (rightRank < 0 ? 999 : rightRank);
      })
      .map(([key, fieldValue]) => {
        const normalized = key.toUpperCase();
        return [
          FORMAT_FIELD_LABELS[normalized] || key,
          this.formatFieldValue(normalized, fieldValue),
        ];
      }));
  }

  strandBiasFields(format, detail) {
    const normalizedFormat = Object.fromEntries(
      Object.entries(format).map(([key, fieldValue]) => [key.toUpperCase(), fieldValue])
    );
    const siteMetrics = detail.metadata?.quality_metrics || {};
    const isIndel = String(detail.variant_type || "").toLowerCase() === "indel";
    const thresholds = {FS: isIndel ? 200 : 60, SOR: isIndel ? 10 : 3};
    return ["FS", "SOR"].flatMap(key => {
      const rawValue = normalizedFormat[key] ?? siteMetrics[key];
      if (rawValue === null || rawValue === undefined || rawValue === "" || rawValue === ".") return [];
      const numericValue = Number(rawValue);
      const threshold = thresholds[key];
      const warning = Number.isFinite(numericValue) && numericValue > threshold;
      const label = key === "FS" ? "Fisher strand bias (FS)" : "Strand odds ratio (SOR)";
      return [[
        label,
        rawValue,
        {
          warning,
          title: warning
            ? `Above GATK ${isIndel ? "indel" : "SNV"} threshold (${key} > ${threshold}); verify`
            : `GATK ${isIndel ? "indel" : "SNV"} threshold: ${key} ≤ ${threshold}`,
        },
      ]];
    });
  }

  formatFieldValue(key, fieldValue) {
    const parts = String(fieldValue).split(",");
    if (key === "SB" && parts.length === 4) {
      return `REF forward: ${parts[0]} · REF reverse: ${parts[1]} · ALT forward: ${parts[2]} · ALT reverse: ${parts[3]}`;
    }
    if (key === "SAC" && parts.length > 1 && parts.length % 2 === 0) {
      return parts.map((part, index) => {
        const allele = Math.floor(index / 2);
        const alleleLabel = allele === 0 ? "REF" : `ALT ${allele}`;
        return `${alleleLabel} ${index % 2 === 0 ? "forward" : "reverse"}: ${part}`;
      }).join(" · ");
    }
    if (["F1R2", "F2R1"].includes(key) && parts.length > 1) {
      return parts.map((part, index) => `${index === 0 ? "REF" : `ALT ${index}`}: ${part}`).join(" · ");
    }
    return parts.length > 1 ? parts.join(" · ") : String(fieldValue);
  }

  annotationMetadataFields(annotations, matches) {
    const collected = new Map();
    annotations.forEach(annotation => {
      const fields = annotation.metadata?.fields || {};
      Object.entries(fields).forEach(([key, fieldValue]) => {
        if (!matches(key) || fieldValue === null || fieldValue === undefined || fieldValue === "") return;
        if (!collected.has(key)) collected.set(key, new Set());
        collected.get(key).add(String(fieldValue).replace(/%3D/gi, "="));
      });
    });
    return Array.from(collected, ([key, values]) => [key, Array.from(values).join(" · ")]);
  }

  populationFrequencyGroups(annotations) {
    const maximum = new Set(
      annotations.map(annotation => annotation.population_af)
        .filter(fieldValue => fieldValue !== null && fieldValue !== undefined && fieldValue !== "")
        .map(String)
    );
    const fields = maximum.size ? [["AF_max", Array.from(maximum).join(" · ")]] : [];
    fields.push(...this.annotationMetadataFields(annotations, key => {
      const normalized = key.toUpperCase();
      return normalized !== "MAX_AF" && (
        normalized === "AF" || normalized === "MAX_AF_POPS"
        || normalized.endsWith("_AF") || normalized.includes("AF_POPMAX")
      );
    }));
    const grouped = new Map();
    fields.forEach(field => {
      const database = this.frequencyDatabase(field[0]);
      if (!grouped.has(database)) grouped.set(database, []);
      grouped.get(database).push(field);
    });
    const order = ["VEP summary", "gnomAD", "1000 Genomes", "ExAC", "ESP", "TOPMed", "ALFA", "Other"];
    return order.filter(database => grouped.has(database))
      .map(database => ({
        database,
        fields: grouped.get(database).map(([fieldName, fieldValue]) => [
          this.populationFrequencyLabel(database, fieldName),
          this.populationFrequencyValue(fieldName, fieldValue),
        ]),
      }));
  }

  frequencyDatabase(fieldName) {
    const normalized = fieldName.toUpperCase();
    if (normalized === "AF_MAX" || normalized.startsWith("MAX_AF")) return "VEP summary";
    if (normalized.includes("GNOMAD")) return "gnomAD";
    if (normalized.includes("EXAC")) return "ExAC";
    if (normalized.includes("TOPMED")) return "TOPMed";
    if (normalized.includes("ALFA")) return "ALFA";
    if (normalized.includes("ESP") || ["AA_AF", "EA_AF"].includes(normalized)) return "ESP";
    if (["AF", "AFR_AF", "AMR_AF", "EAS_AF", "EUR_AF", "SAS_AF"].includes(normalized)) {
      return "1000 Genomes";
    }
    return "Other";
  }

  populationFrequencyLabel(database, fieldName) {
    const normalized = fieldName.toUpperCase();
    if (database === "VEP summary") {
      return normalized === "AF_MAX" ? "Maximum allele frequency" : "Population at maximum AF";
    }
    let code = normalized;
    let scope = "";
    if (database === "gnomAD") {
      if (code.startsWith("GNOMADE_")) scope = "Exomes";
      if (code.startsWith("GNOMADG_")) scope = "Genomes";
      code = code.replace(/^GNOMAD[EG]_/, "");
    } else if (database === "ExAC") {
      code = code.replace(/^EXAC(?:_ADJ)?_/, "");
    } else if (database === "ESP") {
      code = code.replace(/^ESP_/, "");
    } else if (database === "TOPMed") {
      code = code.replace(/^TOPMED_/, "");
    } else if (database === "ALFA") {
      code = code.replace(/^ALFA_/, "");
    }
    code = code.replace(/_AF$/, "");
    const population = POPULATION_LABELS[code] || this.readableFieldName(code);
    return scope ? `${scope} · ${population}` : population;
  }

  populationFrequencyValue(fieldName, fieldValue) {
    if (fieldName.toUpperCase() !== "MAX_AF_POPS") return fieldValue;
    return String(fieldValue).split(/[,&]/).map(rawPopulation => {
      const token = rawPopulation.trim();
      if (!token) return "";
      if (/^gnomAD[eg]_/i.test(token)) {
        return this.populationFrequencyLabel("gnomAD", `${token}_AF`);
      }
      return POPULATION_LABELS[token.toUpperCase()] || this.readableFieldName(token);
    }).filter(Boolean).join(" · ");
  }

  readableFieldName(fieldName) {
    return String(fieldName).replace(/_/g, " ").toLowerCase()
      .replace(/(^|\s)\S/g, character => character.toUpperCase());
  }

  referenceToolConfiguration(referenceBuild) {
    const build = String(referenceBuild || "").trim().toLowerCase();
    if (["grch37", "hg19", "b37", "hs37d5", "human_g1k_v37"].some(name => build.includes(name))) {
      return {
        referenceBuild: "GRCh37",
        tools: {gnomad: {dataset: "gnomad_r2_1", version: "2.1"}},
      };
    }
    if (["grch38", "hg38", "b38", "hs38dh"].some(name => build.includes(name))) {
      return {
        referenceBuild: "GRCh38",
        tools: {gnomad: {dataset: "gnomad_r4", version: "4"}},
      };
    }
    return null;
  }

  externalVariantTool(detail, toolName) {
    const reference = this.referenceToolConfiguration(detail.reference_build);
    const tool = reference?.tools?.[toolName];
    if (!tool) return null;
    const chromosome = String(detail.chromosome || "").replace(/^chr/i, "");
    const variantParts = [chromosome, detail.position, detail.reference, detail.alternate];
    if (variantParts.some(part => part === null || part === undefined || part === "")) return null;
    const variantId = variantParts.map(part => encodeURIComponent(String(part))).join("-");
    if (toolName === "gnomad") {
      return {
        ...tool,
        referenceBuild: reference.referenceBuild,
        url: `https://gnomad.broadinstitute.org/variant/${variantId}?dataset=${tool.dataset}`,
      };
    }
    return null;
  }

  populationFrequencyContent(groups, detail) {
    const content = node("div", undefined, "detail-content population-frequency-groups");
    if (!groups.length) {
      content.append(node("p", "No data available.", "empty"));
      return content;
    }
    groups.forEach(group => {
      const summaryClass = group.database === "VEP summary" ? " frequency-summary" : "";
      const card = node("section", undefined, `frequency-group${summaryClass}`);
      const heading = node("h5");
      const externalTool = group.database === "gnomAD" ? this.externalVariantTool(detail, "gnomad") : null;
      if (externalTool) {
        const link = node("a", undefined, "frequency-external-link");
        link.href = externalTool.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.title = `Open this ${externalTool.referenceBuild} variant in gnomAD ${externalTool.version} (new tab)`;
        link.setAttribute(
          "aria-label",
          `Open this ${externalTool.referenceBuild} variant in gnomAD ${externalTool.version} in a new tab`,
        );
        link.append(
          node("span", "gnomAD"),
          node("small", `v${externalTool.version}`, "frequency-tool-version"),
          node("span", "↗", "external-link-icon"),
        );
        heading.append(link);
      } else {
        heading.textContent = group.database;
      }
      card.append(heading, this.detailCard(group.fields));
      content.append(card);
    });
    return content;
  }

  damagePredictionFields(annotations) {
    const predictors = /SIFT|POLYPHEN|CADD|REVEL|MUTATIONTASTER|METASVM|METALR|FATHMM|DANN|SPLICEAI|ALPHAMISSENSE|PRIMATEAI|MPC|CLINPRED|BAYESDEL/i;
    return this.annotationMetadataFields(annotations, key => predictors.test(key));
  }

  setRoute(runId, sampleId) {
    if (!runId) return;
    const params = new URLSearchParams({run: runId});
    if (sampleId !== null) params.set("sample", String(sampleId));
    const next = `#${this.routePrefix}?${params}`;
    if (window.location.hash !== next) window.history.replaceState(null, "", next);
  }

  async restoreRoute() {
    const hash = window.location.hash;
    if (!hash.startsWith(`#${this.routePrefix}`)) return;
    const params = new URLSearchParams(hash.includes("?") ? hash.split("?")[1] : "");
    const runId = params.get("run");
    const sampleId = params.get("sample");
    if (runId && this.runs.some(run => run.history_id === runId)) {
      if (this.selectedRun !== runId || !this.samples.length) await this.selectRun(runId, sampleId);
      else if (sampleId) {
        const sample = this.samples.find(item => item.sample_id === Number(sampleId));
        if (sample) await this.openSample(sample, false);
      }
    }
  }
}

if (!customElements.get("variant-browser")) customElements.define("variant-browser", VariantBrowser);

export {VariantBrowser};
