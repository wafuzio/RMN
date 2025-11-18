import { useQuery } from '@tanstack/react-query';

interface TimelineParams {
  retailer: string;
  client?: string;
  advertiser?: string;
  start?: string;
  end?: string;
  term?: string;
}

export function useTimeline(params: TimelineParams) {
  const { retailer, client, advertiser, start, end, term } = params;
  
  return useQuery({
    queryKey: ['timeline', retailer, client, advertiser, start, end, term],
    queryFn: async () => {
      const searchParams = new URLSearchParams();
      searchParams.set('retailer', retailer);
      if (client) searchParams.set('client', client);
      if (advertiser) searchParams.set('advertiser', advertiser);
      if (start) searchParams.set('start', start);
      if (end) searchParams.set('end', end);
      if (term) searchParams.set('term', term);
      
      const response = await fetch(`/api/timeline?${searchParams.toString()}`);
      if (!response.ok) {
        throw new Error(`Timeline fetch failed: ${response.statusText}`);
      }
      
      const data = await response.json() as { timestamps: string[] };
      return data.timestamps || [];
    },
    enabled: !!retailer,
    staleTime: 5 * 60_000, // 5 minutes
    refetchOnWindowFocus: false,
  });
}
