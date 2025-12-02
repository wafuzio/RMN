export type AdCardItem = {
  id?: string;
  retailer: string;
  client: string;
  keyword: string;
  ad_type: string;
  brand: string;
  message: string;
  image_url?: string;
  video_url?: string;
  poster_url?: string;
  timestamp: string; // ISO
  run_file?: string;
  ad_index?: number;
  card_format?: string;
  dimensions?: { width: number; height: number };
};

export type AdGroup = {
  group_id: string;            // stable key for React
  retailer: string;
  ad_type: string;
  client: string;
  brand?: string;              // brand of the first or the "mode"
  message?: string;            // message of the first (can vary across instances)
  media_key: string;           // canonical media identifier used for grouping
  cover: AdCardItem;           // representative item for thumbnail/labels
  count: number;               // number of occurrences
  timestamps: string[];        // all timestamps (sorted desc or asc)
  first_seen: string;          // min timestamp
  last_seen: string;           // max timestamp
  instances: AdCardItem[];     // optional for modal drilldown
  keywords: string[];          // all unique keywords this ad appeared for
};

function normalizeUrl(raw?: string): string {
  if (!raw) return '';
  try {
    const u = new URL(raw, window.location.origin);
    // Drop purely presentational params
    u.searchParams.delete('w');
    u.searchParams.delete('width');
    u.searchParams.delete('dpr');
    u.searchParams.delete('fm'); // format
    // Sort the rest for stability
    const pairs = [...u.searchParams.entries()].sort((a, b) => a[0].localeCompare(b[0]));
    u.search = new URLSearchParams(pairs).toString();
    // Return path + normalized query (keep origin-less to avoid env differences)
    return u.pathname + (u.search ? `?${u.search}` : '');
  } catch {
    // Fallback: strip known tokens from naive strings
    return raw.replace(/\?(.*)$/, (m) => {
      const qs = m.slice(1).split('&').filter(p => !/^w=|^width=|^dpr=|^fm=/.test(p)).sort();
      return qs.length ? '?' + qs.join('&') : '';
    });
  }
}

function buildKey(ad: AdCardItem): string {
  // Group by brand + message + ad_type for all retailers
  // This works better than image URL since:
  // - Instacart generates unique filenames per scrape
  // - Other retailers may have cache-busting params or CDN variations
  // - Brand + message is the actual semantic identity of the ad

  // Normalize message: remove extra whitespace, sort words for consistency
  const normalizedMessage = (ad.message || '')
    .toLowerCase()
    .trim()
    .split(/\s+/)
    .filter(w => w.length > 0)
    .sort()
    .join(' ');

  const parts = [
    ad.retailer || '',
    ad.ad_type || '', // Groups stay pure by ad_type
    ad.client || '',
    ad.brand || '',
    normalizedMessage,
    // NOTE: keyword is NOT included - we want to group same ad across different keywords
  ];
  return parts.join('|');
}

function hashKey(s: string): string {
  // Simple hash function for browser
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h) + s.charCodeAt(i);
    h |= 0;
  }
  return 'h' + (h >>> 0).toString(16);
}

export function aggregateAds(ads: AdCardItem[]): AdGroup[] {
  // First, deduplicate exact duplicates (same brand, message, timestamp, ad_type)
  // This handles backend duplicates that slip through
  const dedupeMap = new Map<string, AdCardItem>();
  for (const ad of ads) {
    const dedupeKey = [
      ad.retailer,
      ad.client,
      ad.ad_type,
      ad.brand,
      ad.message?.toLowerCase().trim(),
      ad.timestamp,
    ].join('|');

    // Keep first occurrence, skip duplicates
    if (!dedupeMap.has(dedupeKey)) {
      dedupeMap.set(dedupeKey, ad);
    }
  }

  const dedupedAds = Array.from(dedupeMap.values());
  console.log(`[aggregateAds] Deduped ${ads.length} → ${dedupedAds.length} ads (removed ${ads.length - dedupedAds.length} exact duplicates)`);

  const map = new Map<string, AdGroup>();

  for (const ad of dedupedAds) {
    const media_key = buildKey(ad);
    if (!media_key) continue;

    let group = map.get(media_key);
    if (!group) {
      group = {
        group_id: 'grp_' + hashKey(media_key),
        retailer: ad.retailer,
        ad_type: ad.ad_type,
        client: ad.client,
        brand: ad.brand,
        message: ad.message,
        media_key,
        cover: ad,
        count: 0,
        timestamps: [],
        first_seen: ad.timestamp,
        last_seen: ad.timestamp,
        instances: [],
        keywords: [],
      };
      map.set(media_key, group);
    }

    group.count += 1;
    group.instances.push(ad);
    group.timestamps.push(ad.timestamp);

    // Track unique keywords
    if (ad.keyword && !group.keywords.includes(ad.keyword)) {
      group.keywords.push(ad.keyword);
    }

    if (!group.last_seen || ad.timestamp > group.last_seen) group.last_seen = ad.timestamp;
    if (!group.first_seen || ad.timestamp < group.first_seen) group.first_seen = ad.timestamp;
  }

  // Normalize per-group: sort timestamps (desc for display)
  for (const g of map.values()) {
    g.timestamps.sort((a, b) => b.localeCompare(a)); // newest first
  }

  // Sort groups for display: highest count first, then by newest last_seen
  const groups = [...map.values()].sort((a, b) => {
    // Primary sort: count (descending)
    if (b.count !== a.count) return b.count - a.count;
    // Secondary sort: newest last_seen first
    return b.last_seen.localeCompare(a.last_seen);
  });
  return groups;
}
