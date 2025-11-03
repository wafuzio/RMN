#!/usr/bin/env python3
"""
Instacart legacy → canonical migrator (robust structural detection)
- Scans ALL JSONs under output/instacart/<client>
- Legacy: top-level has "results": list and any r.ads is list
- Canonical: top-level has "ads": list and "results" is NOT a list
- Writes canonical runs to runs/<run_id>/run_results_<run_id>.json
"""

import json, re, os, sys, shutil
from pathlib import Path
from datetime import datetime, timezone

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))
from core.brands import canonicalize

ROOT = Path(os.environ.get("SCRAPER_HOME") or Path(__file__).resolve().parents[1])
INST = ROOT / "output" / "instacart"

# ---------- time helpers ----------
def now_iso_z():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def iso_from_parts(date_str: str, time_str: str) -> str:
    # date: YYYY-MM-DD, time: HH-MM-SS
    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H-%M-%S").replace(tzinfo=timezone.utc)
        return dt.isoformat(timespec="seconds").replace("+00:00","Z")
    except Exception:
        return now_iso_z()

def run_id_from_iso(iso_z: str) -> str:
    dt = datetime.fromisoformat(iso_z.replace("Z","+00:00"))
    return dt.strftime("%Y%m%d%H%M%S")

def to_iso_z(ts: str | None, run_id: str | None):
    """
    Accepts:
      - 2025-10-27T02:56:54Z (ISO)
      - 2025-10-27 02:56:54 (space-separated; assume UTC)
      - 2025-10-27_02-56-54 (underscore + hyphens; assume UTC)
      - 20251027_025654     (compact underscore; assume UTC)  <-- NEW
      - run_id fallback (YYYYMMDDHHMMSS)
    """
    ts = (ts or "").strip()
    try:
        # ISO-like
        if re.match(r'^\d{4}-\d{2}-\d{2}T', ts):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.isoformat(timespec="seconds").replace("+00:00", "Z")
        # Space-separated
        m1 = re.match(r'^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}):(\d{2})$', ts)
        if m1:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            return dt.isoformat(timespec="seconds").replace("+00:00", "Z")
        # Underscore + hyphens (YYYY-MM-DD_HH-MM-SS)
        m2 = re.match(r'^(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})$', ts)
        if m2:
            dt = datetime.strptime(ts, "%Y-%m-%d_%H-%M-%S").replace(tzinfo=timezone.utc)
            return dt.isoformat(timespec="seconds").replace("+00:00", "Z")
        # COMPACT underscore (YYYYMMDD_HHMMSS)  <-- NEW
        m3 = re.match(r'^(\d{8})_(\d{6})$', ts)
        if m3:
            dt = datetime.strptime(ts, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
            return dt.isoformat(timespec="seconds").replace("+00:00", "Z")
    except Exception:
        pass
    if run_id and re.match(r'^\d{14}$', run_id):
        dt = datetime.strptime(run_id, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        return dt.isoformat(timespec="seconds").replace("+00:00", "Z")
    return now_iso_z()

# ---------- canonical helpers ----------
ADTYPE_MAP = {
    "Shoppable Display Ad": "Shoppable_Display_Ad",
    "Shoppable Video Ad": "Shoppable_Video_Ad",
    "Display Ad": "Display_Ad",
    "Shoppable_Display_Ad": "Shoppable_Display_Ad",
    "Shoppable_Video_Ad": "Shoppable_Video_Ad",
    "Display_Ad": "Display_Ad",
}

def ensure_ad_type(t):
    t = (t or "").strip()
    return ADTYPE_MAP.get(t, t or "Display_Ad")

def normalize_rel(client_root: Path, path: str | None):
    if not path: return None
    p = Path(path)
    try:
        if not p.is_absolute():
            return p.as_posix()
        return p.relative_to(client_root).as_posix()
    except Exception:
        return p.name

def pick_brand(ad: dict):
    advs = ad.get("advertisers")
    if isinstance(advs, list) and advs:
        b = canonicalize(str(advs[0]))
        if b: return b
    b = canonicalize(ad.get("brand"))
    if b: return b
    for key in ("title","message"):
        v = ad.get(key)
        if isinstance(v,str) and v.strip():
            b = canonicalize(v.strip())
            if b: return b
    return "unknown"

def build_can_ad(run_id: str, idx: int, ad: dict, iso: str, keyword: str, client_root: Path):
    ad_type = ensure_ad_type(ad.get("type"))
    brand = pick_brand(ad)
    rel_img = None
    for k in ("image_path","screenshot","toa_image_path","display_image_path"):
        rel_img = normalize_rel(client_root, ad.get(k))
        if rel_img:
            break
    can = {
        "id": f"instacart-{run_id}-{idx}",
        "type": ad_type,
        "brand": brand,
        "brand_logo": None,
        "title": ad.get("title"),
        "description": ad.get("description"),
        "cta": ad.get("cta"),
        "href": ad.get("href"),
        "image_url": ad.get("image_url"),
        "image_path": rel_img,
        "products": ad.get("products", []),
        "metadata": {
            "slot": ad.get("slot"),
            "keyword_token": keyword,
            "source": "instacart",
        },
        "timestamp": iso,
    }
    vrel = normalize_rel(client_root, ad.get("video_path"))
    if vrel:
        can["video_path"] = vrel
    if ad.get("advertisers"):
        can["advertisers"] = ad["advertisers"]
    return can

def ensure_unique_run_dir(client_dir: Path, base_run_id: str, index_hint: int | None = None) -> Path:
    runs_root = client_dir / "runs"
    d = runs_root / base_run_id
    if not d.exists():
        return d
    if index_hint is not None:
        d2 = runs_root / f"{base_run_id}_{index_hint:02d}"
        if not d2.exists():
            return d2
    i = 1
    while True:
        d3 = runs_root / f"{base_run_id}_{i:02d}"
        if not d3.exists():
            return d3
        i += 1

def write_canonical_run(client_dir: Path, run_id: str, payload: dict, index_hint: int | None = None) -> Path:
    run_dir = ensure_unique_run_dir(client_dir, run_id, index_hint)
    run_dir.mkdir(parents=True, exist_ok=True)
    # If suffix used, record it in payload for transparency
    m = re.match(rf"^{re.escape(run_id)}_(\d+)$", run_dir.name)
    if m:
        payload = dict(payload)
        payload["run_seq"] = int(m.group(1))
    out = run_dir / f"run_results_{run_id}.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return out

# Support a few shapes:
# 1) search_results_<keyword>_<YYYY-MM-DD>_<HH-MM-SS>.html
# 2) search_results_<keyword>_<YYYYMMDD>_<HHMMSS>.html
# 3) search_results_<YYYYMMDD>_<HHMMSS>.html  (no keyword)
# Also tolerate srp_results_*, instacart_search_results_* variants

PATTERNS = [
    re.compile(r'(?:^|/)(?:search_results|srp_results|instacart_search_results)_(?P<kw>.+?)_(?P<date>\d{4}-\d{2}-\d{2})_(?P<time>\d{2}-\d{2}-\d{2})\.html$', re.I),
    re.compile(r'(?:^|/)(?:search_results|srp_results|instacart_search_results)_(?P<kw>.+?)_(?P<datec>\d{8})_(?P<timec>\d{6})\.html$', re.I),
    re.compile(r'(?:^|/)(?:search_results|srp_results|instacart_search_results)_(?P<datec>\d{8})_(?P<timec>\d{6})\.html$', re.I),
]

def extract_from_source_file(path: str | None):
    if not path:
        return None, None
    p = path.replace("\\", "/")
    for rx in PATTERNS:
        m = rx.search(p)
        if not m:
            continue
        kw = m.groupdict().get("kw")
        date = m.groupdict().get("date")
        time = m.groupdict().get("time")
        datec = m.groupdict().get("datec")
        timec = m.groupdict().get("timec")

        if date and time:
            # YYYY-MM-DD + HH-MM-SS
            iso = iso_from_parts(date, time)
            return (kw.replace("_", " ").strip() if kw else None), iso

        if datec and timec:
            # COMPACT YYYYMMDD + HHMMSS
            try:
                dt = datetime.strptime(f"{datec}_{timec}", "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
                iso = dt.isoformat(timespec="seconds").replace("+00:00", "Z")
                return (kw.replace("_", " ").strip() if kw else None), iso
            except Exception:
                pass
    return None, None

def copy_source_html_into_run(src_path: str | None, client_dir: Path, run_dir: Path, keyword: str, run_id: str):
    if not src_path:
        return
    sp = Path(src_path)
    # If the referenced HTML exists anywhere (absolute or relative to client_dir), copy it into the run dir
    if not sp.is_file():
        # try relative to client_dir
        maybe = client_dir / sp.name
        if maybe.is_file():
            sp = maybe
        else:
            return
    safe_kw = re.sub(r"[^A-Za-z0-9]+", "_", keyword).strip("_") or "search"
    dest = run_dir / f"search_results_{safe_kw}_{run_id}.html"
    try:
        shutil.copy2(sp, dest)
    except Exception:
        pass

# ---------- structural detection ----------

def is_canonical(data: dict) -> bool:
    """
    Canonical iff:
      - top-level 'ads' is a list
      - and 'results' is NOT a list
    Legacy files can have top-level 'retailer' but no top-level ads[].
    """
    return isinstance(data.get("ads"), list) and not isinstance(data.get("results"), list)

def is_legacy(data: dict) -> bool:
    """
    Legacy iff:
      - 'results' is a list
      - and at least one results[i].ads is a list
    """
    results = data.get("results")
    if not isinstance(results, list):
        return False
    for r in results:
        if isinstance(r, dict) and isinstance(r.get("ads"), list):
            return True
    return False

# ---------- migration logic ----------

def migrate_file(jp: Path, client_dir: Path) -> int:
    """
    Migrate ONE legacy JSON file.
    Returns number of canonical runs written for this file.
    """
    try:
        data = json.loads(jp.read_text())
    except Exception as e:
        print(f"⚠️ Could not read {jp}: {e}")
        return 0

    # Skip real canonical
    if is_canonical(data):
        return 0

    # Only handle legacy
    if not is_legacy(data):
        return 0

    results = data["results"]
    written = 0
    client_root = client_dir

    # Aggregator: multiple results entries => write one canonical run per entry
    if len(results) > 1:
        for idx_r, r in enumerate(results, start=1):
            if not isinstance(r, dict):
                continue
            raw_ads = r.get("ads") or []
            if not raw_ads:
                continue

            kw, iso = extract_from_source_file(r.get("source_file"))
            if not kw:
                kw = r.get("keyword") or data.get("keyword") or data.get("search_term") or ""
            if not iso:
                iso = to_iso_z(r.get("timestamp") or data.get("timestamp"), None)

            base_run_id = run_id_from_iso(iso)
            can_ads = []
            for i, ad in enumerate(raw_ads, start=1):
                can_ads.append(build_can_ad(base_run_id, i, ad, iso, kw, client_root))

            payload = {
                "retailer": "instacart",
                "client": client_dir.name,
                "keyword": kw,
                "timestamp": iso,
                "run_id": base_run_id,
                "ads": can_ads,
            }
            out = write_canonical_run(client_dir, base_run_id, payload, index_hint=idx_r)
            print(f"✅ Canonicalized: {out.relative_to(ROOT)} ({len(can_ads)} ads)")
            run_dir = out.parent
            copy_source_html_into_run(r.get("source_file"), client_dir, run_dir, kw, base_run_id)
            written += 1
    else:
        # Single-run legacy
        r0 = results[0]
        raw_ads = r0.get("ads") or []
        if not raw_ads:
            return 0

        kw, iso = extract_from_source_file(r0.get("source_file") or data.get("source_file"))
        if not kw:
            kw = r0.get("keyword") or data.get("keyword") or data.get("search_term") or ""
        if not iso:
            # Try filename: run_results_<kw>_<YYYYMMDD>_<HHMMSS>.json or run_results_<YYYYMMDD>_<HHMMSS>.json
            m = re.search(r'run_results_(?:.+?_)?(\d{8})_(\d{6})', jp.name)
            if m:
                dt = datetime.strptime(f"{m.group(1)}_{m.group(2)}", "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
                iso = dt.isoformat(timespec="seconds").replace("+00:00", "Z")
            else:
                iso = to_iso_z(data.get("timestamp"), None)

        base_run_id = run_id_from_iso(iso)
        can_ads = []
        for i, ad in enumerate(raw_ads, start=1):
            can_ads.append(build_can_ad(base_run_id, i, ad, iso, kw, client_root))

        payload = {
            "retailer": "instacart",
            "client": client_dir.name,
            "keyword": kw,
            "timestamp": iso,
            "run_id": base_run_id,
            "ads": can_ads,
        }
        out = write_canonical_run(client_dir, base_run_id, payload)
        print(f"✅ Canonicalized: {out.relative_to(ROOT)} ({len(can_ads)} ads)")
        run_dir = out.parent
        copy_source_html_into_run(r0.get("source_file") or data.get("source_file"), client_dir, run_dir, kw, base_run_id)
        written += 1

    return written

def migrate_client(client_dir: Path) -> tuple[int, int, int]:
    """
    Scan every JSON under the client and migrate everything legacy.
    Returns (files_scanned, canonical_runs_written, files_already_canonical_count)
    """
    scanned = 0
    migrated_runs = 0
    already_canonical = 0

    for jp in client_dir.rglob("*.json"):
        scanned += 1
        try:
            data = json.loads(jp.read_text())
        except Exception:
            continue

        if is_canonical(data):
            already_canonical += 1
            continue

        if is_legacy(data):
            migrated_runs += migrate_file(jp, client_dir)
        # else: unknown shape → ignore silently

    return scanned, migrated_runs, already_canonical

def main():
    if not INST.exists():
        print(f"❌ No instacart root at {INST}")
        return
    clients = sorted([p for p in INST.iterdir() if p.is_dir()])
    if not clients:
        print("No instacart clients found.")
        return

    print("=" * 60)
    print("Instacart Legacy → Canonical Migration (structural detection)")
    print("=" * 60)
    print(f"Root: {ROOT}")
    print(f"Instacart dir: {INST}")
    print(f"Clients: {len(clients)}")
    print("")

    total_scanned = 0
    total_migrated_runs = 0
    total_already = 0

    for client_dir in clients:
        scanned, migrated_runs, already_canon = migrate_client(client_dir)
        total_scanned += scanned
        total_migrated_runs += migrated_runs
        total_already += already_canon
        print(f"Client {client_dir.name}: scanned_files={scanned}, canonical_runs_written={migrated_runs}, files_already_canonical={already_canon}")

    print("")
    print("=" * 60)
    print("Migration Complete")
    print("=" * 60)
    print(f"Scanned JSON files: {total_scanned}")
    print(f"Canonical runs written: {total_migrated_runs}")
    print(f"Files already canonical (skipped): {total_already}")
    print("")
    print("Next steps:")
    print("1) Verify runs:")
    print("   cat output/instacart/<client>/runs/*/run_results_*.json | jq '. | {retailer, client, keyword, timestamp, run_id, ads_count: (.ads|length)}'")
    print("2) API test:")
    print("   curl -s 'http://localhost:5006/api/runs?retailer=instacart&client=<client>' | jq")
    print("   curl -s 'http://localhost:5006/api/ads/cards?retailer=instacart&client=<client>&page_size=10' | jq '.cards | length'")

if __name__ == "__main__":
    main()
