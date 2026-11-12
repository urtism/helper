"""Bounded, durable bulk writes for automatic ACMG preparation."""
import sqlite3
import threading
import time
from contextlib import contextmanager
from queue import Empty, Queue

from helper_next.core.acmg_pvs1_store import path


_local = threading.local()
_INSERT = "INSERT OR REPLACE INTO automatic_classifications VALUES (?,?,?,?,?,?,?,?)"


def _initialize(db):
    db.execute("CREATE TABLE IF NOT EXISTS automatic_classifications (identity_key TEXT PRIMARY KEY,"
               "variant_key TEXT NOT NULL,identity_json TEXT NOT NULL,signature TEXT NOT NULL,"
               "result_json TEXT NOT NULL,snapshot_json TEXT NOT NULL,source_revision TEXT NOT NULL,input_revision TEXT NOT NULL)")
    db.execute("CREATE INDEX IF NOT EXISTS automatic_classification_variant ON automatic_classifications(variant_key)")
    db.commit()


class CacheWriteError(RuntimeError):
    pass


class CacheWriter:
    """One connection/transaction stream; acknowledge only committed results."""
    def __init__(self, run_dir, coalesce_seconds=.005):
        self.filename = path(run_dir).resolve()
        self.delay = coalesce_seconds
        self.queue = Queue()
        self.ready = threading.Event()
        self.error = None
        self.commits = 0
        self.thread = threading.Thread(target=self._run, name="acmg-cache-writer", daemon=True)

    def __enter__(self):
        self.thread.start()
        self.ready.wait()
        if self.error:
            raise CacheWriteError(str(self.error)) from self.error
        return self

    def __exit__(self, *args):
        self.queue.put(None)
        self.thread.join()

    def write(self, rows):
        if self.error:
            raise CacheWriteError(str(self.error)) from self.error
        request = (rows, threading.Event())
        self.queue.put(request)
        while not request[1].wait(.2):
            if self.error or not self.thread.is_alive():
                raise CacheWriteError(str(self.error or "ACMG cache writer stopped")) from self.error
        if self.error:
            raise CacheWriteError(str(self.error)) from self.error

    def _run(self):
        requests = []
        try:
            self.filename.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.filename, timeout=30) as db:
                _initialize(db)
                self.ready.set()
                while True:
                    first = self.queue.get()
                    if first is None:
                        return
                    requests = [first]
                    deadline = time.monotonic() + self.delay
                    while len(requests) < 32 and time.monotonic() < deadline:
                        try:
                            request = self.queue.get(timeout=max(0, deadline - time.monotonic()))
                        except Empty:
                            break
                        if request is None:
                            self.queue.put(None)
                            break
                        requests.append(request)
                    with db:
                        db.executemany(_INSERT, [row for rows, _ in requests for row in rows])
                    self.commits += 1
                    for _, done in requests:
                        done.set()
                    requests = []
        except BaseException as exc:
            self.error = exc
        finally:
            self.ready.set()
            for _, done in requests:
                done.set()


@contextmanager
def use_writer(writer):
    previous = getattr(_local, "writer", None)
    _local.writer = writer
    try:
        yield
    finally:
        _local.writer = previous


@contextmanager
def write_batch(run_dir):
    """Keep the allele lock until all of its contexts are durably committed."""
    filename = path(run_dir).resolve()
    previous = getattr(_local, "batch", None)
    if previous and previous[0] == filename:
        yield
        return
    rows = []
    _local.batch = (filename, rows)
    try:
        yield
    finally:
        _local.batch = previous
        if rows:
            _write(filename, rows)


def write_row(run_dir, row):
    filename = path(run_dir).resolve()
    batch = getattr(_local, "batch", None)
    if batch and batch[0] == filename:
        batch[1].append(row)
    else:
        _write(filename, [row])


def _write(filename, rows):
    writer = getattr(_local, "writer", None)
    if writer and writer.filename == filename:
        writer.write(rows)
        return
    filename.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(filename, timeout=30) as db:
        _initialize(db)
        db.executemany(_INSERT, rows)
