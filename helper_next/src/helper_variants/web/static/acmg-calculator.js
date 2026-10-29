// New PVS1-only Calculator. No legacy engine/workbench API is called here.
const element = (tag, text, className = "") => {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
};

export function renderTranscriptMolecularImpact(host, analysis) {
  const section = element("section", undefined, "transcript-molecular-impact");
  section.id = "transcript-molecular-impact";
  section.append(element("h4", "Transcript Molecular Impact"));
  section.append(element("p", `Gene ${analysis.gene || "—"} · ${analysis.assembly || "—"} · Ensembl ${analysis.release || "non documentata"} · Catalogo ${analysis.catalog_complete ? "completo" : "incompleto"}`, "detail-note"));
  section.append(element("p", "Analisi molecolare indipendente dalla decisione PVS1. Le percentuali descrivono la sequenza reference; NMD e prodotti proteici sono predetti.", "detail-note"));
  (analysis.warnings || []).forEach(warning => section.append(element("p", warning, "detail-note")));
  const viewport = element("div", undefined, "molecular-impact-viewport");
  const table = element("table");
  const head = element("thead"), headings = element("tr");
  ["Transcript", "Annotation", "CDS nt", "Position", "CDS affected %", "Protein impact %", "NMD"].forEach(label => headings.append(element("th", label)));
  head.append(headings);
  const body = element("tbody");
  const percent = value => value == null ? "—" : `${value.toFixed(2)}%`;
  (analysis.transcripts || []).forEach((row, index) => {
    const tr = element("tr");
    tr.dataset.transcript = row.transcript;
    tr.dataset.status = row.status;
    if (row.selected) tr.setAttribute("aria-current", "true");
    const transcriptCell = element("td");
    const expand = element("button", `${row.transcript}${row.selected ? " · selezionato" : ""}`);
    expand.type = "button";
    expand.setAttribute("aria-expanded", "false");
    expand.setAttribute("aria-controls", `molecular-impact-detail-${index}`);
    transcriptCell.append(expand);
    const flags = [row.mane === "SELECT" ? "MANE Select" : row.mane === "PLUS_CLINICAL" ? "MANE Plus Clinical" : "", row.canonical ? "Canonical" : "", row.appris ? `APPRIS ${row.appris}` : ""].filter(Boolean);
    if (flags.length) transcriptCell.append(element("small", flags.join(" · ")));
    const affected = row.reference_cds_untranslated_percent != null ? `${percent(row.reference_cds_untranslated_percent)} non tradotta`
      : row.reference_cds_disrupted_percent != null ? `${percent(row.reference_cds_disrupted_percent)} frame alterato` : "—";
    tr.append(transcriptCell, element("td", `${row.consequence || "—"} · ${row.status}${row.conditional ? " · condizionale" : ""}`),
      element("td", row.cds_length_nt ?? "—"), element("td", row.cds_position == null ? "—" : `c.${row.cds_position} · codone ${row.first_affected_reference_codon}`),
      element("td", affected), element("td", `${percent(row.protein_impact_percent)}${row.protein_impact_percent == null ? "" : " reference persa/alterata"}`),
      element("td", row.nmd_predicted == null ? "Non determinabile" : row.nmd_predicted ? "Previsto" : "Non previsto"));
    const details = element("tr"), detailCell = element("td");
    details.id = `molecular-impact-detail-${index}`;
    details.hidden = true;
    detailCell.colSpan = 7;
    details.append(detailCell);
    expand.addEventListener("click", () => {
      details.hidden = !details.hidden;
      expand.setAttribute("aria-expanded", String(!details.hidden));
      if (!details.hidden && !detailCell.childNodes.length) {
        detailCell.append(host.detailCard([
          ["Biotype / strand", `${row.biotype || "—"} / ${row.strand || "—"}`],
          ["CDS tradotta reference (stop naturale escluso)", row.translated_cds_length_nt ?? "—"],
          ["Nucleotidi eliminati / inseriti", `${row.physical_deleted_nt ?? "—"} / ${row.physical_inserted_nt ?? "—"}`],
          ["CDS fisicamente eliminata", percent(row.physical_cds_deleted_percent)],
          ["Lunghezza proteina reference / predetta", `${row.reference_protein_length ?? "—"} / ${row.predicted_protein_length ?? "—"} aa`],
          ["Primo residuo divergente", row.first_divergent_aa ?? "—"],
          ["Residui reference persi / sostituiti", `${row.reference_amino_acids_lost ?? "—"} / ${row.reference_amino_acids_replaced ?? "—"}`],
          ["Accorciamento proteico predetto", row.predicted_protein_shortening_aa == null ? "—" : `${row.predicted_protein_shortening_aa} aa`],
          ["Nuovo stop / PTC", `codone ${row.termination_codon ?? "—"} · mRNA ${row.termination_mrna_position ?? "—"} · PTC ${row.ptc_mrna_position ?? "—"}`],
          ["Estensione nella 3′ UTR", row.extends_into_utr == null ? "—" : row.extends_into_utr ? "Sì" : "No"],
          ["Distanza stop–ultima giunzione", row.nmd_distance_nt == null ? "—" : `${row.nmd_distance_nt} nt`],
        ]));
        [...(row.warnings || []), ...(row.missing_data || [])].forEach(message => detailCell.append(element("p", message, "detail-note")));
        detailCell.append(host.detailDisclosure("Formule", element("pre", JSON.stringify(row.formulas || {}, null, 2))));
        detailCell.append(host.detailDisclosure("Provenance", element("pre", JSON.stringify(row.provenance || {}, null, 2))));
        detailCell.append(host.detailDisclosure("CDS e proteina reference", element("pre", JSON.stringify(row.reference || {}, null, 2))));
        detailCell.append(host.detailDisclosure("Dati molecolari e sequenze", element("pre", JSON.stringify(row.calculation || {}, null, 2))));
      }
    });
    body.append(tr, details);
  });
  table.append(head, body);
  viewport.append(table);
  section.append(viewport);
  return section;
}

export function openAcmgCalculator(host, workspace) {
  const detail = workspace.detail;
  if (!detail || detail.loading || detail.error) return;
  const opener = host.shadowRoot.activeElement;
  const layer = host.shadowRoot.querySelector("#dialog-layer");
  const backdrop = element("div", undefined, "dialog-backdrop");
  const dialog = element("section", undefined, "source-registry-dialog");
  dialog.id = "new-acmg-calculator";
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  dialog.setAttribute("aria-labelledby", "new-acmg-calculator-title");
  const heading = element("div", undefined, "dialog-heading");
  const title = element("h4", "ACMG Calculator");
  title.id = "new-acmg-calculator-title";
  const close = element("button", "×", "dialog-close");
  close.setAttribute("aria-label", "Chiudi ACMG Calculator");
  heading.append(title, close);
  const locus = `${detail.reference_build} · ${detail.chromosome}:${detail.position} ${detail.reference}>${detail.alternate}`;
  dialog.append(heading, element("p", locus), element("p", "Criterio PVS1 · Policy STANDARD · Modello PVS1_GENERAL 1.1.0", "detail-note"));
  const controls = element("div", undefined, "detail-cards");
  const transcriptLabel = element("label", "Trascritto selezionato in HELPER ");
  const transcript = element("select");
  transcript.id = "new-acmg-transcript";
  transcript.append(new Option("Seleziona un'annotazione trascrizionale", ""));
  const annotations = detail.annotations || [];
  annotations.forEach(annotation => transcript.append(new Option(
    `${annotation.transcript || "Trascritto assente"} · ${annotation.gene || "Gene assente"} · ${annotation.consequence || ""}`,
    String(annotation.id),
  )));
  const prior = workspace.items?.find(item => String(item.variant_id) === String(detail.variant_id));
  const matches = annotations.filter(annotation => annotation.transcript === prior?.transcript);
  const saved = annotations.find(annotation => String(annotation.id) === workspace.pvs1AnnotationId);
  if (saved || matches.length === 1 || annotations.length === 1) transcript.value = String((saved || matches[0] || annotations[0]).id);
  transcriptLabel.append(transcript);
  const diseaseLabel = element("label", "Contesto gene–malattia disponibile ");
  const disease = element("select");
  disease.id = "new-acmg-context";
  diseaseLabel.append(disease);
  const evaluate = element("button", "Valuta PVS1");
  evaluate.type = "button";
  controls.append(transcriptLabel, diseaseLabel, evaluate);
  const resultHost = element("div");
  resultHost.id = "new-acmg-result";
  resultHost.setAttribute("aria-live", "polite");
  dialog.append(controls, resultHost);
  backdrop.append(dialog);
  let request, closed = false;
  const selectedAnnotation = () => annotations.find(annotation => String(annotation.id) === transcript.value);
  const contextChoices = () => (detail.interpretation_context?.annotations || []).find(
    item => item.annotation_id === selectedAnnotation()?.id && item.transcript === selectedAnnotation()?.transcript,
  )?.contexts || [];
  const updateContexts = () => {
    disease.replaceChildren(new Option("Non documentato / nessuna selezione", ""));
    const choices = contextChoices();
    choices.forEach(choice => disease.append(new Option(
      `${choice.context.disease.label || choice.context.disease.identifier} · ${choice.context.inheritance_modes?.join(", ") || "ereditarietà mancante"}`,
      choice.id,
    )));
    if (choices.length === 1) disease.value = choices[0].id;
    disease.disabled = !choices.length;
    evaluate.disabled = !selectedAnnotation()?.transcript;
  };
  const run = async () => {
    request?.abort();
    const annotation = selectedAnnotation();
    if (!annotation?.transcript) {
      resultHost.replaceChildren(element("p", "Seleziona il trascritto già annotato da HELPER. Nessun altro trascritto viene cercato."));
      return;
    }
    workspace.pvs1AnnotationId = String(annotation.id);
    const current = new AbortController();
    request = current;
    delete resultHost.dataset.status;
    resultHost.replaceChildren(element("p", "Analisi dei trascritti e valutazione PVS1…", "loading"));
    try {
      const response = await fetch("/api/acmg-calculator/pvs1", {
        method: "POST", headers: {"Content-Type": "application/json"}, signal: current.signal,
        body: JSON.stringify({run_id: workspace.runId, sample_id: workspace.sample.sample_id,
          variant_id: detail.variant_id, annotation_id: annotation.id, transcript: annotation.transcript,
          context_id: disease.value || null, policy: "STANDARD"}),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "Richiesta Calculator non valida.");
      if (closed || current !== request) return;
      const result = payload.result;
      resultHost.replaceChildren(host.detailCard([
        ["Gene", payload.input.disease_context.gene], ["Malattia", payload.input.disease_context.disease || "Non disponibile"],
        ["Ereditarietà", payload.input.disease_context.inheritance || "Non disponibile"],
        ["Trascritto", payload.input.transcript?.accession], ["Modello", `${result.ruleset_id} ${result.ruleset_version}`],
        ["Criterio", "PVS1"], ["Stato", result.status], ["Strength calcolata", result.calculated_strength || "—"],
        ["Strength applicata", result.applied_strength || "—"], ["Motivazione", result.reason],
        ["Origine dati molecolari", payload.molecular_origin],
      ]));
      if (payload.molecular_impact) resultHost.prepend(renderTranscriptMolecularImpact(host, payload.molecular_impact));
      if (contextChoices().length > 1 && !disease.value) resultHost.append(element("p", "Seleziona un contesto gene–malattia per la decisione PVS1. L'analisi molecolare dei trascritti è indipendente dal contesto.", "detail-note"));
      resultHost.dataset.status = result.status;
      for (const [label, entries] of [["Informazioni necessarie mancanti", result.missing_data], ["Warning", result.warnings]]) {
        if (!entries?.length) continue;
        resultHost.append(element("h4", label));
        const list = element("ul");
        entries.forEach(value => list.append(element("li", value)));
        resultHost.append(list);
      }
      resultHost.append(element("h4", "Requisiti PVS1"));
      const requirements = element("div");
      requirements.id = "new-acmg-requirements";
      (result.decision_trace || []).forEach(raw => {
        const requirement = JSON.parse(raw);
        const format = value => value == null ? "—" : typeof value === "string" ? value : JSON.stringify(value);
        const row = host.detailDisclosure(requirement.description, host.detailCard([
          ["Stato", requirement.status], ["Valore", format(requirement.value)],
          ["Soglia", format(requirement.threshold)], ["Fonte", requirement.source?.join("; ") || "Non disponibile"],
          ["Regola", requirement.rule], ["Motivazione", requirement.reason],
        ]), {status: requirement.status});
        row.dataset.requirementId = requirement.id;
        row.dataset.status = requirement.status;
        requirements.append(row);
      });
      resultHost.append(requirements);
    } catch (error) {
      if (closed || current !== request || error.name === "AbortError") return;
      const message = element("p", error.message, "inline-error");
      message.setAttribute("role", "alert");
      resultHost.replaceChildren(message);
    }
  };
  const closeDialog = () => {
    closed = true;
    request?.abort();
    document.removeEventListener("keydown", onKeydown);
    layer.replaceChildren();
    opener?.focus();
  };
  const onKeydown = event => {
    if (event.key === "Escape") { event.preventDefault(); closeDialog(); }
    if (event.key === "Tab") {
      const focusable = [...dialog.querySelectorAll("button,select,summary")].filter(item => !item.disabled);
      const first = focusable[0], last = focusable[focusable.length - 1], active = host.shadowRoot.activeElement;
      if (event.shiftKey && active === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && active === last) { event.preventDefault(); first.focus(); }
    }
  };
  close.addEventListener("click", closeDialog);
  backdrop.addEventListener("click", event => { if (event.target === backdrop) closeDialog(); });
  evaluate.addEventListener("click", run);
  transcript.addEventListener("change", () => { updateContexts(); run(); });
  disease.addEventListener("change", run);
  document.addEventListener("keydown", onKeydown);
  layer.replaceChildren(backdrop);
  updateContexts();
  close.focus();
  run();
}
