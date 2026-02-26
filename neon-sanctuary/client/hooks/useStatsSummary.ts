import { useQuery } from '@tanstack/react-query';

interface StatsSummaryResponse {
  totalCards: number;
  activeBrands: number;
  topBrand: { brand: string; count: number; percentage: number } | null;
  brands: Array<{ brand: string; count: number; percentage: number }>;
  builtAt: string | null;
}

export function useStatsSummary(retailers: string[], client?: string) {
  const normalizedRetailers = [...retailers].sort();

  return useQuery<StatsSummaryResponse>({
    queryKey: ['stats-summary', normalizedRetailers, client],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (retailers.length > 0) {
        params.set('retailers', retailers.join(','));
      }
      if (client && client !== 'all') {
        params.set('client', client);
      }
      const resp = await fetch(`/api/stats/summary?${params.toString()}`);
      if (!resp.ok) throw new Error(`Stats summary failed: ${resp.status}`);
      return resp.json();
    },
    enabled: retailers.length > 0,
    staleTime: 2 * 60_000, // 2 minutes
    refetchOnWindowFocus: false,
    refetchOnMount: false,
  });
}
