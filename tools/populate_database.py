#!/usr/bin/env python3
"""
Populate the local Supabase PostgreSQL database from existing JSON files.

Usage:
    python3 tools/populate_database.py [--brands] [--logos] [--schedules] [--runs] [--all]

If no flags are given, defaults to --all.
"""

import argparse
import glob
import json
import os
import sys
import time
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BRANDS_JSON = os.path.join(PROJECT_ROOT, "config", "brands.json")
LOGO_DB_JSON = os.path.join(PROJECT_ROOT, "output", "brand_logos", "brand_logo_database.json")
SCHEDULES_DIR = os.path.join(PROJECT_ROOT, "schedules")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")


def get_conn():
    return psycopg2.connect(DB_URL)


# ---------------------------------------------------------------------------
# 1. Brands + Synonyms
# ---------------------------------------------------------------------------
def populate_brands(conn):
    print("\n=== Populating brands + synonyms ===")
    with open(BRANDS_JSON) as f:
        brands = json.load(f)

    cur = conn.cursor()

    # Clear existing
    cur.execute("DELETE FROM brand_synonyms")
    cur.execute("DELETE FROM brand_logos")
    cur.execute("DELETE FROM ad_brands")
    cur.execute("DELETE FROM brands")
    conn.commit()

    brand_count = 0
    synonym_count = 0

    for b in brands:
        name = b.get("name", "").strip()
        if not name:
            continue
        verified = b.get("verified", False)
        cur.execute(
            "INSERT INTO brands (name, verified) VALUES (%s, %s) RETURNING id",
            (name, verified),
        )
        brand_id = cur.fetchone()[0]
        brand_count += 1

        for syn in b.get("synonyms", []):
            syn = syn.strip()
            if not syn:
                continue
            try:
                cur.execute(
                    "INSERT INTO brand_synonyms (brand_id, synonym) VALUES (%s, %s)",
                    (brand_id, syn),
                )
                synonym_count += 1
            except psycopg2.errors.UniqueViolation:
                conn.rollback()

    conn.commit()
    print(f"  Inserted {brand_count} brands, {synonym_count} synonyms")


# ---------------------------------------------------------------------------
# 2. Brand Logos
# ---------------------------------------------------------------------------
def populate_logos(conn):
    print("\n=== Populating brand logos ===")
    if not os.path.exists(LOGO_DB_JSON):
        print(f"  Logo database not found: {LOGO_DB_JSON}")
        return

    with open(LOGO_DB_JSON) as f:
        logo_db = json.load(f)

    logo_brands = logo_db.get("brands", {})
    cur = conn.cursor()

    # Build brand name → id lookup
    cur.execute("SELECT id, name_lower FROM brands")
    brand_lookup = {row[1]: row[0] for row in cur.fetchall()}

    inserted = 0
    skipped = 0

    for key, entry in logo_brands.items():
        brand_name = entry.get("brand_name", key)
        brand_id = brand_lookup.get(brand_name.lower())

        if not brand_id:
            # Try to insert the brand
            try:
                cur.execute(
                    "INSERT INTO brands (name, verified) VALUES (%s, %s) RETURNING id",
                    (brand_name, entry.get("verified", False)),
                )
                brand_id = cur.fetchone()[0]
                brand_lookup[brand_name.lower()] = brand_id
                conn.commit()
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                cur.execute(
                    "SELECT id FROM brands WHERE name_lower = %s",
                    (brand_name.lower(),),
                )
                row = cur.fetchone()
                if row:
                    brand_id = row[0]
                else:
                    skipped += 1
                    continue

        logo_file = entry.get("logo_file", "")
        if not logo_file:
            skipped += 1
            continue

        source = entry.get("source", "")
        verified = entry.get("verified", False)
        verified_at = entry.get("verified_at")
        source_url = entry.get("source_url") or entry.get("url")
        md5_hash = entry.get("md5_hash")
        retailer = entry.get("retailer")
        first_seen = entry.get("first_seen")
        last_seen = entry.get("last_seen") or entry.get("updated_at")

        try:
            cur.execute(
                """INSERT INTO brand_logos
                   (brand_id, logo_file, source, verified, verified_at,
                    source_url, md5_hash, retailer, first_seen, last_seen)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (brand_id, logo_file, source, verified, verified_at,
                 source_url, md5_hash, retailer, first_seen, last_seen),
            )
            inserted += 1
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            skipped += 1

    conn.commit()
    print(f"  Inserted {inserted} logos, skipped {skipped}")


# ---------------------------------------------------------------------------
# 3. Schedules
# ---------------------------------------------------------------------------
def populate_schedules(conn):
    print("\n=== Populating schedules ===")
    cur = conn.cursor()
    cur.execute("DELETE FROM schedules")
    conn.commit()

    sched_files = glob.glob(os.path.join(SCHEDULES_DIR, "*.json"))
    inserted = 0

    for sf in sched_files:
        if "master" in os.path.basename(sf).lower():
            continue
        try:
            with open(sf) as f:
                s = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        schedule_id = s.get("id", os.path.basename(sf).replace(".json", ""))
        retailer = s.get("retailer", "")
        client = s.get("client", "")
        keywords = s.get("keywords", [])
        days = s.get("days", [])
        times = s.get("times", [])
        enabled = s.get("enabled", True)
        tz = s.get("tz", "")

        try:
            cur.execute(
                """INSERT INTO schedules
                   (schedule_id, retailer, client, keywords, days, times, enabled, tz)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (schedule_id, retailer, client, keywords, days, times, enabled, tz),
            )
            inserted += 1
        except psycopg2.errors.UniqueViolation:
            conn.rollback()

    conn.commit()
    print(f"  Inserted {inserted} schedules from {len(sched_files)} files")


# ---------------------------------------------------------------------------
# 4. Runs + Ads
# ---------------------------------------------------------------------------
def _parse_timestamp(ts_str):
    """Try to parse various timestamp formats into a datetime."""
    if not ts_str:
        return None
    # Strip trailing Z and treat as UTC
    ts_str = ts_str.strip()
    for fmt in [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d_%H-%M-%S",
    ]:
        try:
            dt = datetime.strptime(ts_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _extract_run_id_from_path(json_path):
    """Try to extract a run_id from the filename."""
    basename = os.path.basename(json_path)
    # Pattern: run_results_<run_id>.json or run_results_<retailer>_<client>_<run_id>.json
    # Try to find a 14-digit timestamp
    import re
    m = re.search(r'(\d{14})', basename)
    if m:
        return m.group(1)
    # Try date-time pattern: 2025-12-04_20-13-00
    m = re.search(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})', basename)
    if m:
        return m.group(1).replace("-", "").replace("_", "")
    return basename.replace(".json", "")


def populate_runs(conn):
    print("\n=== Populating runs + ads ===")
    cur = conn.cursor()

    # Clear existing
    cur.execute("DELETE FROM ad_brands")
    cur.execute("DELETE FROM ads")
    cur.execute("DELETE FROM runs")
    conn.commit()

    # Build brand lookup for ad_brands
    cur.execute("SELECT id, name_lower FROM brands")
    brand_lookup = {row[1]: row[0] for row in cur.fetchall()}
    # Also index synonyms
    cur.execute("SELECT brand_id, syn_lower FROM brand_synonyms")
    for row in cur.fetchall():
        if row[1] not in brand_lookup:
            brand_lookup[row[1]] = row[0]

    json_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "*", "*", "runs", "**", "*.json"), recursive=True))
    print(f"  Found {len(json_files)} run JSON files")

    run_count = 0
    ad_count = 0
    error_count = 0
    batch_size = 500
    start_time = time.time()

    for i, jf in enumerate(json_files):
        if i > 0 and i % 1000 == 0:
            elapsed = time.time() - start_time
            rate = i / elapsed
            eta = (len(json_files) - i) / rate if rate > 0 else 0
            print(f"  Progress: {i}/{len(json_files)} files "
                  f"({run_count} runs, {ad_count} ads) "
                  f"[{rate:.0f} files/s, ETA {eta:.0f}s]")

        try:
            with open(jf) as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            error_count += 1
            continue

        # Determine retailer from path: output/<retailer>/<client>/runs/...
        rel_path = os.path.relpath(jf, OUTPUT_DIR)
        parts = rel_path.split(os.sep)
        if len(parts) < 3:
            error_count += 1
            continue

        retailer = parts[0]
        client = parts[1]

        # Skip non-run files (e.g. meta files)
        if "ads" not in data and "results" not in data:
            continue

        # Extract fields
        keyword = data.get("keyword") or data.get("search_term") or ""
        ts_str = data.get("timestamp", "")
        ts = _parse_timestamp(ts_str)
        if not ts:
            # Try to extract from filename
            run_id_str = _extract_run_id_from_path(jf)
            if len(run_id_str) == 14 and run_id_str.isdigit():
                try:
                    ts = datetime.strptime(run_id_str, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
        if not ts:
            ts = datetime(2025, 1, 1, tzinfo=timezone.utc)  # fallback

        run_id_val = data.get("run_id") or _extract_run_id_from_path(jf)

        # Collect ads from either canonical or legacy format
        ads_list = []
        if "ads" in data and isinstance(data["ads"], list):
            ads_list = data["ads"]
        elif "results" in data and isinstance(data["results"], list):
            for result in data["results"]:
                if isinstance(result, dict) and "ads" in result:
                    ads_list.extend(result["ads"])

        # Deduplicate run_id per retailer
        unique_run_id = f"{run_id_val}_{hash(jf) % 100000:05d}"

        try:
            cur.execute(
                """INSERT INTO runs (retailer, client, keyword, run_id, timestamp, json_path, ad_count)
                   VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (retailer, client, keyword, unique_run_id, ts, rel_path, len(ads_list)),
            )
            db_run_id = cur.fetchone()[0]
            conn.commit()
            run_count += 1
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            error_count += 1
            continue

        # Insert ads
        for ad in ads_list:
            if not isinstance(ad, dict):
                continue

            ad_type = ad.get("type", "Unknown")
            brand = ad.get("brand") or ad.get("brand_canonical")
            if not brand and ad.get("advertisers"):
                advs = ad["advertisers"]
                if isinstance(advs, list) and advs:
                    brand = advs[0]

            # Extract metadata (everything that doesn't have a dedicated column)
            metadata_keys = {"has_video_container", "has_product_container",
                             "has_product_image", "has_product_title",
                             "sbv_structure_detected", "video_overlay",
                             "slot", "bbox", "selector", "index"}
            metadata = {}
            for mk in metadata_keys:
                if mk in ad:
                    metadata[mk] = ad[mk]
            if ad.get("metadata") and isinstance(ad["metadata"], dict):
                metadata.update(ad["metadata"])

            slot_val = metadata.pop("slot", ad.get("slot"))
            # slot column is INTEGER; non-numeric values go into metadata
            if isinstance(slot_val, int):
                slot = slot_val
            elif isinstance(slot_val, str) and slot_val.isdigit():
                slot = int(slot_val)
            else:
                slot = None
                if slot_val is not None:
                    metadata["slot_label"] = slot_val

            try:
                cur.execute(
                    """INSERT INTO ads
                       (run_id, original_id, module_id, ad_type, ad_subtype, slot,
                        brand, brand_logo_path, title, message, description, cta, href,
                        image_url, image_path, video_url, video_path,
                        product_image_url, product_title, product_description, metadata)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       RETURNING id""",
                    (
                        db_run_id,
                        ad.get("id"),
                        ad.get("module_id"),
                        ad_type,
                        ad.get("subtype"),
                        slot,
                        brand,
                        ad.get("brand_logo"),
                        ad.get("title"),
                        ad.get("message"),
                        ad.get("description"),
                        ad.get("cta"),
                        ad.get("href"),
                        ad.get("image_url"),
                        ad.get("image_path") or ad.get("screenshot") or ad.get("screenshot_path"),
                        ad.get("video_url"),
                        ad.get("video_path"),
                        ad.get("product_image_url"),
                        ad.get("product_title"),
                        ad.get("product_description"),
                        json.dumps(metadata) if metadata else None,
                    ),
                )
                db_ad_id = cur.fetchone()[0]
                ad_count += 1

                # Insert ad_brands junction rows
                advertisers = ad.get("advertisers", [])
                if isinstance(advertisers, list):
                    for adv in advertisers:
                        adv_lower = adv.strip().lower() if isinstance(adv, str) else ""
                        bid = brand_lookup.get(adv_lower)
                        if bid:
                            try:
                                cur.execute(
                                    "INSERT INTO ad_brands (ad_id, brand_id) VALUES (%s, %s)",
                                    (db_ad_id, bid),
                                )
                            except psycopg2.errors.UniqueViolation:
                                conn.rollback()
                elif brand:
                    bid = brand_lookup.get(brand.strip().lower())
                    if bid:
                        try:
                            cur.execute(
                                "INSERT INTO ad_brands (ad_id, brand_id) VALUES (%s, %s)",
                                (db_ad_id, bid),
                            )
                        except psycopg2.errors.UniqueViolation:
                            conn.rollback()

            except Exception as e:
                conn.rollback()
                error_count += 1
                if error_count <= 10:
                    print(f"  Error inserting ad: {e}")
                continue

        # Insert slots[] — the full ordered page view including SPs, PLs, etc.
        # Each slot becomes an ads row; slots already covered by ads[] are skipped
        # via the original_id dedup key "slot:<run_id_val>:<slot_idx>".
        slots_list = data.get("slots", [])
        if isinstance(slots_list, list):
            for slot_entry in slots_list:
                if not isinstance(slot_entry, dict):
                    continue
                slot_idx = slot_entry.get("slot")
                if slot_idx is None:
                    continue

                # Stable dedup key for this slot within this run
                slot_original_id = f"slot:{run_id_val}:{slot_idx}"

                # Skip if already in DB (e.g. from ads[] pass above)
                cur.execute(
                    "SELECT id FROM ads WHERE run_id=%s AND original_id=%s LIMIT 1",
                    (db_run_id, slot_original_id),
                )
                if cur.fetchone():
                    continue

                ad_type = slot_entry.get("ad_type", "Unknown")
                brand = slot_entry.get("brand") or None
                product_id = slot_entry.get("product_id") or None

                slot_metadata = {
                    "slot_within_type":    slot_entry.get("slot_within_type"),
                    "total_slots":         slot_entry.get("total_slots"),
                    "total_slots_of_type": slot_entry.get("total_slots_of_type"),
                    "is_sponsored":        slot_entry.get("is_sponsored"),
                    "matched_ad_index":    slot_entry.get("matched_ad_index"),
                }
                if slot_entry.get("slot_location"):
                    slot_metadata["slot_location"] = slot_entry["slot_location"]
                if product_id:
                    slot_metadata["product_id"] = product_id

                try:
                    cur.execute(
                        """INSERT INTO ads
                           (run_id, original_id, ad_type, ad_subtype, slot,
                            brand, title, href,
                            image_url, image_path,
                            metadata)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (
                            db_run_id,
                            slot_original_id,
                            ad_type,
                            "sponsored_product" if slot_entry.get("is_sponsored") else "organic_product",
                            slot_idx,
                            brand,
                            slot_entry.get("title") or None,
                            slot_entry.get("href") or None,
                            slot_entry.get("image_url") or None,
                            slot_entry.get("image_path") or None,
                            json.dumps(slot_metadata),
                        ),
                    )
                    ad_count += 1
                except Exception as e:
                    conn.rollback()
                    error_count += 1
                    if error_count <= 10:
                        print(f"  Error inserting slot ad: {e}")
                    continue

        # Commit every batch_size files
        if run_count % batch_size == 0:
            conn.commit()

    conn.commit()
    elapsed = time.time() - start_time
    print(f"  Done: {run_count} runs, {ad_count} ads in {elapsed:.1f}s "
          f"({error_count} errors)")


# ---------------------------------------------------------------------------
# 5. Blacklist
# ---------------------------------------------------------------------------
BLACKLIST_JSON = os.path.join(PROJECT_ROOT, "config", "brand_blacklist.json")


def populate_blacklist(conn):
    print("\n=== Populating blacklist ===")
    with open(BLACKLIST_JSON) as f:
        data = json.load(f)

    entries = data.get("brands", [])
    cur = conn.cursor()
    cur.execute("DELETE FROM blacklist")

    count = 0
    for name in entries:
        name = (name or "").strip()
        if not name:
            continue
        try:
            cur.execute(
                "INSERT INTO blacklist (key, reason) VALUES (%s, %s)",
                (name, "imported from brand_blacklist.json"),
            )
            count += 1
        except psycopg2.errors.UniqueViolation:
            conn.rollback()

    conn.commit()
    print(f"  Inserted {count} blacklist entries from {len(entries)} items")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Populate Supabase DB from JSON files")
    parser.add_argument("--brands", action="store_true", help="Populate brands + synonyms")
    parser.add_argument("--logos", action="store_true", help="Populate brand logos")
    parser.add_argument("--schedules", action="store_true", help="Populate schedules")
    parser.add_argument("--runs", action="store_true", help="Populate runs + ads")
    parser.add_argument("--blacklist", action="store_true", help="Populate blacklist")
    parser.add_argument("--all", action="store_true", help="Populate everything")
    args = parser.parse_args()

    # Default to --all if no flags
    if not any([args.brands, args.logos, args.schedules, args.runs, args.blacklist, args.all]):
        args.all = True

    print(f"Connecting to {DB_URL}...")
    conn = get_conn()
    print("Connected.")

    try:
        if args.all or args.brands:
            populate_brands(conn)
        if args.all or args.logos:
            populate_logos(conn)
        if args.all or args.schedules:
            populate_schedules(conn)
        if args.all or args.runs:
            populate_runs(conn)
        if args.all or args.blacklist:
            populate_blacklist(conn)
    finally:
        conn.close()

    # Print summary
    print("\n=== Final Summary ===")
    conn = get_conn()
    cur = conn.cursor()
    for table in ["brands", "brand_synonyms", "brand_logos", "runs", "ads", "ad_brands", "schedules", "blacklist"]:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"  {table}: {count:,} rows")
    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
