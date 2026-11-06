import {deletePanel, getPanels, savePanel} from "../api.js?v=20261030-1";

const FIELD_IDS = {
  panel_name: "panel-name",
  panel_technology: "panel-technology",
  gene_list: "panel-gene-list",
  transcripts_list: "panel-transcripts-list",
  target_list: "panel-target-list",
  target_bed: "panel-target-bed",
  cnv_calls_model: "panel-cnv-calls-model",
  cnv_ploidy_model: "panel-cnv-ploidy-model",
  cnv_target_list: "panel-cnv-target-list",
  cnv_exons_info: "panel-cnv-exons-info",
};

const state = {
  panels: [],
  selected: "",
  originalName: "",
  dirty: false,
};

const byId = id => document.getElementById(id);

export function initPanels() {
  byId("panels-new").addEventListener("click", createDraft);
  byId("panels-select").addEventListener("change", changeSelection);
  byId("panels-delete").addEventListener("click", removePanel);
  byId("panels-cancel").addEventListener("click", cancelDraft);
  byId("panels-editor").addEventListener("submit", saveDraft);
  byId("panels-editor").addEventListener("input", markDirty);

  window.addEventListener("helper:project-loaded", () => loadPanels().catch(showError));
  window.addEventListener("beforeunload", event => {
    if (!state.dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });
  document.addEventListener("click", event => {
    const navigation = event.target.closest(".nav-item");
    if (!navigation || navigation.dataset.section === "panels" || !state.dirty) return;
    if (!window.confirm("Discard unsaved panel design changes?")) {
      event.preventDefault();
      event.stopImmediatePropagation();
    } else {
      clearEditor();
    }
  }, true);
}

async function loadPanels(selectedName = "") {
  const response = await getPanels();
  state.panels = response.panels || [];
  renderList();
  if (selectedName) {
    const selected = state.panels.find(panel => panel.name === selectedName);
    if (selected) selectPanel(selected);
    else clearEditor();
  }
}

function renderList() {
  const select = byId("panels-select");
  select.replaceChildren(new Option("Select a design...", ""));
  byId("panels-count").textContent = `${state.panels.length} design${state.panels.length === 1 ? "" : "s"}`;
  for (const panel of state.panels) {
    const technology = panel.design.panel_technology || "Technology not set";
    const status = panel.errors?.length ? " · Needs attention" : "";
    select.add(new Option(`${panel.name} · ${technology}${status}`, panel.name));
  }
  select.value = state.selected;
}

function changeSelection(event) {
  const name = event.target.value;
  if (!name) {
    if (state.dirty && !window.confirm("Discard unsaved panel design changes?")) {
      event.target.value = state.selected;
      return;
    }
    clearEditor();
    return;
  }
  if (state.dirty && !window.confirm("Discard unsaved panel design changes?")) {
    event.target.value = state.selected;
    return;
  }
  const panel = state.panels.find(item => item.name === name);
  if (panel) selectPanel(panel);
}

function selectPanel(panel) {
  state.selected = panel.name;
  state.originalName = panel.name;
  state.dirty = false;
  for (const [field, id] of Object.entries(FIELD_IDS)) {
    byId(id).value = panel.design[field] || (field === "panel_name" ? panel.name : "");
  }
  byId("panels-editor-empty").hidden = true;
  byId("panels-editor").hidden = false;
  byId("panels-delete").hidden = false;
  byId("panels-editor-title").textContent = panel.name;
  const status = byId("panels-editor-status");
  status.textContent = panel.errors?.length ? panel.errors.join("; ") : "Saved design";
  status.classList.toggle("invalid", Boolean(panel.errors?.length));
  byId("panels-feedback").textContent = "";
  renderList();
}

function createDraft() {
  if (state.dirty && !window.confirm("Discard unsaved panel design changes?")) return;
  state.selected = "";
  state.originalName = "";
  state.dirty = false;
  for (const id of Object.values(FIELD_IDS)) byId(id).value = "";
  byId("panels-editor-empty").hidden = true;
  byId("panels-editor").hidden = false;
  byId("panels-delete").hidden = true;
  byId("panels-editor-title").textContent = "New panel design";
  byId("panels-editor-status").textContent = "New design";
  byId("panels-editor-status").classList.remove("invalid");
  byId("panels-feedback").textContent = "";
  byId("panel-name").focus();
  renderList();
}

function markDirty() {
  state.dirty = true;
  byId("panels-editor-status").textContent = "Unsaved changes";
  byId("panels-editor-status").classList.remove("invalid");
}

async function saveDraft(event) {
  event.preventDefault();
  if (!byId("panels-editor").reportValidity()) return;
  const design = Object.fromEntries(
    Object.entries(FIELD_IDS).map(([field, id]) => [field, byId(id).value.trim()])
  );
  const name = design.panel_name;
  setFeedback("Saving panel design...");
  try {
    await savePanel(name, design, state.originalName);
    const previousName = state.originalName;
    state.dirty = false;
    await loadPanels(name);
    publishPanelChanges({previousName, name});
    setFeedback(`Saved "${name}".`);
  } catch (error) {
    showError(error);
  }
}

async function removePanel() {
  if (!state.originalName) return;
  const name = state.originalName;
  if (!window.confirm(`Delete "${name}" from the saved panel designs?`)) return;
  setFeedback("Deleting panel design...");
  try {
    await deletePanel(name);
    state.dirty = false;
    clearEditor();
    await loadPanels();
    publishPanelChanges({deletedName: name});
    setFeedback(`Deleted "${name}".`);
  } catch (error) {
    showError(error);
  }
}

function cancelDraft() {
  if (state.dirty && !window.confirm("Discard unsaved panel design changes?")) return;
  const panel = state.panels.find(item => item.name === state.originalName);
  if (panel) selectPanel(panel);
  else clearEditor();
}

function clearEditor() {
  state.selected = "";
  state.originalName = "";
  state.dirty = false;
  byId("panels-editor").hidden = true;
  byId("panels-editor-empty").hidden = false;
  renderList();
}

function setFeedback(message, isError = false) {
  const feedback = byId("panels-feedback");
  feedback.textContent = message;
  feedback.classList.toggle("error", isError);
}

function showError(error) {
  setFeedback(error.message, true);
}

function publishPanelChanges(change) {
  const designs = state.panels
    .filter(panel => !panel.errors?.length)
    .map(panel => panel.name);
  window.dispatchEvent(new CustomEvent("helper:panels-updated", {
    detail: {...change, designs},
  }));
}
