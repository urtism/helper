import {getProject} from "./api.js?v=20260626-2";
import {initAnalysis} from "./sections/analysis.js?v=20260629-8";
import {initSampleSheet} from "./sections/samplesheet.js?v=20260518-6";

const sectionTitles = {
  samplesheet: "Compile Sample Sheet",
  pipeline: "Add or Edit Pipeline",
  tools: "Tools Settings",
  panels: "Add or Edit Gene Panel Info",
  analysis: "Start Analysis",
};

function showSection(sectionId) {
  document.querySelectorAll(".module").forEach((section) => {
    section.classList.toggle("active", section.id === sectionId);
  });

  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.section === sectionId);
  });

  document.querySelector("#section-title").textContent = sectionTitles[sectionId];
}

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", () => showSection(button.dataset.section));
});

initSampleSheet();
initAnalysis();

document.querySelector("#refresh-project").addEventListener("click", loadProject);
loadProject().catch((error) => {
  document.querySelector("#project-root").textContent = error.message;
});

async function loadProject() {
  const root = document.querySelector("#project-root");
  const pipelines = document.querySelector("#pipelines");
  const toolConfigs = document.querySelector("#tool-configs");
  const scripts = document.querySelector("#scripts");

  root.textContent = "Loading...";
  pipelines.replaceChildren();
  toolConfigs.replaceChildren();
  scripts.replaceChildren();

  const data = await getProject();

  root.textContent = data.root;
  fillList(pipelines, data.pipelines);
  fillList(toolConfigs, data.tool_configs);
  fillList(scripts, data.scripts);
}

function fillList(node, items) {
  if (!items.length) {
    const empty = document.createElement("li");
    empty.textContent = "No files found";
    node.appendChild(empty);
    return;
  }

  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = item;
    node.appendChild(li);
  }
}
