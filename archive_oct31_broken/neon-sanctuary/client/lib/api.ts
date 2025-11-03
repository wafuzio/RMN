import type {
  Retailer,
  RetailersResponse,
  ClientsResponse,
  AdCardItem,
  AdsCardsResponse,
  BatchAdsResponse,
  AdsStatsResponse
} from "@shared/api";

// Re-export for convenience
export type {
  Retailer,
  RetailersResponse,
  ClientsResponse,
  AdCardItem,
  AdsCardsResponse,
  BatchAdsResponse,
  AdsStatsResponse
};

// Use relative path in dev (proxied by Vite), absolute in production
const DEFAULT_API_BASE = "";  // Empty string = same origin (proxied by Vite)
const raw = (import.meta.env.VITE_API_BASE || '').trim().replace(/\/+$/, '');
export const API_BASE = raw || DEFAULT_API_BASE;

// Log API configuration once on module load
if (typeof window !== 'undefined') {
  console.info('[api] API_BASE:', API_BASE || '(relative via Vite proxy)');
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  console.debug('[http] GET', url, { API_BASE, path });  // Log the full URL for debugging
  try {
    const res = await fetch(url, {
      ...init,
      headers: {
        ...(init?.headers||{}),
        "Accept": "application/json",
        "ngrok-skip-browser-warning": "true",
        "User-Agent": "Mozilla/5.0"
      },
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`${res.status} ${res.statusText} ${text}`);
    }
    return res.json() as Promise<T>;
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    const errorName = error instanceof Error ? error.name : 'Unknown';
    console.error('[http] Fetch failed', { url, API_BASE, errorName, errorMessage });
    throw new Error(`Fetch failed for ${path}: ${errorMessage}`);
  }
}

type GetAdsOpts = {
  retailer: string;
  client: string;  // REQUIRED - server expects this
  term?: string;
  advertiser?: string;
  page?: number;
  pageSize?: number;  // camel here; we will map to page_size in query
  start?: string;
  end?: string;
  types?: string[];
  brands?: string[];
  search?: string;
};

export const api = {
  getRetailers: () => http<RetailersResponse>(`/api/retailers`),
  getClients: (retailer: string) => http<ClientsResponse>(`/api/clients?retailer=${encodeURIComponent(retailer)}`),
  getAds: (params: GetAdsOpts) => {
    const { retailer, client, term, advertiser, page = 1, pageSize = 24, start, end, types, brands, search } = params;

    // Validate required params
    if (!retailer) throw new Error('getAds: retailer is required');
    if (!client) throw new Error('getAds: client is required');

    // Build query string with explicit parameter names
    const q = new URLSearchParams();
    q.set('retailer', retailer);
    q.set('client', client);              // REQUIRED
    q.set('page', String(page));
    q.set('page_size', String(pageSize)); // server expects snake_case

    // Optional filters
    if (term?.trim()) q.set('term', term.trim());
    if (advertiser?.trim()) q.set('advertiser', advertiser.trim());
    if (start?.trim()) q.set('start', start.trim());
    if (end?.trim()) q.set('end', end.trim());
    if (search?.trim()) q.set('search', search.trim());
    if (types?.length) q.set('types', types.join(','));
    if (brands?.length) q.set('brands', brands.join(','));

    const url = `/api/ads/cards?${q.toString()}`;
    console.debug('📡 getAds request:', { retailer, client, start, end, startTrimmed: start?.trim(), endTrimmed: end?.trim(), url });

    return http<AdsCardsResponse>(url).then((response) => {
      console.debug('📡 getAds response received:', {
        retailer,
        client,
        count: response.cards.length,
        total: response.total_cards,
        sampleImageUrl: response.cards[0]?.image_url,
      });
      return response;
    });
  },
  getAdsBatch: (params: {
    retailers: string[];
    clients: string[];
    page?: number;
    pageSize?: number;
    term?: string;
    advertiser?: string;
    start?: string;
    end?: string;
    types?: string[];
    brands?: string[];
    search?: string;
  }) => {
    const { retailers, clients, page = 1, pageSize = 24, term, advertiser, start, end, types, brands, search } = params;

    if (!retailers.length || !clients.length) {
      throw new Error('getAdsBatch: retailers and clients are required');
    }

    const q = new URLSearchParams();
    q.set('retailers', retailers.join(','));
    q.set('clients', clients.join(','));
    q.set('page', String(page));
    q.set('page_size', String(pageSize));

    if (term?.trim()) q.set('term', term.trim());
    if (advertiser?.trim()) q.set('advertiser', advertiser.trim());
    if (start?.trim()) q.set('start', start.trim());
    if (end?.trim()) q.set('end', end.trim());
    if (search?.trim()) q.set('search', search.trim());
    if (types?.length) q.set('types', types.join(','));
    if (brands?.length) q.set('brands', brands.join(','));

    const url = `/api/ads/batch?${q.toString()}`;
    console.debug('📡 getAdsBatch request:', { retailers, clients, page, pageSize });

    return http<BatchAdsResponse>(url).then((response) => {
      // Debug logging
      console.info('[api] /ads/batch response keys', Object.keys(response));
      console.info('[api] /ads/batch first result', Object.values(response)[0]);
      
      return response;
    });
  },
  getAdsStats: (params: {
    retailers: string[];
    clients: string[];
    term?: string;
    advertiser?: string;
    start?: string;
    end?: string;
    types?: string[];
    brands?: string[];
    search?: string;
  }) => {
    const { retailers, clients, term, advertiser, start, end, types, brands, search } = params;

    if (!retailers.length || !clients.length) {
      throw new Error('getAdsStats: retailers and clients are required');
    }

    const q = new URLSearchParams();
    q.set('retailers', retailers.join(','));
    q.set('clients', clients.join(','));

    if (term?.trim()) q.set('term', term.trim());
    if (advertiser?.trim()) q.set('advertiser', advertiser.trim());
    if (start?.trim()) q.set('start', start.trim());
    if (end?.trim()) q.set('end', end.trim());
    if (search?.trim()) q.set('search', search.trim());
    if (types?.length) q.set('types', types.join(','));
    if (brands?.length) q.set('brands', brands.join(','));

    const url = `/api/ads/stats?${q.toString()}`;
    console.debug('📡 getAdsStats request:', { retailers, clients });

    return http<AdsStatsResponse>(url);
  },
  imageUrl: (relativePath: string) => `${API_BASE}${relativePath}`,
};
