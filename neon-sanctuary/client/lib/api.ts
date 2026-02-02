import type {
  Retailer,
  RetailersResponse,
  ClientsResponse,
  AdCardItem,
  AdsCardsResponse,
  AdsCountResponse
} from "@shared/api";
import { mark, readServerTiming, count } from './metrics';

// Re-export for convenience
export type {
  Retailer,
  RetailersResponse,
  ClientsResponse,
  AdCardItem,
  AdsCardsResponse,
  AdsCountResponse
};

// Use relative path in dev (proxied by Vite), absolute in production
const DEFAULT_API_BASE = "";  // Empty string = same origin (proxied by Vite)
export const API_BASE = import.meta.env.VITE_API_BASE || DEFAULT_API_BASE;

// Request deduplication: track in-flight requests and abort duplicates
const inflight = new Map<string, AbortController>();

function inflightKey(url: string): string {
  // Normalize URL by sorting query params to create stable cache key
  try {
    const u = new URL(url, location.origin);
    const params = [...u.searchParams.entries()].sort((a,b) => a[0].localeCompare(b[0]));
    u.search = new URLSearchParams(params).toString();
    return u.toString();
  } catch { 
    return url; 
  }
}

async function timeFetch(input: RequestInfo, init?: RequestInit, label?: string): Promise<Response> {
  const url = typeof input === 'string' ? input : (input as Request).url;
  const key = inflightKey(url);

  // Abort any identical in-flight request (last write wins)
  const prev = inflight.get(key);
  if (prev) {
    prev.abort();
    count('dedupe_abort', 1);  // Track how many duplicates we're preventing
  }

  const ctrl = new AbortController();
  inflight.set(key, ctrl);

  try {
    const t0 = performance.now();
    const res = await fetch(input, { ...init, signal: ctrl.signal });
    const t1 = performance.now();
    mark(`http:${label || url}`, t1 - t0, 'ms', { url, status: res.status });
    readServerTiming(res.headers);
    return res;
  } catch (err: any) {
    // Don't log aborted requests as errors (they're expected from deduplication)
    if (err.name !== 'AbortError') {
      const isTypeError = err instanceof TypeError;
      const errorDetails = {
        label,
        urlPath: url.split('?')[0],
        errorName: err.name || 'unknown',
        errorMessage: err.message || String(err),
        isNetworkError: isTypeError && err.message === 'Failed to fetch',
      };
      console.error(`[timeFetch] Error for ${label}:`, errorDetails, err);
    }
    throw err;
  } finally {
    inflight.delete(key);
  }
}

async function http<T>(path: string, init?: RequestInit, label?: string): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await timeFetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'ngrok-skip-browser-warning': '1',  // Required for ngrok tunnel
      ...init?.headers
    }
  }, label);

  if (!res.ok) {
    let errorBody = '';
    try {
      errorBody = await res.text();
    } catch {
      errorBody = '(unable to read response)';
    }
    const errorMsg = `HTTP ${res.status}: ${res.statusText}`;
    console.error(`[http] Request failed for ${label || path}`, {
      status: res.status,
      statusText: res.statusText,
      bodyPreview: errorBody.substring(0, 200),
    });
    throw new Error(errorMsg);
  }

  return res.json();
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
  tz_offset_minutes?: number;  // User's timezone offset for correct date filtering (e.g., -360 for UTC-6)
  types?: string[];
  brands?: string[];
  search?: string;
  sort?: "latest" | "oldest" | "name";  // Sorting applied on backend before pagination
};

export const api = {
  getRetailers: () => http<RetailersResponse>(`/api/retailers`, undefined, 'retailers'),
  getClients: (retailer: string) => http<ClientsResponse>(`/api/clients?retailer=${encodeURIComponent(retailer)}`, undefined, 'clients'),
  getBrands: (retailers: string[], filters?: { client?: string; advertiser?: string; start?: string; end?: string; term?: string; types?: string[] }) => {
    const retailerParam = retailers.length > 0 ? retailers.join(',') : 'all';
    const params = new URLSearchParams();
    params.set('retailers', retailerParam);
    if (filters?.client) params.set('client', filters.client);
    if (filters?.advertiser) params.set('advertiser', filters.advertiser);
    if (filters?.start) params.set('start', filters.start);
    if (filters?.end) params.set('end', filters.end);
    if (filters?.term) params.set('term', filters.term);
    if (filters?.types?.length) params.set('types', filters.types.join(','));
    return http<{ brands: Array<{ brand: string; count: number; percentage: number }> }>(`/api/brands?${params.toString()}`, undefined, 'brands');
  },
  getAdCount: (params: Omit<GetAdsOpts, 'page' | 'pageSize'>) => {
    const { retailer, client, term, advertiser, start, end, tz_offset_minutes, types, brands, search } = params;

    if (!retailer) throw new Error('getAdCount: retailer is required');
    if (!client) throw new Error('getAdCount: client is required');

    const q = new URLSearchParams();
    q.set('retailer', retailer);
    q.set('client', client);
    if (term?.trim()) q.set('term', term.trim());
    if (advertiser?.trim()) q.set('advertiser', advertiser.trim());
    if (start?.trim()) q.set('start', start.trim());
    if (end?.trim()) q.set('end', end.trim());
    if (typeof tz_offset_minutes === 'number') q.set('tz_offset_minutes', String(tz_offset_minutes));
    if (search?.trim()) q.set('search', search.trim());
    if (types?.length) q.set('types', types.join(','));
    if (brands?.length) q.set('brands', brands.join(','));

    const url = `/api/ads/count?${q.toString()}`;
    console.debug('📡 getAdCount request:', { retailer, client, start, end, tz_offset_minutes });

    return http<AdsCountResponse>(url, undefined, 'ads-count').then((response) => {
      console.debug('📡 getAdCount response:', { total: response.total });
      return response;
    });
  },
  getAdTypes: (params: { retailer: string; client: string; start?: string; end?: string }) => {
    const { retailer, client, start, end } = params;
    
    if (!retailer) throw new Error('getAdTypes: retailer is required');
    if (!client) throw new Error('getAdTypes: client is required');
    
    const q = new URLSearchParams();
    q.set('retailer', retailer);
    q.set('client', client);
    if (start?.trim()) q.set('start', start.trim());
    if (end?.trim()) q.set('end', end.trim());
    
    const url = `/api/ads/types?${q.toString()}`;
    return http<{ types: string[]; retailer: string; client: string }>( url, undefined, 'ads-types');
  },
  getAds: (params: GetAdsOpts) => {
    const { retailer, client, term, advertiser, page = 1, pageSize = 24, start, end, tz_offset_minutes, types, brands, search, sort } = params;

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
    if (typeof tz_offset_minutes === 'number') q.set('tz_offset_minutes', String(tz_offset_minutes));
    if (search?.trim()) q.set('search', search.trim());
    if (types?.length) q.set('types', types.join(','));
    if (brands?.length) q.set('brands', brands.join(','));
    if (sort) q.set('sort', sort);

    const url = `/api/ads/cards?${q.toString()}`;
    console.log('🔍 API getAds - types param:', { types, typesLength: types?.length, typesJoined: types?.join(',') });
    console.debug('📡 getAds request:', { start, end, tz_offset_minutes, sort, url });

    return http<AdsCardsResponse>(url, undefined, 'ads').then((response) => {
      console.debug('📡 getAds response received:', {
        count: response.cards.length,
        sampleImageUrl: response.cards[0]?.image_url,
      });
      return response;
    });
  },
  imageUrl: (relativePath: string) => `${API_BASE}${relativePath}`,
};
