#!/usr/bin/env python3
"""
walmart_run_viewer.py
Generates a browser-based viewer for the last N Walmart scrape runs.
Shows run metadata, ad types captured, corresponding images, full-page
screenshots, and the scraper source code — all in one browser tab.

Usage:
    python tools/walmart_run_viewer.py            # last 5 runs
    python tools/walmart_run_viewer.py --n 10     # last 10 runs
    python tools/walmart_run_viewer.py --client Proactiv
"""

import argparse
import json
import sys
import tempfile
import webbrowser
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
WALMART_OUTPUT = Path(__file__).parent.parent / "output" / "walmart"
SCRAPER_SOURCE = Path(__file__).parent.parent / "walmart_search_and_capture.py"

AD_TYPE_COLORS = {
    "SBA":           "#0071CE",
    "SBV":           "#7B2FBE",
    "Gallery_Cards": "#00A651",
    "Tile_Takeover": "#FF6900",
    "Skyline":       "#E31837",
    "Marquee":       "#00AEEF",
    "Main":          "#555555",
}

def ad_color(ad_type: str) -> str:
    for key, color in AD_TYPE_COLORS.items():
        if key.lower() in ad_type.lower():
            return color
    return "#888888"


# ── Data loading ──────────────────────────────────────────────────────────────

def find_run_jsons(client_filter: str | None) -> list[dict]:
    """Walk output/walmart and collect all run_results JSONs with metadata."""
    results = []
    if not WALMART_OUTPUT.exists():
        print(f"[error] output dir not found: {WALMART_OUTPUT}", file=sys.stderr)
        return results

    for client_dir in WALMART_OUTPUT.iterdir():
        if not client_dir.is_dir():
            continue
        if client_filter and client_dir.name.lower() != client_filter.lower():
            continue

        # New format: output/walmart/{client}/runs/{run_id}/run_results_{run_id}.json
        runs_dir = client_dir / "runs"
        if runs_dir.exists():
            for run_id_dir in runs_dir.iterdir():
                if not run_id_dir.is_dir():
                    continue
                for jf in run_id_dir.glob("run_results_*.json"):
                    results.append({
                        "json_path": jf,
                        "client_root": client_dir,
                        "client": client_dir.name,
                    })
        
        # Legacy format: output/walmart/{client}/{timestamp}/run_results_{ts}.json
        for ts_dir in client_dir.iterdir():
            if not ts_dir.is_dir() or ts_dir.name in ("runs", "Gallery_Cards", "Main", "SBA", "SBV", "Tile_Takeover", "Top_Banner", "locks", "walmart"):
                continue
            for jf in ts_dir.glob("run_results_*.json"):
                results.append({
                    "json_path": jf,
                    "client_root": client_dir,
                    "client": client_dir.name,
                })

    # Sort by file mtime descending
    results.sort(key=lambda r: r["json_path"].stat().st_mtime, reverse=True)
    return results


def load_run(entry: dict) -> dict | None:
    try:
        data = json.loads(entry["json_path"].read_text())
        data["_client_root"] = entry["client_root"]
        data["_json_path"] = entry["json_path"]
        if not data.get("client"):
            data["client"] = entry["client"]
        return data
    except Exception as e:
        print(f"[warn] could not read {entry['json_path']}: {e}", file=sys.stderr)
        return None


def resolve_image(ad: dict, client_root: Path) -> str | None:
    """Return file:// URL for the ad image, or None."""
    img = ad.get("image_path")
    if not img:
        return None
    abs_path = client_root / img
    if abs_path.exists():
        return abs_path.as_uri()
    # Sometimes image_path is already absolute
    if Path(img).is_absolute() and Path(img).exists():
        return Path(img).as_uri()
    return None


def find_fullpage_for_run(run: dict) -> str | None:
    """Return file:// URI of the Main/ full-page screenshot for this run."""
    run_id = run.get("run_id", "")
    client_root: Path = run["_client_root"]
    main_dir = client_root / "Main"
    if not main_dir.exists() or len(run_id) < 14:
        return None
    y, mo, d = run_id[:4], run_id[4:6], run_id[6:8]
    hh, mi, ss = run_id[8:10], run_id[10:12], run_id[12:14]
    pattern = f"D{y}-{mo}-{d}_T{hh}-{mi}.{ss}"
    matches = list(main_dir.glob(f"*{pattern}*"))
    return matches[0].as_uri() if matches else None


# ── HTML generation ───────────────────────────────────────────────────────────

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       background: #f0f2f5; color: #1a1a2e; }

/* ── Tabs ── */
.tab-bar { background: #0071CE; display: flex; align-items: stretch; padding: 0 24px; gap: 4px; }
.tab-btn { color: rgba(255,255,255,.7); border: none; background: none; cursor: pointer;
           padding: 14px 20px; font-size: .9rem; font-weight: 600; border-bottom: 3px solid transparent;
           transition: color .15s, border-color .15s; }
.tab-btn:hover { color: white; }
.tab-btn.active { color: white; border-bottom-color: white; }
.tab-pane { display: none; }
.tab-pane.active { display: block; }

header { background: #0071CE; color: white; padding: 18px 28px;
         display: flex; align-items: center; gap: 14px; }
header h1 { font-size: 1.3rem; font-weight: 600; }
header .subtitle { opacity: .75; font-size: .85rem; }

/* ── Runs ── */
.runs { padding: 24px; display: flex; flex-direction: column; gap: 28px; }
.run-card { background: white; border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,.08); overflow: hidden; }
.run-header { padding: 16px 22px; border-bottom: 1px solid #eef0f4;
              display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.run-header .client { font-size: 1.1rem; font-weight: 700; color: #0071CE; }
.run-header .keyword { font-size: .95rem; color: #444; }
.run-header .ts { font-size: .8rem; color: #888; margin-left: auto; }
.run-header .badge { background: #eef7ff; color: #0071CE; border-radius: 20px;
                     padding: 3px 10px; font-size: .78rem; font-weight: 600; }
.run-header .html-link { font-size: .8rem; color: #0071CE; text-decoration: none;
                          font-weight: 600; padding: 3px 10px; border: 1px solid #0071CE;
                          border-radius: 20px; }
.run-header .html-link:hover { background: #eef7ff; }
.no-ads { padding: 22px; color: #999; font-style: italic; font-size: .9rem; }
.ad-grid { display: grid;
           grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
           gap: 18px; padding: 20px; }
.ad-card { border: 1px solid #e8eaf0; border-radius: 10px; overflow: hidden;
           background: #fafbfc; display: flex; flex-direction: column; }
.ad-card .ad-type-bar { height: 5px; }
.ad-card .ad-body { padding: 12px; flex: 1; display: flex; flex-direction: column; gap: 6px; }
.ad-card .type-label { display: inline-block; font-size: .72rem; font-weight: 700;
                        color: white; border-radius: 4px; padding: 2px 7px; }
.ad-card .brand { font-size: .9rem; font-weight: 600; color: #1a1a2e; }
.ad-card .title { font-size: .8rem; color: #555; }
.ad-card .img-wrap { background: #f0f2f5; min-height: 160px;
                     display: flex; align-items: center; justify-content: center; }
.ad-card img { max-width: 100%; max-height: 220px; object-fit: contain;
               display: block; cursor: zoom-in; }
.ad-card .no-img { color: #bbb; font-size: .78rem; padding: 16px; text-align: center; }
.summary-bar { display: flex; gap: 8px; flex-wrap: wrap; padding: 10px 22px 0; }
.type-chip { font-size: .75rem; font-weight: 600; color: white;
             border-radius: 20px; padding: 3px 10px; }

/* ── Full-page screenshot ── */
.fullpage-section { padding: 16px 22px 20px; border-top: 1px solid #eef0f4; }
.fullpage-section h3 { font-size: .82rem; font-weight: 600; color: #888;
                        text-transform: uppercase; letter-spacing: .05em; margin-bottom: 10px; }
.fullpage-thumb { border: 1px solid #e0e4ea; border-radius: 8px; overflow: hidden;
                  cursor: zoom-in; display: inline-block; max-width: 100%; }
.fullpage-thumb img { width: 100%; display: block; max-height: 300px;
                       object-fit: cover; object-position: top; }

/* ── Full-page lightbox (scrollable) ── */
#fp-lightbox { display:none; position:fixed; inset:0; background:rgba(0,0,0,.92);
               z-index:999; overflow-y:auto; }
#fp-lightbox.open { display:block; }
#fp-lightbox .fp-close { position:fixed; top:16px; right:20px; color:white; font-size:1.8rem;
                           cursor:pointer; z-index:1000; background:rgba(0,0,0,.4);
                           border-radius:50%; width:40px; height:40px; display:flex;
                           align-items:center; justify-content:center; line-height:1; }
#fp-lightbox img { display:block; margin:60px auto 40px; max-width:900px; width:90%;
                   border-radius:6px; box-shadow:0 8px 40px rgba(0,0,0,.7); }
#fp-lightbox .fp-hint { color:rgba(255,255,255,.5); text-align:center; font-size:.8rem;
                         padding-bottom:30px; }

/* ── Regular ad lightbox ── */
#lightbox { display:none; position:fixed; inset:0; background:rgba(0,0,0,.88);
            z-index:998; align-items:center; justify-content:center; cursor:zoom-out; }
#lightbox.open { display:flex; }
#lightbox img { max-width:92vw; max-height:92vh; object-fit:contain;
                border-radius:8px; box-shadow:0 8px 40px rgba(0,0,0,.7); }
"""

JS = r"""
// ── Tabs ──────────────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const target = btn.dataset.tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(target).classList.add('active');
  });
});

// ── Full-page scrollable lightbox ─────────────────────────────────────────────
const fpLb = document.getElementById('fp-lightbox');
const fpImg = document.getElementById('fp-img');

document.querySelectorAll('.fullpage-thumb').forEach(thumb => {
  thumb.addEventListener('click', () => {
    fpImg.src = thumb.querySelector('img').src;
    fpLb.classList.add('open');
    fpLb.scrollTop = 0;
  });
});
document.getElementById('fp-close').addEventListener('click', () => fpLb.classList.remove('open'));
fpLb.addEventListener('click', e => { if (e.target === fpLb) fpLb.classList.remove('open'); });

// ── Ad card lightbox ──────────────────────────────────────────────────────────
document.querySelectorAll('img[data-zoomable]').forEach(img => {
  img.addEventListener('click', e => {
    e.stopPropagation();
    document.getElementById('lb-img').src = img.src;
    document.getElementById('lightbox').classList.add('open');
  });
});
document.getElementById('lightbox').addEventListener('click', () =>
  document.getElementById('lightbox').classList.remove('open'));

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.getElementById('lightbox').classList.remove('open');
    document.getElementById('fp-lightbox').classList.remove('open');
  }
});
"""


def ad_card_html(ad: dict, client_root: Path) -> str:
    ad_type = ad.get("type", "Unknown")
    brand = ad.get("brand") or ""
    title = ad.get("title") or ad.get("subheadline") or ""
    color = ad_color(ad_type)
    img_url = resolve_image(ad, client_root)

    img_html = (
        f'<img src="{img_url}" alt="{brand}" loading="lazy" data-zoomable>'
        if img_url
        else '<div class="no-img">No image captured</div>'
    )

    return f"""
    <div class="ad-card">
      <div class="ad-type-bar" style="background:{color}"></div>
      <div class="img-wrap">{img_html}</div>
      <div class="ad-body">
        <span class="type-label" style="background:{color}">{ad_type}</span>
        {"<div class='brand'>" + brand + "</div>" if brand else ""}
        {"<div class='title'>" + title[:80] + "</div>" if title else ""}
      </div>
    </div>"""


def run_card_html(run: dict) -> str:
    client = run.get("client", "Unknown")
    keyword = run.get("keyword", "—")
    ts_raw = run.get("timestamp", "")
    try:
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).strftime("%b %d %Y  %H:%M")
    except Exception:
        ts = ts_raw

    ads = run.get("ads") or []
    client_root = run["_client_root"]

    type_counts: dict[str, int] = {}
    for a in ads:
        t = a.get("type", "Unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    chips = "".join(
        f'<span class="type-chip" style="background:{ad_color(t)}">{t} ×{n}</span>'
        for t, n in sorted(type_counts.items())
    )
    summary_bar = f'<div class="summary-bar">{chips}</div>' if chips else ""

    if not ads:
        ad_body = '<div class="no-ads">No ads captured in this run.</div>'
    else:
        cards = "".join(ad_card_html(a, client_root) for a in ads)
        ad_body = f'<div class="ad-grid">{cards}</div>'

    # Full-page screenshot
    fp_url = find_fullpage_for_run(run)
    if fp_url:
        fullpage_section = f"""
    <div class="fullpage-section">
      <h3>Full Page Screenshot</h3>
      <div class="fullpage-wrap">
        <img src="{fp_url}" alt="full page" loading="lazy" data-zoomable>
        <div class="expand-hint">Click to enlarge</div>
      </div>
    </div>"""
    else:
        fullpage_section = ""

    return f"""
  <div class="run-card">
    <div class="run-header">
      <span class="client">{client}</span>
      <span class="keyword">"{keyword}"</span>
      <span class="badge">{len(ads)} ad{"s" if len(ads) != 1 else ""}</span>
      <span class="ts">{ts}</span>
    </div>
    {summary_bar}
    {ad_body}
    {fullpage_section}
  </div>"""


def find_html_for_run(run: dict) -> str | None:
    """Return file:// URI of the captured search results HTML for this run."""
    json_path: Path = run["_json_path"]
    run_dir = json_path.parent
    # Primary: search_results_{run_id}.html
    run_id = run.get("run_id", "")
    candidate = run_dir / f"search_results_{run_id}.html"
    if candidate.exists():
        return candidate.as_uri()
    # Fallback: any search_results_*.html in the same dir
    matches = sorted(run_dir.glob("search_results_*.html"))
    if matches:
        return matches[-1].as_uri()
    return None


def run_card_html(run: dict) -> str:
    client = run.get("client", "Unknown")
    keyword = run.get("keyword", "—")
    ts_raw = run.get("timestamp", "")
    try:
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).strftime("%b %d %Y  %H:%M")
    except Exception:
        ts = ts_raw

    ads = run.get("ads") or []
    client_root = run["_client_root"]

    type_counts: dict[str, int] = {}
    for a in ads:
        t = a.get("type", "Unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    chips = "".join(
        f'<span class="type-chip" style="background:{ad_color(t)}">{t} ×{n}</span>'
        for t, n in sorted(type_counts.items())
    )
    summary_bar = f'<div class="summary-bar">{chips}</div>' if chips else ""

    if not ads:
        ad_body = '<div class="no-ads">No ads captured in this run.</div>'
    else:
        cards = "".join(ad_card_html(a, client_root) for a in ads)
        ad_body = f'<div class="ad-grid">{cards}</div>'

    # HTML link
    html_url = find_html_for_run(run)
    html_link = (
        f'<a class="html-link" href="{html_url}" target="_blank">View HTML</a>'
        if html_url else ""
    )

    # Full-page screenshot — thumbnail clicks open the scrollable lightbox
    fp_url = find_fullpage_for_run(run)
    if fp_url:
        fullpage_section = f"""
    <div class="fullpage-section">
      <h3>Full Page Screenshot</h3>
      <div class="fullpage-thumb">
        <img src="{fp_url}" alt="full page" loading="lazy">
      </div>
    </div>"""
    else:
        fullpage_section = ""

    return f"""
  <div class="run-card">
    <div class="run-header">
      <span class="client">{client}</span>
      <span class="keyword">"{keyword}"</span>
      <span class="badge">{len(ads)} ad{"s" if len(ads) != 1 else ""}</span>
      {html_link}
      <span class="ts">{ts}</span>
    </div>
    {summary_bar}
    {ad_body}
    {fullpage_section}
  </div>"""


def generate_html(runs: list[dict]) -> str:
    run_cards = "\n".join(run_card_html(r) for r in runs)
    now = datetime.now().strftime("%b %d %Y %H:%M")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Walmart Run Viewer</title>
  <style>{CSS}</style>
</head>
<body>
  <header>
    <div>
      <h1>📊 Walmart Run Viewer</h1>
      <div class="subtitle">Last {len(runs)} run{"s" if len(runs) != 1 else ""} · Generated {now}</div>
    </div>
  </header>

  <div class="runs">{run_cards}</div>

  <!-- Full-page scrollable lightbox -->
  <div id="fp-lightbox">
    <div class="fp-close" id="fp-close">✕</div>
    <img id="fp-img" src="" alt="full page">
    <div class="fp-hint">Scroll to see the full page · Click outside or press Esc to close</div>
  </div>

  <!-- Ad card lightbox -->
  <div id="lightbox"><img id="lb-img" src="" alt=""></div>

  <script>{JS}</script>
</body>
</html>"""


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="View last N Walmart scrape runs in browser")
    parser.add_argument("--n", type=int, default=5, help="Number of runs to show (default: 5)")
    parser.add_argument("--client", type=str, default=None, help="Filter to a specific client folder name")
    parser.add_argument("--no-open", action="store_true", help="Generate HTML but don't open browser")
    args = parser.parse_args()

    entries = find_run_jsons(args.client)
    if not entries:
        print("[error] No run_results JSON files found.", file=sys.stderr)
        sys.exit(1)

    entries = entries[: args.n]
    runs = [r for e in entries if (r := load_run(e)) is not None]

    if not runs:
        print("[error] Could not load any runs.", file=sys.stderr)
        sys.exit(1)

    print(f"[viewer] Loaded {len(runs)} run(s):")
    for r in runs:
        print(f"  {r.get('client')} | {r.get('keyword')} | {r.get('timestamp')} | {len(r.get('ads') or [])} ads")

    html = generate_html(runs)

    out = Path(tempfile.mktemp(suffix=".html", prefix="walmart_runs_"))
    out.write_text(html, encoding="utf-8")
    print(f"[viewer] HTML written to {out}")

    if not args.no_open:
        webbrowser.open(out.as_uri())
        print("[viewer] Opened in browser.")


if __name__ == "__main__":
    main()
