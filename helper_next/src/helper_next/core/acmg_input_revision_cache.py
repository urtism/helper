"""Optional, rebuildable annotation digests shared across samples and restarts."""
from collections import OrderedDict
from functools import lru_cache
import json
import os
from pathlib import Path
import tempfile
import threading

from helper_next.core.acmg_digest import digest

FORMAT = "helper-acmg-input-revisions-v1"
_creation_lock = threading.Lock()


def _stamp(filename):
    states = []
    for name in (filename, filename + "-wal"):
        try:
            stat = os.stat(name)
            states.append((stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
        except OSError:
            states.append(None)
    return digest([FORMAT, filename, states])["value"]


@lru_cache(maxsize=4)
def _cache(filename, stamp):
    return dict(values=OrderedDict(), lock=threading.Lock(), loaded=False, saved=set())


def _read(path, stamp):
    try:
        payload = json.loads(path.read_text())
        if payload.get("format") == FORMAT and payload.get("index") == stamp:
            return {int(key): value for key, value in payload["revisions"].items()
                    if isinstance(value, str) and len(value) == 64
                    and all(char in "0123456789abcdef" for char in value)}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    return {}


def _write(path, stamp, values):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=path.name + ".", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(dict(format=FORMAT, index=stamp, revisions=values), handle, separators=(",", ":"))
        os.replace(temporary, path)
    except (OSError, ValueError, TypeError):
        pass  # A read-only run or unavailable optional cache must still load.
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def revisions(database, variant_ids, calculate):
    ids = sorted(set(variant_ids))
    if not ids:
        return {}
    filename = str(Path(database).resolve())
    path = Path(filename + ".acmg-inputs.json")
    batch = len(ids) > 1
    for _ in range(2):
        stamp = _stamp(filename)
        with _creation_lock:
            entry = _cache(filename, stamp)
        with entry["lock"]:
            values = entry["values"]
            if batch and not entry["loaded"]:
                saved = _read(path, stamp)
                values.update(saved)
                entry["saved"].update(saved)
                entry["loaded"] = True
            missing = [variant for variant in ids if variant not in values]
            fresh = calculate(database, missing) if missing else {}
            if _stamp(filename) != stamp:
                continue  # An in-place edit/WAL commit/replacement invalidates every old digest.
            values.update(fresh)
            result = {variant: values[variant] for variant in ids if variant in values}
            for variant in result:
                values.move_to_end(variant)
            while len(values) > 8192:
                values.popitem(last=False)
            # Run preparation evaluates single alleles; avoid adding a disk write per allele.
            if batch and any(variant not in entry["saved"] for variant in result):
                _write(path, stamp, values)
                entry["saved"].update(values)
            return result
    return calculate(database, ids)  # Concurrent edits: read fresh inputs without publishing a receipt.
