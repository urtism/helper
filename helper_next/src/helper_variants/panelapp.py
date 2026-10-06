"""Small read-only client for Genomics England PanelApp public panels."""
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://panelapp.genomicsengland.co.uk/api/v1"
CACHE_SECONDS = 24 * 60 * 60
MAX_PAGES = 20
_cache = {"expires": 0.0, "panels": []}
_cache_lock = threading.Lock()


class PanelAppError(RuntimeError):
    pass


def search_panels(query_text, limit=20):
    query_text = str(query_text or "").strip()
    if len(query_text) < 2 and not query_text.isdigit():
        raise PanelAppError("PanelApp search requires at least 2 characters or a numeric panel ID")
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        raise PanelAppError("PanelApp result limit must be an integer")
    query_folded = query_text.casefold()
    matches = []
    for panel in _panel_catalog():
        fields = [
            str(panel.get("id", "")), panel.get("name", ""), panel.get("disease_group", ""),
            panel.get("disease_sub_group", ""), *(panel.get("relevant_disorders") or []),
        ]
        searchable = " ".join(str(value) for value in fields).casefold()
        if query_folded not in searchable:
            continue
        name = str(panel.get("name", ""))
        exact = query_folded in (str(panel.get("id", "")).casefold(), name.casefold())
        prefix = name.casefold().startswith(query_folded)
        matches.append((0 if exact else 1 if prefix else 2, name.casefold(), _public_panel(panel)))
    matches.sort(key=lambda item: (item[0], item[1]))
    return {"query": query_text, "panels": [item[2] for item in matches[:limit]]}


def list_panels():
    panels = [_public_panel(panel) for panel in _panel_catalog()]
    panels.sort(key=lambda item: item["name"].casefold())
    cache = _disk_cache()
    return {
        "panels": panels, "synced_at": cache.get("synced_at", ""),
        "cache_path": str(cache_path()), "source": "local-cache",
    }


def sync_panels():
    with _cache_lock:
        panels = _fetch_catalog()
        synced_at = datetime.now(timezone.utc).isoformat()
        _write_disk_cache({"schema_version": 1, "synced_at": synced_at, "panels": panels})
        _cache.update({"expires": time.monotonic() + CACHE_SECONDS, "panels": panels})
        return {"panels": len(panels), "synced_at": synced_at, "cache_path": str(cache_path())}


def panel_detail(panel_id, version=""):
    try:
        panel_id = int(panel_id)
    except (TypeError, ValueError):
        raise PanelAppError("PanelApp panel identifier must be an integer")
    if panel_id < 1:
        raise PanelAppError("PanelApp panel identifier must be positive")
    version = str(version or "").strip()
    if version and not re.fullmatch(r"\d+(?:\.\d+)*", version):
        raise PanelAppError("invalid PanelApp panel version")
    detail_path = _detail_cache_path(panel_id, version)
    cached = _read_json_file(detail_path)
    if cached.get("genes") and cached.get("id"):
        return cached
    suffix = "/panels/{}/".format(panel_id)
    if version:
        suffix += "?" + urlencode({"version": version})
    try:
        payload = _get_json(BASE_URL + suffix)
    except PanelAppError:
        latest = _read_json_file(_detail_cache_path(panel_id, ""))
        same_version = not version or str(latest.get("version", "")) == version
        if same_version and latest.get("genes") and latest.get("id"):
            return latest
        raise
    confidence = {"green": [], "amber": [], "red": []}
    records = []
    for entry in payload.get("genes") or []:
        if str(entry.get("entity_type", "gene")).lower() != "gene":
            continue
        gene_data = entry.get("gene_data") or {}
        symbol = str(gene_data.get("hgnc_symbol") or gene_data.get("gene_symbol")
                     or entry.get("entity_name") or "").strip()
        if not symbol:
            continue
        level = str(entry.get("confidence_level", ""))
        group = "green" if level in ("3", "4") else "amber" if level == "2" else "red"
        if symbol not in confidence[group]:
            confidence[group].append(symbol)
        records.append({
            "symbol": symbol, "confidence": group,
            "mode_of_inheritance": str(entry.get("mode_of_inheritance") or ""),
        })
    for values in confidence.values():
        values.sort(key=str.casefold)
    panel = _public_panel(payload)
    panel.update({
        "genes": confidence, "gene_records": records,
        "gene_counts": {key: len(value) for key, value in confidence.items()},
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source_url": "https://panelapp.genomicsengland.co.uk/panels/{}/".format(panel_id),
    })
    _write_json_file(detail_path, panel, required=False)
    if version:
        _write_json_file(_detail_cache_path(panel_id, ""), panel, required=False)
    return panel


def _panel_catalog():
    now = time.monotonic()
    with _cache_lock:
        if _cache["panels"] and _cache["expires"] > now:
            return list(_cache["panels"])
        disk = _disk_cache()
        if disk.get("panels"):
            _cache.update({"expires": now + CACHE_SECONDS, "panels": disk["panels"]})
            return list(disk["panels"])
        panels = _fetch_catalog()
        synced_at = datetime.now(timezone.utc).isoformat()
        _write_disk_cache({"schema_version": 1, "synced_at": synced_at, "panels": panels})
        _cache.update({"expires": now + CACHE_SECONDS, "panels": panels})
        return list(panels)


def _fetch_catalog():
    stale = list(_cache["panels"])
    panels = []
    url = BASE_URL + "/panels/?page_size=100"
    try:
        for page in range(MAX_PAGES):
            payload = _get_json(url)
            panels.extend(payload.get("results") or [])
            url = payload.get("next")
            if not url:
                return panels
            if page:
                time.sleep(0.2)
        raise PanelAppError("PanelApp panel catalogue exceeded the pagination limit")
    except PanelAppError:
        if stale:
            return stale
        raise


def cache_path():
    configured = os.environ.get("HELPER_PANELAPP_CACHE", "").strip()
    if configured:
        return Path(configured).expanduser()
    data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return data_home / "helper_next" / "panelapp" / "catalog.json"


def _disk_cache():
    payload = _read_json_file(cache_path())
    if isinstance(payload.get("panels"), list):
        return payload
    return {"panels": [], "synced_at": ""}


def _read_json_file(path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except (OSError, TypeError, ValueError):
        pass
    return {}


def _detail_cache_path(panel_id, version):
    suffix = "v{}".format(version) if version else "latest"
    return cache_path().parent / "panels" / "{}-{}.json".format(panel_id, suffix)


def _write_disk_cache(payload):
    _write_json_file(cache_path(), payload)


def _write_json_file(path, payload, required=True):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        if required:
            raise PanelAppError("cannot save PanelApp cache: {}".format(exc))


def _public_panel(panel):
    stats = panel.get("stats") or {}
    return {
        "id": panel.get("id"), "name": str(panel.get("name") or ""),
        "version": str(panel.get("version") or ""),
        "version_created": str(panel.get("version_created") or ""),
        "disease_group": str(panel.get("disease_group") or ""),
        "disease_sub_group": str(panel.get("disease_sub_group") or ""),
        "relevant_disorders": list(panel.get("relevant_disorders") or []),
        "gene_count": int(stats.get("number_of_genes") or len(panel.get("genes") or [])),
        "types": [str(item.get("name") or "") for item in panel.get("types") or [] if item.get("name")],
    }


def _get_json(url):
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "Helper-Variants/1.0"})
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 429:
            retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
            suffix = " Retry after {} seconds.".format(retry_after) if retry_after else ""
            raise PanelAppError("PanelApp rate limit reached (HTTP 429).{}".format(suffix))
        raise PanelAppError("PanelApp returned HTTP {}".format(exc.code))
    except (URLError, TimeoutError, OSError) as exc:
        raise PanelAppError("PanelApp is unavailable: {}".format(exc))
    except (UnicodeError, ValueError) as exc:
        raise PanelAppError("PanelApp returned invalid JSON: {}".format(exc))
