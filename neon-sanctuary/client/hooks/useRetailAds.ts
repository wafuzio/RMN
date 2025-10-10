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

export function useAds(params: { retailer: string; client?: string; start?: string; end?: string; types?: string[]; search?: string; pageSize?: number; }) {
  const { retailer, client, start, end, types, search, pageSize=24 } = params;
  return useInfiniteQuery<AdsCardsResponse>({
    queryKey: ["ads", retailer, client, start, end, types?.join("|"), search, pageSize],
    initialPageParam: 1,
    getNextPageParam: (lastPage, pages) => lastPage.has_more ? pages.length + 1 : undefined,
    queryFn: ({ pageParam }) => api.getAds({ retailer, client, start, end, types, search, page: pageParam as number, page_size: pageSize }),
    enabled: !!retailer,
  });
}
