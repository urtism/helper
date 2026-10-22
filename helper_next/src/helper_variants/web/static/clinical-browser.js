const params = new URLSearchParams(window.location.search);
const statusNode = document.querySelector("#clinical-status");
const regionNode = document.querySelector("#clinical-region");

function integerParameter(name, fallback) {
  const parsed = Number(params.get(name));
  return Number.isFinite(parsed) ? Math.trunc(parsed) : fallback;
}

function showError(error) {
  statusNode.hidden = false;
  statusNode.className = "clinical-status error";
  statusNode.textContent = `Could not load the clinical view: ${error?.message || error}`;
}

function assemblyConfiguration(build) {
  const grch37 = /(?:37|hg19)/i.test(build);
  const name = grch37 ? "hg19" : "GRCh38";
  const fasta = grch37
    ? "https://jbrowse.org/genomes/hg19/fasta/hg19.fa.gz"
    : "https://jbrowse.org/genomes/GRCh38/fasta/hg38.prefix.fa.gz";
  const aliases = grch37
    ? "https://s3.amazonaws.com/jbrowse.org/genomes/hg19/hg19_aliases.txt"
    : "https://s3.amazonaws.com/jbrowse.org/genomes/GRCh38/hg38_aliases.txt";
  return {
    name,
    aliases: grch37 ? ["GRCh37"] : ["hg38"],
    sequence: {
      type: "ReferenceSequenceTrack",
      trackId: `${name}-reference-sequence`,
      adapter: {
        type: "BgzipFastaAdapter",
        fastaLocation: {uri: fasta, locationType: "UriLocation"},
        faiLocation: {uri: `${fasta}.fai`, locationType: "UriLocation"},
        gziLocation: {uri: `${fasta}.gzi`, locationType: "UriLocation"},
      },
    },
    refNameAliases: {
      adapter: {
        type: "RefNameAliasAdapter",
        location: {uri: aliases, locationType: "UriLocation"},
      },
    },
  };
}

function clinvarTrack(assemblyName, build) {
  const directory = /(?:37|hg19)/i.test(build) ? "vcf_GRCh37" : "vcf_GRCh38";
  const uri = `https://ftp.ncbi.nlm.nih.gov/pub/clinvar/${directory}/clinvar.vcf.gz`;
  const clinicalColor = [
    "jexl:",
    "get(feature,'INFO.CLNSIG')[0]=='Pathogenic' || ",
    "get(feature,'INFO.CLNSIG')[0]=='Pathogenic/Likely_pathogenic' ? '#b42318' : ",
    "get(feature,'INFO.CLNSIG')[0]=='Likely_pathogenic' ? '#d84a3a' : ",
    "get(feature,'INFO.CLNSIG')[0]=='Uncertain_significance' ? '#d6a400' : ",
    "get(feature,'INFO.CLNSIG')[0]=='Conflicting_classifications_of_pathogenicity' ? '#d56a00' : ",
    "get(feature,'INFO.CLNSIG')[0]=='Benign' || ",
    "get(feature,'INFO.CLNSIG')[0]=='Benign/Likely_benign' ? '#238636' : ",
    "get(feature,'INFO.CLNSIG')[0]=='Likely_benign' ? '#45a657' : '#718096'",
  ].join("");
  return {
    type: "VariantTrack",
    trackId: "clinvar-clinical-significance",
    name: "ClinVar variants · colored by clinical significance",
    assemblyNames: [assemblyName],
    category: ["Clinical"],
    adapter: {
      type: "VcfTabixAdapter",
      vcfGzLocation: {uri, locationType: "UriLocation"},
      index: {
        indexType: "TBI",
        location: {uri: `${uri}.tbi`, locationType: "UriLocation"},
      },
    },
    displays: [{
      type: "LinearVariantDisplay",
      displayId: "clinvar-clinical-significance-LinearVariantDisplay",
      height: 330,
      renderer: {
        type: "CanvasFeatureRenderer",
        color1: clinicalColor,
        outline: "#ffffff",
      },
    }],
  };
}

function initializeClinicalBrowser() {
  const library = window.JBrowseReactLinearGenomeView;
  if (!library) throw new Error("JBrowse library did not load. Check the network connection.");
  const build = params.get("build") || "GRCh38";
  const chromosome = params.get("chr") || "chr1";
  const start = Math.max(1, integerParameter("start", 1));
  const end = Math.max(start + 1, integerParameter("end", start + 50000));
  const position = Math.min(end, Math.max(start, integerParameter("position", start)));
  const length = Math.max(1, integerParameter("length", 1));
  const allele = params.get("allele") || "selected variant";
  const assembly = assemblyConfiguration(build);
  const track = clinvarTrack(assembly.name, build);
  const location = `${chromosome}:${start}..${end}`;
  const highlight = `${chromosome}:${position}..${position + length - 1}`;
  regionNode.textContent = `${build} · ${location} · ${allele}`;

  const viewState = library.createViewState({
    assembly,
    tracks: [track],
    highlight: [highlight],
    disableAddTracks: true,
    defaultSession: {
      name: "ClinVar regional review",
      margin: 0,
      view: {
        id: "clinicalLinearGenomeView",
        type: "LinearGenomeView",
        init: {
          assembly: assembly.name,
          loc: location,
          tracks: [assembly.sequence.trackId, track.trackId],
        },
      },
    },
  });
  const root = library.createRoot(document.querySelector("#jbrowse-clinical-view"));
  root.render(library.React.createElement(library.JBrowseLinearGenomeView, {viewState}));
  statusNode.hidden = true;
}

window.addEventListener("error", event => showError(event.error || event.message));
window.addEventListener("unhandledrejection", event => showError(event.reason));

try {
  initializeClinicalBrowser();
} catch (error) {
  showError(error);
}
