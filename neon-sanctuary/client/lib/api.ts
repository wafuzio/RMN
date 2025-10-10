const DEFAULT_API_BASE = "https://foilable-ruthie-consultive.ngrok-free.dev";
export const API_BASE = import.meta.env.VITE_API_BASE || DEFAULT_API_BASE;

export type Retailer = "kroger" | "instacart" | "walmart" | "amazon";

export interface RetailersResponse { retailers: string[]; count: number }
export interface ClientsResponse { clients: string[]; count: number }
export interface AdCardItem {
  retailer: string;
  client: string;
  keyword: string;
  ad_type: string;
  brand: string;
  message: string;
  image_url: string;
  timestamp: string; // YYYY-MM-DD HH:MM:SS
  run_date?: string;
}
export interface AdsCardsResponse { cards: AdCardItem[]; has_more: boolean; total_cards: number }

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { 
    ...init, 
    headers: { 
      ...(init?.headers||{}), 
      "Accept": "application/json",
      "ngrok-skip-browser-warning": "true",
      "User-Agent": "Mozilla/5.0"
    } 
  });
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  getRetailers: () => http<RetailersResponse>(`/api/retailers`),
  getClients: (retailer: string) => http<ClientsResponse>(`/api/clients?retailer=${encodeURIComponent(retailer)}`),
  getAds: (params: { retailer: string; client?: string; page?: number; page_size?: number; start?: string; end?: string; types?: string[]; search?: string; }) => {
    const { retailer, client, page=1, page_size=24, start, end, types, search } = params;
    const q = new URLSearchParams({ retailer, page: String(page), page_size: String(page_size) });
    if (client) q.set("client", client);
    if (start) q.set("start", start);
    if (end) q.set("end", end);
    if (search) q.set("search", search);
    if (types?.length) q.set("types", types.join(","));
    return http<AdsCardsResponse>(`/api/ads/cards?${q.toString()}`);
  },
  imageUrl: (relativePath: string) => `${API_BASE}${relativePath}`,
};
