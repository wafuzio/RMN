import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';

interface BrandsFilters {
  client?: string;
  advertiser?: string;
  start?: string;
  end?: string;
  term?: string;
  types?: string[];
}

export function useBrands(retailers: string[], filters?: BrandsFilters) {
  // Normalize query key by sorting retailers for stable caching
  const normalizedRetailers = [...retailers].sort();
  
  return useQuery({
    queryKey: ['brands', normalizedRetailers, filters],
    queryFn: () => api.getBrands(retailers, filters),
    enabled: retailers.length > 0,
    staleTime: 5 * 60_000, // 5 minutes
    refetchOnWindowFocus: false,
    refetchOnMount: false,
  });
}
