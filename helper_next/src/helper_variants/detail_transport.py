"""Optional lossless wire representation for repeated detail provenance.

The default detail API retains its existing structure. Browser clients expand
this representation before using existing rendering and interpretation code.
"""
import json


FORMAT = "helper-variant-detail-compact-v1"


def compact_detail(detail):
    shared, positions = [], {}

    def intern(value):
        key = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if key not in positions:
            positions[key] = len(shared)
            shared.append(value)
        return positions[key]

    result = dict(detail)
    result["annotations"] = []
    for annotation in detail.get("annotations", []):
        row = dict(annotation)
        if "release_resources" in row:
            row["release_resources"] = intern(row["release_resources"])
        result["annotations"].append(row)
    catalog = detail.get("interpretation_context")
    if catalog is not None:
        result["interpretation_context"] = dict(catalog, annotations=[])
        for annotation in catalog.get("annotations", []):
            row = dict(annotation, contexts=[])
            for choice in annotation.get("contexts", []):
                item = dict(choice)
                for key in ("context", "origin"):
                    if key in item:
                        item[key] = intern(item[key])
                row["contexts"].append(item)
            result["interpretation_context"]["annotations"].append(row)
    return dict(format=FORMAT, detail=result, shared=shared)
