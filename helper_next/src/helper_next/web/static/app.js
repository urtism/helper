import {initAnalysisHistory} from "./sections/analysis_history.js?v=20260922-1";
import {getProject} from "./api.js?v=20260910-2";
import {initAnalysis} from "./sections/analysis.js?v=20260922-1";
import {initPipeline} from "./sections/pipeline.js?v=20260921-1";
import {initSampleSheet} from "./sections/samplesheet.js?v=20260909-2";
import {initTools} from "./sections/tools.js?v=20260915-2";

const sectionTitles = {
  samplesheet: "Compile Sample Sheet",
  pipeline: "Add or Edit Pipeline",
  tools: "Tools Settings",
  panels: "Add or Edit Gene Panel Info",
  analysis: "Start Analysis",
  "analysis-history": "Analysis History",
};

const sidebarStorageKey = "helper-next.sidebar-collapsed";
const appShell = document.querySelector(".app-shell");
const sidebar = document.querySelector("#primary-sidebar");
const sidebarToggle = document.querySelector("#sidebar-toggle");

function setSidebarCollapsed(collapsed) {
  appShell.classList.toggle("sidebar-collapsed", collapsed);
  sidebar.setAttribute("aria-hidden", String(collapsed));
  sidebarToggle.setAttribute("aria-expanded", String(!collapsed));
  sidebarToggle.setAttribute("aria-label", collapsed ? "Show navigation" : "Hide navigation");
  sidebarToggle.title = collapsed ? "Show navigation" : "Hide navigation";
  window.localStorage.setItem(sidebarStorageKey, String(collapsed));
}

setSidebarCollapsed(window.localStorage.getItem(sidebarStorageKey) === "true");
sidebarToggle.addEventListener("click", () => {
  setSidebarCollapsed(!appShell.classList.contains("sidebar-collapsed"));
});

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
initAnalysisHistory();
initPipeline();
initTools();

loadProject().catch((error) => {
  document.querySelector("#project-root").textContent = error.message;
});

async function loadProject() {
  const root = document.querySelector("#project-root");
  const scripts = document.querySelector("#scripts");

  root.textContent = "Loading...";
  scripts.replaceChildren();

  const data = await getProject();

  root.textContent = data.root;
  window.dispatchEvent(new CustomEvent("helper:project-loaded", {detail: data}));
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
