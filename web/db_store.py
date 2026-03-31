"""
Database-backed store for run metadata, brand counts, and ad queries.

Drop-in replacement for manifest_store.py — provides the same interface
(runs(), brands(), brands_by_client(), daily_totals()) but reads from
the local Supabase PostgreSQL instead of cache/run_manifest.json.

Falls back to manifest_store if the database is unavailable.
"""
from __future__ import annotations

import os
import json
from typing import Any, Dict, List, Optional

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
)

# Ad types that should never appear as cards in the dashboard
EXCLUDED_AD_TYPES = ["product_listing", "sponsored_product", "shoppable_ad_item"]

# Message/title patterns that indicate Amazon house ads (not third-party advertising)
EXCLUDED_MESSAGES = ["seen on social media"]

_pool = None


def _get_conn():
    """Get a database connection (lazy-init connection pool)."""
    global _pool
    if _pool is None:
        import psycopg2
        import psycopg2.pool
        _pool = psycopg2.pool.SimpleConnectionPool(1, 5, DB_URL)
    return _pool.getconn()


def _put_conn(conn):
    """Return connection to pool."""
    if _pool:
        _pool.putconn(conn)


def _db_available() -> bool:
    """Check if the database is reachable."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        _put_conn(conn)
        return True
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────
# Interface matching manifest_store.py
# ──────────────────────────────────────────────────────────────

def runs() -> List[Dict[str, Any]]:
    """
    Get all run metadata (sorted newest first).
    Returns list of dicts matching the manifest format:
      {retailer, client, keyword, run_id, day, ad_count, json_path,
       timestamp, brands_by_type}
    """
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT r.retailer, r.client, r.keyword, r.run_id,
                   r.day::text, r.ad_count, r.json_path,
                   r.timestamp AT TIME ZONE 'UTC' as ts
            FROM runs r
            ORDER BY r.timestamp DESC
        """)
        rows = cur.fetchall()
        cur.close()
        _put_conn(conn)

        result = []
        for row in rows:
            ts_str = row[7].strftime("%Y-%m-%dT%H:%M:%SZ") if row[7] else ""
            result.append({
                "retailer": row[0],
                "client": row[1],
                "keyword": row[2] or "",
                "run_id": row[3],
                "day": row[4] or "",
                "ad_count": row[5] or 0,
                "json_path": row[6] or "",
                "timestamp": ts_str,
                "brands_by_type": {},  # populated on demand, not stored in DB
            })
        return result
    except Exception as e:
        print(f"⚠️  db_store.runs() failed: {e}, falling back to manifest")
        from web.manifest_store import runs as mf_runs
        return mf_runs()


def daily_totals() -> Dict[str, Any]:
    """
    Get daily totals by retailer.
    Returns: {retailer: {day: ad_count, ...}, ...}
    """
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT retailer, day::text, SUM(ad_count)
            FROM runs
            GROUP BY retailer, day
            ORDER BY day DESC
        """)
        rows = cur.fetchall()
        cur.close()
        _put_conn(conn)

        result: Dict[str, Dict[str, int]] = {}
        for retailer, day, count in rows:
            result.setdefault(retailer, {})[day] = int(count)
        return result
    except Exception as e:
        print(f"⚠️  db_store.daily_totals() failed: {e}")
        from web.manifest_store import daily_totals as mf_daily
        return mf_daily()


def brands() -> Dict[str, List[Dict[str, Any]]]:
    """
    Get brand counts by retailer.
    Returns: {retailer: [{brand, count, percentage}, ...], ...}
    """
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT r.retailer, a.brand, COUNT(*) as cnt
            FROM ads a
            JOIN runs r ON a.run_id = r.id
            WHERE a.brand IS NOT NULL AND a.brand != '' AND a.brand != 'Unknown'
            GROUP BY r.retailer, a.brand
            ORDER BY r.retailer, cnt DESC
        """)
        rows = cur.fetchall()
        cur.close()
        _put_conn(conn)

        # Group by retailer
        by_retailer: Dict[str, List[tuple]] = {}
        for retailer, brand, count in rows:
            by_retailer.setdefault(retailer, []).append((brand, count))

        result: Dict[str, List[Dict[str, Any]]] = {}
        for retailer, brand_list in by_retailer.items():
            total = sum(c for _, c in brand_list)
            result[retailer] = [
                {
                    "brand": brand,
                    "count": count,
                    "percentage": round((count / total) * 100, 1) if total > 0 else 0,
                }
                for brand, count in brand_list
            ]
        return result
    except Exception as e:
        print(f"⚠️  db_store.brands() failed: {e}")
        from web.manifest_store import brands as mf_brands
        return mf_brands()


def brands_by_client() -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """
    Get brand counts by retailer and client.
    Returns: {retailer: {client: [{brand, count, percentage}, ...], ...}, ...}
    """
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT r.retailer, r.client, a.brand, COUNT(*) as cnt
            FROM ads a
            JOIN runs r ON a.run_id = r.id
            WHERE a.brand IS NOT NULL AND a.brand != '' AND a.brand != 'Unknown'
            GROUP BY r.retailer, r.client, a.brand
            ORDER BY r.retailer, r.client, cnt DESC
        """)
        rows = cur.fetchall()
        cur.close()
        _put_conn(conn)

        # Group by retailer → client
        nested: Dict[str, Dict[str, List[tuple]]] = {}
        for retailer, client, brand, count in rows:
            nested.setdefault(retailer, {}).setdefault(client, []).append((brand, count))

        result: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        for retailer, clients in nested.items():
            result[retailer] = {}
            for client, brand_list in clients.items():
                total = sum(c for _, c in brand_list)
                result[retailer][client] = [
                    {
                        "brand": brand,
                        "count": count,
                        "percentage": round((count / total) * 100, 1) if total > 0 else 0,
                    }
                    for brand, count in brand_list
                ]
        return result
    except Exception as e:
        print(f"⚠️  db_store.brands_by_client() failed: {e}")
        from web.manifest_store import brands_by_client as mf_bbc
        return mf_bbc()


def built_at() -> Optional[str]:
    """Get latest run timestamp as a proxy for 'built_at'."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT MAX(timestamp) FROM runs")
        row = cur.fetchone()
        cur.close()
        _put_conn(conn)
        if row and row[0]:
            return row[0].strftime("%Y-%m-%dT%H:%M:%SZ")
        return None
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────
# Extended queries (not in manifest_store, used by new endpoints)
# ──────────────────────────────────────────────────────────────

def count_ads(
    retailer: str = None,
    clients: set = None,
    keyword: str = None,
    start: str = None,
    end: str = None,
    brand: str = None,
    brands: list = None,
    ad_types: list = None,
) -> int:
    """Count ads matching filters — pure SQL, no file I/O."""
    try:
        conn = _get_conn()
        cur = conn.cursor()

        where = ["lower(a.ad_type) != ALL(%s)", "(a.image_path IS NULL OR a.image_path NOT LIKE '%%product_images/%%')", "NOT (lower(COALESCE(a.title,'') || ' ' || COALESCE(a.message,'')) LIKE ANY(%s))"]
        params = [EXCLUDED_AD_TYPES, [f"%{p}%" for p in EXCLUDED_MESSAGES]]

        if retailer:
            where.append("r.retailer = %s")
            params.append(retailer)
        if clients:
            where.append("r.client = ANY(%s)")
            params.append(list(clients))
        if keyword:
            where.append("r.keyword = %s")
            params.append(keyword)
        if start:
            where.append("r.day >= %s")
            params.append(start)
        if end:
            where.append("r.day <= %s")
            params.append(end)
        if brand:
            where.append("lower(a.brand) = lower(%s)")
            params.append(brand)
        if brands:
            where.append("lower(a.brand) = ANY(%s)")
            params.append([b.lower() for b in brands])
        if ad_types:
            # Normalize types for matching
            type_conditions = []
            for t in ad_types:
                type_conditions.append("lower(replace(a.ad_type, '_', ' ')) LIKE %s")
                params.append(f"%{t.lower().replace('_', ' ')}%")
            where.append(f"({' OR '.join(type_conditions)})")

        where_clause = " AND ".join(where)

        cur.execute(f"""
            SELECT COUNT(*)
            FROM ads a
            JOIN runs r ON a.run_id = r.id
            WHERE {where_clause}
        """, params)
        count = cur.fetchone()[0]
        cur.close()
        _put_conn(conn)
        return count
    except Exception as e:
        print(f"⚠️  db_store.count_ads() failed: {e}")
        return 0


def query_ads(
    retailer: str = None,
    clients: set = None,
    keyword: str = None,
    start: str = None,
    end: str = None,
    brand: str = None,
    brands: list = None,
    ad_types: list = None,
    page: int = 1,
    page_size: int = 24,
    sort: str = "latest",
) -> Dict[str, Any]:
    """
    Query ads with filtering and pagination — pure SQL.
    brand: single brand (advertiser filter)
    brands: list of brands (Top Brands multi-select filter)
    Returns dict with: ads, total, page, page_size, has_more
    """
    try:
        conn = _get_conn()
        cur = conn.cursor()

        where = ["lower(a.ad_type) != ALL(%s)", "(a.image_path IS NULL OR a.image_path NOT LIKE '%%product_images/%%')", "NOT (lower(COALESCE(a.title,'') || ' ' || COALESCE(a.message,'')) LIKE ANY(%s))"]
        params = [EXCLUDED_AD_TYPES, [f"%{p}%" for p in EXCLUDED_MESSAGES]]

        if retailer:
            where.append("r.retailer = %s")
            params.append(retailer)
        if clients:
            where.append("r.client = ANY(%s)")
            params.append(list(clients))
        if keyword:
            where.append("r.keyword = %s")
            params.append(keyword)
        if start:
            where.append("r.day >= %s")
            params.append(start)
        if end:
            where.append("r.day <= %s")
            params.append(end)
        if brand:
            where.append("lower(a.brand) = lower(%s)")
            params.append(brand)
        if brands:
            where.append("lower(a.brand) = ANY(%s)")
            params.append([b.lower() for b in brands])
        if ad_types:
            type_conditions = []
            for t in ad_types:
                type_conditions.append("lower(replace(a.ad_type, '_', ' ')) LIKE %s")
                params.append(f"%{t.lower().replace('_', ' ')}%")
            where.append(f"({' OR '.join(type_conditions)})")

        where_clause = " AND ".join(where)

        # Sort
        order = "r.timestamp DESC"
        if sort == "oldest":
            order = "r.timestamp ASC"
        elif sort == "name":
            order = "a.brand ASC, r.timestamp DESC"

        # Count total
        count_params = list(params)
        cur.execute(f"""
            SELECT COUNT(*)
            FROM ads a JOIN runs r ON a.run_id = r.id
            WHERE {where_clause}
        """, count_params)
        total = cur.fetchone()[0]

        # Fetch page
        offset = (page - 1) * page_size
        params.extend([page_size, offset])

        cur.execute(f"""
            SELECT
                a.id, a.original_id, a.ad_type, a.ad_subtype, a.slot,
                a.brand, a.brand_logo_path,
                a.title, a.message, a.description, a.cta, a.href,
                a.image_url, a.image_path, a.video_url, a.video_path,
                a.product_image_url, a.product_title, a.product_description,
                a.metadata,
                r.retailer, r.client, r.keyword, r.json_path,
                r.timestamp AT TIME ZONE 'UTC' as run_ts
            FROM ads a
            JOIN runs r ON a.run_id = r.id
            WHERE {where_clause}
            ORDER BY {order}
            LIMIT %s OFFSET %s
        """, params)

        rows = cur.fetchall()
        cur.close()
        _put_conn(conn)

        ads = []
        for row in rows:
            ts = row[24].strftime("%Y-%m-%dT%H:%M:%SZ") if row[24] else ""
            ads.append({
                "db_id": row[0],
                "original_id": row[1],
                "ad_type": row[2],
                "ad_subtype": row[3],
                "slot": row[4],
                "brand": row[5],
                "brand_logo_path": row[6],
                "title": row[7],
                "message": row[8],
                "description": row[9],
                "cta": row[10],
                "href": row[11],
                "image_url": row[12],
                "image_path": row[13],
                "video_url": row[14],
                "video_path": row[15],
                "product_image_url": row[16],
                "product_title": row[17],
                "product_description": row[18],
                "metadata": row[19],
                "retailer": row[20],
                "client": row[21],
                "keyword": row[22],
                "json_path": row[23],
                "timestamp": ts,
            })

        return {
            "ads": ads,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": (offset + len(ads)) < total,
        }
    except Exception as e:
        print(f"⚠️  db_store.query_ads() failed: {e}")
        return {"ads": [], "total": 0, "page": page, "page_size": page_size, "has_more": False}


def get_ad_types(
    retailer: str = None,
    clients: set = None,
    start: str = None,
    end: str = None,
) -> List[str]:
    """Get distinct ad types matching filters."""
    try:
        conn = _get_conn()
        cur = conn.cursor()

        where = ["lower(a.ad_type) != ALL(%s)", "a.ad_type IS NOT NULL", "(a.image_path IS NULL OR a.image_path NOT LIKE '%%product_images/%%')", "NOT (lower(COALESCE(a.title,'') || ' ' || COALESCE(a.message,'')) LIKE ANY(%s))"]
        params = [EXCLUDED_AD_TYPES, [f"%{p}%" for p in EXCLUDED_MESSAGES]]
        if retailer:
            where.append("r.retailer = %s")
            params.append(retailer)
        if clients:
            where.append("r.client = ANY(%s)")
            params.append(list(clients))
        if start:
            where.append("r.day >= %s")
            params.append(start)
        if end:
            where.append("r.day <= %s")
            params.append(end)

        where_clause = " AND ".join(where)

        cur.execute(f"""
            SELECT DISTINCT upper(a.ad_type) as ad_type_upper
            FROM ads a JOIN runs r ON a.run_id = r.id
            WHERE {where_clause}
            ORDER BY ad_type_upper
        """, params)
        types = [row[0] for row in cur.fetchall()]
        cur.close()
        _put_conn(conn)
        return types
    except Exception as e:
        print(f"⚠️  db_store.get_ad_types() failed: {e}")
        return []


def get_brands_filtered(
    retailer=None,
    clients: set = None,
    start: str = None,
    end: str = None,
    keyword: str = None,
    ad_types: list = None,
) -> List[Dict[str, Any]]:
    """Get brand counts with full filtering — replaces slow JSON scan.
    retailer can be a single string or a list of strings."""
    try:
        conn = _get_conn()
        cur = conn.cursor()

        where = ["a.brand IS NOT NULL", "a.brand != ''", "a.brand != 'Unknown'", "lower(a.ad_type) != ALL(%s)", "(a.image_path IS NULL OR a.image_path NOT LIKE '%%product_images/%%')", "NOT (lower(COALESCE(a.title,'') || ' ' || COALESCE(a.message,'')) LIKE ANY(%s))"]
        params = [EXCLUDED_AD_TYPES, [f"%{p}%" for p in EXCLUDED_MESSAGES]]

        if retailer:
            if isinstance(retailer, list):
                where.append("r.retailer = ANY(%s)")
                params.append(retailer)
            else:
                where.append("r.retailer = %s")
                params.append(retailer)
        if clients:
            where.append("r.client = ANY(%s)")
            params.append(list(clients))
        if start:
            where.append("r.day >= %s")
            params.append(start)
        if end:
            where.append("r.day <= %s")
            params.append(end)
        if keyword:
            where.append("r.keyword = %s")
            params.append(keyword)
        if ad_types:
            type_conditions = []
            for t in ad_types:
                type_conditions.append("lower(replace(a.ad_type, '_', ' ')) LIKE %s")
                params.append(f"%{t.lower().replace('_', ' ')}%")
            where.append(f"({' OR '.join(type_conditions)})")

        where_clause = " AND ".join(where)

        cur.execute(f"""
            SELECT a.brand, COUNT(*) as cnt
            FROM ads a JOIN runs r ON a.run_id = r.id
            WHERE {where_clause}
            GROUP BY a.brand
            ORDER BY cnt DESC
        """, params)
        rows = cur.fetchall()
        cur.close()
        _put_conn(conn)

        # Canonicalize brand names to merge synonyms, case variants, punctuation
        from core.brands import canonicalize as _canon, is_blacklisted as _is_bl
        merged: dict[str, tuple[str, int]] = {}  # canon_key -> (display_name, count)
        for raw_brand, count in rows:
            if _is_bl(raw_brand):
                continue
            canon = _canon(raw_brand, mark_ambiguous=False)
            display = canon if canon else raw_brand
            key = display.lower()
            if key in merged:
                prev_display, prev_count = merged[key]
                # Keep the display name with the higher count (most common variant)
                if count > prev_count:
                    merged[key] = (display, prev_count + count)
                else:
                    merged[key] = (prev_display, prev_count + count)
            else:
                merged[key] = (display, count)

        # Sort by count descending
        sorted_brands = sorted(merged.values(), key=lambda x: x[1], reverse=True)
        total = sum(c for _, c in sorted_brands)
        return [
            {
                "brand": display,
                "count": count,
                "percentage": round((count / total) * 100, 1) if total > 0 else 0,
            }
            for display, count in sorted_brands
        ]
    except Exception as e:
        print(f"⚠️  db_store.get_brands_filtered() failed: {e}")
        return []


def get_brand_details(
    brand_name: str,
    retailers: list = None,
    keywords_filter: set = None,
) -> Dict[str, Any]:
    """
    Get detailed brand info in a single DB round-trip:
      total_ads, retailer_ads, last_seen, top_keywords,
      top_competitors, monthly_activity.
    Replaces the 3-pass JSON filesystem scan.
    """
    try:
        conn = _get_conn()
        cur = conn.cursor()

        # Build retailer filter clause
        ret_clause = ""
        ret_params: list = []
        if retailers:
            ret_clause = "AND r.retailer = ANY(%s)"
            ret_params = [retailers]

        # ── 1. Total ads + per-retailer counts + last_seen ──
        cur.execute(f"""
            SELECT r.retailer, COUNT(*) as cnt,
                   MAX(r.timestamp AT TIME ZONE 'UTC') as last_ts
            FROM ads a
            JOIN runs r ON a.run_id = r.id
            WHERE lower(a.brand) = lower(%s) {ret_clause}
            GROUP BY r.retailer
        """, [brand_name] + ret_params)
        retailer_rows = cur.fetchall()

        retailer_ads = {}
        total_ads = 0
        last_seen = None
        for retailer, cnt, last_ts in retailer_rows:
            retailer_ads[retailer] = cnt
            total_ads += cnt
            if last_ts:
                ts_str = last_ts.strftime("%Y-%m-%dT%H:%M:%SZ")
                if last_seen is None or ts_str > last_seen:
                    last_seen = ts_str

        # ── 2. Top keywords ──
        kw_filter_clause = ""
        kw_filter_params: list = []
        if keywords_filter:
            kw_filter_clause = "AND lower(r.keyword) = ANY(%s)"
            kw_filter_params = [list(keywords_filter)]

        cur.execute(f"""
            SELECT lower(r.keyword) as kw, COUNT(*) as cnt
            FROM ads a
            JOIN runs r ON a.run_id = r.id
            WHERE lower(a.brand) = lower(%s) {ret_clause}
              AND r.keyword IS NOT NULL AND r.keyword != ''
              {kw_filter_clause}
            GROUP BY lower(r.keyword)
            ORDER BY cnt DESC
            LIMIT 10
        """, [brand_name] + ret_params + kw_filter_params)
        top_keywords = [
            {"keyword": row[0], "count": row[1]}
            for row in cur.fetchall()
        ]

        # ── 3. Top competitors (brands appearing on same keywords) ──
        brand_keywords = list(keywords_filter) if keywords_filter else [item["keyword"] for item in top_keywords]

        top_competitors = []
        if brand_keywords:
            cur.execute(f"""
                WITH brand_pairs AS (
                    SELECT DISTINCT r.retailer, lower(r.keyword) AS kw
                    FROM ads a0
                    JOIN runs r ON a0.run_id = r.id
                    WHERE lower(a0.brand) = lower(%s) {ret_clause}
                      AND r.keyword IS NOT NULL AND r.keyword != ''
                      AND lower(r.keyword) = ANY(%s)
                )
                SELECT a.brand, bp.kw, COUNT(*) as cnt
                FROM brand_pairs bp
                JOIN runs r ON r.retailer = bp.retailer AND lower(r.keyword) = bp.kw
                JOIN ads a ON a.run_id = r.id
                WHERE lower(a.brand) != lower(%s)
                  AND a.brand IS NOT NULL AND a.brand != '' AND a.brand != 'Unknown'
                GROUP BY a.brand, bp.kw
            """, [brand_name] + ret_params + [brand_keywords] + [brand_name])
            comp_rows = cur.fetchall()

            # Aggregate by brand
            comp_map: Dict[str, Dict[str, Any]] = {}
            for comp_brand, kw, cnt in comp_rows:
                if comp_brand not in comp_map:
                    comp_map[comp_brand] = {"total": 0, "keywords": {}}
                comp_map[comp_brand]["total"] += cnt
                comp_map[comp_brand]["keywords"][kw] = cnt

            top_competitors = sorted(
                [{"brand": b, "total": d["total"], "keywords": d["keywords"]}
                 for b, d in comp_map.items()],
                key=lambda x: x["total"], reverse=True
            )[:10]

        # ── 4. Monthly activity (last 12 months) ──
        from datetime import datetime as dt_cls
        now = dt_cls.now()
        cur.execute(f"""
            SELECT to_char(r.timestamp AT TIME ZONE 'UTC', 'YYYY-MM') as month,
                   COUNT(*) as cnt
            FROM ads a
            JOIN runs r ON a.run_id = r.id
            WHERE lower(a.brand) = lower(%s) {ret_clause}
              AND r.timestamp >= (now() - interval '12 months')
              {kw_filter_clause}
            GROUP BY month
            ORDER BY month
        """, [brand_name] + ret_params + kw_filter_params)
        monthly_rows = {row[0]: row[1] for row in cur.fetchall()}

        # Fill in missing months with 0
        monthly_activity = []
        for i in range(11, -1, -1):
            m = now.month - i
            y = now.year
            while m <= 0:
                m += 12
                y -= 1
            month_key = f"{y:04d}-{m:02d}"
            monthly_activity.append({
                "month": month_key,
                "count": monthly_rows.get(month_key, 0),
            })

        cur.close()
        _put_conn(conn)

        return {
            "brand": brand_name,
            "total_ads": total_ads,
            "retailer_ads": retailer_ads,
            "last_seen": last_seen,
            "top_keywords": top_keywords,
            "top_competitors": top_competitors,
            "monthly_activity": monthly_activity,
        }
    except Exception as e:
        print(f"⚠️  db_store.get_brand_details() failed: {e}")
        import traceback; traceback.print_exc()
        return None


# ──────────────────────────────────────────────────────────────
# Review flags
# ──────────────────────────────────────────────────────────────

def flag_ad_for_review(ad_id: int, reason: str = None) -> bool:
    """Flag an ad for re-review (brand re-extraction)."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO review_flags (flag_type, ad_id, reason)
            VALUES ('ad', %s, %s)
        """, [ad_id, reason])
        conn.commit()
        cur.close()
        _put_conn(conn)
        return True
    except Exception as e:
        print(f"⚠️  db_store.flag_ad_for_review() failed: {e}")
        return False


def flag_brand_for_review(brand_name: str, reason: str = None) -> bool:
    """Flag a brand for re-review (synonym/canonicalization check)."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO review_flags (flag_type, brand_name, reason)
            VALUES ('brand', %s, %s)
        """, [brand_name, reason])
        conn.commit()
        cur.close()
        _put_conn(conn)
        return True
    except Exception as e:
        print(f"⚠️  db_store.flag_brand_for_review() failed: {e}")
        return False


def get_pending_review_flags(flag_type: str = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Get pending review flags, optionally filtered by type."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        where = ["status = 'pending'"]
        params = []
        if flag_type:
            where.append("flag_type = %s")
            params.append(flag_type)
        params.append(limit)
        cur.execute(f"""
            SELECT id, flag_type, ad_id, brand_name, reason, created_at
            FROM review_flags
            WHERE {' AND '.join(where)}
            ORDER BY created_at DESC
            LIMIT %s
        """, params)
        rows = cur.fetchall()
        cur.close()
        _put_conn(conn)
        return [
            {
                "id": r[0], "flag_type": r[1], "ad_id": r[2],
                "brand_name": r[3], "reason": r[4],
                "created_at": r[5].isoformat() if r[5] else None,
            }
            for r in rows
        ]
    except Exception as e:
        print(f"⚠️  db_store.get_pending_review_flags() failed: {e}")
        return []
