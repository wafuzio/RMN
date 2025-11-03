export type RawCard = any;

export type Card = {
  retailer: string;
  client: string;
  keyword?: string | null;
  adType?: string | null;
  typeLabel?: string | null;
  brand?: string | null;
  brandCanonical?: string | null;
  advertisers?: string[];
  imageUrl?: string | null;
  hasImage?: boolean;
  timestamp?: string | null;
  timestampMs?: number | null;
  brandLogoUrl?: string | null;
  message?: string | null;
  id?: string;    // we'll set this later if needed
  _raw?: RawCard; // for debugging
};

export function normalizeCard(c: RawCard): Card {
  const imageUrl  = c.imageUrl ?? c.image_url ?? null;
  const adType    = c.adType   ?? c.ad_type   ?? c.type ?? null;
  const hasImage  = (c.hasImage ?? c.has_image ?? (imageUrl ? true : false)) === true;
  const brand     = c.brand_canonical ?? (c.brand || null) ?? null;

  return {
    retailer: c.retailer,
    client: c.client,
    keyword: c.keyword ?? c.term ?? null,
    adType,
    typeLabel: c.type_label ?? (adType ? String(adType).replace(/[_-]/g, ' ').trim() : null),
    brand,
    brandCanonical: c.brand_canonical ?? null,
    advertisers: Array.isArray(c.advertisers) ? c.advertisers : (c.advertiser ? [c.advertiser] : []),
    imageUrl,
    hasImage,
    timestamp: c.timestamp ?? c.ts ?? null,
    timestampMs: typeof c.timestamp_ms === 'number' ? c.timestamp_ms : null,
    brandLogoUrl: c.brand_logo_url ?? null,
    message: c.message ?? null,
    _raw: c,
  };
}

// helper to grab cards out of many shapes
function grabCards(v: any): any[] {
  if (Array.isArray(v)) return v;
  if (Array.isArray(v?.cards)) return v.cards;
  if (Array.isArray(v?.data?.cards)) return v.data.cards;
  // sometimes nested containers use other labels
  for (const k of ['results', 'payload', 'items']) {
    if (Array.isArray(v?.[k]?.cards)) return v[k].cards;
    if (Array.isArray(v?.[k])) return v[k];
  }
  return [];
}

export function normalizeBatchPayload(payload: any): Card[] {
  if (Array.isArray(payload?.cards)) return payload.cards.map(normalizeCard);
  if (Array.isArray(payload)) return payload.map(normalizeCard);

  const out: Card[] = [];
  if (payload && typeof payload === 'object') {
    for (const [k, v] of Object.entries(payload)) {
      const arr = grabCards(v);
      for (const c of arr) out.push(normalizeCard(c));
    }
  }
  return out;
}

export function normalizeCardsPayload(payload: any): Card[] {
  const arr = Array.isArray(payload?.cards) ? payload.cards : (Array.isArray(payload) ? payload : []);
  return arr.map(normalizeCard);
}
