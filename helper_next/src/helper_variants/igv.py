"""Resolve run-owned files that may be exposed to the embedded IGV browser."""
from pathlib import Path


class IgvResourceError(ValueError):
    """Raised when a run cannot provide an unambiguous IGV resource."""


def manifest(record, sample):
    sample_name = _sample_name(sample)
    alignment, alignment_stage = _alignment(record, sample_name)
    reference = _reference(record)
    resources = {}
    tracks = []
    warnings = []

    if alignment:
        alignment_index = _alignment_index(alignment)
        if alignment_index:
            resources.update({"alignment": alignment, "alignment-index": alignment_index})
            tracks.append({
                "id": "sample-alignment", "name": sample_name,
                "type": "alignment",
                "format": "cram" if alignment.suffix.lower() == ".cram" else "bam",
                "stage": alignment_stage,
                "resource": "alignment", "index_resource": "alignment-index",
                "category": "Sample", "description": "Coverage and aligned reads.",
                "source": "Run output", "default_visible": True,
            })
            tracks.append({
                "id": "split-read-evidence", "name": "Split-read evidence",
                "type": "alignment",
                "format": "cram" if alignment.suffix.lower() == ".cram" else "bam",
                "stage": "chimeric / supplementary",
                "resource": "alignment", "index_resource": "alignment-index",
                "category": "Sample",
                "description": "Soft clips and SA-tagged or supplementary alignments grouped together.",
                "source": "Run output", "default_visible": False, "mode": "split-reads",
            })
        else:
            warnings.append("Alignment found, but its BAI/CRAI index is missing.")
    else:
        warnings.append("No indexed alignment was found for this sample.")

    variant, variant_stage = _variant_file(record, sample_name)
    if variant:
        resources["variants"] = variant
        variant_track = {
            "id": "sample-variants", "name": f"{sample_name} variants",
            "type": "variant", "format": "vcf", "stage": variant_stage,
            "resource": "variants",
            "category": "Sample", "description": "Variants called for this sample.",
            "source": "Run output", "default_visible": True,
        }
        variant_index = _feature_index(variant)
        if variant_index:
            resources["variants-index"] = variant_index
            variant_track["index_resource"] = "variants-index"
        tracks.append(variant_track)

    targets = _target_bed(record)
    if targets:
        resources["targets"] = targets
        target_track = {
            "id": "panel-targets", "name": "Panel target regions",
            "type": "annotation", "format": "bed", "stage": "panel",
            "resource": "targets",
            "category": "Panel", "description": "Capture or analysis target intervals.",
            "source": "Panel design", "default_visible": True,
        }
        target_index = _feature_index(targets)
        if target_index:
            resources["targets-index"] = target_index
            target_track["index_resource"] = "targets-index"
        tracks.append(target_track)

    reference_config = _reference_config(record, reference, resources, warnings)
    tracks.extend(_reference_tracks(_reference_build(record)))
    return {
        "available": bool(tracks),
        "alignment_available": any(track["type"] == "alignment" for track in tracks),
        "sample_name": sample_name,
        "reference_build": _reference_build(record),
        "reference": reference_config,
        "tracks": tracks,
        "warnings": warnings,
    }, resources


def resource(record, sample, kind):
    _, resources = manifest(record, sample)
    path = resources.get(str(kind))
    if path is None:
        raise IgvResourceError("IGV resource is not available")
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise IgvResourceError("IGV resource is no longer available")
    return resolved


def _sample_name(sample):
    name = str(sample.get("display_name") or sample.get("sample_key") or "").strip()
    if not name or Path(name).name != name or name in {".", ".."}:
        raise IgvResourceError("Sample name cannot be mapped safely to an alignment")
    return name


def _alignment(record, sample_name):
    run_dir = Path(record.get("run_dir", "")).expanduser().resolve()
    candidates = (
        (run_dir / "results" / "PREPROCESSING" / f"{sample_name}.preprocessed.bam", "preprocessed"),
        (run_dir / "results" / "PREPROCESSING" / f"{sample_name}.preprocessed.cram", "preprocessed"),
        (run_dir / "results" / "ALIGNMENT" / f"{sample_name}.sort.bam", "aligned"),
        (run_dir / "results" / "ALIGNMENT" / f"{sample_name}.sort.cram", "aligned"),
    )
    for path, stage in candidates:
        if path.is_file():
            return path.resolve(), stage
    return None, ""


def _alignment_index(alignment):
    suffix = ".crai" if alignment.suffix.lower() == ".cram" else ".bai"
    candidates = (Path(str(alignment) + suffix), alignment.with_suffix(suffix))
    return next((path.resolve() for path in candidates if path.is_file()), None)


def _variant_file(record, sample_name):
    results = Path(record.get("run_dir", "")).expanduser().resolve() / "results"
    searches = (
        ("annotation", results / "ANNOTATION", (
            f"{sample_name}.annotated.vcf.gz", f"{sample_name}.annotated.vcf",
            f"{sample_name}.VEP.vcf.gz", f"{sample_name}.VEP.vcf",
        )),
        ("postprocessed", results / "POSTPROCESSING", (
            f"{sample_name}.postprocessed.vcf.gz", f"{sample_name}.postprocessed.vcf",
            f"{sample_name}.filter.vcf.gz", f"{sample_name}.filter.vcf",
        )),
        ("called", results / "VARIANTCALLING", (
            f"{sample_name}.vcf.gz", f"{sample_name}.vcf",
            f"{sample_name}.GATK.vcf.gz", f"{sample_name}.GATK.vcf",
            f"{sample_name}.Mutect.filter.vcf.gz", f"{sample_name}.Mutect.filter.vcf",
        )),
    )
    for stage, directory, names in searches:
        for name in names:
            path = directory / name
            if path.is_file() and (not name.endswith(".gz") or _feature_index(path)):
                return path.resolve(), stage
    return None, ""


def _target_bed(record):
    panel = record.get("panel_design") or {}
    assets = panel.get("assets") if isinstance(panel, dict) else {}
    candidate = assets.get("target_bed") if isinstance(assets, dict) else ""
    if not candidate:
        return None
    path = Path(str(candidate)).expanduser()
    if not path.is_file() or (path.name.endswith(".gz") and not _feature_index(path)):
        return None
    return path.resolve()


def _feature_index(path):
    candidates = (Path(str(path) + ".tbi"), Path(str(path) + ".csi"))
    return next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)


def _reference_tracks(reference_build):
    build = (
        "GRCh37"
        if any(value in str(reference_build).casefold() for value in ("37", "hg19"))
        else "GRCh38"
    )
    ucsc = "hg19" if build == "GRCh37" else "hg38"
    clinvar = "vcf_GRCh37" if build == "GRCh37" else "vcf_GRCh38"
    giab = (
        "https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/"
        f"genome-stratifications/v3.6/{build}@all/Union/{build}_alldifficultregions.bb"
    )
    clinvar_url = f"https://ftp.ncbi.nlm.nih.gov/pub/clinvar/{clinvar}/clinvar.vcf.gz"
    return [
        {
            "id": "refseq-transcripts", "name": "RefSeq transcripts",
            "type": "annotation", "format": "refgene", "stage": build,
            "url": f"https://hgdownload.soe.ucsc.edu/goldenPath/{ucsc}/database/ncbiRefSeq.txt.gz",
            "indexed": False, "category": "Reference",
            "description": "Genes, exons and alternative RefSeq transcript models.",
            "source": "NCBI RefSeq via UCSC", "default_visible": True,
        },
        {
            "id": "giab-difficult", "name": "GIAB difficult regions",
            "type": "annotation", "format": "bigbed", "stage": "v3.6",
            "url": giab, "category": "Quality",
            "description": "Union of GIAB regions difficult for small-variant assessment.",
            "source": "NIST Genome in a Bottle", "default_visible": False,
        },
        {
            "id": "clinvar-variants", "name": "ClinVar variants",
            "type": "variant", "format": "vcf", "stage": build,
            "url": clinvar_url, "index_url": f"{clinvar_url}.tbi",
            "category": "Clinical", "description": "ClinVar short variants with precise coordinates.",
            "source": "NCBI ClinVar", "default_visible": False,
        },
        {
            "id": "gnomad-regional", "name": "gnomAD regional variants",
            "type": "annotation", "format": "json", "stage": "v2.1.1" if build == "GRCh37" else "v4.1",
            "source_type": "custom", "url_template": "gnomad-region",
            "category": "Population", "description": "Population variants and allele frequencies in the visible region.",
            "source": "gnomAD genomes", "default_visible": False,
        },
    ]


def _reference(record):
    run_config = record.get("run_config") or {}
    pipeline = record.get("pipeline_config") or {}
    direct = run_config.get("reference_fasta") or pipeline.get("reference_fasta")
    if direct and Path(str(direct)).expanduser().is_file():
        return Path(str(direct)).expanduser().resolve()

    tools = record.get("tools_config") or {}
    wanted = _reference_build(record).casefold().replace("grch", "hg")
    aliases = {wanted, "hg19" if wanted in {"hg37", "hg19"} else wanted}
    for key, config in tools.items():
        if str(key).casefold().replace("grch", "hg") not in aliases or not isinstance(config, dict):
            continue
        fasta = config.get("fasta") or config.get("path")
        if fasta and Path(str(fasta)).expanduser().is_file():
            return Path(str(fasta)).expanduser().resolve()
    return None


def _reference_config(record, reference, resources, warnings):
    build = _reference_build(record)
    genome = "hg19" if any(value in build.casefold() for value in ("37", "hg19")) else "hg38"
    if reference is None:
        warnings.append(f"Using the IGV-hosted {genome} reference; the run FASTA was not found.")
        return {"genome": genome, "local": False, "contig_prefix": "chr"}

    index = Path(str(reference) + ".fai")
    if not index.is_file():
        alternate = reference.with_suffix(reference.suffix + ".fai")
        index = alternate if alternate.is_file() else index
    if not index.is_file():
        warnings.append("The run reference FASTA has no FAI index; using the hosted reference.")
        return {"genome": genome, "local": False, "contig_prefix": "chr"}

    resources.update({"reference": reference, "reference-index": index.resolve()})
    config = {
        "id": genome, "name": f"{build or genome} · run reference", "local": True,
        "resource": "reference", "index_resource": "reference-index",
        "contig_prefix": _contig_prefix(index),
    }
    compressed_index = Path(str(reference) + ".gzi")
    if compressed_index.is_file():
        resources["reference-compressed-index"] = compressed_index.resolve()
        config["compressed_index_resource"] = "reference-compressed-index"
    return config


def _contig_prefix(index):
    try:
        with index.open(encoding="utf-8") as handle:
            first = handle.readline().split("\t", 1)[0]
    except OSError:
        return ""
    return "chr" if first.lower().startswith("chr") else ""


def _reference_build(record):
    candidates = (
        (record.get("run_config") or {}).get("reference_version"),
        (record.get("run_config") or {}).get("reference_build"),
        (record.get("pipeline_config") or {}).get("reference_version"),
        (record.get("request") or {}).get("reference_version"),
    )
    return str(next((value for value in candidates if value), "GRCh38"))
