import { useMemo, useRef, useState, useEffect } from "react";
import { useRetailers, useClients, useAdsBatch, useAdsStats } from "@/hooks/useRetailAds";
import { useDebounce } from "@/hooks/useDebounce";
import { StatCard } from "@/components/dashboard/StatCard";
import { RetailerSelector } from "@/components/dashboard/RetailerSelector";
import { Filters, FiltersState } from "@/components/dashboard/Filters";
import { Timeline } from "@/components/dashboard/Timeline";
import { Ad, AdCard } from "@/components/dashboard/AdCard";
import { AdModal } from "@/components/dashboard/AdModal";
import { TopBrandModal } from "@/components/dashboard/TopBrandModal";
import { AllBrandsModal } from "@/components/dashboard/AllBrandsModal";
import { SkeletonGrid } from "@/components/dashboard/SkeletonGrid";
import { TemporalVisualMap } from "@/components/visual/TemporalVisualMap";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import GaleLogo from "../../../web/assets/logos/GALE.svg";

// Stable ID builder for ads - prevents key collisions without index dependency
type Cardish = {
  retailer: string;
  client: string;
  keyword?: string | null;
  adType?: string | null;
  brand?: string | null;
  message?: string | null;
  imageUrl?: string | null;
  timestamp?: string | null;
  run_file?: string;
  ad_index?: number;
  timestampMs?: number | null;
  json_path?: string;
  run_date?: string;
};

const buildAdId = (c: Cardish, fallbackIndex: number): string => {
  const tsMs = typeof c.timestampMs === 'number'
    ? c.timestampMs
    : (c.timestamp ? Date.parse(c.timestamp.replace(' ', 'T')) : 0);

  const runId = (c.json_path || c.run_file || 'unknown').trim();
  const idx = c.ad_index ?? fallbackIndex;

  const brand = (c.brand || 'unknown').replace(/[|]/g, '-');
  const adType = (c.adType || 'unknown').replace(/[|]/g, '-');

  return `${c.retailer}|${c.client}|${runId}|${idx}|${brand}|${adType}|${tsMs}`;
};

function useDnD<T>(items: T[], setItems: (v:T[])=>void) {
  const dragIndex = useRef<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  return {
    dragIndex: dragIndex.current,
    dragOverIndex,
    makeProps: (index: number) => ({
      draggable: true,
      onDragStart: () => { dragIndex.current = index; setDragOverIndex(null); },
      onDragOver: (e: any) => { e.preventDefault?.(); setDragOverIndex(index); },
      onDragLeave: () => { setDragOverIndex(null); },
      onDrop: () => {
        if (dragIndex.current === null) return;
        const from = dragIndex.current;
        const to = index;
        const next = items.slice();
        const [moved] = next.splice(from, 1);
        next.splice(to, 0, moved as any);
        setItems(next);
        dragIndex.current = null;
        setDragOverIndex(null);
      },
    }),
  } as const;
}

function rangeFromPreset(preset: { type: string } | undefined, start?: Date, end?: Date) {
  const pad = (n: number) => String(n).padStart(2, '0');
  const ymd = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;

  const today = new Date();
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());

  if (!preset || preset.type === 'lifetime') {
    // pick a sane floor far in the past so "lifetime" always returns everything
    return { start: '2000-01-01', end: undefined };
  }
  if (preset.type === 'last7') {
    const s = new Date(startOfToday); s.setDate(s.getDate()-6);
    return { start: ymd(s), end: ymd(startOfToday) };
  }
  if (preset.type === 'last30') {
    const s = new Date(startOfToday); s.setDate(s.getDate()-29);
    return { start: ymd(s), end: ymd(startOfToday) };
  }
  if (preset.type === 'custom') {
    return { start: start ? ymd(start) : '2000-01-01', end: end ? ymd(end) : undefined };
  }
  // fallback
  return { start: '2000-01-01', end: undefined };
}

export default function Index() {
  const [retailers, setRetailers] = useState<("kroger"|"amazon"|"instacart"|"walmart")[]>(["kroger", "amazon", "instacart", "walmart"]);
  const { data: retailersData } = useRetailers();
  const enabledRetailers = useMemo(() => new Set(retailersData?.retailers || []), [retailersData]);

  // Use first selected retailer for single-retailer operations (filters, clients)
  const primaryRetailer = retailers[0];

  const [filters, setFilters] = useState<FiltersState>({ clients: [], brands: [], types: [], search: "", keywords: [], datePreset: { type: "lifetime" } });
  const [leftFilters, setLeftFilters] = useState<FiltersState | null>(null);
  const [rightFilters, setRightFilters] = useState<FiltersState | null>(null);
  const [compareMode, setCompareMode] = useState(false);
  const { data: clientsResp } = useClients(primaryRetailer);

  // Restore last session state
  useEffect(() => {
    try {
      const raw = localStorage.getItem("retail-dashboard:last-state:v1");
      if (!raw) return;
      const saved = JSON.parse(raw) as any;
      if (Array.isArray(saved.retailers) && saved.retailers.length) {
        setRetailers(saved.retailers);
      }
      if (saved.filters && typeof saved.filters === "object") {
        const f = saved.filters as Partial<FiltersState> & { start?: string; end?: string; client?: string };
        const parsedStart = f.start ? new Date(f.start) : undefined;
        const parsedEnd = f.end ? new Date(f.end) : undefined;
        const start = parsedStart && isFinite(+parsedStart) ? parsedStart : undefined;
        const end = parsedEnd && isFinite(+parsedEnd) ? parsedEnd : undefined;
        const parsed: FiltersState = {
          types: Array.isArray(f.types) ? f.types : [],
          brands: Array.isArray(f.brands) ? f.brands : [],
          search: typeof f.search === "string" ? f.search : "",
          keywords: Array.isArray(f.keywords) ? f.keywords : [],
          clients: Array.isArray(f.clients) ? f.clients : (typeof f.client === "string" ? [f.client] : []),
          start,
          end,
          datePreset: f.datePreset || { type: "lifetime" },
        };
        setFilters(prev => ({ ...prev, ...parsed }));
      }
    } catch {}
  }, []);

  // Persist state changes
  useEffect(() => {
    try {
      const toSave = {
        retailers,
        filters: {
          ...filters,
          start: filters.start ? filters.start.toISOString() : undefined,
          end: filters.end ? filters.end.toISOString() : undefined,
        },
      };
      localStorage.setItem("retail-dashboard:last-state:v1", JSON.stringify(toSave));
    } catch {}
  }, [retailers, filters]);

  // Auto-select first client if none selected (run once to prevent refetch storm)
  useEffect(() => {
    if (clientsResp?.clients.length && !filters.clients?.length) {
      setFilters(prev => ({ ...prev, clients: [clientsResp.clients[0]] }));
    }
  }, [clientsResp?.clients.length]); // Only depend on length, not the whole object

  // Handle multiple clients by creating queries for each
  // When all clients are selected, use the special "all" client parameter
  const selectedClients = filters.clients || [];
  const allClientsAvailable = clientsResp?.clients || [];
  const isAllClientsSelected = selectedClients.length > 0 && selectedClients.length === allClientsAvailable.length;

  // If all clients are selected, use "all"; otherwise use selected clients
  const clientsToQuery = isAllClientsSelected
    ? ["all"]
    : (selectedClients.length > 0 ? selectedClients : []);

  // Apply debouncing to filter changes to avoid excessive refetching
  // When user changes filters, wait 500ms before making new queries
  const debouncedFilters = useDebounce(filters, 500);
  const debouncedRetailers = useDebounce(retailers, 500);

  // List of active retailers (ones currently selected)
  const activeRetailers = debouncedRetailers.length > 0 ? debouncedRetailers : ["kroger"];

  // Build query params for debounced filters with explicit date ranges
  const queryParams = useMemo(() => {
    const range = rangeFromPreset(debouncedFilters.datePreset, debouncedFilters.start, debouncedFilters.end);
    return {
      start: range.start,
      end: range.end,
      types: debouncedFilters.types,
      brands: debouncedFilters.brands,
      search: (debouncedFilters.keywords && debouncedFilters.keywords.length)
        ? debouncedFilters.keywords.join(",")
        : debouncedFilters.search,
    };
  }, [debouncedFilters]);

  // Main batch query for filtered ads - simplified, always-on
  // Load larger page size to get all data in single request
  const batchAdsQuery = useAdsBatch({
    retailers: activeRetailers,
    clients: clientsToQuery.length > 0 ? clientsToQuery : ["all"],
    start: queryParams.start,
    end: queryParams.end || undefined, // explicitly pass undefined instead of empty string
    types: queryParams.types,
    brands: queryParams.brands,
    search: queryParams.search,
    pageSize: 200, // increased to load more cards upfront
  }, { enabled: !compareMode, keepPreviousData: false, staleTime: 0 });

  // Brands batch: DISABLED - we compute brands from main batch data instead
  const brandsBatchQuery = { data: batchAdsQuery.data, isLoading: false, error: null };

  // Stats query: DISABLED - compute from loaded data instead to reduce API calls
  // This saves a completely separate API request and speeds up dashboard load
  const statsQuery = { data: undefined, isLoading: false, error: null };

  // Compare mode queries: DISABLED for now to reduce concurrent requests
  // Will re-enable when explicitly needed
  const leftBatchQuery = { data: [], isLoading: false, error: null };
  const rightBatchQuery = { data: [], isLoading: false, error: null };

  // Reference queries for backward compatibility and status checking
  const adsQuery = batchAdsQuery;

  const flatAds: Ad[] = useMemo(() => {
    const rows = batchAdsQuery.data || [];
    // Add snake_case back for now so existing JSX doesn't break
    const uniq = new Map<string, Ad>();
    for (let i = 0; i < rows.length; i++) {
      const c = rows[i] as any;
      const id = buildAdId(
        {
          retailer: c.retailer,
          client: c.client,
          keyword: c.keyword || '',
          adType: c.adType || '',
          brand: c.brand || '',
          message: c.message || '',
          imageUrl: c.imageUrl || '',
          timestamp: c.timestamp || '',
          ad_index: c._raw?.ad_index ?? i,
          timestampMs: c.timestampMs ?? null,
          json_path: c._raw?.json_path,
          run_file: c._raw?.run_file,
          run_date: c._raw?.run_date,
        },
        i
      );
      if (!uniq.has(id)) {
        uniq.set(id, {
          ...c,
          id,
          ad_type: c.adType ?? c._raw?.ad_type ?? null,
          image_url: c.imageUrl ?? c._raw?.image_url ?? null,
          has_image: c.hasImage ?? c._raw?.has_image ?? Boolean(c.imageUrl),
        } as Ad);
      }
    }
    const result = Array.from(uniq.values());
    if (import.meta.env.DEV) {
      console.info('[ui] cards before filters', result.length, result[0]);
    }
    return result;
  }, [batchAdsQuery.data]);

  // Derive available ad types from the fetched data
  const availableAdTypes = useMemo(() => {
    const typeSet = new Set<string>();
    for (const ad of flatAds) {
      if (ad.adType?.trim()) {
        typeSet.add(ad.adType.trim());
      }
    }
    return Array.from(typeSet).sort();
  }, [flatAds]);

  // Derive available brands from loaded data (fast, no extra round-trip)
  const availableBrands = useMemo(() => {
    const s = new Set<string>();
    for (const ad of flatAds) {
      if (ad.brand?.trim() && ad.brand !== 'Unknown') {
        s.add(ad.brand.trim());
      }
    }
    return Array.from(s).sort();
  }, [flatAds]);

  const [ads, setAds] = useState<Ad[]>([]);
  // sync local ads list with fetched pages (enables reordering/dismiss)
  // Force clear when filters change to prevent stale data mixing
  useEffect(() => { 
    setAds(flatAds); 
  }, [flatAds]);
  
  // Clear ads when date filters change
  useEffect(() => {
    setAds([]);
    console.log('🔄 Date filters changed:', { start: filters.start, end: filters.end });
  }, [filters.start, filters.end]);

  // Debug: Show retailer coverage to verify multi-retailer support
  useEffect(() => {
    if (!flatAds?.length) return;
    const byRetailer: Record<string, number> = {};
    for (const a of flatAds) byRetailer[a.retailer] = (byRetailer[a.retailer] || 0) + 1;
    console.info('[ui] byRetailer', byRetailer, 'total', flatAds.length);
  }, [flatAds]);

  const dnd = useDnD(ads, setAds);

  const timestamps = useMemo(() => flatAds.map(a => a.timestamp), [flatAds]);

  const totalCards = useMemo(() => flatAds.length || statsQuery.data?.total_cards || 0, [flatAds.length, statsQuery.data?.total_cards]);
  const activeBrands = useMemo(() => {
    // Count total available brands across all retailers, not just filtered ads
    return availableBrands.length;
  }, [availableBrands]);
  const sov = useMemo(() => {
    const countByBrand: Record<string, number> = {};
    for (const a of flatAds) countByBrand[a.brand] = (countByBrand[a.brand]||0)+1;
    const entries = Object.entries(countByBrand).sort((a,b)=>b[1]-a[1]);
    if (!entries.length) return { brand: "-", pct: 0 };
    const top = entries[0];
    const pct = Math.round((top[1] / flatAds.length) * 100);
    return { brand: top[0], pct: isFinite(pct) ? pct : 0 };
  }, [flatAds]);

  const topBrands = useMemo(() => {
    const countByBrand: Record<string, number> = {};
    const retailersByBrand: Record<string, Record<string, number>> = {};

    for (const a of flatAds) {
      countByBrand[a.brand] = (countByBrand[a.brand]||0)+1;

      if (!retailersByBrand[a.brand]) retailersByBrand[a.brand] = {};
      retailersByBrand[a.brand][a.retailer] = (retailersByBrand[a.brand][a.retailer]||0)+1;
    }

    const entries = Object.entries(countByBrand).sort((a,b)=>b[1]-a[1]);
    return entries.map(([brand, count]) => ({
      brand,
      count,
      percentage: flatAds.length > 0 ? Math.round((count / flatAds.length) * 100) : 0,
      retailers: retailersByBrand[brand],
    }));
  }, [flatAds]);

  // All brands with counts from loaded data (for the modal)
  const allBrandsForModal = useMemo(() => {
    const countByBrand: Record<string, number> = {};
    const retailersByBrand: Record<string, Record<string, number>> = {};
    let totalAds = 0;

    for (const ad of flatAds) {
      if (ad.brand?.trim() && ad.brand !== 'Unknown') {
        countByBrand[ad.brand] = (countByBrand[ad.brand] || 0) + 1;
        if (!retailersByBrand[ad.brand]) retailersByBrand[ad.brand] = {};
        retailersByBrand[ad.brand][ad.retailer] = (retailersByBrand[ad.brand][ad.retailer] || 0) + 1;
        totalAds++;
      }
    }

    const entries = Object.entries(countByBrand).sort((a, b) => b[1] - a[1]);
    return entries.map(([brand, count]) => ({
      brand,
      count,
      percentage: totalAds > 0 ? Math.round((count / totalAds) * 100) : 0,
      retailers: retailersByBrand[brand],
    }));
  }, [flatAds]);

  const trend: "up"|"down"|null = useMemo(()=>{
    if (timestamps.length < 2) return null;
    const recent = timestamps.slice(-50).map(t=>new Date(t.replace(" ","T"))).sort((a,b)=>+a-+b);
    const mid = Math.floor(recent.length/2);
    const left = recent.slice(0, mid).length;
    const right = recent.slice(mid).length;
    return right >= left ? "up" : "down";
  }, [timestamps]);

  const [modalAd, setModalAd] = useState<Ad|null>(null);
  const [showTopBrandModal, setShowTopBrandModal] = useState(false);
  const [showAllBrandsModal, setShowAllBrandsModal] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showVisualMap, setShowVisualMap] = useState(true);
  const [showLeftVisualMap, setShowLeftVisualMap] = useState(true);
  const [showRightVisualMap, setShowRightVisualMap] = useState(true);
  const [sortBy, setSortBy] = useState<"latest" | "oldest" | "name">("latest");

  const dismiss = (id: string) => setAds(prev => prev.filter(a => a.id !== id));

  const toggleSelect = (id: string) => setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const selectAll = () => setSelected(new Set(ads.map(a=>a.id)));
  const hideSelected = () => setAds(prev => prev.filter(a => !selected.has(a.id)));

  const handleBrandClick = (brand: string) => {
    setFilters(prev => ({
      ...prev,
      brands: [brand],
    }));
    setShowTopBrandModal(false);
    setShowAllBrandsModal(false);
  };

  const sortedAds = useMemo(() => {
    const sorted = [...ads];
    if (sortBy === "latest") {
      sorted.sort((a, b) => new Date(b.timestamp.replace(" ", "T")).getTime() - new Date(a.timestamp.replace(" ", "T")).getTime());
    } else if (sortBy === "oldest") {
      sorted.sort((a, b) => new Date(a.timestamp.replace(" ", "T")).getTime() - new Date(b.timestamp.replace(" ", "T")).getTime());
    } else if (sortBy === "name") {
      sorted.sort((a, b) => a.brand.localeCompare(b.brand));
    }
    return sorted;
  }, [ads, sortBy]);

  const applyFilters = () => adsQuery.refetch();
  const resetFilters = () => setFilters({ clients: [], brands: [], types: [], search: "", keywords: [], datePreset: { type: "lifetime" } });

  const downloadCSV = () => {
    const rows = [
      ["retailer","client","brand","ad_type","keyword","timestamp"],
      ...ads.map(a => [a.retailer,a.client,a.brand,a.adType,a.keyword,a.timestamp])
    ];
    const csv = rows.map(r => r.map(x => `"${String(x).replace(/"/g,'""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'ads.csv'; a.click(); URL.revokeObjectURL(url);
  };

  return (
    <main className="min-h-screen py-6 pb-32 md:pb-48 px-4 md:px-8">
      <div className="w-full max-w-[1400px]">
        <header className="flex flex-wrap items-center gap-3 mb-6">
          <div className="flex items-center gap-3">
            <img src={GaleLogo} alt="GALE" className="h-8 w-auto" />
            <h1 className="text-white text-2xl font-extrabold">Retail Ad Monitoring</h1>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button type="button" disabled className="px-3 py-2 rounded-md bg-white/5 text-white/50 border border-white/20 cursor-not-allowed" aria-label="Compare mode (coming soon)">Compare Mode</button>

            {/* Download button with dropdown */}
            <div className="relative group">
              <button type="button" className="px-3 py-2 rounded-md bg-white text-[#111827] hover:bg-gray-50 focus-visible:ring-2">Download</button>
              <div className="absolute right-0 mt-0 w-40 bg-white rounded-md shadow-lg hidden group-hover:block z-50">
                <button type="button" onClick={downloadCSV} className="w-full text-left px-4 py-2 hover:bg-gray-100 text-sm" aria-label="Download CSV">Download CSV</button>
                <button type="button" onClick={()=>{
                  const win = window.open('', '_blank', 'width=900,height=700');
                  if (!win) return;
                  const rows = ads.map(a => `<tr><td>${a.retailer}</td><td>${a.client}</td><td>${a.brand}</td><td>${a.adType}</td><td>${a.keyword}</td><td>${a.timestamp}</td></tr>`).join('');
                  win.document.write(`<!doctype html><html><head><title>Ads Report</title><style>body{font-family:system-ui,sans-serif;padding:24px} table{width:100%;border-collapse:collapse} th,td{border:1px solid #e5e7eb;padding:8px;font-size:12px} th{background:#f3f4f6;text-align:left}</style></head><body><h1>Ads Report</h1><table><thead><tr><th>Retailer</th><th>Client</th><th>Brand</th><th>Type</th><th>Keyword</th><th>Timestamp</th></tr></thead><tbody>${rows}</tbody></table><script>window.onload=()=>window.print()</script></body></html>`);
                  win.document.close();
                }} className="w-full text-left px-4 py-2 hover:bg-gray-100 text-sm border-t border-gray-200" aria-label="Download PDF">Download PDF</button>
              </div>
            </div>

            {/* Clients selector in header */}
            <div className="relative group">
              <div
                role="button"
                tabIndex={0}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); } }}
                className="px-3 py-2 rounded-md bg-white/10 text-white border border-white/30 hover:bg-white/20 focus-visible:ring-2 cursor-pointer"
              >
                {!filters.clients?.length ? "Select Clients" : filters.clients.length === (clientsResp?.clients?.length || 0) ? "All Clients" : `${filters.clients.length} Client${filters.clients.length === 1 ? '' : 's'}`}
              </div>
              <div className="absolute right-0 mt-0 w-56 bg-white rounded-md shadow-lg hidden group-hover:block z-50 max-h-72 overflow-y-auto" role="menu" aria-label="Clients">
                <div
                  role="menuitem"
                  tabIndex={0}
                  onClick={() => {
                    const allClients = clientsResp?.clients || [];
                    if (filters.clients?.length === allClients.length) {
                      setFilters(f => ({ ...f, clients: [] }));
                    } else {
                      setFilters(f => ({ ...f, clients: allClients }));
                    }
                  }}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.currentTarget.click(); } }}
                  className="w-full text-left px-4 py-2 hover:bg-gray-100 text-sm font-semibold border-b border-gray-200 cursor-pointer"
                >
                  All
                </div>
                {(clientsResp?.clients || []).map((c) => (
                  <div
                    key={c}
                    role="menuitemcheckbox"
                    aria-checked={!!filters.clients?.includes(c)}
                    tabIndex={0}
                    onClick={() => {
                      setFilters(f => {
                        const next = new Set(f.clients || []);
                        if (next.has(c)) next.delete(c); else next.add(c);
                        return { ...f, clients: Array.from(next) };
                      });
                    }}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.currentTarget.click(); } }}
                    className="w-full text-left px-4 py-2 hover:bg-gray-100 text-sm flex items-center cursor-pointer"
                  >
                    <input type="checkbox" checked={filters.clients?.includes(c) || false} readOnly className="mr-2" />
                    {c}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </header>

        {!compareMode && (
          <section className="space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
              <StatCard value={totalCards} label="Total Ad Cards" />
              <StatCard
                value={activeBrands}
                label="Active Brands"
                onClick={() => setShowAllBrandsModal(true)}
              />
              <StatCard
                value={`${sov.brand}`}
                label="Top Brand by SOV"
                hint={`${sov.pct}%`}
                brandName={sov.brand}
                onClick={() => setShowTopBrandModal(true)}
              />
              <StatCard value={""} label="Ad Volume Trend" trend={trend} />
            </div>

            <RetailerSelector value={retailers} onChange={setRetailers} enabledRetailers={enabledRetailers} />

            <Filters
              retailer={primaryRetailer}
              brands={availableBrands}
              clients={clientsResp?.clients || []}
              availableAdTypes={availableAdTypes}
              value={filters}
              onChange={setFilters}
              onApply={applyFilters}
              onReset={resetFilters}
            />

            <Timeline timestamps={timestamps} onRangeChange={(from, to) => setFilters(v => ({ ...v, start: from, end: to, datePreset: { type: "custom" } }))} />

            <div className="card-surface">
              <div className="flex items-center justify-between p-4 border-b border-gray-200 cursor-pointer" onClick={() => setShowVisualMap(!showVisualMap)}>
                <h3 className="text-sm font-semibold text-gray-700">Visual Timeline</h3>
                <button className="p-1 hover:bg-gray-100 rounded transition" aria-label={showVisualMap ? "Collapse visual timeline" : "Expand visual timeline"}>
                  <svg className={`w-5 h-5 text-gray-600 transition-transform ${showVisualMap ? '' : '-rotate-90'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                  </svg>
                </button>
              </div>
              {showVisualMap && (
                <div className="p-2">
                  <TemporalVisualMap ads={ads} onRangeChange={(from,to)=> setFilters(v=>({ ...v, start: from, end: to }))} onAdClick={setModalAd} />
                </div>
              )}
            </div>

            <div className="card-surface p-3 flex items-center gap-4">
              <div className="flex items-center gap-2">
                <Checkbox checked={selected.size === ads.length && ads.length>0} onCheckedChange={(v)=> v ? selectAll() : setSelected(new Set())} aria-label="Select all" />
                <span className="text-sm text-[#111827]">Select All</span>
              </div>
              <Button variant="outline" onClick={hideSelected}>Hide Selected</Button>
              <div className="ml-auto flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <label htmlFor="sort-by" className="text-sm text-[#111827] font-medium">Sort by:</label>
                  <Select value={sortBy} onValueChange={(v) => setSortBy(v as "latest" | "oldest" | "name")}>
                    <SelectTrigger id="sort-by" className="w-32 h-9 bg-white border-gray-300">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="latest">Latest</SelectItem>
                      <SelectItem value="oldest">Oldest</SelectItem>
                      <SelectItem value="name">Name</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <span className="text-sm text-white/80">{ads.length} results</span>
              </div>
            </div>

            {adsQuery.isError ? (
              <div className="card-surface p-6 text-center">
                <div className="text-[#111827] font-semibold mb-2">Failed to load ads.</div>
                <Button onClick={()=>adsQuery.refetch()}>Retry</Button>
              </div>
            ) : adsQuery.isLoading ? (
              <SkeletonGrid count={8} />
            ) : ads.length === 0 ? (
              <div className="card-surface p-10 text-center text-[#111827]">No ads found for the selected filters.</div>
            ) : (
              <div className="grid gap-4" style={{ gridTemplateColumns: "1fr minmax(0, 300px)" }}>
                <div className="space-y-4">
                  {sortedAds.map((ad, idx) => {
                    if (ad.adType === "Skyscraper") return null;
                    return (
                    <div
                      key={ad.id}
                      onClickCapture={(e)=>{ const target = e.target as HTMLElement; if (target?.closest('input[type=\"checkbox\"]')) e.stopPropagation(); }}
                    >
                      <div className="absolute z-10 m-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <input aria-label="Select ad" type="checkbox" className="h-4 w-4" checked={selected.has(ad.id)} onChange={()=>toggleSelect(ad.id)} />
                      </div>
                      <AdCard ad={ad} onRemove={dismiss} onOpen={setModalAd} draggableProps={dnd.makeProps(idx)} dragIndex={dnd.dragIndex} dragOverIndex={dnd.dragOverIndex} currentIndex={idx} />
                    </div>
                    );
                  })}
                </div>
                <div className="space-y-4">
                  {sortedAds.map((ad, idx) => {
                    if (ad.adType !== "Skyscraper") return null;
                    return (
                    <div
                      key={ad.id}
                      onClickCapture={(e)=>{ const target = e.target as HTMLElement; if (target?.closest('input[type=\"checkbox\"]')) e.stopPropagation(); }}
                    >
                      <div className="absolute z-10 m-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <input aria-label="Select ad" type="checkbox" className="h-4 w-4" checked={selected.has(ad.id)} onChange={()=>toggleSelect(ad.id)} />
                      </div>
                      <AdCard ad={ad} onRemove={dismiss} onOpen={setModalAd} draggableProps={dnd.makeProps(idx)} dragIndex={dnd.dragIndex} dragOverIndex={dnd.dragOverIndex} currentIndex={idx} />
                    </div>
                    );
                  })}
                </div>
              </div>
            )}

          </section>
        )}

        {compareMode && (
          <section className="grid md:grid-cols-2 gap-4">
            {(() => {
              // Hook returns normalized Card[] directly
              const leftAds  = (leftBatchQuery.data  || []).map((c,i)=>({ ...c, id: `L-${buildAdId(c, i)}` })) as Ad[];
              const rightAds = (rightBatchQuery.data || []).map((c,i)=>({ ...c, id: `R-${buildAdId(c, i)}` })) as Ad[];

              const leftTs = leftAds.map(a=>a.timestamp);
              const rightTs = rightAds.map(a=>a.timestamp);
              return (
                <>
                  <div className="space-y-4">
                    <h2 className="text-white font-semibold">Left View</h2>
                    <Filters retailer={primaryRetailer} brands={availableBrands} clients={clientsResp?.clients||[]} availableAdTypes={availableAdTypes} value={lf} onChange={(v)=>setLeftFilters(v)} onApply={()=>{}} onReset={()=>setLeftFilters({ clients: [], types: [], brands: [], search: '', keywords: [], datePreset: { type: 'lifetime' } })} />
                    <Timeline timestamps={leftTs} onRangeChange={(from,to)=> setLeftFilters(prev=>({ ...prev, start: from, end: to, datePreset: { type: 'custom' } }))} />
                    <div className="card-surface">
                      <div className="flex items-center justify-between p-4 border-b border-gray-200 cursor-pointer" onClick={() => setShowLeftVisualMap(!showLeftVisualMap)}>
                        <h3 className="text-sm font-semibold text-gray-700">Visual Timeline</h3>
                        <button className="p-1 hover:bg-gray-100 rounded transition" aria-label={showLeftVisualMap ? "Collapse visual timeline" : "Expand visual timeline"}>
                          <svg className={`w-5 h-5 text-gray-600 transition-transform ${showLeftVisualMap ? '' : '-rotate-90'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                          </svg>
                        </button>
                      </div>
                      {showLeftVisualMap && (
                        <div className="p-2">
                          <TemporalVisualMap ads={leftAds} onRangeChange={(from,to)=> setLeftFilters(prev=>({ ...prev, start: from, end: to, datePreset: { type: 'custom' } }))} onAdClick={setModalAd} />
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="space-y-4">
                    <h2 className="text-white font-semibold">Right View</h2>
                    <Filters retailer={primaryRetailer} brands={availableBrands} clients={clientsResp?.clients||[]} availableAdTypes={availableAdTypes} value={rf} onChange={(v)=>setRightFilters(v)} onApply={()=>{}} onReset={()=>setRightFilters({ clients: [], types: [], brands: [], search: '', keywords: [], datePreset: { type: 'lifetime' } })} />
                    <Timeline timestamps={rightTs} onRangeChange={(from,to)=> setRightFilters(prev=>({ ...prev, start: from, end: to, datePreset: { type: 'custom' } }))} />
                    <div className="card-surface">
                      <div className="flex items-center justify-between p-4 border-b border-gray-200 cursor-pointer" onClick={() => setShowRightVisualMap(!showRightVisualMap)}>
                        <h3 className="text-sm font-semibold text-gray-700">Visual Timeline</h3>
                        <button className="p-1 hover:bg-gray-100 rounded transition" aria-label={showRightVisualMap ? "Collapse visual timeline" : "Expand visual timeline"}>
                          <svg className={`w-5 h-5 text-gray-600 transition-transform ${showRightVisualMap ? '' : '-rotate-90'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                          </svg>
                        </button>
                      </div>
                      {showRightVisualMap && (
                        <div className="p-2">
                          <TemporalVisualMap ads={rightAds} onRangeChange={(from,to)=> setRightFilters(prev=>({ ...prev, start: from, end: to, datePreset: { type: 'custom' } }))} onAdClick={setModalAd} />
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="col-span-full card-surface p-3 text-center">Exit Comparison to view full visual maps.</div>
                </>
              );
            })()}
          </section>
        )}

        <AdModal open={!!modalAd} ad={modalAd} onOpenChange={(v)=>!v && setModalAd(null)} onCompare={(ad)=>{ setModalAd(null); setCompareMode(true); }} />
        <TopBrandModal
          open={showTopBrandModal}
          onOpenChange={setShowTopBrandModal}
          topBrands={topBrands}
          onRetailerClick={(brand) => handleBrandClick(brand)}
        />
        <AllBrandsModal
          open={showAllBrandsModal}
          onOpenChange={setShowAllBrandsModal}
          brands={allBrandsForModal}
          filterParams={{
            retailers: retailers,
            clients: filters.clients || [],
            dateRange: filters.start || filters.end ? { start: filters.start, end: filters.end } : undefined,
            adTypes: filters.types || [],
            keywords: filters.keywords || [],
          }}
          onRetailerClick={(brand) => handleBrandClick(brand)}
        />
      </div>
    </main>
  );
}
