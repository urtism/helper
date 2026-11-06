"""Bounded BigWig interval reader; no complete tracks are downloaded or retained."""
import atexit
from collections import OrderedDict
from functools import lru_cache
import math
import multiprocessing
import os
from pathlib import Path
import threading
import time

from helper_variants.acquisition import coverage_flights


BASE_URL = "https://hgdownload.soe.ucsc.edu/gbdb/hg38/gnomAD/coverage"
DATASETS = {"exome": ("v4-exome", "gnomAD v4.0 exome coverage"),
            "genome": ("v3-genome", "gnomAD v3.0.1 genome coverage")}
TILE_SIZE = 512
MAX_TILES = 32
READ_TIMEOUT = 20
_lock = threading.Lock()
_process = _connection = None
_retry_after = 0.0


def _sources():
    directory = os.environ.get("HELPER_GNOMAD_COVERAGE_DIR", "").strip()
    sources = {}
    for dataset, (folder, _) in DATASETS.items():
        tracks = []
        for metric in ("mean", "over_20"):
            name = "gnomad.coverage." + metric + ".bw"
            if directory:
                path = Path(directory).expanduser() / folder / name
                try:
                    info = path.stat()
                    signature = (info.st_size, info.st_mtime_ns, info.st_ino, info.st_dev)
                except OSError:
                    signature = None
                tracks.append((str(path), signature))
            else:
                tracks.append((BASE_URL + "/" + folder + "/" + name, None))
        sources[dataset] = tuple(tracks)
    return sources


def _worker(connection):
    # Native BigWig I/O holds the GIL and lacks a total request timeout. Keep it
    # outside the web process so a slow server cannot freeze unrelated requests.
    import pyBigWig
    handles, failures = OrderedDict(), {}

    def track(descriptor):
        if failures.get(descriptor, 0) > time.monotonic():
            raise OSError("Coverage file is temporarily unavailable")
        handle = handles.get(descriptor)
        if handle is None:
            path = descriptor[0]
            if path.startswith("https://") and not pyBigWig.remote:
                raise OSError("pyBigWig was built without remote access")
            try:
                handle = pyBigWig.open(path)
                if handle is None or not handle.isBigWig():
                    raise OSError("Coverage source is not a readable BigWig")
            except Exception:
                failures[descriptor] = time.monotonic() + 30
                if len(failures) > 8:
                    failures.pop(next(iter(failures)))
                raise
            handles[descriptor] = handle
        handles.move_to_end(descriptor)
        while len(handles) > 4:
            _, old = handles.popitem(last=False)
            old.close()
        return handle

    @lru_cache(maxsize=MAX_TILES)
    def tile(tracks, chrom, start):
        values = []
        for descriptor in tracks:
            handle = track(descriptor)
            length = handle.chroms(chrom)
            if length is None or start >= length:
                values.append(())
            else:
                values.append(tuple(handle.values(chrom, start, min(start + TILE_SIZE, length))))
        return tuple(zip(*values))

    try:
        while True:
            command = connection.recv()
            if command is None:
                break
            if command == "status":
                connection.send(dict(tiles=tile.cache_info().currsize, maximum_tiles=MAX_TILES,
                                     open_files=len(handles), maximum_open_files=4))
                continue
            sources, chrom, start, stop = command
            data, errors = {}, {}
            for dataset, tracks in sources.items():
                try:
                    rows = []
                    for first in range((start // TILE_SIZE) * TILE_SIZE, stop, TILE_SIZE):
                        for offset, (mean, over_20) in enumerate(tile(tracks, chrom, first)):
                            position = first + offset
                            if (start <= position < stop and math.isfinite(mean) and mean >= 0
                                    and math.isfinite(over_20) and 0 <= over_20 <= 1):
                                rows.append(dict(pos=position + 1, mean=mean, over_20=over_20))
                    data[dataset] = rows
                except Exception as exc:
                    errors[dataset] = str(exc)
            connection.send(dict(data=data, errors=errors))
    except (EOFError, BrokenPipeError):
        pass
    finally:
        for handle in handles.values():
            handle.close()
        connection.close()


def _stop():
    global _process, _connection
    if _connection is not None:
        _connection.close()
    if _process is not None:
        if _process.is_alive():
            _process.terminate()
        _process.join(timeout=1)
        if _process.is_alive():
            _process.kill()
            _process.join(timeout=1)
    _process = _connection = None


def _read(command):
    global _process, _connection, _retry_after
    if not _lock.acquire(timeout=READ_TIMEOUT):
        return {"data": {}, "errors": {"reader": "Coverage reader is busy"}}
    try:
        if _retry_after > time.monotonic():
            return {"data": {}, "errors": {"reader": "Coverage reader is cooling down"}}
        try:
            if _process is None or not _process.is_alive():
                _stop()
                context = multiprocessing.get_context("spawn")
                _connection, child = context.Pipe()
                _process = context.Process(target=_worker, args=(child,), daemon=True,
                                           name="helper-coverage")
                _process.start()
                child.close()
            _connection.send(command)
            if not _connection.poll(READ_TIMEOUT):
                raise TimeoutError("Indexed coverage read exceeded its time limit")
            result = _connection.recv()
            if command != "status" and not result.get("data"):
                _retry_after = time.monotonic() + 30
            return result
        except (OSError, EOFError, TimeoutError, ImportError) as exc:
            _stop()
            _retry_after = time.monotonic() + 30
            return {"data": {}, "errors": {"reader": str(exc)}}
    finally:
        _lock.release()


def read_region(chromosome, start, stop):
    """One-based inclusive, exact per-base values; missing bases stay missing."""
    mode = os.environ.get("HELPER_GNOMAD_COVERAGE_MODE", "auto").strip().lower()
    if mode in ("graphql", "off"):
        return {"data": {}, "sources": {}}
    if start < 1 or stop < start or stop - start + 1 > 250:
        raise ValueError("Coverage interval must contain 1 to 250 bases")
    sources = _sources()
    name = str(chromosome).removeprefix("chr")
    chrom = "chr" + ("M" if name == "MT" else name)
    key = ("indexed", tuple(sorted(sources.items())), chrom, start, stop)
    result = coverage_flights.run(key, lambda: _read((sources, chrom, start - 1, stop)))
    result["sources"] = {dataset: dict(source=DATASETS[dataset][1],
        mean=tracks[0][0], over_20=tracks[1][0], over_20_units="fraction")
        for dataset, tracks in sources.items() if dataset in result.get("data", {})}
    return result


def resource_status():
    with _lock:
        alive = _process is not None and _process.is_alive()
        pid = _process.pid if alive else None
    status = _read("status") if alive else {"tiles": 0, "open_files": 0}
    return dict(status, pid=pid, maximum_tiles=MAX_TILES, maximum_open_files=4)


atexit.register(_stop)
