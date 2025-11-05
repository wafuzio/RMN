import type { 
  Retailer, 
  RetailersResponse, 
  ClientsResponse, 
  AdCardItem, 
  AdsCardsResponse 
} from "@shared/api";
import { mark, readServerTiming, count } from './metrics';

// Re-export for convenience
export type { 
  Retailer, 
  RetailersResponse, 
  ClientsResponse, 
  AdCardItem, 
  AdsCardsResponse 
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
      console.error(`[timeFetch] Error for ${label}:`, err);
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
      ...init?.headers 
    } 
  }, label);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${res.statusText}`);
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
  types?: string[];
  search?: string;
  sort?: "latest" | "oldest" | "name";  // Sorting applied on backend before pagination
};

export const api = {
  getRetailers: () => http<RetailersResponse>(`/api/retailers`, undefined, 'retailers'),
  getClients: (retailer: string) => http<ClientsResponse>(`/api/clients?retailer=${encodeURIComponent(retailer)}`, undefined, 'clients'),
  getBrands: (retailers: string[]) => {
    const retailerParam = retailers.length > 0 ? retailers.join(',') : 'all';
    return http<{ brands: Array<{ brand: string; count: number; percentage: number }> }>(`/api/brands?retailers=${encodeURIComponent(retailerParam)}`, undefined, 'brands');
  },
  getAds: (params: GetAdsOpts) => {
    const { retailer, client, term, advertiser, page = 1, pageSize = 24, start, end, types, search, sort } = params;

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
    if (sort) q.set('sort', sort);

    const url = `/api/ads/cards?${q.toString()}`;
    console.debug('📡 getAds request:', { start, end, sort, url });

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
