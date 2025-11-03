import { useQuery, useInfiniteQuery } from "@tanstack/react-query";
import { api, RetailersResponse, ClientsResponse, AdsCardsResponse, BatchAdsResponse, AdsStatsResponse } from "@/lib/api";
import { fetchJson } from '@/lib/fetchJson';
import { normalizeBatchPayload, normalizeCardsPayload, Card } from '@/lib/normalize';

export function useRetailers() {
  return useQuery({
    queryKey: ["retailers"],
    queryFn: () => api.getRetailers(),
    staleTime: 1000 * 60 * 10,
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
  brands?: string[];
  search?: string;
  pageSize?: number;
}) {
  const { retailer, client, term, advertiser, start, end, types, brands, search, pageSize = 24 } = params;

  // Guard: don't fire query until both retailer and client are present
  const enabled = Boolean(retailer && client);

  // Log params to see if dates are included
  if (enabled && (start || end)) {
    console.log(`📍 useAds(${retailer}, ${client}):`, { start, end });
  }

  return useInfiniteQuery<AdsCardsResponse>({
    queryKey: ["ads", retailer, client, term, advertiser, start, end, types?.join("|"), brands?.join("|"), search, pageSize],
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
        brands,
        search,
        page: pageParam as number,
        pageSize
      });
    },
    enabled,  // Only run when both retailer and client are present
    staleTime: 0, // Always refetch - don't cache
    gcTime: 0, // Don't keep old data in memory
  });
}

function stableCsv(arr?: string[]) {
  return (arr || []).slice().sort((a, b) => a.localeCompare(b)).join(',');
}

export function useAdsBatch(
  params: {
    retailers: string[];
    clients: string[];
    term?: string;
    advertiser?: string;
    start?: string;
    end?: string;
    types?: string[];
    brands?: string[];
    search?: string;
    pageSize?: number;
  },
  opts?: {
    enabled?: boolean;
    keepPreviousData?: boolean;
    staleTime?: number;
    cacheTime?: number;
  }
) {
  const qs = new URLSearchParams();
  const retailersCsv = stableCsv(params.retailers);
  const clientsCsv = stableCsv(params.clients);
  const typesCsv = stableCsv(params.types);
  const brandsCsv = stableCsv(params.brands);

  if (retailersCsv) qs.set('retailers', retailersCsv);
  if (clientsCsv) qs.set('clients', clientsCsv);
  if (params.term) qs.set('term', params.term);
  if (params.advertiser) qs.set('advertiser', params.advertiser);
  if (params.start) qs.set('start', params.start);
  if (params.end) qs.set('end', params.end);
  if (typesCsv) qs.set('types', typesCsv);
  if (brandsCsv) qs.set('brands', brandsCsv);
  if (params.search) qs.set('search', params.search);
  qs.set('page', '1');
  qs.set('page_size', String(params.pageSize || 50)); // lowered default page size

  const enabled = !!(opts?.enabled ?? true) && !!retailersCsv && !!clientsCsv;

  return useQuery<Card[]>({
    queryKey: [
      'ads-batch',
      retailersCsv,
      clientsCsv,
      params.start || '',
      params.end || '',
      typesCsv,
      brandsCsv,
      params.search || '',
      params.pageSize || 50,
    ],
    enabled,
    placeholderData: opts?.keepPreviousData ? (prev) => prev : undefined,
    staleTime: opts?.staleTime ?? 2 * 60_000, // 2 minutes
    gcTime: opts?.cacheTime ?? 10 * 60_000,
    queryFn: async () => {
      const t0 = performance.now();
      const payload = await fetchJson(`/ads/batch?${qs.toString()}`);
      const cards = normalizeBatchPayload(payload);

      // Set stable IDs for deduplication
      const dedup = new Map<string, Card>();
      for (let i = 0; i < cards.length; i++) {
        const c = cards[i];
        const tsMs = c.timestampMs ?? (c.timestamp ? Date.parse(c.timestamp.replace(' ', 'T')) : 0);
        const id = `${c.retailer}|${c.client}|${c.brand ?? 'unknown'}|${c.adType ?? 'unknown'}|${tsMs}|${i}`;
        if (!dedup.has(id)) dedup.set(id, { ...c, id });
      }

      const result = Array.from(dedup.values());
      const t1 = performance.now();
      console.info(`[perf] batch ${result.length} in ${(t1 - t0).toFixed(0)}ms`, { retailersCsv, clientsCsv });

      return result;
    },
  });
}

export function useAdsStats(params: {
  retailers: string[];
  clients: string[];
  term?: string;
  advertiser?: string;
  start?: string;
  end?: string;
  types?: string[];
  brands?: string[];
  search?: string;
}) {
  const { retailers, clients, term, advertiser, start, end, types, brands, search } = params;

  // Only enable if we have retailers and clients
  const enabled = retailers.length > 0 && clients.length > 0;

  return useQuery<AdsStatsResponse>({
    queryKey: ["ads-stats", retailers.join(","), clients.join(","), term, advertiser, start, end, types?.join("|"), brands?.join("|"), search],
    queryFn: () => {
      if (!enabled) {
        throw new Error('retailers and clients are required');
      }
      return api.getAdsStats({
        retailers,
        clients,
        term,
        advertiser,
        start,
        end,
        types,
        brands,
        search
      });
    },
    enabled,
    staleTime: 30 * 1000, // Cache for 30 seconds
    gcTime: 5 * 60 * 1000, // Keep in memory for 5 minutes
  });
}
