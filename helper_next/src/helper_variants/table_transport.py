"""Opt-in, lossless transfer of repeated table filter rows and provenance."""
import json

FORMAT = "helper-variant-table-compact-v1"


def compact_table(payload):
    shared, positions = [], {}

    def intern(value):
        key = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if key not in positions:
            positions[key] = len(shared)
            shared.append(value)
        return positions[key]

    table = dict(payload, items=[])
    for item in payload.get("items", []):
        row = dict(item)
        if "annotations" in item.get("filter_data", {}):
            row["filter_data"] = dict(item["filter_data"], annotations=[
                intern(annotation) for annotation in item["filter_data"].get("annotations", [])])
        evidence = item.get("clinvar_evidence", {})
        if "provenance" in evidence:
            row["clinvar_evidence"] = dict(evidence, provenance=intern(evidence["provenance"]))
        table["items"].append(row)
    return dict(format=FORMAT, table=table, shared=shared)
