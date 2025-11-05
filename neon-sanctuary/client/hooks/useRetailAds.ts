import { useQuery, useInfiniteQuery } from "@tanstack/react-query";
import { api, RetailersResponse, ClientsResponse, AdsCardsResponse } from "@/lib/api";

// Helper: normalize params for stable query keys
function normalizeParams(p: Record<string, any>) {
  const out: Record<string, any> = {};
  for (const [k, v] of Object.entries(p || {})) {
    if (v == null || v === '' || (Array.isArray(v) && v.length === 0)) continue;
    out[k] = Array.isArray(v) ? [...v].sort() : v;
  }
  return out;
}

export function useRetailers() {
  return useQuery({
    queryKey: ["retailers"],
    queryFn: () => api.getRetailers(),
    staleTime: 1000 * 60 * 10, // 10 minutes - retailers rarely change
    gcTime: 1000 * 60 * 30, // 30 minutes in memory
    refetchOnWindowFocus: false,
    refetchOnMount: false,
  });
}

export function useClients(retailer?: string) {
  return useQuery<ClientsResponse>({
    queryKey: ["clients", retailer],
    queryFn: () => {
      if (!retailer) return Promise.resolve({ clients: [], count: 0 });
      return api.getClients(retailer);
    },
    enabled: !!retailer,
    staleTime: 1000 * 60 * 5, // 5 minutes - clients rarely change
    gcTime: 1000 * 60 * 15, // 15 minutes in memory
    refetchOnWindowFocus: false,
    refetchOnMount: false,
  });
}

export function useAds(params: {
  retailer?: string;
  client?: string;
  term?: string;
  advertiser?: string;
  start?: string;
  end?: string;
  types?: string[];
  search?: string;
  pageSize?: number;
  sort?: "latest" | "oldest" | "name";
}) {
  const { retailer, client, term, advertiser, start, end, types, search, pageSize = 48, sort } = params;

  // Guard: don't fire query until both retailer and client are present AND non-empty
  const enabled = Boolean(retailer && client && retailer.trim() && client.trim());

  // Normalize params for stable query key
  const normalized = normalizeParams({
    retailer,
    client,
    term,
    advertiser,
    start,
    end,
    types,
    search,
    sort,
    pageSize
  });

  // Debug: Log the actual query key to detect churn
  const keyDebug = JSON.stringify(normalized);
  if (import.meta.env.DEV) {
    console.log('[useAds] key:', keyDebug, 'enabled:', enabled);
  }

  return useInfiniteQuery<AdsCardsResponse>({
    queryKey: ["ads", normalized],
    initialPageParam: 1,
    getNextPageParam: (lastPage, pages) => lastPage.has_more ? pages.length + 1 : undefined,
    queryFn: ({ pageParam }) => {
      // TypeScript knows these are non-null because enabled=true
      if (!retailer || !client) {
        throw new Error('retailer and client are required');
      }
      return api.getAds({
        retailer,
        client,
        term,
        advertiser,
        start,
        end,
        types,
        search,
        sort,
        page: pageParam as number,
        pageSize
      });
    },
    enabled,
    staleTime: 60_000, // 1 minute cache - safe for ad browsing
    gcTime: 300_000, // 5 minutes in memory
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    retry: false, // Don't retry failed requests - fail fast
    placeholderData: (previousData) => previousData, // Keep previous data while fetching (replaces keepPreviousData)
  });
}
