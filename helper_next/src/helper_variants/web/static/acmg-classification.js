// Manual worksheet: scoring selected assertions never runs molecular analysis.
const el = (tag, text, className = "") => {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  item.className = className;
  return item;
};
const weights = {SUPPORTING: 1, MODERATE: 2, STRONG: 4, VERY_STRONG: 8};
const strengths = {SUPPORTING: "Supporting", MODERATE: "Moderate", STRONG: "Strong", VERY_STRONG: "Very Strong"};
const modes = {AUTOSOMAL_DOMINANT: "Dominante (AD)", AUTOSOMAL_RECESSIVE: "Recessiva (AR)",
  X_LINKED: "Legata all'X", Y_LINKED: "Legata all'Y", MITOCHONDRIAL: "Mitocondriale"};

// Informative subdivision only; the clinical class and persisted code stay VUS.
export function vusSubcategory(result) {
  if (result.classification !== "VUS" || result.requires_review || !result.criteria?.length
      || !Number.isInteger(result.total_points) || result.total_points < 0 || result.total_points > 5) return null;
  return result.total_points >= 4 ? "high" : result.total_points >= 2 ? "mid" : "low";
}

export function openClassification(host, workspace, gene, association, summaries = []) {
  const detail = workspace.detail;
  const contexts = host.classificationContexts(detail, gene, association);
  const layer = host.shadowRoot.querySelector("#dialog-layer");
  const opener = host.shadowRoot.activeElement;
  const backdrop = el("div", undefined, "dialog-backdrop");
  const dialog = el("section", undefined, "source-registry-dialog pvs1-dialog classification-dialog");
  dialog.id = "acmg-classification";
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  dialog.setAttribute("aria-labelledby", "classification-title");
  const heading = el("div", undefined, "dialog-heading");
  const title = el("h4", "Classificazione ACMG"); title.id = "classification-title";
  const close = el("button", "×", "dialog-close"); close.setAttribute("aria-label", "Chiudi classificazione");
  heading.append(title, close);
  const identity = el("div", undefined, "detail-identity-row pvs1-identity");
  identity.append(el("strong", gene.symbol), el("span", association.disease || association.disease_id),
    el("small", `${detail.chromosome}:${detail.position} ${detail.reference}>${detail.alternate}`));
  const controls = el("div", undefined, "classification-controls");
  const transcriptLabel = el("label", "Trascritto"), transcript = el("select");
  transcript.id = "classification-transcript";
  transcript.append(new Option("Seleziona trascritto", ""));
  contexts.forEach(({annotation}) => transcript.append(new Option(annotation.transcript, String(annotation.annotation_id))));
  const inheritanceLabel = el("label", "Ereditarietà"), inheritance = el("select");
  inheritance.id = "classification-inheritance";
  transcriptLabel.append(transcript); inheritanceLabel.append(inheritance);
  controls.append(transcriptLabel, inheritanceLabel);
  const body = el("div"); body.id = "classification-body";
  const tablist = el("div", undefined, "classification-tabs"); tablist.setAttribute("role", "tablist");
  tablist.setAttribute("aria-label", "Schede ACMG");
  const mainTab = el("button", "Classificazione ACMG"); mainTab.type = "button"; mainTab.id = "classification-main-tab";
  mainTab.setAttribute("role", "tab"); mainTab.setAttribute("aria-controls", body.id);
  body.className = "classification-tabpanel"; body.setAttribute("role", "tabpanel"); body.setAttribute("aria-labelledby", mainTab.id);
  const panels = el("div"); panels.append(body); tablist.append(mainTab);
  dialog.append(heading, identity, tablist, controls, panels); backdrop.append(dialog);
  layer.replaceChildren(backdrop);
  let closed = false, request, previewRequest, timer, selectedKey = "", state = null;
  const drafts = new Map();
  const criterionTabs = new Map(), criterionViews = new Map();
  let activeTab = "main";
  const activateTab = (key, focus = false) => {
    activeTab = key;
    const entries = [["main", {button: mainTab, panel: body}], ...criterionTabs];
    for (const [name, entry] of entries) {
      entry.button.setAttribute("aria-selected", String(name === key)); entry.button.tabIndex = name === key ? 0 : -1;
      entry.panel.hidden = name !== key;
    }
    const button = key === "main" ? mainTab : criterionTabs.get(key)?.button;
    if (focus) button?.focus();
    dialog.scrollTop = 0;
  };
  const closeTab = code => {
    const entry = criterionTabs.get(code); if (!entry) return;
    const focused = entry.tab.contains(host.shadowRoot.activeElement);
    entry.dispose?.(); entry.tab.remove(); entry.panel.remove(); criterionTabs.delete(code); criterionViews.delete(code);
    if (activeTab === code) activateTab("main", true);
    else if (focused) activateTab(activeTab, true);
  };
  const clearTabs = () => {
    for (const entry of criterionTabs.values()) { entry.dispose?.(); entry.tab.remove(); entry.panel.remove(); }
    criterionTabs.clear(); criterionViews.clear(); activateTab("main");
  };
  mainTab.addEventListener("click", () => activateTab("main"));
  tablist.addEventListener("keydown", event => {
    const buttons = [mainTab, ...[...criterionTabs.values()].map(item => item.button)];
    const index = buttons.indexOf(host.shadowRoot.activeElement); if (index < 0) return;
    let next;
    if (event.key === "ArrowRight") next = buttons[(index + 1) % buttons.length];
    else if (event.key === "ArrowLeft") next = buttons[(index + buttons.length - 1) % buttons.length];
    else if (event.key === "Home") next = buttons[0];
    else if (event.key === "End") next = buttons.at(-1);
    else if (event.key === "Delete" && activeTab !== "main") { event.preventDefault(); closeTab(activeTab); return; }
    if (next) { event.preventDefault(); next.click(); next.focus(); }
  });
  activateTab("main");
  const selection = () => {
    const entry = contexts.find(item => String(item.annotation.annotation_id) === transcript.value);
    if (!entry || !inheritance.value) return null;
    return {run_id: workspace.runId, sample_id: workspace.sample.sample_id, variant_id: detail.variant_id,
      annotation_id: entry.annotation.annotation_id, transcript: entry.annotation.transcript,
      context_id: entry.choice.id, interpretation_context: {...entry.choice.context, inheritance_modes: [inheritance.value]}};
  };
  const call = async (path, data, signal) => {
    const response = await fetch(`/api/acmg-calculator/classification/${path}`, {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data), signal,
    });
    const payload = await response.json();
    if (!response.ok) throw Error(typeof payload.detail === "string" ? payload.detail : "Classificazione non disponibile");
    return payload;
  };
  const updateModes = (preferred = "") => {
    const entry = contexts.find(item => String(item.annotation.annotation_id) === transcript.value);
    inheritance.replaceChildren(new Option("Seleziona ereditarietà", ""));
    const available = entry?.choice.context.inheritance_modes || [];
    const choices = available.length ? available : Object.keys(modes);
    if (entry) choices.forEach(mode => inheritance.append(new Option(modes[mode] || mode, mode)));
    if (choices.includes(preferred)) inheritance.value = preferred;
    else if (entry && available.length === 1) inheritance.value = available[0];
  };
  const capture = () => { if (selectedKey && state) drafts.set(selectedKey, state); };
  const automaticFor = payload => (detail.automaticClassifications || []).find(item =>
    item.annotation_id === payload.annotation_id && item.context_id === payload.context_id &&
    JSON.stringify(item.identity.inheritance) === JSON.stringify(payload.interpretation_context.inheritance_modes));

  const openCriterion = binding => {
    const {definition} = binding, code = definition.code;
    if (criterionTabs.has(code)) { activateTab(code, true); return; }
    const tab = el("div", undefined, "classification-tab");
    const button = el("button", code); button.type = "button"; button.id = `classification-tab-${code}`;
    button.setAttribute("role", "tab"); button.title = definition.label;
    const closeTabButton = el("button", "×", "classification-tab-close"); closeTabButton.type = "button"; closeTabButton.tabIndex = -1;
    closeTabButton.setAttribute("aria-label", `Chiudi scheda ${code}`);
    const panel = el("div", undefined, "classification-tabpanel"); panel.id = `classification-panel-${code}`;
    panel.setAttribute("role", "tabpanel"); panel.setAttribute("aria-labelledby", button.id); button.setAttribute("aria-controls", panel.id);
    const entry = {tab, button, panel}; criterionTabs.set(code, entry);
    tab.append(button, closeTabButton); tablist.append(tab); panels.append(panel);
    button.addEventListener("click", () => activateTab(code)); closeTabButton.addEventListener("click", () => closeTab(code));
    const sheet = el("section", undefined, "classification-criterion-sheet");
    sheet.append(el("h5", `${code} · ${definition.label}`));
    const fields = el("div", undefined, "classification-criterion-fields");
    const activeLabel = el("div", undefined, "classification-criterion-sheet-activation"), activeSwitch = el("label", undefined, "classification-criterion-switch");
    const active = el("input"); active.type = "checkbox"; active.setAttribute("role", "switch");
    active.setAttribute("aria-label", `Attiva ${code} nella scheda`); active.dataset.criterionSheetSwitch = code;
    const activeTrack = el("span"); activeTrack.setAttribute("aria-hidden", "true"); activeSwitch.append(active, activeTrack); activeLabel.append(el("span", "Criterio attivo"), activeSwitch);
    const strengthLabel = el("label", "Strength in classificazione"), strength = el("select"); strength.setAttribute("aria-label", `Strength ${code} nella scheda`);
    Object.entries(code === "BA1" ? {STAND_ALONE: "Stand alone"} : strengths).forEach(([value, label]) => strength.append(new Option(label, value)));
    strengthLabel.append(strength); const points = el("strong", undefined, "classification-criterion-sheet-points");
    fields.append(activeLabel, strengthLabel, points); sheet.append(fields);
    const metadata = new Map();
    for (const [key, title] of [["source", "Fonte"], ["note", "Nota"]]) {
      const label = el("label", title), input = el(key === "note" ? "textarea" : "input"); input.maxLength = 1000;
      input.setAttribute("aria-label", `${title} ${code} nella scheda`); label.append(input); sheet.append(label); metadata.set(key, input);
      input.addEventListener("input", () => binding.setField(key, input.value));
    }
    active.addEventListener("change", () => binding.setActive(active.checked));
    strength.addEventListener("change", () => binding.setStrength(strength.value));
    const update = () => {
      const row = binding.value(), enabled = binding.isActive();
      active.checked = enabled; active.setAttribute("aria-checked", String(enabled)); strength.value = row.strength; strength.disabled = !enabled;
      points.textContent = !enabled ? "Non attivo" : code === "BA1" ? "Criterio autonomo" : `${code.startsWith("P") ? "+" : "−"}${weights[row.strength]} punti`;
      metadata.forEach((input, key) => { if (input.value !== (row[key] || "")) input.value = row[key] || ""; input.disabled = !enabled; });
    };
    criterionViews.set(code, update); update(); panel.append(sheet);
    if (code === "PVS1") {
      sheet.append(el("p", "Usa nella classificazione trasferisce la strength del valutatore al punteggio.", "detail-note"));
      const evaluator = el("div", undefined, "classification-pvs1-evaluator"); evaluator.append(el("p", "Caricamento PVS1…", "loading")); panel.append(evaluator);
      const selected = selection();
      import("./acmg-calculator.js?v=20261112-acmg-cache-1").then(module => {
        if (closed || criterionTabs.get(code) !== entry) return;
        const annotation = detail.annotations.find(item => item.id === selected.annotation_id);
        const context = contexts.find(item => item.annotation.annotation_id === selected.annotation_id && item.choice.id === selected.context_id);
        const embeddedWorkspace = {...workspace, pvs1AnnotationId: String(selected.annotation_id), pvs1StrengthOverrides: {...workspace.pvs1StrengthOverrides},
          detail: {...detail, annotations: [annotation], interpretation_context: {annotations: [{...context.annotation,
            contexts: [{...context.choice, context: selected.interpretation_context}]}]}}};
        const controller = module.openAcmgCalculator(host, embeddedWorkspace, {container: evaluator,
          inheritance: selected.interpretation_context.inheritance_modes[0], onApply: payload => { binding.applyPvs1(payload); activateTab("main", true); }});
        entry.dispose = controller?.close;
      }).catch(error => { if (!closed && criterionTabs.get(code) === entry) evaluator.replaceChildren(el("p", error.message, "inline-error")); });
    }
    const back = el("button", "Torna alla classificazione"); back.type = "button";
    back.addEventListener("click", () => activateTab("main", true)); panel.append(back);
    activateTab(code, true);
  };

  const render = () => {
    const current = state, data = current.data;
    body.replaceChildren();
    const score = el("div", undefined, "classification-score");
    const badge = el("strong", "Calcolo…", "variant-classification-button"); badge.id = "classification-result";
    const total = el("span"); total.id = "classification-points";
    score.append(badge, total, el("small", "ACMG a punti · Tavtigian 2020"));
    const warnings = el("div", undefined, "classification-warnings"); warnings.setAttribute("role", "status");
    const status = el("p", current.dirty ? "Modifiche non salvate" : data.saved ? `Salvata · rev. ${data.saved.revision}`
      : data.automatic ? "Calcolata automaticamente sul main · non salvata" : "Non ancora salvata", "detail-note");
    status.id = "classification-save-status"; status.setAttribute("role", "status");
    if (data.needs_review) status.textContent = "⚠ Dati aggiornati: controlla i criteri e salva una nuova revisione";
    const rows = el("div", undefined, "classification-criteria");
    const inactive = current.inactiveCriteria ||= new Map();
    const pvs1 = data.pvs1;
    const automaticPvs1 = data.automatic?.assessment.criteria.find(item => item.code === "PVS1");
    const importPvs1 = el("button", automaticPvs1 ? "Usa PVS1 automatico" : "Usa PVS1 salvato"); importPvs1.id = "classification-import-pvs1";
    const updateImport = () => {
      importPvs1.disabled = automaticPvs1 ? current.criteria.some(item => item.code === "PVS1" && item.origin === "PVS1_AUTO" &&
        item.pvs1_evaluation_id === automaticPvs1.pvs1_evaluation_id && item.strength === automaticPvs1.strength)
        : !pvs1?.strength || pvs1.needs_review || current.criteria.some(item => item.code === "PVS1");
    };
    importPvs1.title = automaticPvs1 ? `PVS1 automatico · ${strengths[automaticPvs1.strength]} · main ${selection().transcript}`
      : !pvs1 ? "Nessun PVS1 salvato per questo contesto"
      : pvs1.needs_review ? "PVS1 da rivalutare: fonti aggiornate"
        : !pvs1.strength ? "PVS1 salvato senza strength applicata"
          : `PVS1 ${strengths[pvs1.strength]} · rev. ${pvs1.revision}${pvs1.manual ? " · strength manuale" : ""}`;
    const save = el("button", "Salva classificazione", "primary"); save.id = "classification-save";
    const actions = el("div", undefined, "classification-actions"); actions.append(importPvs1, save);
    const advanced = el("details", undefined, "gene-evidence-sources classification-advanced");
    advanced.append(el("summary", "Informazioni avanzate"));
    const noteLabel = el("label", "Nota della classificazione"), note = el("textarea"); note.maxLength = 1000;
    note.value = current.note; note.setAttribute("aria-label", "Nota della classificazione"); noteLabel.append(note);
    const model = el("p", "Supporting ±1 · Moderate ±2 · Strong ±4 · Very Strong ±8. Soglie: ≥10 patogena; 6–9 probabilmente patogena; 0–5 VUS; −1…−6 probabilmente benigna; ≤−7 benigna. BA1 è un criterio benigno autonomo.", "detail-note");
    const legend = el("p", "P = patogena · LP = probabilmente patogena · VUS = significato incerto · LB = probabilmente benigna · B = benigna", "detail-note");
    const vus = el("p", undefined, "detail-note"); vus.id = "classification-vus-subcategory"; vus.hidden = true;
    const source = el("a", "Tavtigian 2020"); source.href = data.source_url; source.target = "_blank"; source.rel = "noopener noreferrer";
    const pm2 = el("a", "ClinGen SVI · PM2 Supporting"); pm2.href = data.pm2_source_url; pm2.target = "_blank"; pm2.rel = "noopener noreferrer";
    const vusPolicy = el("p", "Sottolivello VUS informativo sul punteggio disponibile: low 0–1, mid 2–3, high 4–5. La classe rimane VUS; non misura la completezza della valutazione.", "detail-note");
    const vusSource = el("a", "Sottolivelli VUS · studio 2024");
    vusSource.href = "https://www.gimjournal.org/article/S1098-3600(24)00210-7/fulltext"; vusSource.target = "_blank"; vusSource.rel = "noopener noreferrer";
    advanced.append(noteLabel, legend, model, vus, vusPolicy, vusSource, source, pm2, el("small", "PP5 e BP6 esclusi. Il totale usa i criteri presenti nella scheda; PVS1 può essere proposto automaticamente sul main."));
    if (data.automatic) advanced.append(el("p", `PVS1 automatico: ${data.automatic.error || data.automatic.pvs1?.reason || "Non determinato"}`, "detail-note"));
    body.append(score, warnings, rows, actions, status, advanced);

    const dirty = () => { current.dirty = true; status.textContent = "Modifiche non salvate"; };
    note.addEventListener("input", () => { current.note = note.value; dirty(); });
    const preview = async () => {
      clearTimeout(timer); previewRequest?.abort();
      const controller = previewRequest = new AbortController();
      save.disabled = true;
      try {
        const result = await call("preview", {criteria: current.criteria, splice: data.splice}, controller.signal);
        if (closed || state !== current || controller.signal.aborted) return;
        badge.textContent = result.label; badge.dataset.classification = result.classification;
        const tier = data.needs_review || data.automatic?.assessment.requires_review ? null : vusSubcategory(result);
        vus.hidden = !tier;
        vus.textContent = tier ? `VUS (${tier}) · ${result.total_points} punti · indicatore informativo` : "";
        total.textContent = `${result.total_points > 0 ? "+" : ""}${result.total_points} punti${current.criteria.some(item => item.code === "BA1") ? " · BA1 autonomo" : ""}`;
        warnings.replaceChildren(...result.warnings.map(text => el("p", `⚠ ${text}`, "detail-note")));
        save.disabled = false;
      } catch (error) {
        if (error.name !== "AbortError" && state === current && !closed) { badge.textContent = "Calcolo non disponibile"; warnings.textContent = error.message; }
      }
    };
    const changed = () => { dirty(); previewRequest?.abort(); save.disabled = true; clearTimeout(timer); timer = setTimeout(preview, 150); };
    const rowViews = new Map(), groupCounts = new Map();
    const updateRows = () => {
      rowViews.forEach(update => update());
      criterionViews.forEach(update => update());
      for (const [direction, counter] of groupCounts) {
        const definitions = data.catalog.filter(item => item.direction === direction);
        counter.textContent = `${definitions.filter(item => current.criteria.some(row => row.code === item.code)).length}/${definitions.length} attivi`;
      }
      updateImport();
    };
    const renderRows = () => {
      rows.replaceChildren();
      const columns = new Map();
      for (const [direction, title] of [["PATHOGENIC", "Patogenicità · P"], ["BENIGN", "Benignità · B"]]) {
        const column = el("section", undefined, "classification-criteria-column"); column.dataset.direction = direction;
        const heading = el("h5"), counter = el("small"); heading.append(el("span", title), counter);
        column.append(heading); rows.append(column); columns.set(direction, column); groupCounts.set(direction, counter);
      }
      data.catalog.forEach(definition => {
        const code = definition.code;
        const activeRow = () => current.criteria.find(item => item.code === code);
        const value = () => activeRow() || inactive.get(code) || {code, strength: definition.default_strength, origin: "MANUAL", source: "", note: ""};
        const wrapper = el("div", undefined, "classification-criterion"); wrapper.dataset.criterion = code;
        const line = el("div", undefined, "classification-criterion-line");
        const name = el("button", undefined, "classification-criterion-name"); name.type = "button";
        name.setAttribute("aria-label", `Apri scheda ${code} · ${definition.label}`);
        name.append(el("strong", code), el("small", definition.label)); name.title = definition.label;
        const setActive = enabled => {
          const row = value();
          if (enabled && !activeRow()) current.criteria.push(row);
          else if (!enabled) { inactive.set(code, row); current.criteria = current.criteria.filter(item => item.code !== code); }
          updateRows(); changed();
        };
        const setStrength = selected => {
          const row = activeRow(); if (!row) return;
          row.strength = selected; row.origin = "MANUAL"; delete row.pvs1_revision; delete row.pvs1_evaluation_id;
          updateRows(); changed();
        };
        const setField = (key, text) => { const row = activeRow(); if (row) { row[key] = text; updateRows(); dirty(); } };
        name.addEventListener("click", () => openCriterion({definition, value, isActive: () => Boolean(activeRow()), setActive, setStrength, setField,
          applyPvs1: payload => {
            const previous = value(), applied = payload.result.applied_strength;
            inactive.set(code, previous); current.criteria = current.criteria.filter(item => item.code !== code);
            if (applied) {
              const row = {...previous, strength: applied, origin: "MANUAL", source: "HELPER PVS1 · strength manuale"};
              delete row.pvs1_revision; delete row.pvs1_evaluation_id;
              if (!payload.strength_override && payload.result.status === "ACTIVE" && payload.evaluation_id) {
                row.origin = "PVS1_AUTO"; row.pvs1_evaluation_id = payload.evaluation_id; row.source = "HELPER PVS1 · valutatore";
              }
              current.criteria.push(row);
            }
            updateRows(); changed();
          }}));
        const strength = el("select"); strength.setAttribute("aria-label", `Strength ${code}`);
        Object.entries(code === "BA1" ? {STAND_ALONE: "Stand alone"} : strengths).forEach(([value, label]) => strength.append(new Option(label, value)));
        const points = el("span", undefined, "classification-criterion-points");
        const switchLabel = el("label", undefined, "classification-criterion-switch");
        const toggle = el("input"); toggle.type = "checkbox"; toggle.setAttribute("role", "switch");
        toggle.dataset.criterionSwitch = code; toggle.setAttribute("aria-label", `Attiva ${code} · ${definition.label}`);
        const track = el("span"); track.setAttribute("aria-hidden", "true"); switchLabel.append(toggle, track);
        line.append(name, strength, points, switchLabel);
        const metadata = el("details"), summary = el("summary"); metadata.append(summary);
        const inputs = new Map();
        for (const [key, label] of [["source", "Fonte"], ["note", "Nota"]]) {
          const inputLabel = el("label", label), input = el("input"); input.type = "text"; input.maxLength = 1000;
          input.setAttribute("aria-label", `${label} ${code}`); inputLabel.append(input); metadata.append(inputLabel); inputs.set(key, input);
          input.addEventListener("input", () => setField(key, input.value));
        }
        rowViews.set(code, () => {
          const row = value(), active = Boolean(activeRow());
          wrapper.dataset.active = String(active);
          toggle.checked = active; toggle.setAttribute("aria-checked", String(active));
          switchLabel.title = `${code}: ${active ? "attivo" : "non attivo"}`;
          strength.value = row.strength; strength.disabled = !active;
          points.textContent = !active ? "—" : code === "BA1" ? "SA" : `${code.startsWith("P") ? "+" : "−"}${weights[row.strength]}`;
          points.title = code === "BA1" ? "Criterio benigno autonomo" : active ? "Punti applicati" : "Criterio non attivo";
          metadata.hidden = !active;
          summary.textContent = row.origin === "PVS1_SAVED" ? `Fonte e nota · PVS1 rev. ${row.pvs1_revision}`
            : row.origin === "PVS1_AUTO" ? "Fonte e nota · PVS1 automatico" : "Fonte e nota";
          inputs.forEach((input, key) => { if (input.value !== (row[key] || "")) input.value = row[key] || ""; input.disabled = !active; });
        });
        toggle.addEventListener("change", () => setActive(toggle.checked));
        strength.addEventListener("change", () => setStrength(strength.value));
        wrapper.append(line, metadata); columns.get(definition.direction).append(wrapper);
      });
      updateRows();
    };
    importPvs1.addEventListener("click", () => {
      if (automaticPvs1) {
        current.criteria = current.criteria.filter(item => item.code !== "PVS1");
        current.criteria.push(structuredClone(automaticPvs1));
      } else current.criteria.push({code: "PVS1", strength: pvs1.strength, origin: "PVS1_SAVED", pvs1_revision: pvs1.revision,
        source: `HELPER PVS1 · rev. ${pvs1.revision}${pvs1.manual ? " · strength manuale" : ""}`, note: ""});
      updateRows(); changed();
    });
    save.addEventListener("click", async () => {
      save.disabled = true; status.textContent = "Salvataggio…";
      const pendingSelection = selection();
      transcript.disabled = true; inheritance.disabled = true;
      // Editing is suspended while this explicit save is in flight.
      const fields = [...body.querySelectorAll("input,textarea,select,button"), ...tablist.querySelectorAll("button")];
      fields.forEach(item => { item.dataset.wasDisabled = String(item.disabled); item.disabled = true; });
      try {
        const payload = await call("save", {...pendingSelection, criteria: current.criteria, note: current.note,
          signature: data.signature, expected_revision: data.saved?.revision || 0});
        data.saved = payload.saved; data.needs_review = false; current.dirty = false;
        const record = payload.saved;
        const summary = {identity: record.identity, revision: record.revision, saved_at: record.saved_at,
          applied_criteria: record.assessment.criteria.map(({code, strength}) => ({code, strength})),
          classification: record.assessment.classification, points: record.assessment.total_points, requires_review: record.assessment.requires_review};
        detail.classifications = (detail.classifications || []).filter(item => !(item.identity.gene === record.identity.gene && item.identity.disease === record.identity.disease &&
          item.identity.transcript === record.identity.transcript && JSON.stringify(item.identity.inheritance) === JSON.stringify(record.identity.inheritance)));
        detail.classifications.push(summary); delete detail.classificationsError;
        if (workspace.detail === detail) {
          host.updateTableClassifications(workspace);
          host.renderDetailSection(workspace, "ACMG");
        }
        status.textContent = `Salvata · rev. ${record.revision}`;
      } catch (error) { if (error.name !== "AbortError" && !closed) status.textContent = error.message; }
      finally {
        fields.forEach(item => { item.disabled = item.dataset.wasDisabled === "true"; delete item.dataset.wasDisabled; });
        transcript.disabled = false; inheritance.disabled = false;
        save.disabled = false;
      }
    });
    renderRows(); preview();
  };

  const load = async () => {
    clearTabs();
    capture(); clearTimeout(timer); previewRequest?.abort(); request?.abort(); state = null;
    const payload = selection(); selectedKey = payload ? JSON.stringify([payload.annotation_id, inheritance.value]) : "";
    body.replaceChildren(el("p", payload ? "Caricamento classificazione…" : "Seleziona trascritto ed ereditarietà.", "empty"));
    if (!payload) return;
    const controller = request = new AbortController();
    try {
      const data = await call("load", payload, controller.signal);
      if (closed || controller.signal.aborted) return;
      data.automatic = automaticFor(payload);
      const draft = drafts.get(selectedKey);
      state = {data, criteria: structuredClone(draft?.criteria || data.saved?.assessment.criteria || data.automatic?.assessment.criteria || []),
        inactiveCriteria: draft?.inactiveCriteria || new Map(), note: draft?.note ?? data.saved?.note ?? "", dirty: draft?.dirty || false};
      render();
    } catch (error) {
      if (error.name !== "AbortError" && !closed) body.replaceChildren(el("p", error.message, "inline-error"));
    }
  };
  const closeDialog = () => {
    closed = true; clearTimeout(timer); request?.abort(); previewRequest?.abort();
    clearTabs();
    document.removeEventListener("keydown", onKeydown); backdrop.remove();
    if (opener?.isConnected) opener.focus();
    else [...host.shadowRoot.querySelectorAll(".variant-classification-button[data-disease]")].find(item => item.dataset.disease === association.disease_id)?.focus();
  };
  const onKeydown = event => {
    if (event.key === "Escape") { event.preventDefault(); closeDialog(); }
    if (event.key === "Tab") {
      const items = [...dialog.querySelectorAll("button,select,input,textarea,summary,a[href]")].filter(item => !item.disabled && item.getClientRects().length);
      const first = items[0], last = items[items.length - 1], active = host.shadowRoot.activeElement;
      if (event.shiftKey && active === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && active === last) { event.preventDefault(); first.focus(); }
    }
  };
  close.addEventListener("click", closeDialog);
  backdrop.addEventListener("click", event => { if (event.target === backdrop) closeDialog(); });
  transcript.addEventListener("change", () => { updateModes(); load(); }); inheritance.addEventListener("change", load);
  document.addEventListener("keydown", onKeydown);
  const onlySaved = summaries.length === 1 ? summaries[0] : null;
  const prior = contexts.find(item => item.annotation.transcript === onlySaved?.identity.transcript);
  const main = detail.classificationMains?.find(item => item.gene.toUpperCase() === gene.symbol.toUpperCase());
  const mainContext = contexts.find(item => item.annotation.annotation_id === main?.annotation_id);
  if (mainContext || prior || contexts.length === 1) transcript.value = String((mainContext || prior || contexts[0]).annotation.annotation_id);
  updateModes(onlySaved?.identity.transcript === (mainContext || prior)?.annotation.transcript ? onlySaved?.identity.inheritance?.[0] : ""); close.focus(); load();
}
