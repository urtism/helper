/* Criterion audit UI. Scientific values are displayed exactly as returned by ACMG Engine. */
const CSS = new URL("./acmg-workbench.css", import.meta.url).href;
const CODES = "PVS1 PS1 PS2 PS3 PS4 PM1 PM2 PM3 PM4 PM5 PM6 PP1 PP2 PP3 PP4 PP5 BA1 BS1 BS2 BS3 BS4 BP1 BP2 BP3 BP4 BP5 BP6 BP7".split(" ");
const CATEGORIES = "EVIDENCE_MAPPING_ERROR WRONG_THRESHOLD WRONG_CALCULATION WRONG_RULE_PROFILE INCORRECT_APPLICABILITY INCORRECT_STRENGTH MISSING_EVIDENCE SCIENTIFIC_RULE_DISAGREEMENT DEPENDENCY_ERROR OTHER".split(" ");
const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
const show = value => value === null || value === undefined || (Array.isArray(value) && !value.length) ? "NOT_RECORDED" : typeof value === "object" ? JSON.stringify(value) : String(value);
const option = (value, label = value) => { const n = el("option", label); n.value = value; return n; };

async function api(path, body) {
  const response = await fetch(`/api/acmg${path}`, body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok && result.detail?.code === "ENGINE_UNAVAILABLE") throw new Error(result.detail.message);
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : JSON.stringify(result.detail || result));
  return result;
}

function tree(value) {
  if (value === null || value === undefined || (Array.isArray(value) && !value.length)) return el("p", "NOT_RECORDED");
  if (typeof value !== "object") return el("span", show(value));
  const table = el("table", undefined, "acmg-values");
  for (const [key, item] of Object.entries(value)) {
    const row = el("tr"); row.append(el("th", key));
    const cell = el("td"); cell.append(tree(item)); row.append(cell); table.append(row);
  }
  return table;
}

function disclosure(label, value, open = false) {
  const box = el("details"); box.open = open; box.append(el("summary", label), tree(value)); return box;
}

function section(label, ...children) {
  const box = el("details"); box.append(el("summary", label), ...children); return box;
}

function recordedFields(value, names, path = "") {
  const output = [];
  if (value && typeof value === "object") for (const [key, item] of Object.entries(value)) {
    const next = path ? `${path}.${key}` : key;
    if (names.includes(key) && item !== null && item !== undefined) output.push({path: next, value: item});
    output.push(...recordedFields(item, names, next));
  }
  return output;
}

function rows(result) {
  const classification = result.classification || {};
  return CODES.map(code => {
    const raw = result.criterion_results?.find(c => c.code === code);
    const excluded = classification.excluded_criteria?.find(c => c.code === code);
    const dependencyExclusion = excluded && classification.dependencies?.some(d => d.disposition === "EXCLUDE" && d.criterion_codes?.includes(code));
    return {code, raw, engine_status: raw?.status || "NOT_RECORDED",
      display_status: ["PP5", "BP6"].includes(code) ? "DEPRECATED" : dependencyExclusion ? "EXCLUDED_BY_DEPENDENCY" : raw?.activation === "UNSUPPORTED" ? "UNSUPPORTED" : raw?.status || "NOT_EVALUATED",
      candidate_active: raw?.status === "MET" ? true : raw?.status === "NOT_MET" ? false : null,
      effective_active: classification.included_criteria ? classification.included_criteria.includes(code) : null,
      candidate_strength: raw?.strength,
      effective_strength: classification.effective_strengths?.find(c => c.code === code)?.strength,
      explanation: raw?.explanation, excluded};
  });
}

export async function openAcmgWorkbench(browser, sourceWorkspace) {
  const layer = browser.shadowRoot.querySelector("#dialog-layer");
  const backdrop = el("div", undefined, "dialog-backdrop");
  const panel = el("section", undefined, "acmg-workbench");
  panel.setAttribute("role", "dialog"); panel.setAttribute("aria-modal", "true"); panel.setAttribute("aria-label", "ACMG Interpretation Workbench");
  const link = document.createElement("link"); link.rel = "stylesheet"; link.href = CSS;
  const close = el("button", "Close"); close.onclick = () => layer.replaceChildren();
  const heading = el("div", undefined, "acmg-heading"); heading.append(el("h3", "ACMG classification"), close);
  panel.append(link, heading, el("p", "Research only · Experimental profiles, not clinically validated.", "acmg-warning"));
  const status = el("p", "Connecting to ACMG Engine…", "status"); status.setAttribute("aria-live", "polite"); panel.append(status);
  const detail = sourceWorkspace.detail;
  const variantLabel = el("p", `${detail.reference_build} · ${detail.chromosome}:${detail.position} ${detail.reference}>${detail.alternate}`, "acmg-variant");
  panel.append(variantLabel);
  const contextBox = section("1. Variant context"); contextBox.className = "acmg-context"; contextBox.open = true;
  const contextSummary = contextBox.querySelector("summary");
  const config = el("form", undefined, "acmg-config");
  const automatic = el("div", undefined, "acmg-config");
  const input = (label, value = "") => { const wrap = el("label", label), field = el("input"); field.value = value; field.required = true; wrap.append(field); automatic.append(wrap); return field; };
  const geneNS = input("Gene namespace (HELPER)"), geneID = input("Stable gene ID (automatic)");
  const diseaseNS = input("Disease namespace (HELPER)"), diseaseID = input("Disease ID (automatic)");
  [geneNS, geneID, diseaseNS, diseaseID].forEach(field => { field.readOnly = true; field.required = false; field.placeholder = "Not available in HELPER data"; });
  const assembly = el("select"); assembly.required = true;
  assembly.append(option("", "Confirm assembly"), option("GRCh37"), option("GRCh38"));
  assembly.className = "acmg-assembly";
  assembly.value = ({grch37: "GRCh37", hg19: "GRCh37", grch38: "GRCh38", hg38: "GRCh38"})[String(detail.reference_build || '').toLowerCase()] || "";
  const tx = el("select"); tx.required = true; tx.append(option("", "Select relevant transcript"));
  (detail.annotations || []).filter(a => a.transcript).forEach(a => tx.append(option(String(a.id), `${a.gene || 'Gene not recorded'} · ${a.transcript} · ${a.annotator || 'VCF'} · annotation ${a.id}`)));
  tx.className = "acmg-transcript";
  if (tx.options.length === 2) tx.selectedIndex = 1;
  const inheritance = el("select"); inheritance.append(option("", "Inheritance not supplied"));
  inheritance.className = "acmg-inheritance";
  const contextSelect = el("select"); contextSelect.className = "acmg-disease-context"; contextSelect.required = true;
  contextSelect.append(option("", "Loading HELPER gene-disease data…"));
  const field = (label, control, host = config) => { const wrap = el("label", label); wrap.append(control); host.append(wrap); return wrap; };
  field("Assembly", assembly, assembly.value ? automatic : config);
  const transcriptField = field("Transcript", tx);
  const diseaseField = field("Disease", contextSelect);
  const inheritanceField = field("Inheritance", inheritance);
  const prepare = el("button", "Continue to classification"); prepare.className = "acmg-primary"; prepare.type = "submit"; prepare.disabled = true;
  const contextStatus = el("p", "Loading structured HELPER interpretation context…"); contextStatus.setAttribute("aria-live", "polite");
  const reloadContext = el("button", "Reload HELPER context"); reloadContext.type = "button";
  const contextSources = el("div");
  const contextDetails = section("Automatic data and sources", automatic, reloadContext, contextSources);
  config.append(contextStatus, contextDetails, prepare); contextBox.append(config); panel.append(contextBox);
  const body = el("div"); panel.append(body); backdrop.append(panel); layer.replaceChildren(backdrop); close.focus();
  const state = {workspace: null, profiles: [], selected: null, history: [], capability: null, criteria: [],
    catalog: detail.interpretation_context || null, contextChoice: null, inheritanceModes: [], loadingDiscovery: true};
  const storageKey = `helper-acmg:${sourceWorkspace.runId}:${sourceWorkspace.sample.sample_id}:${detail.id}`;
  const busy = async action => { status.textContent = "Working…"; try { await action(); status.textContent = "Ready · research only"; } catch (error) { status.textContent = error.message; } };
  function chooseContext() {
    const record = state.catalog?.annotations.find(a => String(a.annotation_id) === tx.value);
    const choice = record?.contexts.find(c => c.id === contextSelect.value);
    state.contextChoice = choice || null;
    const gene = choice?.context.gene || record?.gene;
    geneNS.value = gene?.namespace || ""; geneID.value = gene?.identifier || "";
    diseaseNS.value = choice?.context.disease.namespace || ""; diseaseID.value = choice?.context.disease.identifier || "";
    inheritance.replaceChildren(option("", "Inheritance missing / unresolved"));
    const modes = (choice?.context.inheritance_modes || []).filter(mode => !state.inheritanceModes.length || state.inheritanceModes.includes(mode));
    modes.forEach(mode => inheritance.append(option(mode)));
    if (modes.length === 1) inheritance.value = modes[0];
    (modes.length > 1 ? config : automatic).append(inheritanceField);
    if (modes.length > 1) config.insertBefore(inheritanceField, contextStatus);
    (tx.options.length !== 2 ? config : automatic).append(transcriptField);
    if (tx.options.length !== 2) config.insertBefore(transcriptField, config.firstChild);
    (record?.contexts.length === 1 ? automatic : config).append(diseaseField);
    if (record?.contexts.length !== 1) config.insertBefore(diseaseField, contextStatus);
    const annotation = detail.annotations.find(a => String(a.id) === tx.value);
    contextSummary.textContent = `1. Context · ${annotation?.gene || gene?.identifier || 'Select transcript'}${choice ? ' · ' + (choice.context.disease.label || choice.context.disease.identifier) : ''}${annotation?.transcript ? ' · ' + annotation.transcript : ''}`;
    prepare.disabled = !choice || state.loadingDiscovery;
    contextStatus.textContent = choice
      ? `Context supplied by HELPER${choice.origin?.stale ? ' · source snapshot is stale' : ''}${modes.length > 1 ? ' · select inheritance or leave unresolved' : ''}`
      : record?.contexts.length > 1 ? "Select the relevant disease association; HELPER supplies its identifiers automatically."
        : `HELPER context unavailable (${record?.status || 'select a transcript'}). Update HELPER gene-disease sources and reload; no identifiers or disease are inferred.`;
    contextSources.replaceChildren(disclosure("HELPER structured context and source provenance", choice || record));
  }
  function annotationContext(preferredId = "") {
    const record = state.catalog?.annotations.find(a => String(a.annotation_id) === tx.value);
    contextSelect.replaceChildren(option("", record?.contexts.length ? "Select gene-disease context" : "No structured disease context available"));
    (record?.contexts || []).forEach(choice => contextSelect.append(option(choice.id, `${choice.context.disease.label || choice.context.disease.identifier} · ${choice.context.disease.identifier}`)));
    if (preferredId && record?.contexts.some(c => c.id === preferredId)) contextSelect.value = preferredId;
    else if (record?.contexts.length === 1) contextSelect.value = record.contexts[0].id;
    chooseContext();
  }
  async function refreshContext(force = false) {
    if (force || !state.catalog) state.catalog = await api(`/contexts?source_id=${encodeURIComponent(sourceWorkspace.runId)}&sample_id=${sourceWorkspace.sample.sample_id}&variant_id=${detail.id}`);
    annotationContext(state.contextChoice?.id || "");
  }
  tx.onchange = () => annotationContext(); contextSelect.onchange = chooseContext;
  reloadContext.onclick = () => busy(() => refreshContext(true));
  const savedWorkspaces = el("select"); savedWorkspaces.setAttribute("aria-label", "Previously saved variant contexts");
  savedWorkspaces.append(option("", "Saved interpretation contexts"));
  const savedBox = section("Saved contexts", savedWorkspaces); savedBox.hidden = true; contextBox.before(savedBox);
  const refreshSaved = async () => {
    const result = await api(`/workspaces?source_id=${encodeURIComponent(sourceWorkspace.runId)}&sample_id=${sourceWorkspace.sample.sample_id}&variant_id=${detail.id}`);
    savedWorkspaces.replaceChildren(option("", "Saved interpretation contexts"));
    result.workspaces.forEach(w => savedWorkspaces.append(option(w.id, `${w.created_at} · ${w.context.gene?.identifier} · ${w.context.disease?.identifier} · ${w.context.transcripts?.map(t => t.accession + (t.version ? '.' + t.version : '')).join(', ')}`)));
    savedBox.hidden = !result.workspaces.length;
    if (state.workspace) savedWorkspaces.value = state.workspace.id;
  };
  savedWorkspaces.onchange = () => { if (savedWorkspaces.value) busy(async () => {
    state.workspace = (await api(`/workspaces/${savedWorkspaces.value}`)).workspace; state.selected = null;
    localStorage.setItem(storageKey, state.workspace.id); await load();
  }); };
  config.onsubmit = event => { event.preventDefault(); busy(async () => {
    const annotation = detail.annotations.find(a => String(a.id) === tx.value);
    if (!annotation) throw new Error("Select the relevant transcript annotation explicitly");
    if (!state.contextChoice) throw new Error("Select an available structured HELPER gene-disease context");
    state.workspace = await api("/workspaces", {source_id: sourceWorkspace.runId, sample_id: sourceWorkspace.sample.sample_id,
      variant_id: detail.id, transcript: annotation.transcript, annotation_id: annotation.id, assembly: assembly.value,
      context_id: state.contextChoice.id, context_fingerprint: state.contextChoice.fingerprint.value,
      inheritance_mode: inheritance.value});
    localStorage.setItem(storageKey, state.workspace.id); state.selected = null; await load(); await refreshSaved();
  }); };

  async function load() {
    const workspace = await api(`/workspaces/${state.workspace.id}`);
    state.workspace = workspace.workspace; state.history = workspace.history;
    const snapshot = state.workspace.document.normalized_evidence.snapshot;
    geneNS.value = snapshot.context.gene.namespace; geneID.value = snapshot.context.gene.identifier;
    diseaseNS.value = snapshot.context.disease.namespace; diseaseID.value = snapshot.context.disease.identifier;
    assembly.value = snapshot.variant.identity.assembly;
    const selectedTx = snapshot.variant.transcript_selection?.transcript;
    if (selectedTx) tx.value = String(state.workspace.document.selected_annotation_id || '');
    annotationContext(state.workspace.document.context_resolution?.id || "");
    inheritance.value = snapshot.context.gene_disease?.inheritance_modes?.[0] || "";
    state.profiles = (await api(`/workspaces/${state.workspace.id}/profiles`)).profiles;
    contextBox.open = false;
    render();
  }

  function exports(host, result) {
    const links = el("div", undefined, "acmg-actions");
    const extra = section("Other exports");
    const formats = result.kind === "comparison" ? ["comparison", "evidence", "report"] : ["engine", "table", "evidence", "report", "troubleshooting", "reviews", "rerun"];
    formats.forEach(format => {
      if (format === "rerun" && !result.document.parent_id) return;
      const a = el("a", format === "report" ? "Download report" : `Export ${format}`); a.href = `/api/acmg/results/${result.id}/export/${format}`; a.download = "";
      (format === "report" ? links : extra).append(a);
    }); links.append(extra); host.append(links);
  }

  function render() {
    body.replaceChildren();
    const packet = state.workspace.document.normalized_evidence;
    const advanced = section("Advanced tools and evidence",
      el("p", `Evidence saved: ${state.workspace.created_at}. Prepare again to capture changed annotations or context.`),
      disclosure("Resolved HELPER gene-disease context", state.workspace.document.context_resolution),
      disclosure("Original VCF evidence (local, immutable)", state.workspace.document.original_vcf_evidence),
      disclosure("Normalized EvidencePacket / missing prerequisites", packet));
    const selectors = el("div", undefined, "acmg-config acmg-profile-selectors"), base = el("select"), special = el("select"), comparator = el("select");
    base.append(option("", "Select generic profile/version")); special.append(option("", "No specialization")); comparator.append(option("", "Select comparison baseline/profile"));
    state.profiles.forEach((profile, index) => {
      const label = `${profile.strategy === "CLINGEN_GUIDED" ? 'ClinGen' : profile.strategy === "CUSTOM_ALGORITHMIC" ? 'Custom' : profile.strategy} · ${profile.profile_id} · ${profile.version}`;
      const opt = option(String(index), label); opt.disabled = ["DRAFT", "DEPRECATED"].includes(profile.release_status);
      (profile.applicability.specificity === "NONE" ? base : special).append(opt);
      if (profile.applicability.specificity === "NONE") comparator.append(opt.cloneNode(true));
    });
    base.setAttribute("aria-label", "Classification profile"); special.setAttribute("aria-label", "Specialization"); comparator.setAttribute("aria-label", "Comparison profile");
    const baseField = el("label", "Classification profile"); baseField.append(base);
    const specialField = el("label", "Specialization (optional)"); specialField.append(special); specialField.hidden = special.options.length === 1;
    selectors.append(baseField, specialField); body.append(el("h4", "2. Classification"), selectors);
    if (!state.profiles.length) body.append(el("p", "UNSUPPORTED: no profiles available for this explicit gene-disease context."));
    const profileInfo = el("div"); advanced.append(profileInfo);
    let updateActions = () => {};
    const profileChanged = () => {
      const indexes = [base.value, special.value].filter(x => x !== "");
      profileInfo.replaceChildren(disclosure("Selected profile applicability, scientific sources and classification method", indexes.map(i => state.profiles[Number(i)])));
      for (const o of special.options) if (o.value !== "") o.disabled = !base.value || state.profiles[Number(o.value)].strategy !== state.profiles[Number(base.value)].strategy || ["DRAFT", "DEPRECATED"].includes(state.profiles[Number(o.value)].release_status);
      updateActions();
    };
    base.onchange = () => { special.value = ""; profileChanged(); }; special.onchange = profileChanged;
    const availableBases = [...base.options].filter(o => o.value !== "" && !o.disabled);
    if (availableBases.length === 1) base.value = availableBases[0].value;
    profileChanged();
    const editBox = el("details"); editBox.append(el("summary", "User-supplied evidence / explicit corrections"));
    editBox.append(el("p", "JSON array: each item requires evidence, source (version/checksum), comment and optional replaces (evidence ID). Evidence uses the engine schema; provenance.extraction_method must be MANUAL. Scientific thresholds belong in the engine registry."));
    const corrections = el("textarea"); corrections.rows = 8; corrections.value = "[]"; corrections.setAttribute("aria-label", "Structured evidence corrections"); editBox.append(corrections);
    const schemas = el("a", "Inspect live engine evidence schemas"); schemas.href = "/api/acmg/discovery"; schemas.target = "_blank"; schemas.rel = "noopener"; editBox.append(schemas); advanced.append(editBox);
    const actions = el("div", undefined, "acmg-actions"), run = el("button", "Classify variant"), compare = el("button", "Compare Standard vs VCEP");
    run.className = "acmg-primary";
    const selection = () => {
      if (base.value === "") throw new Error("Select an explicit generic profile and version");
      return [base.value, special.value].filter(x => x !== "").map(i => ({profile_id: state.profiles[Number(i)].profile_id, version: state.profiles[Number(i)].version}));
    };
    const referenceRequired = packet.snapshot.evidence.length > 0 && packet.snapshot.variant.normalization.reference_validated !== true;
    const executionStatus = el("p", undefined, "acmg-warning acmg-execution-status");
    executionStatus.setAttribute("role", "status");
    body.append(executionStatus);
    updateActions = () => {
      const blockers = [];
      if (!state.capability?.research_execution_enabled) blockers.push("Research interpretation is disabled on ACMG Engine. Enable research execution in the server configuration, then reopen this workbench.");
      if (referenceRequired) blockers.push("PACKET_NORMALIZATION_REQUIRED: configure HELPER_ACMG_REFERENCE_CONFIG with a matching FASTA and .fai, then prepare this workspace again. Imported evidence remains preserved.");
      if (base.value === "") blockers.push("Select a classification profile to enable Classify variant.");
      run.disabled = blockers.length > 0;
      compare.disabled = run.disabled || comparator.value === "";
      executionStatus.textContent = blockers.join(" ");
      executionStatus.hidden = blockers.length === 0;
      run.title = executionStatus.textContent;
    };
    updateActions(); comparator.onchange = updateActions;
    run.onclick = () => busy(async () => {
      const result = await api(`/workspaces/${state.workspace.id}/interpret`, {selections: selection(), corrections: JSON.parse(corrections.value), parent_id: state.selected?.kind === "interpretation" ? state.selected.id : ""});
      state.selected = result; state.history = (await api(`/workspaces/${state.workspace.id}`)).history; renderResult(result); renderHistory();
    });
    compare.onclick = () => busy(async () => {
      if (comparator.value === "") throw new Error("Select an explicit comparison baseline/profile");
      const p = state.profiles[Number(comparator.value)];
      const result = await api(`/workspaces/${state.workspace.id}/compare`, {selections: [[{profile_id: p.profile_id, version: p.version}], selection()], corrections: JSON.parse(corrections.value)});
      state.selected = result; state.history = (await api(`/workspaces/${state.workspace.id}`)).history; renderComparison(result); renderHistory();
    });
    actions.append(run); selectors.append(actions);
    advanced.append(section("Compare profiles", comparator, compare));
    const resultHost = el("div"), historyHost = el("div"), historyBox = section("Interpretation history", historyHost); historyBox.hidden = true;
    body.append(resultHost, advanced, historyBox);

    function renderResult(result) {
      state.selected = result; resultHost.replaceChildren();
      corrections.value = JSON.stringify(result.document.corrections || [], null, 2);
      const response = result.document.engine_result, engine = response.result;
      const classification = engine.classification || {};
      const identity = result.document.packet.snapshot.variant.identity, context = result.document.packet.snapshot.context;
      const config = result.document.configuration;
      const outcome = el("div", undefined, "acmg-outcome");
      outcome.append(el("h4", classification.status === "CLASSIFIED" ? classification.category : classification.status || "Classification unavailable"),
        el("p", `Evidence: ${show(response.evidence_completeness)} · Effective criteria: ${classification.included_criteria?.join(', ') || 'None recorded'}`));
      const summary = el("dl", undefined, "acmg-summary");
      const summaryFields = {
        Variant: `${identity.assembly} ${identity.chromosome}:${identity.position} ${identity.reference}>${identity.alternate}`,
        Gene: context.gene?.identifier, Disease: context.disease?.identifier, Methodology: config.strategy,
        Profiles: [config.base_profile, ...config.specializations].map(p => `${p.profile_id}@${p.version}`).join("; "),
        Classification: classification.status === "CLASSIFIED" ? classification.category : classification.status,
        Method: classification.method, Completeness: `${show(engine.evaluation_status)} / ${show(response.evidence_completeness)}`,
        "Effective criteria": classification.included_criteria?.join(", ") || "None recorded",
      };
      for (const [key, value] of Object.entries(summaryFields)) summary.append(el("dt", key), el("dd", show(value)));
      resultHost.append(outcome,
        section("Classification details and limitations", summary,
          disclosure("Configuration and full engine audit", {context, configuration: config, classification,
            warnings: engine.warnings, limitations: response.limitations})));
      if (engine.warnings?.length || response.limitations?.length) resultHost.append(disclosure("Engine warnings and limitations", {warnings: engine.warnings, limitations: response.limitations}));
      exports(resultHost, result);
      const filter = el("input"); filter.type = "search"; filter.placeholder = "Find criterion or status"; filter.setAttribute("aria-label", "Filter criteria");
      const technical = el("input"); technical.type = "checkbox";
      const technicalLabel = el("label", undefined, "acmg-checkbox"); technicalLabel.append(technical, el("span", "Show technical columns"));
      const toolbar = el("div", undefined, "acmg-actions"); toolbar.append(filter, technicalLabel); resultHost.append(toolbar);
      const tableHost = el("div", undefined, "acmg-table-scroll"), inspector = el("div", undefined, "acmg-inspector"); resultHost.append(tableHost, inspector);
      const renderTable = () => {
        const table = el("table"), head = el("tr");
        const headers = technical.checked
          ? ["Criterion", "Definition", "Applicability", "Standard rule", "VCEP modification", "Status", "Engine status", "Candidate active", "Effective active", "Candidate strength", "Effective strength", "Observed / calculated", "Threshold / operator", "Condition result", "Explanation", "Review"]
          : ["Criterion", "Status", "Effective strength", "Contribution", "Explanation", "Review"];
        headers.forEach(v => head.append(el("th", v))); table.append(head);
        (result.document.rows || rows(engine)).forEach(row => {
          const reviews = state.history.filter(e => e.kind === "review" && e.document.interpretation_id === result.id && e.document.criterion === row.code);
          const review = reviews.at(-1)?.document.decision || "UNREVIEWED";
          if (!JSON.stringify([row, review]).toLowerCase().includes(filter.value.toLowerCase())) return;
          const tr = el("tr"); const button = el("button", row.code); button.onclick = () => { inspect(row, result, inspector); inspector.scrollIntoView({block: "nearest", behavior: "smooth"}); }; const td = el("td"); td.append(button); tr.append(td);
          const coverage = state.criteria.find(c => c.code === row.code)?.coverage;
          const mapping = row.raw?.rules?.find(r => r.vcep_mapping)?.vcep_mapping;
          button.title = coverage?.original_definition || `Inspect ${row.code}`;
          const values = technical.checked ? [coverage?.original_definition, mapping?.applicability_conditions || coverage?.applicability,
            mapping?.original_definition || coverage?.current_general_rule,
            mapping ? {definition: mapping.modified_definition, types: mapping.modification_types} : null,
            row.display_status, row.engine_status, row.candidate_active, row.effective_active,
            row.candidate_strength, row.effective_strength,
            recordedFields(row.raw, ["selected_value", "observed_score", "binomial_upper95", "poisson_upper95"]),
            recordedFields(row.raw, ["threshold", "operator"]),
            recordedFields(row.raw, ["primary_candidate_met", "sensitivity_candidate_met", "condition_met"]),
            row.explanation, review] : [row.display_status, row.effective_strength || '—',
            row.effective_active === true ? 'Included' : row.excluded ? 'Excluded' : row.effective_active === false ? 'Not included' : 'Not recorded', row.explanation, review];
          values.forEach(v => tr.append(el("td", show(v)))); table.append(tr);
        }); tableHost.replaceChildren(table);
      }; filter.oninput = renderTable; technical.onchange = renderTable; renderTable();
    }

    function inspect(row, result, host) {
      const c = row.raw, packet = result.document.packet;
      const closeInspector = el("button", "Close criterion"); closeInspector.onclick = () => host.replaceChildren();
      const inspectorHeading = el("div", undefined, "acmg-heading"); inspectorHeading.append(el("h4", `${row.code} · ${row.display_status}`), closeInspector);
      host.replaceChildren(inspectorHeading, el("p", c?.explanation || "No explanation recorded"));
      host.append(disclosure("Criterion context and contribution", {context: packet.snapshot.context, profile: result.document.configuration,
        engine_status: row.engine_status, display_status: row.display_status, candidate_active: row.candidate_active,
        effective_active: row.effective_active, candidate_strength: row.candidate_strength, effective_strength: row.effective_strength,
        reason_code: c?.reason_code, explanation: c?.explanation, dependency_exclusion: row.excluded}));
      if (c?.reason_code) host.append(el("p", c.reason_code, "acmg-reason"));
      if (c?.population_upper_ci?.length) {
        host.append(el("h5", "Numerical threshold inspector · full precision"), tree(c.population_upper_ci));
      }
      host.append(disclosure("Numerical fields recorded by the engine (input, calculation, method, operator, condition)", {
        metric: recordedFields(c, ["metric"]),
        inputs: recordedFields(c, ["allele_count", "allele_number", "observed_af", "observed_score"]),
        calculated_value: recordedFields(c, ["selected_value", "binomial_upper95", "poisson_upper95"]),
        mathematical_operation: recordedFields(c, ["formula", "algorithm", "operation"]),
        operator: recordedFields(c, ["operator"]), threshold: recordedFields(c, ["threshold"]),
        scientific_rule: c?.rules,
        calculation_method: recordedFields(c, ["method", "primary_method", "sensitivity_method"]),
        dataset_and_source_version: recordedFields(c, ["dataset_id", "source_identifier", "source_version"]),
        condition_satisfied: recordedFields(c, ["primary_candidate_met", "sensitivity_candidate_met", "condition_met"]),
        method_discordance: recordedFields(c, ["method_discordance"]),
      }));
      const audits = Object.fromEntries(Object.entries(c || {}).filter(([key]) => key.endsWith("_audit") || key === "population_upper_ci"));
      host.append(disclosure("Actual calculations and qualitative decision branches", Object.keys(audits).length ? audits : null),
        disclosure("Scientific rules / thresholds / operators / VCEP mapping / provenance", c?.rules),
        disclosure("Input EvidencePacket and sources", packet),
        disclosure("Missing / rejected evidence and required manual actions", {missing: packet.missing_evidence, excluded: c?.excluded_evidence, manual_actions: c?.required_manual_actions, warnings: c?.warnings}),
        disclosure("Complete criterion result (unchanged)", c));
      const troubleshooting = el("details"); troubleshooting.append(el("summary", "Scientific troubleshooting: evidence path"));
      troubleshooting.append(el("p", "The first unavailable stage below is a transport/data observation. Scientific insufficiency and rejected evidence are reported only by the engine."));
      const stages = [
        ["RAW VCF VALUE", state.workspace.document.original_vcf_evidence.metadata?.original_vcf],
        ["NORMALIZED ANNOTATION", packet.snapshot.variant.annotations], ["EVIDENCE PACKET", packet.snapshot.evidence],
        ["SCIENTIFIC RULE SELECTION", c?.rules], ["EVALUATOR INPUT", Object.keys(audits).length ? audits : null],
        ["CALCULATION / DECISION TREE", Object.keys(audits).length ? audits : null],
        ["THRESHOLD COMPARISON", c?.population_upper_ci || audits], ["CANDIDATE CRITERION RESULT", c],
        ["DEPENDENCY RECONCILIATION", result.document.engine_result.result.classification.dependencies],
        ["EFFECTIVE CONTRIBUTION", {active: row.effective_active, strength: row.effective_strength, excluded: row.excluded}],
        ["CLASSIFICATION", result.document.engine_result.result.classification]];
      let first = true;
      for (const [name, value] of stages) {
        const missing = value == null || (Array.isArray(value) && !value.length) || (typeof value === "object" && !Object.keys(value).length);
        troubleshooting.append(disclosure(`${name}${missing ? first ? " · FIRST NOT_RECORDED" : " · NOT_RECORDED" : ""}`, value));
        if (missing) first = false;
      } host.append(troubleshooting);
      if (!c) return;
      const review = el("form", undefined, "acmg-review"), decision = el("select"), category = el("select"), reviewer = el("input"), comment = el("textarea"), evidence = el("textarea");
      ["CONFIRM", "CONTEST", "REQUEST_REVIEW"].forEach(v => decision.append(option(v))); CATEGORIES.forEach(v => category.append(option(v)));
      reviewer.placeholder = "Reviewer identifier (optional)"; comment.placeholder = "Review comments / reason for disagreement"; comment.required = true;
      evidence.value = "[]"; evidence.setAttribute("aria-label", "Relevant review evidence (JSON)");
      const save = el("button", "Record criterion review"); save.type = "submit";
      review.append(decision, comment, section("Review category and references", category, reviewer, evidence), save);
      decision.setAttribute("aria-label", "Review decision"); category.setAttribute("aria-label", "Review category"); reviewer.setAttribute("aria-label", "Reviewer identifier"); comment.setAttribute("aria-label", "Review comments");
      review.onsubmit = event => { event.preventDefault(); busy(async () => {
        await api(`/results/${result.id}/reviews`, {criterion: row.code, decision: decision.value, discrepancy: category.value, reviewer_id: reviewer.value, comments: comment.value, evidence: JSON.parse(evidence.value)});
        state.history = (await api(`/workspaces/${state.workspace.id}`)).history; renderResult(result); renderHistory();
      }); };
      host.append(section("Review this criterion", review), disclosure("Review annotations for this result only", state.history.filter(e => e.kind === "review" && e.document.interpretation_id === result.id && e.document.criterion === row.code)));
    }

    function renderComparison(result) {
      state.selected = result; resultHost.replaceChildren(el("h4", "Same evidence snapshot · engine profile comparison")); exports(resultHost, result);
      const comparison = result.document.engine_result, grid = el("div", undefined, "acmg-comparison");
      (comparison.branches || []).forEach(branch => {
        const column = el("div"); column.append(el("h4", branch.configuration.base_profile?.profile_id || branch.configuration.configuration_id || "Profile"), disclosure("Profile configuration", branch.configuration));
        if (!branch.result) column.append(tree(branch.error));
        else {
          column.append(el("p", branch.result.classification?.category || branch.result.classification?.status || "Classification unavailable"), disclosure("Classification audit", branch.result.classification));
          for (const row of rows(branch.result)) column.append(disclosure(`${row.code} · ${row.display_status} · ${show(row.candidate_strength)} → ${show(row.effective_strength)}`, row.raw));
        } grid.append(column);
      }); resultHost.append(grid, disclosure("Engine-reported rule differences / provenance (no local modification inference)", {comparisons: comparison.comparisons, not_comparable: comparison.not_comparable}, true));
    }

    function renderHistory() {
      historyBox.hidden = !state.history.some(e => ["interpretation", "comparison"].includes(e.kind));
      historyHost.replaceChildren(el("h4", "Interpretation history / rerun comparison"));
      state.history.filter(e => ["interpretation", "comparison"].includes(e.kind)).forEach(result => {
        const button = el("button", `${result.created_at} · ${result.kind} · ${result.id.slice(0, 12)}`);
        button.onclick = () => result.kind === "comparison" ? renderComparison(result) : renderResult(result); historyHost.append(button);
        if (result.kind === "interpretation" && state.selected?.kind === "interpretation" && result.id !== state.selected.id) {
          const diff = el("button", "Compare with selected result"); diff.onclick = () => busy(async () => {
            const data = await api(`/results/${state.selected.id}/diff/${result.id}`); resultHost.append(disclosure("Before / after: evidence, thresholds, effective contributions and classification", data, true));
          }); historyHost.append(diff);
        }
      });
    }
    renderHistory();
    if (state.selected) state.selected.kind === "comparison" ? renderComparison(state.selected) : renderResult(state.selected);
  }

  await refreshContext().catch(error => { contextStatus.textContent = error.message; });
  await busy(async () => {
    const discovery = await api("/discovery"); state.capability = discovery.capabilities; state.criteria = discovery.criteria.criteria;
    state.inheritanceModes = discovery.schemas.InheritanceMode?.enum || [];
    annotationContext(state.contextChoice?.id || "");
    const saved = localStorage.getItem(storageKey);
    if (saved) { const response = await api(`/workspaces/${saved}`); state.workspace = response.workspace; await load(); }
    await refreshSaved();
  });
  state.loadingDiscovery = false;
  prepare.disabled = !state.contextChoice;
}
