import { useNavigate } from "react-router-dom";
import { useRetailers, useClients, useAds, useAdCount } from "@/hooks/useRetailAds";
import { useTimeline } from "@/hooks/useTimeline";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { StatCard } from "@/components/dashboard/StatCard";
import { RetailerSelector } from "@/components/dashboard/RetailerSelector";
import { Filters, FiltersState } from "@/components/dashboard/Filters";
import { Ad, AdCard } from "@/components/dashboard/AdCard";
import { AdModal } from "@/components/dashboard/AdModal";
import { TemporalVisualMap } from "@/components/visual/TemporalVisualMap";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import GaleLogo from "../../../web/assets/logos/GALE.svg";
import { useMemo, useState } from "react";

// Helper: Format date to YYYY-MM-DD for API
function formatLocalDate(d?: Date) {
  if (!d) return undefined;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

// Stable ID builder for ads - prevents key collisions without index dependency
type Cardish = {
  retailer: string;
  client: string;
  keyword: string;
  ad_type: string;
  brand: string;
  message: string;
  image_url: string;
};
function stableId(ad: Cardish) {
  const parts = [ad.retailer, ad.client, ad.keyword, ad.ad_type, ad.brand, ad.message, ad.image_url];
  return parts.map((p) => String(p || '').toLowerCase().replace(/\W+/g, '_')).join('-');
}

export function TemporalVisualMapPage() {
  const navigate = useNavigate();
  
  // Retailer selection
  const { data: allRetailers } = useRetailers();
  const [retailers, setRetailers] = useState<string[]>(allRetailers?.retailers.map(r => r.name) || []);
  const primaryRetailer = retailers[0];

  // Filters state
  const [filters, setFilters] = useState<FiltersState>({
    clients: [],
    types: [],
    search: "",
    keywords: [],
    datePreset: { type: "last_52_weeks" },
    groupIdentical: false,
  });

  // Debounce term for smoother searching
  const debouncedFilters = useDebouncedValue(filters, 300);

  // Fetch data
  const { data: clientsResp } = useClients(primaryRetailer);
  const adsQuery = useAds({
    retailer: primaryRetailer,
    client: filters.clients?.[0],
    term: debouncedFilters.search?.trim() || undefined,
    start: debouncedFilters.start ? formatLocalDate(debouncedFilters.start) : undefined,
    end: debouncedFilters.end ? formatLocalDate(debouncedFilters.end) : undefined,
  });

  // Fetch timeline data for all retailers
  const krogerTimeline = useTimeline({
    retailer: "kroger",
  });
  const walmartTimeline = useTimeline({
    retailer: "walmart",
  });
  const amazonTimeline = useTimeline({
    retailer: "amazon",
  });
  const instacartTimeline = useTimeline({
    retailer: "instacart",
  });
  const targetTimeline = useTimeline({
    retailer: "target",
  });

  // Merge all timeline timestamps
  const timestamps = useMemo(() => {
    const all = [
      ...(krogerTimeline.data?.timestamps || []),
      ...(walmartTimeline.data?.timestamps || []),
      ...(amazonTimeline.data?.timestamps || []),
      ...(instacartTimeline.data?.timestamps || []),
      ...(targetTimeline.data?.timestamps || []),
    ];
    console.log(`[Timeline] Merged ${all.length} timestamps from all retailers`);
    return all;
  }, [krogerTimeline.data?.timestamps, walmartTimeline.data?.timestamps, amazonTimeline.data?.timestamps, instacartTimeline.data?.timestamps, targetTimeline.data?.timestamps]);

  const ads = useMemo(() => {
    return (adsQuery.data?.pages || []).flatMap(p => p.cards).map((card, idx) => ({
      ...card,
      id: stableId(card),
    })) as Ad[];
  }, [adsQuery.data?.pages]);

  const [modalAd, setModalAd] = useState<Ad | null>(null);

  const applyFilters = () => adsQuery.refetch();
  const resetFilters = () => setFilters({ clients: [], types: [], search: "", keywords: [], datePreset: { type: "last_52_weeks" }, groupIdentical: false });

  return (
    <main className="min-h-screen py-6 pb-32 md:pb-48 px-4 md:px-8">
      <div className="w-full max-w-[1400px]">
        <header className="flex flex-wrap items-center gap-3 mb-6">
          <div className="flex items-center gap-3">
            <img src={GaleLogo} alt="GALE" className="h-8 w-auto" />
            <h1 className="text-white text-2xl font-extrabold">Temporal Visual Timeline</h1>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button onClick={() => navigate("/")} className="px-3 py-2 rounded-md bg-white/10 text-white border border-white/30 hover:bg-white/20 focus-visible:ring-2" aria-label="Back to main">← Back to Main</button>
          </div>
        </header>

        <div className="space-y-6">
          <RetailerSelector value={retailers} onChange={setRetailers} />

          <Filters
            retailer={primaryRetailer}
            clients={clientsResp?.clients || []}
            availableAdTypes={[]}
            availableKeywords={[]}
            value={filters}
            onChange={setFilters}
            onApply={applyFilters}
            onReset={resetFilters}
          />

          <div className="card-surface">
            <div className="p-4 border-b border-gray-200">
              <h3 className="text-sm font-semibold text-gray-700">Visual Timeline</h3>
              <p className="text-xs text-gray-500 mt-1">Zoom and pan to explore ad activity over time. Click on bars to filter by time period.</p>
            </div>
            <div className="p-2">
              <TemporalVisualMap
                ads={ads}
                allTimestamps={timestamps}
                onRangeChange={(from, to) => setFilters(v => ({ ...v, start: from, end: to }))}
                onAdClick={setModalAd}
                retailer={primaryRetailer}
                client={filters.clients?.join(',')}
                term={debouncedFilters.search}
              />
            </div>
          </div>

          {ads.length > 0 && (
            <div className="card-surface">
              <div className="p-4 border-b border-gray-200">
                <h3 className="text-sm font-semibold text-gray-700">Ads in Selected Period</h3>
                <p className="text-xs text-gray-500 mt-1">{ads.length} ads found</p>
              </div>
              <div className="grid gap-4 p-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))" }}>
                {ads.map((ad) => (
                  <div key={ad.id} onClick={() => setModalAd(ad)} className="cursor-pointer">
                    <AdCard ad={ad} onRemove={() => {}} onOpen={setModalAd} isLeftColumn={false} />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {modalAd && (
          <AdModal ad={modalAd} onClose={() => setModalAd(null)} onRemove={() => setModalAd(null)} />
        )}
      </div>
    </main>
  );
}
