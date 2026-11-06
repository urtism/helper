import {getDataSources, getDataSource, checkDataSource, updateClinVar, postponeClinVar} from "../api.js?v=20261102-2";

const statusLabels = {
  installed: "Installato", missing: "Non installato", error: "Errore",
  not_configured: "Non configurato", configured: "Configurato",
};
const phases = {
  CHECKING: "Verifica dei file approvati", DOWNLOADING: "Download",
  VALIDATING_DOWNLOAD: "Verifica checksum e archivi", BUILDING: "Costruzione SQLite",
  VALIDATING_DATABASE: "Validazione database", PUBLISHING: "Attivazione CURRENT",
  CLEANING: "Pulizia", COMPLETED: "Aggiornamento completato", FAILED: "Aggiornamento fallito",
};

function display(value) {
  return value === null || value === undefined || value === "" ? "Sconosciuto" : String(value);
}

function date(value) {
  if (!value) return "Sconosciuto";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
}

export function initDataSources() {
  const page = document.querySelector("#data-sources");
  const body = page.querySelector("#data-sources-body");
  const feedback = page.querySelector("#data-sources-feedback");
  const reload = page.querySelector("#data-sources-reload");
  const detail = page.querySelector("#data-sources-detail");
  let sources = [], selected = null, loaded = false, timer = null, loading = false;
  const pending = new Set();

  function showDetails(source) {
    selected = source.source_id;
    detail.hidden = false;
    page.querySelector("#data-sources-detail-title").textContent = source.name;
    const fields = page.querySelector("#data-sources-detail-fields");
    fields.replaceChildren();
    // Nested metadata is rendered as text, including provider errors and paths.
    for (const [key, value] of Object.entries(source)) {
      if (key === "name") continue;
      const term = document.createElement("dt");
      term.textContent = key;
      const description = document.createElement("dd");
      if (key === "source_url" && /^https:\/\//.test(value || "")) {
        const link = document.createElement("a");
        link.href = value;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "Sito ufficiale";
        description.appendChild(link);
      } else if (value && typeof value === "object") {
        const pre = document.createElement("pre");
        pre.textContent = JSON.stringify(value, null, 2);
        description.appendChild(pre);
      } else {
        description.textContent = display(value);
      }
      fields.append(term, description);
    }
  }

  function render() {
    body.replaceChildren();
    for (const source of sources) {
      const row = document.createElement("tr");
      const check = source.check;
      const operation = source.update || {};
      const installing = operation.status === "running";
      const running = pending.has(source.source_id) || check?.status === "running";
      const update = installing ? phases[operation.phase] || operation.phase
        : running ? "Verifica in corso…" : check?.status === "error" ? `Errore: ${check.error}`
        : source.update_available === true ? "Disponibile"
        : source.update_available === false ? "Non disponibile"
        : operation.status === "completed" ? "Aggiornamento completato" : "Sconosciuto";
      for (const value of [source.name, source.storage_type, source.version || source.snapshot_id,
        date(source.installed_at || source.last_updated), statusLabels[source.status] || source.status, update]) {
        const cell = document.createElement("td");
        cell.textContent = display(value);
        row.appendChild(cell);
      }
      const updates = row.children[5];
      const checked = document.createElement("small");
      checked.textContent = `Ultimo controllo: ${date(source.last_checked)}`;
      updates.appendChild(checked);
      if (source.source_id === "clinvar") {
        const dateLabel = document.createElement("small");
        dateLabel.textContent = source.installed_at ? "Installazione completata" : "Data di importazione, se documentata";
        row.children[3].appendChild(dateLabel);
        if (source.update_available && check?.update_id) {
          const candidate = document.createElement("small");
          candidate.textContent = `File disponibili: ${check.update_id}`;
          updates.appendChild(candidate);
        }
        if (operation.status === "failed") {
          const error = document.createElement("small");
          error.textContent = `Ultimo aggiornamento fallito: ${operation.error}`;
          updates.appendChild(error);
        }
        const backup = document.createElement("small");
        backup.textContent = `BACKUP: ${source.details?.backup?.snapshot_id || "Assente"}`;
        row.children[2].appendChild(backup);
        if (source.postpone?.silenced) {
          const reminder = document.createElement("small");
          reminder.textContent = `Avviso posticipato fino al ${date(source.postpone.remind_after)}`;
          updates.appendChild(reminder);
        }
        if (installing) {
          const progress = document.createElement("small");
          const event = operation.progress || {};
          if (event.bytes !== undefined) {
            progress.textContent = `${event.filename}: ${event.bytes.toLocaleString()} byte` +
              (event.total_bytes ? ` / ${event.total_bytes.toLocaleString()}` : "");
          } else {
            progress.textContent = Object.entries(event).filter(([key]) => key.endsWith("_rows"))
              .map(([key, value]) => `${key}: ${value.toLocaleString()}`).join(" · ");
          }
          updates.appendChild(progress);
        }
      }
      if (source.error) row.children[4].title = source.error;
      const actions = document.createElement("td");
      const inspect = document.createElement("button");
      inspect.type = "button";
      inspect.textContent = "Dettagli";
      inspect.addEventListener("click", () => showDetails(source));
      actions.appendChild(inspect);
      if (source.update_supported) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "Verifica aggiornamenti";
        button.disabled = running || installing;
        button.addEventListener("click", () => startCheck(source));
        actions.appendChild(button);
      }
      if (source.can_update) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "Aggiorna";
        button.disabled = running;
        button.addEventListener("click", () => startUpdate(source));
        actions.appendChild(button);
      }
      if (source.can_postpone) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "Posticipa";
        button.disabled = running;
        button.addEventListener("click", () => postpone(source));
        actions.appendChild(button);
      }
      row.appendChild(actions);
      body.appendChild(row);
    }
    const current = sources.find(source => source.source_id === selected);
    if (current) showDetails(current);
    const clinvar = sources.find(source => source.source_id === "clinvar");
    const notice = page.querySelector("#data-sources-notice");
    notice.hidden = !clinvar?.notification || clinvar.update?.status === "running";
    notice.textContent = "È disponibile un nuovo snapshot potenziale ClinVar. Puoi aggiornarlo oppure posticipare l’avviso.";
  }

  function schedulePoll() {
    clearTimeout(timer);
    if (page.classList.contains("active")) {
      const busy = sources.some(source => source.check?.status === "running" || source.update?.status === "running");
      timer = setTimeout(poll, busy ? 1000 : 60000);
    }
  }

  async function poll() {
    try {
      const current = await getDataSource("clinvar");
      sources = sources.map(source => source.source_id === current.source_id ? current : source);
      render();
      schedulePoll();
    } catch (error) {
      feedback.textContent = `${error.message}. Usa “Rileggi stato locale” per riprovare.`;
    }
  }

  async function load() {
    if (loading) return;
    loading = true;
    reload.disabled = true;
    feedback.textContent = "Lettura metadati locali…";
    try {
      const result = await getDataSources();
      sources = result.sources;
      loaded = true;
      render();
      feedback.textContent = `${sources.length} sorgenti. Accesso amministrativo locale.`;
      schedulePoll();
    } catch (error) {
      feedback.textContent = error.message;
    } finally {
      loading = false;
      reload.disabled = false;
    }
  }

  async function startCheck(source) {
    pending.add(source.source_id);
    render();
    try {
      const check = await checkDataSource(source.source_id);
      source.check = check;
      await poll();
    } catch (error) {
      feedback.textContent = error.message;
    } finally {
      pending.delete(source.source_id);
      render();
    }
  }

  async function startUpdate(source) {
    pending.add(source.source_id);
    render();
    try {
      const current = await getDataSource(source.source_id);
      if (!current.can_update) throw new Error("La selezione non è più valida. Rileggi lo stato ed esegui una nuova verifica.");
      const files = Object.entries(current.check.files).map(([name, value]) => `${name}: MD5 ${value.remote_md5}`).join("\n");
      const confirmation = `Aggiornare ClinVar?\n\nCURRENT: ${current.snapshot_id}\n` +
        `Ultimo controllo: ${date(current.last_checked)}\n\nFile disponibili:\n${files}\n\n` +
        "Il precedente CURRENT diventerà BACKUP e il backup più vecchio sarà rimosso rispettando i reader attivi. " +
        "Il nuovo snapshot può modificare la prioritizzazione.\n\nConferma per avviare download e installazione.";
      if (!window.confirm(confirmation)) return;
      await updateClinVar({snapshot_id: current.snapshot_id, update_id: current.check.update_id, confirmed: true});
      await poll();
    } catch (error) {
      feedback.textContent = error.message;
    } finally {
      pending.delete(source.source_id);
      render();
    }
  }

  async function postpone(source) {
    pending.add(source.source_id);
    render();
    try {
      await postponeClinVar({snapshot_id: source.snapshot_id, update_id: source.check.update_id});
      await poll();
    } catch (error) {
      feedback.textContent = error.message;
    } finally {
      pending.delete(source.source_id);
      render();
    }
  }

  reload.addEventListener("click", load);
  window.addEventListener("helper:section-changed", event => {
    if (event.detail === "data-sources") {
      if (!loaded) load();
      else poll();
    } else {
      clearTimeout(timer);
    }
  });
  if (page.classList.contains("active")) load();
}
