import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';

export function useClients(retailer?: string) {
  return useQuery({
    queryKey: ['clients', retailer || 'none'],
    queryFn: () => {
      if (!retailer) return Promise.resolve({ clients: [], count: 0 });
      return api.getClients(retailer);
    },
    enabled: !!retailer,
    staleTime: 5 * 60_000, // 5 minutes
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    retry: false,
  });
}
