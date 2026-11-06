"""Share only active source acquisitions; completed data live in existing stores."""
import copy
from concurrent.futures import Future
import threading


class SingleFlight:
    def __init__(self):
        self._lock = threading.Lock()
        self._active = {}

    def batch(self, keys, acquire):
        keys = list(dict.fromkeys(keys))
        owned, futures = [], {}
        with self._lock:
            for key in keys:
                future = self._active.get(key)
                if future is None:
                    future = self._active[key] = Future()
                    owned.append(key)
                futures[key] = future
        if owned:
            try:
                try:
                    values = acquire(owned)
                    if any(key not in values for key in owned):
                        raise ValueError("Source acquisition returned an incomplete batch")
                finally:
                    # Detach before waking waiters: a detail consumer may need
                    # to immediately acquire an optional subset after the main
                    # cohort finishes. It must not rejoin the completed flight.
                    with self._lock:
                        for key in owned:
                            self._active.pop(key, None)
                for key in owned:
                    futures[key].set_result(values[key])
            except BaseException as exc:
                for key in owned:
                    if not futures[key].done():
                        futures[key].set_exception(exc)
                raise
        return {key: copy.deepcopy(futures[key].result()) for key in keys}

    def run(self, key, acquire):
        return self.batch([key], lambda keys: {key: acquire()})[key]


projection_flights = SingleFlight()
frequency_flights = SingleFlight()
coverage_flights = SingleFlight()
