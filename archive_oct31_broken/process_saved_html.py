"""
Process Saved HTML Files for Ad Extraction

This script processes HTML files that have already been saved by test_session_persistence.py
to extract ad data without needing to use Playwright.
"""

import os
import shutil
import json
import glob
import argparse
import requests
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List
from bs4 import BeautifulSoup
from archived.kroger_ad_core import extract_ads_from_html, extract_common_words_and_phrases
from urllib.parse import urljoin


def run_id_from_ts(ts: str) -> str:
    """Convert YYYY-MM-DD_HH-MM-SS timestamp to YYYYMMDDHHMMSS run_id"""
    dt = datetime.strptime(ts, "%Y-%m-%d_%H-%M-%S")
    return dt.strftime("%Y%m%d%H%M%S")

def iso_z_from_ts(ts: str) -> str:
    """Convert YYYY-MM-DD_HH-MM-SS timestamp to ISO 8601 with Z"""
    dt = datetime.strptime(ts, "%Y-%m-%d_%H-%M-%S").replace(tzinfo=timezone.utc)
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")

def _load_core_for_retailer(retailer: str):
    """Load the appropriate ad_core module for the given retailer."""
    retailer = (retailer or "").lower()
    if retailer == "walmart":
        from archived import walmart_ad_core as core
        return core
    # default to Kroger
    from archived import kroger_ad_core as core
    return core


def process_html_to_run_results(runs_root: str, retailer: str, html_paths: List[str]) -> List[str]:
    """
    Parse the given HTML file(s) for `retailer`, write Kroger-shaped run_results JSON(s),
    and return the list of created JSON file paths.
    
    This is a simplified version for Walmart that mirrors Kroger's JSON structure.
    """
    created = []
    core = _load_core_for_retailer(retailer)

    for html_path in html_paths:
        try:
            with open(html_path, "r", encoding="utf-8") as f:
                html = f.read()
        except Exception as e:
            # skip unreadable files
            continue

        # Derive keyword & timestamp from filename if present, else fallback
        base = os.path.basename(html_path)
        # expected: search_results_{clean_kw}_{run_ts}.html
        # where run_ts format is YYYY-MM-DD_HH-MM-SS (contains dashes/hyphens)
        keyword = "search"
        run_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        # Use regex to extract timestamp in format YYYY-MM-DD_HH-MM-SS
        ts_match = re.search(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})', base)
        if ts_match:
            run_ts = ts_match.group(1)
            # Extract keyword from everything between "search_results_" and the timestamp
            prefix = "search_results_"
            if base.startswith(prefix):
                keyword_part = base[len(prefix):base.index(run_ts)].rstrip("_")
                if keyword_part:
                    keyword = keyword_part.replace("_", " ")
        elif base.startswith("search_results_"):
            # Fallback: use old parsing for backward compatibility
            parts = base.replace(".html","").split("_")
            if len(parts) >= 3 and parts[0] == "search" and parts[1] == "results":
                if len(parts) > 3:
                    keyword = "_".join(parts[2:-1]).replace("_", " ")
                else:
                    keyword = parts[2]
        
        # Build a core-level single result
        # Advertiser extraction now happens directly in walmart_ad_core.py
        result = core.extract_ads_from_html(
            html=html,
            keyword=keyword.replace("_"," "),
            timestamp=run_ts,
            source_file=html_path,
        )

        # Build the top-level Kroger-shaped JSON with a single results entry
        clean_kw = (result.get('search_term') or result.get('keyword') or 'search').replace(' ', '_').lower()
        results_path = os.path.join(runs_root, f"run_results_{clean_kw}_{run_ts}.json")

        # Build search URL from keyword for cookie seeding
        keyword_for_url = result.get('search_term') or result.get('keyword') or ''
        if retailer == "kroger":
            search_url = f"https://www.kroger.com/search?query={keyword_for_url.replace(' ', '+')}" if keyword_for_url else ""
        elif retailer == "walmart":
            search_url = f"https://www.walmart.com/search?q={keyword_for_url.replace(' ', '+')}" if keyword_for_url else ""
        else:
            search_url = ""

        run_results = {
            "count": result.get('count', 0),
            "keyword": result.get('keyword'),
            "search_term": result.get('search_term'),
            "timestamp": result.get('timestamp'),
            "source_file": result.get('source_file'),
            "retailer": retailer,  # Add retailer for downstream tools
            "url": search_url,  # Primary URL for extractors
            "srp_url": search_url,  # Alias for compatibility
            "results": [result],
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        try:
            with open(results_path, "w", encoding="utf-8") as f:
                json.dump(run_results, f, indent=2)
            created.append(results_path)
        except Exception:
            continue

    return created


# Import for TOA image capture
try:
    from PIL import Image
    from io import BytesIO
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Constants
DEFAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def parse_output_segments(p: Path) -> tuple[Optional[str], Optional[str]]:
    """
    Given a path, return (retailer, client) if path contains output/<retailer>/<client>/...
    Otherwise (None, None).
    """
    parts = list(p.resolve().parts)
    try:
        idx = parts.index("output")
    except ValueError:
        return None, None
    
    retailer = parts[idx + 1] if idx + 1 < len(parts) else None
    client = parts[idx + 2] if idx + 2 < len(parts) else None
    
    # Harden: ignore when 'runs' or None is in either slot
    if retailer in (None, "runs") or client in (None, "runs"):
        return None, None
    
    return retailer, client

def extract_toa_images(json_file, html_file=None, client_name=None, output_override=None):
    """
    Extract TOA images using screenshot_toa_image.py
    
    Args:
        json_file (str): Path to the JSON file with TOA data
        html_file (str, optional): Path to specific HTML file to process
        client_name (str): Client name for organizing output
        
        bool: True if successful, False otherwise
    """
    try:
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(here, "extractors", "screenshot_toa_image.py")
        
        # Build command to run extractors/screenshot_toa_image.py (headed by default)
        json_abs = os.path.abspath(json_file)
        cmd = ["python3", script_path, "--json", json_abs]

        # Add HTML file if provided; otherwise enable safe batch mode
        if html_file:
            html_abs = os.path.abspath(html_file)
            cmd.extend(["--html", html_abs])  # Using --html flag (short form is -f)
            # Parse timestamp from HTML filename (YYYY-MM-DD_HH-MM-SS) and pass through
            try:
                base = os.path.basename(html_file)
                ts_match = re.search(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})", base)
                if ts_match:
                    cmd.extend(["--timestamp", ts_match.group(1)])
            except Exception:
                pass
        else:
            # When not targeting a specific HTML file, allow batch mode but keep a time window to avoid old runs
            if "--allow-batch" not in cmd:
                cmd.append("--allow-batch")
            # Use a conservative time window so we don't reprocess old results
            cmd.extend(["--time-window", "15"])  # 15 minutes

        # Add output override (per-run directory) if provided
        if output_override:
            out_abs = os.path.abspath(output_override)
            cmd.extend(["--output", out_abs])
        # Add client name if provided (helps prevent incorrect derivation from paths)
        if client_name:
            cmd.extend(["--client", client_name])

        print(f"\n📷 Extracting TOA images using extractors/screenshot_toa_image.py...")
        try:
            print("   Command:", " ".join(cmd))
        except Exception:
            pass

        # Use subprocess.run to wait for completion
        try:
            # Set a timeout to prevent hanging indefinitely
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=900,
                cwd=here,
            )  # 900 second timeout to allow for per-client and browser locks

            # Parse and echo stdout/stderr for transparency
            saved_paths = []
            if result.stdout:
                try:
                    print("--- stdout ---")
                    print(result.stdout.rstrip())
                except Exception:
                    pass
                for line in result.stdout.splitlines():
                    m = re.search(r"Image screenshot saved to:\s*(.*)$", line)
                    if m:
                        saved_paths.append(m.group(1).strip())
            if result.stderr:
                try:
                    print("--- stderr ---")
                    print(result.stderr.rstrip())
                except Exception:
                    pass

            # If we targeted a specific HTML file, update its record in the daily JSON
            if html_file:
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        daily = json.load(f)
                    updated = False
                    for r in daily.get('results', []):
                        if os.path.normpath(r.get('source_file', '')) == os.path.normpath(html_file) or \
                           os.path.basename(r.get('source_file', '')) == os.path.basename(html_file):
                            if saved_paths:
                                r['image_files'] = saved_paths
                                r['images_collected'] = True
                                updated = True
                                break
                    if updated:
                        with open(json_file, 'w', encoding='utf-8') as f:
                            json.dump(daily, f, indent=2)
                        print(f"📝 Updated JSON with {len(saved_paths)} image file(s) for {os.path.basename(html_file)}")
                except Exception as e:
                    print(f"⚠️ Could not update JSON with image files: {e}")

            if result.returncode == 0:
                print("✅ TOA image extraction completed successfully")
                return True
            else:
                print(f"⚠️ TOA image extraction completed with issues (code {result.returncode})")
                return True  # Continue despite issues
        except subprocess.TimeoutExpired:
            print("⚠️ TOA image extraction timed out after 900 seconds (likely waiting on a lock); continuing anyway")
            return True
    except Exception as e:
        print(f"❌ Error starting TOA image extraction: {e}")
        return False

def process_specific_html_files(files, output_dir=None, force_images: bool = False):
    """Process only the specified HTML files.

    Args:
        files (list[str]): HTML file paths to process.
        output_dir (str | None): Optional client/output directory override.
        force_images (bool): When True, always run the screenshot extractor even if
            existing TOA/Skyscraper images are detected.
    """
    output_dir = output_dir or DEFAULT_DIR
    # Normalize file list and filter to existing files
    files = [f for f in files if os.path.exists(f)]
    if not files:
        print("No valid HTML files provided to --files")
        print("❌ No valid HTML files provided to --files")
        return False
    print(f"📃 Processing {len(files)} specific HTML file(s)")
    
    processed = 0

    def detect_client_from_path_local(html_path: str, fallback_output_dir: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        """
        Return (retailer, client) parsed from html_path or fallback_output_dir.
        """
        try:
            r, c = parse_output_segments(Path(html_path))
            if r and c:
                return r, c
        except Exception:
            pass
        
        # Try fallback_output_dir if it already points under output/<retailer>/<client>
        try:
            if fallback_output_dir:
                r, c = parse_output_segments(Path(fallback_output_dir))
                if r and c:
                    return r, c
        except Exception:
            pass
        
        return None, None

    def find_runs_root_from_html(html_path: str) -> Optional[str]:
        try:
            p = Path(html_path).resolve()
            last = None
            for parent in p.parents:
                if parent.name == "runs":
                    last = parent
            return str(last) if last else None
        except Exception:
            return None

    def compute_client_root_local(retailer: Optional[str], client: Optional[str], output_dir: Optional[str]) -> str:
        """
        Return absolute path to output/<retailer>/<client>.
        If unknown, return output_dir or DEFAULT_DIR as last resort.
        """
        base = Path(output_dir or DEFAULT_DIR).resolve()
        if retailer and client:
            # If base already is .../output/<retailer>/<client>, return as-is
            parts = list(base.parts)
            try:
                idx = parts.index("output")
                if idx + 2 < len(parts) and parts[idx + 1] == retailer and parts[idx + 2] == client:
                    return str(base)
            except ValueError:
                pass
            return str(Path(DEFAULT_DIR).resolve() / retailer / client)
        # Fall back to whatever output_dir is, or DEFAULT_DIR
        return str(base)

    def compute_runs_root_local(retailer: Optional[str], client: Optional[str], output_dir: Optional[str]) -> str:
        """
        Return absolute path to output/<retailer>/<client>/runs when retailer/client known,
        else fall back to <output_dir or DEFAULT>/runs.
        """
        client_root = compute_client_root_local(retailer, client, output_dir)
        return str(Path(client_root) / "runs")

    def normalize_output_layout(retailer: Optional[str], client: Optional[str], output_dir: Optional[str], html_path: str):
        """Normalize folder layout:
        - Ensure no ad-type subfolders live under runs/; move them to top-level client folder.
        - Move any top-level search_results_*.html into runs/.
        Safe to run repeatedly.
        """
        try:
            client_root = compute_client_root_local(retailer, client, output_dir)
            runs_root = compute_runs_root_local(retailer, client, output_dir)
            os.makedirs(client_root, exist_ok=True)
            os.makedirs(runs_root, exist_ok=True)

            # 1) Move any image files from runs/{TOA,Skyscraper,Carousel} to client_root/{...}
            for sub in ("TOA", "Skyscraper", "Carousel"):
                src_dir = os.path.join(runs_root, sub)
                dst_dir = os.path.join(client_root, sub)
                if os.path.isdir(src_dir):
                    os.makedirs(dst_dir, exist_ok=True)
                    for name in os.listdir(src_dir):
                        src = os.path.join(src_dir, name)
                        dst = os.path.join(dst_dir, name)
                        try:
                            if os.path.isfile(src):
                                if not os.path.exists(dst):
                                    shutil.move(src, dst)
                                else:
                                    # If same name exists, skip to avoid overwrite
                                    pass
                        except Exception:
                            pass
                    # Remove empty src_dir if now empty
                    try:
                        if not os.listdir(src_dir):
                            os.rmdir(src_dir)
                    except Exception:
                        pass

            # 2) Move any top-level HTMLs into runs/
            try:
                for fn in os.listdir(client_root):
                    if fn.startswith("search_results_") and fn.endswith(".html"):
                        src = os.path.join(client_root, fn)
                        dst = os.path.join(runs_root, fn)
                        if os.path.abspath(src) != os.path.abspath(dst) and not os.path.exists(dst):
                            shutil.move(src, dst)
            except Exception:
                pass

            # 3) Also move any stray search_results_*.html from known subfolders into runs/
            for sub in ("TOA", "Skyscraper", "Carousel"):
                try:
                    subdir = os.path.join(client_root, sub)
                    if os.path.isdir(subdir):
                        for fn in os.listdir(subdir):
                            if fn.startswith("search_results_") and fn.endswith(".html"):
                                src = os.path.join(subdir, fn)
                                dst = os.path.join(runs_root, fn)
                                if os.path.abspath(src) != os.path.abspath(dst) and not os.path.exists(dst):
                                    shutil.move(src, dst)
                except Exception:
                    pass

            # 4) Clean up empty runs/* ad type folders if they exist
            for sub in ("TOA", "Skyscraper", "Carousel"):
                try:
                    d = os.path.join(runs_root, sub)
                    if os.path.isdir(d) and not os.listdir(d):
                        os.rmdir(d)
                except Exception:
                    pass
        except Exception:
            # Non-fatal; normalization is best-effort
            pass
    for html_file in files:
        print(f"\n📝 Processing HTML file: {os.path.basename(html_file)}")
        result = extract_ads_from_html_file(html_file)
        if not result:
            continue
        
        # Derive retailer and client from path
        retailer, client = detect_client_from_path_local(html_file, output_dir)
        # Normalize layout before proceeding (idempotent)
        normalize_output_layout(retailer, client, output_dir, html_file)
        existing_runs_root = find_runs_root_from_html(html_file)
        in_runs_folder = bool(existing_runs_root)
        run_ts = parse_run_timestamp_from_filename(os.path.basename(html_file))
        if not run_ts:
            print("⚠️ Could not parse run timestamp from HTML filename; skipping per-run routing")
            continue
        
        # Compute the correct runs/ root
        runs_root = existing_runs_root or compute_runs_root_local(retailer, client, output_dir)
        os.makedirs(runs_root, exist_ok=True)

        # Build per-run JSON filename with keyword + timestamp
        clean_kw = (result.get('search_term') or result.get('keyword') or 'search').replace(' ', '_').lower()
        results_path = os.path.join(runs_root, f"run_results_{clean_kw}_{run_ts}.json")

        # Place/canonicalize HTML within runs_root
        try:
            new_html_path = os.path.join(runs_root, os.path.basename(html_file))
            src_dir = os.path.dirname(os.path.abspath(html_file))
            dst_dir = os.path.abspath(runs_root)
            client_root = compute_client_root_local(retailer, client, output_dir)
            if src_dir != dst_dir:
                # Move when source is already under output/<client> (including existing runs) to avoid duplicates
                if src_dir.startswith(os.path.abspath(client_root)):
                    shutil.move(html_file, new_html_path)
                    print(f"📦 Moved HTML into runs/: {new_html_path}")
                else:
                    shutil.copy2(html_file, new_html_path)
                    print(f"📥 Copied HTML into runs/: {new_html_path}")
            result['source_file'] = new_html_path
        except Exception as e:
            print(f"⚠️ Could not place HTML into runs/: {e}")

        # Build run-level JSON with top-level metadata and a single results entry
        # Build search URL from keyword for cookie seeding (Kroger-specific function)
        keyword_for_url = result.get('search_term') or result.get('keyword') or ''
        search_url = f"https://www.kroger.com/search?query={keyword_for_url.replace(' ', '+')}" if keyword_for_url else ""
        
        run_results = {
            "count": result.get('count', 0),
            "keyword": result.get('keyword'),
            "search_term": result.get('search_term'),
            "timestamp": result.get('timestamp'),
            "source_file": result.get('source_file'),
            "retailer": "kroger",  # Add retailer for downstream tools
            "url": search_url,  # Primary URL for extractors
            "srp_url": search_url,  # Alias for compatibility
            "results": [result],
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        processed += 1
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(run_results, f, indent=2)
        print(f"💾 Saved run JSON to {results_path}")
        
        # Canonical run JSON alongside legacy (safe during transition)
        try:
            # Compute client root and keyword
            retailer_name = retailer or "kroger"
            client_root = compute_client_root_local(retailer_name, client, output_dir)
            # Enforce ISO Z and run_id
            iso_ts = iso_z_from_ts(run_ts)
            run_id = run_id_from_ts(run_ts)
            # Build canonical payload
            canonical = {
                "retailer": "kroger",
                "client": client or os.path.basename(client_root),
                "keyword": (result.get("search_term") or result.get("keyword") or "").strip(),
                "timestamp": iso_ts,
                "run_id": run_id,
                "ads": result.get("ads", []),
            }
            # Write canonical alongside (named by run_id to be stable)
            canon_path = os.path.join(runs_root, f"run_results_{run_id}.json")
            with open(canon_path, "w", encoding="utf-8") as cf:
                json.dump(canonical, cf, indent=2, ensure_ascii=False)
            print(f"💾 Saved canonical run JSON to {canon_path}")
        except Exception as e:
            print(f"⚠️ Could not write canonical run JSON: {e}")
        
        # Track existing source files within this run only
        existing_sources = set()
        for r in run_results.get("results", []):
            sf = r.get('source_file')
            if sf:
                existing_sources.add(os.path.normpath(sf))
        
        # (Flattened runs format already saved above; skipping legacy append logic)
        
        # Trigger screenshot extraction for this HTML file.
        # Always run the extractor so fresh scrapes consistently produce images.
        target_html = result.get('source_file') or html_file
        client_root = compute_client_root_local(retailer, client, output_dir)
        # Pass client explicitly to prevent incorrect derivation from path
        extract_toa_images(results_path, target_html, client_name=client, output_override=client_root)
    
    print(f"✅ Processed {processed} specific file(s)")
    return True

def parse_run_timestamp_from_filename(filename):
    """Extract run timestamp (YYYY-MM-DD_HH-MM-SS) from search_results filename"""
    m = re.search(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})", filename)
    return m.group(1) if m else None

def parse_run_datetime_from_filename(filename):
    """Return a datetime object parsed from the filename's run timestamp, or None"""
    ts = parse_run_timestamp_from_filename(filename)
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None

def image_already_collected(html_path):
    """Check filesystem to determine if screenshots already exist for this HTML file."""
    try:
        base = os.path.basename(html_path)
        ts = parse_run_timestamp_from_filename(base)
        if not ts:
            return False
        # Extract keyword between prefix and timestamp
        m = re.search(r'^search_results_(.+?)_' + re.escape(ts) + r'\.html$', base)
        keyword_part = m.group(1) if m else None
        clean = keyword_part.lower() if keyword_part else None
        client_dir = os.path.basename(os.path.dirname(html_path))
        if not (clean and client_dir and client_dir != 'output'):
            return False
        base_out = os.path.join(DEFAULT_DIR, client_dir)
        runs_root = os.path.join(base_out, 'runs')
        import glob as _glob
        patterns = [
            # Legacy top-level locations (TOA, Skyscraper only)
            os.path.join(base_out, 'TOA', f"*_" + clean + f"_{ts}_*.png"),
            os.path.join(base_out, 'Skyscraper', f"*_" + clean + f"_{ts}_*.png"),
            # New runs/ locations (should be empty for images now, but check for legacy remnants)
            os.path.join(runs_root, 'TOA', f"*_" + clean + f"_{ts}_*.png"),
            os.path.join(runs_root, 'Skyscraper', f"*_" + clean + f"_{ts}_*.png"),
        ]
        for pat in patterns:
            if _glob.glob(pat):
                return True
    except Exception:
        return False
    return False

def find_latest_run_files(search_root, window_minutes=15):
    """Recursively find search_results_*.html files and return files for the latest run window.

    The window groups all files whose filename timestamp is within `window_minutes`
    before the latest observed timestamp. This accommodates runs that span multiple minutes
    due to multiple keywords.
    """
    from datetime import timedelta
    candidates = []
    for root, _, files in os.walk(search_root):
        for fn in files:
            if fn.startswith("search_results_") and fn.endswith(".html"):
                dt = parse_run_datetime_from_filename(fn)
                if dt:
                    full = os.path.join(root, fn)
                    # Skip files whose images already exist to minimize processing
                    if image_already_collected(full):
                        continue
                    candidates.append((dt, full))
    if not candidates:
        return None, []
    # Determine latest timestamp and include files within the window
    latest_dt = max(dt for dt, _ in candidates)
    cutoff = latest_dt - timedelta(minutes=window_minutes)
    latest_files = [f for dt, f in candidates if dt >= cutoff]
    # Return the latest timestamp string for logging
    latest_ts = latest_dt.strftime("%Y-%m-%d_%H-%M-%S")
    return latest_ts, sorted(latest_files)

def process_latest_run(search_root=None, output_dir=None, window_minutes=15, force_images=False):
    """Process only the HTML files that belong to the latest scheduled run across clients.

    Files are grouped by a time window ending at the latest filename timestamp.
    """
    search_root = search_root or DEFAULT_DIR
    output_dir = output_dir or DEFAULT_DIR
    latest_ts, files = find_latest_run_files(search_root, window_minutes=window_minutes)
    if not files:
        print(f"❌ No search_results_*.html files found under {search_root}/")
        return False
    print(f"🕒 Detected latest run window ending at: {latest_ts} with {len(files)} file(s)")
    return process_specific_html_files(files, output_dir, force_images=force_images)

def find_latest_missing_files(search_root, gap_minutes=2):
    """Find the newest group of HTML files that do NOT yet have images, grouped by small gaps.

    Sort all files by timestamp desc, drop any with existing images, then take a contiguous
    prefix where adjacent files differ by <= gap_minutes. This avoids using a fixed window.
    """
    from datetime import timedelta
    items = []
    for root, _, files in os.walk(search_root):
        for fn in files:
            if fn.startswith('search_results_') and fn.endswith('.html'):
                dt = parse_run_datetime_from_filename(fn)
                if not dt:
                    continue
                full = os.path.join(root, fn)
                if image_already_collected(full):
                    continue
                items.append((dt, full))
    if not items:
        return []
    items.sort(key=lambda x: x[0], reverse=True)
    # Take a contiguous prefix with small gaps
    selected = []
    prev_dt = None
    for dt, fp in items:
        if not selected:
            selected.append(fp)
            prev_dt = dt
        else:
            delta = (prev_dt - dt).total_seconds() / 60.0
            if delta <= gap_minutes:
                selected.append(fp)
                prev_dt = dt
            else:
                break
    return selected

def process_latest_missing(search_root=None, output_dir=None, gap_minutes=2, force_images=False):
    search_root = search_root or DEFAULT_DIR
    output_dir = output_dir or DEFAULT_DIR
    files = find_latest_missing_files(search_root, gap_minutes=gap_minutes)
    if not files:
        print(f"✅ No missing images detected for latest runs under {search_root}/")
        return True
    print(f"🖼️ Processing {len(files)} file(s) without images; gap threshold = {gap_minutes} minute(s)")
    return process_specific_html_files(files, output_dir, force_images=force_images)

def remove_html_from_ads(ads):
    """Remove HTML content from ads to reduce JSON size"""
    for ad in ads:
        if 'html' in ad:
            del ad['html']
    return ads

def filter_kroji_ads(ads):
    """Filter out Kroji house ads (Kroger mascot)"""
    filtered = []
    kroji_count = 0
    
    for ad in ads:
        # Check message field
        message = ad.get('message', '')
        if 'kroji' in message.lower():
            kroji_count += 1
            continue
        
        # Check header field
        header = ad.get('header', '')
        if 'kroji' in header.lower():
            kroji_count += 1
            continue
        
        # Check advertisers
        advertisers = ad.get('advertisers', [])
        if any('kroji' in str(adv).lower() for adv in advertisers):
            kroji_count += 1
            continue
        
        filtered.append(ad)
    
    if kroji_count > 0:
        print(f"  Filtered out {kroji_count} Kroji house ad(s)")
    
    return filtered

def dedupe_ads(ads):
    """Conservatively deduplicate ads that are likely the same unit with different types.

    - Prefer TOA over Skyscraper when keys collide.
    - Use image_url if present as the primary key; else fallback to (href, message).
    - Does not remove unique Skyscraper ads; only trims true duplicates.
    """
    priority = {"TOA": 3, "SkyscraperTOA": 2, "Skyscraper": 1, "CuratedCarousel": 0}
    def norm_url(u):
        try:
            if not u:
                return None
            if u.startswith('/'):
                return f"https://www.kroger.com{u}"
            return u
        except Exception:
            return u

    selected = {}
    for ad in ads or []:
        ad_type = ad.get('type') or 'TOA'
        img = norm_url(ad.get('image_url'))
        href = norm_url(ad.get('href'))
        msg = (ad.get('message') or '').strip()

        if img:
            key = ("img", img)
        elif href or msg:
            key = ("hm", href or '', msg)
        else:
            # No stable key; keep as-is with a unique nonce
            key = ("idx", id(ad))

        existing = selected.get(key)
        if not existing:
            selected[key] = ad
            continue

        # If existing present, keep the one with higher priority
        cur_p = priority.get(ad_type, 0)
        ex_p = priority.get(existing.get('type') or 'TOA', 0)
        if cur_p > ex_p:
            selected[key] = ad

    return list(selected.values())

def extract_ads_from_html_file(html_file, process_images_for_html=None):
    """Extract ad data from a saved HTML file"""
    print(f"\n📝 Processing HTML file: {os.path.basename(html_file)}")
    
    try:
        # Read the HTML file
        with open(html_file, 'r', encoding='utf-8') as f:
            html = f.read()
        
        # Try to extract keyword and timestamp from filename
        keyword = None
        run_timestamp = None
        filename = os.path.basename(html_file)
        if filename.startswith("search_results_"):
            # Extract search term from filename
            # Format is typically search_results_SEARCH_TERM_TIMESTAMP.html
            # Extract everything between search_results_ and the timestamp
            timestamp_pattern = r'_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})'
            match = re.search(timestamp_pattern, filename)
            
            if match:
                # Get everything between 'search_results_' and the timestamp
                keyword_part = filename[len('search_results_'):match.start()]
                keyword = keyword_part.replace('_', ' ').strip()
                # Extract the timestamp for consistent filename generation
                run_timestamp = match.group(1)
            else:
                # Fallback to old method
                parts = filename.replace("search_results_", "").split("_")
                if len(parts) > 1:
                    # Last part is usually the timestamp
                    keyword = "_".join(parts[:-1])
                    keyword = keyword.replace("_", " ")
                    
                # Try to extract search term from page title or search input
                soup = BeautifulSoup(html, 'html.parser')
                
                # Method 1: Look for search query in title
                title = soup.title.text if soup.title else ""
                if "Search:" in title:
                    search_term = title.split("Search:")[1].strip()
                    keyword = search_term
                
                # Method 2: Look for search input value
                if not keyword:
                    search_input = soup.select_one('input[type="search"]')
                    if search_input and search_input.get('value'):
                        keyword = search_input.get('value')
                
                # Method 3: Look for search term in URL
                if not keyword:
                    meta_refresh = soup.select_one('meta[http-equiv="refresh"]')
                    if meta_refresh and 'query=' in meta_refresh.get('content', ''):
                        content = meta_refresh.get('content')
                        query_part = content.split('query=')[1].split('&')[0]
                        keyword = query_part.replace('%20', ' ')
                
                # Fallback: Use the filename parts without timestamp
                if not keyword:
                    keyword = "_".join(parts[:-1]).replace(".html", "").replace("_", " ")
        
        # Get client name from directory path
        client = None
        dir_path = os.path.dirname(html_file)
        if "output" in dir_path:
            # If HTML is in runs/ subdirectory, go up one level to get client
            client_dir = os.path.basename(dir_path)
            if client_dir == "runs":
                client_dir = os.path.basename(os.path.dirname(dir_path))
            if client_dir != "output":  # Make sure it's not the main output dir
                client = client_dir
        
        # Find corresponding screenshot in main subfolder
        screenshot_path = None
        if client:
            main_dir = os.path.join(dir_path, "main")
            if os.path.exists(main_dir):
                # Get the base filename without extension
                base_filename = os.path.splitext(filename)[0]
                # Look for matching screenshot
                screenshot_candidates = glob.glob(os.path.join(main_dir, f"{base_filename}.png"))
                if screenshot_candidates:
                    screenshot_path = screenshot_candidates[0]
        
        # Extract all ads from the HTML (pass timestamp for consistent carousel filenames)
        ads = extract_ads_from_html(
            html, 
            client=client, 
            search_term=keyword,
            timestamp=run_timestamp,
            source_file=html_file
        )
        
        # Remove HTML content from ads to reduce JSON size
        ads = remove_html_from_ads(ads)
        # Conservatively de-duplicate overlapping TOA/Skyscraper units
        ads = dedupe_ads(ads)
        # Filter out Kroji house ads (Kroger mascot)
        ads = filter_kroji_ads(ads)
        
        # Create TOA subfolder for images
        if client:
            toa_dir = os.path.join(os.path.dirname(html_file), "TOA")
            os.makedirs(toa_dir, exist_ok=True)
        
        # Get titles for analysis
        titles = [ad.get('message', '') for ad in ads if ad.get('message')]
        analysis = extract_common_words_and_phrases(titles)
        
        # Determine a stable run timestamp from filename if available
        run_ts = parse_run_timestamp_from_filename(filename)
        if run_ts:
            try:
                ts_for_json = datetime.strptime(run_ts, "%Y-%m-%d_%H-%M-%S").strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                ts_for_json = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            ts_for_json = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return {
            'ads': ads,
            'analysis': analysis,
            'count': len(ads),
            'keyword': keyword,
            'search_term': keyword,  # Adding search_term field explicitly
            'timestamp': ts_for_json,
            'source_file': html_file
        }
        
    except FileNotFoundError as e:
        print(f"❌ File not found error: {e}")
        return None
    except (ValueError, AttributeError, TypeError) as e:
        print(f"❌ Error processing HTML file: {e}")
        return None

def get_daily_results_file(output_dir):
    """Get the path to the daily results file"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Create TOA subfolder if it doesn't exist
    toa_dir = os.path.join(output_dir, "TOA")
    os.makedirs(toa_dir, exist_ok=True)
    
    return os.path.join(toa_dir, f"toa_results_{today}.json")

def load_existing_results(results_path):
    """Load existing results from the daily file if it exists"""
    if os.path.exists(results_path):
        try:
            with open(results_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load existing results: {e}")
            return {"results": []}
    return {"results": []}

def process_latest_html_file(input_dir=None, output_dir=None, force_images=False):
    """Process the most recently saved HTML file"""
    # Use default directories if not provided
    input_dir = input_dir or DEFAULT_DIR
    output_dir = output_dir or DEFAULT_DIR
    
    # Find the latest HTML file
    html_files = glob.glob(os.path.join(input_dir, "search_results_*.html"))
    if not html_files:
        print(f"❌ No HTML files found in the input directory: {input_dir}")
        return False
    
    # Sort by modification time (newest first)
    latest_html = max(html_files, key=os.path.getmtime)
    print(f"���� Found latest HTML file: {os.path.basename(latest_html)}")
    
    # Process the HTML file
    results = extract_ads_from_html_file(latest_html)
    if not results:
        return False
    
    # Get the daily results file path
    os.makedirs(output_dir, exist_ok=True)
    results_path = get_daily_results_file(output_dir)
    
    # Load existing results or create new structure
    daily_results = load_existing_results(results_path)
    
    # Append new results
    daily_results["results"].append(results)
    daily_results["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Save the updated results
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(daily_results, f, indent=2)
    
    print(f"✅ Found {results['count']} TOAs")
    print(f"💾 Results saved to {results_path}")
    
    # Extract TOA images only for the specific HTML file if requested
    # if process_images_for_html and process_images_for_html == html_file:
    #     print(f"🖼️ Processing images for current HTML file: {os.path.basename(html_file)}")
    #     # Extract client name from the directory structure
    #     client_name = None
    #     dir_path = os.path.dirname(html_file)
    #     if dir_path:
    #         client_dir = os.path.basename(dir_path)
    #         if client_dir != "output":
    #             client_name = client_dir
        
    #     # Call image extraction for this specific HTML file only
    #     extract_toa_images(results_path, html_file, client_name)
    # else:
    print(f"🖼️ Processing images for current HTML file: {os.path.basename(latest_html)}")

    # Extract client name from the directory structure
    client_name = None
    dir_path = os.path.dirname(latest_html)
    if dir_path:
        client_dir = os.path.basename(dir_path)
        if client_dir != "output":
            client_name = client_dir

    # Call image extraction for this specific HTML file only
    extract_toa_images(results_path, latest_html, client_name)
    
    # NOTE: Carousel images are now captured directly in archived/kroger_search_and_capture.py
    # No need to extract carousel images here anymore
    
    # Print some details about the ads found
    if results['ads']:
        print("\n📋 TOA Details:")
        for i, ad in enumerate(results['ads'], 1):
            print(f"  Ad #{i}: {ad.get('message', 'No message')}")
            print(f"    - Description: {ad.get('description', 'None')}")
            print(f"    - CTA: {ad.get('cta', 'None')}")
            print(f"    - Brand: {ad.get('brand', 'Unknown')}")
            print()
    
    return True

def process_all_html_files(input_dir=None, output_dir=None, force_images=False):
    """Process all HTML files in the input directory"""
    # Use default directories if not provided
    input_dir = input_dir or DEFAULT_DIR
    output_dir = output_dir or DEFAULT_DIR
    
    html_files = glob.glob(os.path.join(input_dir, "search_results_*.html"))
    if not html_files:
        print(f"❌ No HTML files found in the input directory: {input_dir}")
        return False
    
    print(f"📃 Found {len(html_files)} HTML files to process")
    
    # Get the daily results file path
    os.makedirs(output_dir, exist_ok=True)
    results_path = get_daily_results_file(output_dir)
    
    # Load existing results or create new structure
    daily_results = load_existing_results(results_path)
    
    # Group HTML files by search term
    search_term_files = {}
    
    # Process each HTML file and organize by search term
    for html_file in html_files:
        # Extract data from the file
        result = extract_ads_from_html_file(html_file)
        if not result:
            continue
            
        # Get the search term
        search_term = result.get('keyword')
        if not search_term:
            # Use filename as fallback
            filename = os.path.basename(html_file)
            search_term = filename.replace("search_results_", "").split("_")[0]
        
        # Add to the appropriate group
        if search_term not in search_term_files:
            search_term_files[search_term] = []
        
        search_term_files[search_term].append(result)
    
    # Process each search term group
    processed_count = 0
    for search_term, results_list in search_term_files.items():
        if not results_list:
            continue
            
        # Sort results by timestamp (newest first)
        results_list.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Include ONLY the newest result for this search term
        for result in results_list[:1]:
            # Make sure the keyword is set correctly
            result['keyword'] = search_term
            result['search_term'] = search_term  # Ensure search_term is set
            
            # Add to daily results
            daily_results["results"].append(result)
            processed_count += 1
    
    # Update timestamp
    daily_results["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Save the updated results
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(daily_results, f, indent=2)
    
    print(f"✅ Processed {processed_count} search terms from {len(html_files)} HTML files")
    print(f"💾 Combined results saved to {results_path}")
    
    # Process TOA images ONCE from the combined results
    print("\n📷 Extracting TOA images from combined results...")
    extract_toa_images(results_path, client_name=os.path.basename(output_dir))
    # Note: force_images is ignored for combined results as this is a different path
    
    return True

if __name__ == "__main__":
    print("\n" + "="*50)
    print("KROGER TOA HTML PROCESSOR")
    print("="*50)
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Process saved HTML files to extract TOA data")
    parser.add_argument("--input-dir", "-i", type=str, help="Directory containing HTML files to process")
    parser.add_argument("--output-dir", "-o", type=str, help="Directory to save extracted TOA data")
    parser.add_argument("--all", "-a", action="store_true", help="Process all HTML files instead of just the latest")
    parser.add_argument("--all-files", action="store_true", help="Process all HTML files instead of just the latest")
    parser.add_argument("--latest-run", action="store_true", help="Process only the latest scheduled run across clients (grouped by filename timestamp and time window)")
    parser.add_argument("--run-window-minutes", type=int, default=15, help="Minutes to include before the latest timestamp to define a run window (default: 15)")
    parser.add_argument("--latest-missing", action="store_true", help="Process only the newest group of HTML files that do not yet have images (gap-based)")
    parser.add_argument("--missing-gap-minutes", type=int, default=2, help="Max allowed gap in minutes between consecutive files to group as one run (default: 2)")
    parser.add_argument("--files", "-F", nargs="+", help="Specific HTML file(s) to process")
    parser.add_argument("--force-images", action="store_true", help="Bypass all 'already exists' checks and always generate fresh TOA/Skyscraper images")
    args = parser.parse_args()
    
    # Process HTML files
    if args.files:
        success = process_specific_html_files(args.files, args.output_dir, force_images=args.force_images)
    elif args.latest_run:
        # Search root defaults to input-dir if provided, else DEFAULT_DIR
        search_root = args.input_dir or DEFAULT_DIR
        success = process_latest_run(search_root, args.output_dir, window_minutes=args.run_window_minutes, force_images=args.force_images)
    elif args.latest_missing:
        search_root = args.input_dir or DEFAULT_DIR
        success = process_latest_missing(search_root, args.output_dir, gap_minutes=args.missing_gap_minutes, force_images=args.force_images)
    elif args.all or args.all_files:
        success = process_all_html_files(args.input_dir, args.output_dir, force_images=args.force_images)
    else:
        success = process_latest_html_file(args.input_dir, args.output_dir, force_images=args.force_images)
    
    if success:
        print("\n✅ TOA EXTRACTION COMPLETED SUCCESSFULLY")
    else:
        print("\n❌ TOA EXTRACTION FAILED")
