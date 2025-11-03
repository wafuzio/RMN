import { useQuery, useInfiniteQuery } from "@tanstack/react-query";
import { api, RetailersResponse, ClientsResponse, AdsCardsResponse } from "@/lib/api";

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
  search?: string;
  pageSize?: number;
  sort?: "latest" | "oldest" | "name";
}) {
  const { retailer, client, term, advertiser, start, end, types, search, pageSize = 100, sort } = params;

  // Guard: don't fire query until both retailer and client are present
  const enabled = Boolean(retailer && client);

  // Log params to see if dates are included
  if (enabled && (start || end)) {
    console.log(`📍 useAds(${retailer}, ${client}):`, { start, end });
  }
  
  return useInfiniteQuery<AdsCardsResponse>({
    queryKey: [
      "ads",
      retailer,
      client,
      term,
      advertiser,
      start, // These are already strings from formatLocalDate
      end,   // These are already strings from formatLocalDate
      types?.join("|"),
      search,
      sort,  // Include sort in queryKey for proper cache invalidation
      pageSize
    ],
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
        sort,  // Pass sort to backend
        page: pageParam as number,
        pageSize
      });
    },
    enabled,  // Only run when both retailer and client are present
    staleTime: 0, // Always refetch - don't cache
    gcTime: 0, // Don't keep old data in memory
  });
}
