import type { 
  Retailer, 
  RetailersResponse, 
  ClientsResponse, 
  AdCardItem, 
  AdsCardsResponse 
} from "@shared/api";

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

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  console.debug('[http] GET', url);  // Log the full URL for debugging
  const res = await fetch(url, { 
    ...init, 
    headers: { 
      ...(init?.headers||{}), 
      "Accept": "application/json",
      "ngrok-skip-browser-warning": "true",
      "User-Agent": "Mozilla/5.0"
    },
    // Most reads do not need credentials, omit by default
    credentials: init?.credentials ?? 'omit',
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${res.status} ${res.statusText} ${text}`);
  }
  return res.json() as Promise<T>;
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
};

export const api = {
  getRetailers: () => http<RetailersResponse>(`/api/retailers`),
  getClients: (retailer: string) => http<ClientsResponse>(`/api/clients?retailer=${encodeURIComponent(retailer)}`),
  getAds: (params: GetAdsOpts) => {
    const { retailer, client, term, advertiser, page = 1, pageSize = 24, start, end, types, search } = params;

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

    const url = `/api/ads/cards?${q.toString()}`;
    console.debug('📡 getAds request:', { start, end, url });

    return http<AdsCardsResponse>(url).then((response) => {
      console.debug('📡 getAds response received:', {
        count: response.cards.length,
        sampleImageUrl: response.cards[0]?.image_url,
      });
      return response;
    });
  },
  imageUrl: (relativePath: string) => `${API_BASE}${relativePath}`,
};
