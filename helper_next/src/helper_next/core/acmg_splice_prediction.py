"""Read existing, allele/gene-bound SpliceAI annotations; no predictor or fetch."""
import math
import re

from helper_next.core.acmg_digest import digest
from helper_next.core.acmg_transcripts import primary_chromosome


THRESHOLD = 0.5  # Scenario selection, not an ACMG evidence-strength threshold.
FIELDS = ("DS_AG", "DS_AL", "DS_DG", "DS_DL", "DP_AG", "DP_AL", "DP_DG", "DP_DL")
SOURCE = "https://github.com/Illumina/SpliceAI#usage"


def _edit(position, ref, alt):
    while ref and alt and ref[0] == alt[0]:
        position, ref, alt = position + 1, ref[1:], alt[1:]
    while ref and alt and ref[-1] == alt[-1]:
        ref, alt = ref[:-1], alt[:-1]
    return position, ref, alt


def spliceai_prediction(annotation, variant, original=None):
    """Preserve raw fields and the original VCF position used by delta positions.

    Accept native INFO, VEP split fields and VEP's packed field. Distinct rows,
    malformed values and conflicting formats are never resolved by maximum score.
    """
    annotation, original = annotation or {}, original or {}
    fields = annotation.get("metadata", {}).get("fields", {})
    supplied = annotation.get("metadata", {}).get("spliceai_prediction")
    raw_info = original.get("info", {}).get("SpliceAI")
    split = {key: fields.get("SpliceAI_pred_" + key) for key in ("SYMBOL", *FIELDS)}
    packed = fields.get("SpliceAI_pred")
    present = lambda value: value is not None and value != "" and value != "."
    if supplied is None and not present(raw_info) and not present(packed) and not any(present(v) for v in split.values()):
        return None
    result = {"tool": "SpliceAI", "source_url": SOURCE, "threshold": THRESHOLD,
              "model_version": None, "annotation_id": annotation.get("id"),
              "raw": {"INFO/SpliceAI": raw_info, "VEP/SpliceAI_pred": packed, "VEP/split": split,
                      "supplied_prediction": supplied},
              "status": "UNRESOLVED", "records": [], "issues": []}
    try:
        position = original.get("position", variant["position"])
        ref = original.get("reference", variant["reference_allele"])
        alt = original.get("alternate", variant["alternate_allele"])
        if original.get("chromosome") and primary_chromosome(original["chromosome"]) != primary_chromosome(variant["contig"]):
            raise ValueError("SpliceAI original chromosome differs from the selected allele")
        if (type(position) is not int or _edit(position, ref, alt) != _edit(
                variant["position"], variant["reference_allele"], variant["alternate_allele"])):
            raise ValueError("SpliceAI original and selected allele representations cannot be reconciled")
        symbol = str(annotation.get("gene") or "").strip()
        if not symbol:
            raise ValueError("SpliceAI requires the selected annotation's gene symbol")
        candidates = []
        if supplied is not None:
            if not isinstance(supplied, dict) or not supplied.get("source_url"):
                raise ValueError("Supplied SpliceAI prediction requires its original source URL")
            if (type(supplied.get("position")) is not int or supplied.get("position") != variant["position"]
                    or supplied.get("reference") != variant["reference_allele"]
                    or supplied.get("alternate") != variant["alternate_allele"] or supplied.get("assembly") != variant["assembly"]):
                raise ValueError("Supplied SpliceAI prediction differs from the selected allele/build")
            if supplied.get("SYMBOL") == symbol:
                candidates.append(supplied)
                result["source_url"] = supplied["source_url"]
        same_representation = (position, ref, alt) == (variant["position"], variant["reference_allele"], variant["alternate_allele"])
        vep_present = present(packed) or any(present(v) for v in split.values())
        if vep_present and not same_representation:
            if not present(raw_info):
                raise ValueError("Shifted allele: VEP SpliceAI delta positions require native INFO coordinates")
            result["ignored_formats"] = ["VEP: shifted allele representation; native INFO used"]
        for value, native in ((raw_info, True), (packed, False)):
            if not present(value) or (not native and not same_representation):
                continue
            values = value if isinstance(value, list) else str(value).split(",")
            for entry in values:
                parts = str(entry).split("|")
                if len(parts) != (10 if native else 9):
                    raise ValueError("Incomplete or ambiguous packed SpliceAI record")
                if native:
                    allele, *parts = parts
                    if allele != alt:
                        continue
                if parts[0] == symbol:
                    candidates.append(dict(zip(("SYMBOL", *FIELDS), parts)))
        if same_representation and any(present(v) for v in split.values()):
            if split["SYMBOL"] == symbol:
                candidates.append(split)
        if not candidates:
            result["status"] = "NOT_APPLICABLE"
            result["issues"].append("No SpliceAI record matches the selected allele and gene")
            return result
        normalized = {}
        for candidate in candidates:
            row = {"SYMBOL": symbol, "position": candidate.get("position", position)}
            for key in FIELDS:
                value = candidate.get(key)
                if isinstance(value, bool):
                    raise ValueError("Invalid SpliceAI numeric value")
                if key.startswith("DS_"):
                    number = float(value)
                    if not math.isfinite(number) or not 0 <= number <= 1:
                        raise ValueError("SpliceAI scores must be finite values in [0, 1]")
                else:
                    if not re.fullmatch(r"[+-]?\d+", str(value)):
                        raise ValueError("SpliceAI delta positions must be integers")
                    number = int(value)
                    if abs(number) > 10000:
                        raise ValueError("SpliceAI position exceeds the bounded 10 kb reconstruction window")
                row[key] = number
            normalized[digest(row)["value"]] = row
        result["records"] = list(normalized.values())
        if len(normalized) != 1:
            raise ValueError("Multiple distinct SpliceAI records for the same allele/gene")
        result["status"] = "AVAILABLE"
    except (TypeError, ValueError, OverflowError) as exc:
        result["issues"].append(str(exc))
    return result
