import { useMemo, useRef, useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useRetailers, useClients, useAds } from "@/hooks/useRetailAds";
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
  keyword: string;
  ad_type: string;
  brand: string;
  message: string;
  image_url: string;
  timestamp: string;
  run_file?: string;
  ad_index?: number;
  timestamp_ms?: number;
  json_path?: string;
  run_date?: string;
};

const buildAdId = (c: Cardish, fallbackIndex: number): string => {
  // Prefer millisecond epoch for stability
  const tsMs = typeof c.timestamp_ms === 'number' 
    ? c.timestamp_ms 
    : (c.timestamp ? Date.parse(c.timestamp.replace(' ', 'T')) : 0);
  
  // Prefer full path if available; else run_file
  const runId = (c.json_path || c.run_file || 'unknown').trim();
  
  // Keep 0; only fall back if undefined/null
  const idx = c.ad_index ?? fallbackIndex;
  
  // Include brand and ad_type for semantic uniqueness
  const brand = (c.brand || 'unknown').replace(/[|]/g, '-');
  const adType = (c.ad_type || 'unknown').replace(/[|]/g, '-');
  
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

export default function Index() {
  const navigate = useNavigate();
  const [retailers, setRetailers] = useState<("kroger"|"amazon"|"instacart"|"walmart")[]>(["kroger"]);
  const { data: retailersData } = useRetailers();
  const enabledRetailers = useMemo(() => new Set(retailersData?.retailers || []), [retailersData]);

  // Use first selected retailer for single-retailer operations (filters, clients)
  const primaryRetailer = retailers[0];

  const [filters, setFilters] = useState<FiltersState>({ clients: [], types: [], search: "", keywords: [], datePreset: { type: "lifetime" } });
  const [leftFilters, setLeftFilters] = useState<FiltersState | null>(null);
  const [rightFilters, setRightFilters] = useState<FiltersState | null>(null);
  const [sortBy, setSortBy] = useState<"latest" | "oldest" | "name">("latest");
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

  // Auto-select first client if none selected
  useEffect(() => {
    if (clientsResp?.clients.length && !filters.clients?.length) {
      setFilters(prev => ({ ...prev, clients: [clientsResp.clients[0]] }));
    }
  }, [clientsResp, filters.clients]);

  // Handle multiple clients by creating queries for each
  // When all clients are selected, use the special "all" client parameter
  const selectedClients = filters.clients || [];
  const allClientsAvailable = clientsResp?.clients || [];
  const isAllClientsSelected = selectedClients.length > 0 && selectedClients.length === allClientsAvailable.length;

  // If all clients are selected, use "all"; otherwise use selected clients (up to 3)
  const clientsToQuery = isAllClientsSelected
    ? ["all"]
    : (selectedClients.length > 0 ? selectedClients : [""]);

  // Pad to ensure we always call hooks the same number of times
  const paddedClients = [...clientsToQuery];
  while (paddedClients.length < 3) paddedClients.push("");

  const client1 = paddedClients[0];
  const client2 = paddedClients[1];
  const client3 = paddedClients[2];

  // Fetch ads for each possible retailer with each selected client
  // Helper to format date as YYYY-MM-DD in local timezone (not UTC)
  const formatLocalDate = (d: Date | undefined) => {
    if (!d) return undefined;
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  const isKrogerSelected = retailers.includes("kroger");
  const krogerQuery1 = useAds({
    retailer: isKrogerSelected ? "kroger" : undefined,
    client: client1,
    term: (filters.keywords && filters.keywords.length) ? filters.keywords.join(",") : undefined,
    start: formatLocalDate(filters.start),
    end: formatLocalDate(filters.end),
    types: filters.types,
    search: filters.search,
    sort: sortBy,
  });
  const krogerQuery2 = useAds({
    retailer: isKrogerSelected ? "kroger" : undefined,
    client: client2,
    term: (filters.keywords && filters.keywords.length) ? filters.keywords.join(",") : undefined,
    start: formatLocalDate(filters.start),
    end: formatLocalDate(filters.end),
    types: filters.types,
    search: filters.search,
    sort: sortBy,
  });
  const krogerQuery3 = useAds({
    retailer: isKrogerSelected ? "kroger" : undefined,
    client: client3,
    term: (filters.keywords && filters.keywords.length) ? filters.keywords.join(",") : undefined,
    start: formatLocalDate(filters.start),
    end: formatLocalDate(filters.end),
    types: filters.types,
    search: filters.search,
    sort: sortBy,
  });

  const isWalmartSelected = retailers.includes("walmart");
  const walmartQuery1 = useAds({
    retailer: isWalmartSelected ? "walmart" : undefined,
    client: client1,
    term: (filters.keywords && filters.keywords.length) ? filters.keywords.join(",") : undefined,
    start: formatLocalDate(filters.start),
    end: formatLocalDate(filters.end),
    types: filters.types,
    search: filters.search,
    sort: sortBy,
  });
  const walmartQuery2 = useAds({
    retailer: isWalmartSelected ? "walmart" : undefined,
    client: client2,
    term: (filters.keywords && filters.keywords.length) ? filters.keywords.join(",") : undefined,
    start: formatLocalDate(filters.start),
    end: formatLocalDate(filters.end),
    types: filters.types,
    search: filters.search,
    sort: sortBy,
  });
  const walmartQuery3 = useAds({
    retailer: isWalmartSelected ? "walmart" : undefined,
    client: client3,
    term: (filters.keywords && filters.keywords.length) ? filters.keywords.join(",") : undefined,
    start: formatLocalDate(filters.start),
    end: formatLocalDate(filters.end),
    types: filters.types,
    search: filters.search,
    sort: sortBy,
  });

  const isInstacartSelected = retailers.includes("instacart");
  const instacartQuery1 = useAds({
    retailer: isInstacartSelected ? "instacart" : undefined,
    client: client1,
    term: (filters.keywords && filters.keywords.length) ? filters.keywords.join(",") : undefined,
    start: formatLocalDate(filters.start),
    end: formatLocalDate(filters.end),
    types: filters.types,
    search: filters.search,
    sort: sortBy,
  });
  const instacartQuery2 = useAds({
    retailer: isInstacartSelected ? "instacart" : undefined,
    client: client2,
    term: (filters.keywords && filters.keywords.length) ? filters.keywords.join(",") : undefined,
    start: formatLocalDate(filters.start),
    end: formatLocalDate(filters.end),
    types: filters.types,
    search: filters.search,
    sort: sortBy,
  });
  const instacartQuery3 = useAds({
    retailer: isInstacartSelected ? "instacart" : undefined,
    client: client3,
    term: (filters.keywords && filters.keywords.length) ? filters.keywords.join(",") : undefined,
    start: formatLocalDate(filters.start),
    end: formatLocalDate(filters.end),
    types: filters.types,
    search: filters.search,
    sort: sortBy,
  });

  const isAmazonSelected = retailers.includes("amazon");
  const amazonQuery1 = useAds({
    retailer: isAmazonSelected ? "amazon" : undefined,
    client: client1,
    term: (filters.keywords && filters.keywords.length) ? filters.keywords.join(",") : undefined,
    start: formatLocalDate(filters.start),
    end: formatLocalDate(filters.end),
    types: filters.types,
    search: filters.search,
    sort: sortBy,
  });
  const amazonQuery2 = useAds({
    retailer: isAmazonSelected ? "amazon" : undefined,
    client: client2,
    term: (filters.keywords && filters.keywords.length) ? filters.keywords.join(",") : undefined,
    start: formatLocalDate(filters.start),
    end: formatLocalDate(filters.end),
    types: filters.types,
    search: filters.search,
    sort: sortBy,
  });
  const amazonQuery3 = useAds({
    retailer: isAmazonSelected ? "amazon" : undefined,
    client: client3,
    term: (filters.keywords && filters.keywords.length) ? filters.keywords.join(",") : undefined,
    start: formatLocalDate(filters.start),
    end: formatLocalDate(filters.end),
    types: filters.types,
    search: filters.search,
    sort: sortBy,
  });
  
  // Collect all queries - flatten by retailer and client
  const allQueries = [
    krogerQuery1, krogerQuery2, krogerQuery3,
    walmartQuery1, walmartQuery2, walmartQuery3,
    instacartQuery1, instacartQuery2, instacartQuery3,
    amazonQuery1, amazonQuery2, amazonQuery3,
  ];

  // Build retailer-based query map (for backward compatibility)
  const queryMap = {
    kroger: [krogerQuery1, krogerQuery2, krogerQuery3],
    walmart: [walmartQuery1, walmartQuery2, walmartQuery3],
    instacart: [instacartQuery1, instacartQuery2, instacartQuery3],
    amazon: [amazonQuery1, amazonQuery2, amazonQuery3],
  };
  const retailerQueries = retailers.flatMap(r => queryMap[r]);

  // For backwards compatibility, keep adsQuery as a reference query
  const adsQuery = retailerQueries[0];

  const lf = leftFilters ?? filters;
  const rf = rightFilters ?? filters;

  // For compare mode, we'll use the first client from each filter set
  const leftClients = lf.clients || [];
  const rightClients = rf.clients || [];

  // Pad to 3 clients for query stability
  const leftPadded = [...leftClients];
  while (leftPadded.length < 3) leftPadded.push("");
  const rightPadded = [...rightClients];
  while (rightPadded.length < 3) rightPadded.push("");

  const leftAdsQuery1 = useAds({
    retailer: primaryRetailer,
    client: leftPadded[0],
    start: formatLocalDate(lf.start),
    end: formatLocalDate(lf.end),
    types: lf.types,
    search: lf.search,
    sort: sortBy,
  });
  const leftAdsQuery2 = useAds({
    retailer: primaryRetailer,
    client: leftPadded[1],
    start: formatLocalDate(lf.start),
    end: formatLocalDate(lf.end),
    types: lf.types,
    search: lf.search,
    sort: sortBy,
  });
  const leftAdsQuery3 = useAds({
    retailer: primaryRetailer,
    client: leftPadded[2],
    start: formatLocalDate(lf.start),
    end: formatLocalDate(lf.end),
    types: lf.types,
    search: lf.search,
    sort: sortBy,
  });

  const rightAdsQuery1 = useAds({
    retailer: primaryRetailer,
    client: rightPadded[0],
    start: formatLocalDate(rf.start),
    end: formatLocalDate(rf.end),
    types: rf.types,
    search: rf.search,
    sort: sortBy,
  });
  const rightAdsQuery2 = useAds({
    retailer: primaryRetailer,
    client: rightPadded[1],
    start: formatLocalDate(rf.start),
    end: formatLocalDate(rf.end),
    types: rf.types,
    search: rf.search,
    sort: sortBy,
  });
  const rightAdsQuery3 = useAds({
    retailer: primaryRetailer,
    client: rightPadded[2],
    start: formatLocalDate(rf.start),
    end: formatLocalDate(rf.end),
    types: rf.types,
    search: rf.search,
    sort: sortBy,
  });

  const flatAds: Ad[] = useMemo(() => {
    // Merge cards from all selected retailers and clients with deduplication
    try {
      const allCards = [
        ...(krogerQuery1.data?.pages.flatMap(p => p.cards || []) || []),
        ...(krogerQuery2.data?.pages.flatMap(p => p.cards || []) || []),
        ...(krogerQuery3.data?.pages.flatMap(p => p.cards || []) || []),
        ...(walmartQuery1.data?.pages.flatMap(p => p.cards || []) || []),
        ...(walmartQuery2.data?.pages.flatMap(p => p.cards || []) || []),
        ...(walmartQuery3.data?.pages.flatMap(p => p.cards || []) || []),
        ...(instacartQuery1.data?.pages.flatMap(p => p.cards || []) || []),
        ...(instacartQuery2.data?.pages.flatMap(p => p.cards || []) || []),
        ...(instacartQuery3.data?.pages.flatMap(p => p.cards || []) || []),
        ...(amazonQuery1.data?.pages.flatMap(p => p.cards || []) || []),
        ...(amazonQuery2.data?.pages.flatMap(p => p.cards || []) || []),
        ...(amazonQuery3.data?.pages.flatMap(p => p.cards || []) || []),
      ];

      // Dedupe using stable IDs (prevents duplicates from pagination/multiple queries)
      const uniq = new Map<string, Ad>();
      for (let i = 0; i < allCards.length; i++) {
        const c = allCards[i] as any;
        const id = buildAdId(c, i);
        if (!uniq.has(id)) {
          const ad = { ...c, id } as Ad;
          // Debug: log first ad to verify image_url is present
          if (i === 0) {
            console.log('First ad object:', ad);
            console.log('Has image_url?', !!ad.image_url);
          }
          uniq.set(id, ad);
        }
        // else duplicate from another page/query; ignore it
      }

      const result = Array.from(uniq.values());

      // Dev-only sanity check for duplicate IDs
      if (import.meta.env.DEV) {
        const seen = new Set<string>();
        for (const a of result) {
          if (seen.has(a.id)) {
            console.warn('Duplicate id detected:', a.id, a);
          }
          seen.add(a.id);
        }
      }

      return result;
    } catch (error) {
      console.error('Error in flatAds:', error);
      return [];
    }
  }, [
    krogerQuery1.data, krogerQuery2.data, krogerQuery3.data,
    walmartQuery1.data, walmartQuery2.data, walmartQuery3.data,
    instacartQuery1.data, instacartQuery2.data, instacartQuery3.data,
    amazonQuery1.data, amazonQuery2.data, amazonQuery3.data,
    retailers
  ]);

  // Derive available ad types from the fetched data
  const availableAdTypes = useMemo(() => {
    const typeSet = new Set<string>();
    for (const ad of flatAds) {
      if (ad.ad_type?.trim()) {
        typeSet.add(ad.ad_type.trim());
      }
    }
    return Array.from(typeSet).sort();
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

  const dnd = useDnD(ads, setAds);

  const timestamps = useMemo(() => flatAds.map(a => a.timestamp), [flatAds]);

  const totalCards = useMemo(() => {
    return [
      krogerQuery1, krogerQuery2, krogerQuery3,
      walmartQuery1, walmartQuery2, walmartQuery3,
      instacartQuery1, instacartQuery2, instacartQuery3,
      amazonQuery1, amazonQuery2, amazonQuery3,
    ].reduce((sum, query) => sum + (query.data?.pages?.[0]?.total_cards || 0), 0);
  }, [
    krogerQuery1.data, krogerQuery2.data, krogerQuery3.data,
    walmartQuery1.data, walmartQuery2.data, walmartQuery3.data,
    instacartQuery1.data, instacartQuery2.data, instacartQuery3.data,
    amazonQuery1.data, amazonQuery2.data, amazonQuery3.data,
  ]);
  // Get brand aggregations from API response (first page has the full aggregation)
  const apiBrands = useMemo(() => {
    const allBrands = retailerQueries
      .flatMap(q => q.data?.pages?.[0]?.brands || [])
      .filter(b => b.brand !== "Unknown");
    
    // Merge brands across queries
    const merged: Record<string, { count: number; percentage: number }> = {};
    for (const b of allBrands) {
      if (!merged[b.brand]) {
        merged[b.brand] = { count: 0, percentage: 0 };
      }
      merged[b.brand].count += b.count;
    }
    
    // Recalculate percentages
    const totalCount = Object.values(merged).reduce((sum, b) => sum + b.count, 0);
    return Object.entries(merged)
      .map(([brand, data]) => ({
        brand,
        count: data.count,
        percentage: totalCount > 0 ? Math.round((data.count / totalCount) * 100) : 0
      }))
      .sort((a, b) => b.count - a.count);
  }, [
    krogerQuery1.data, krogerQuery2.data, krogerQuery3.data,
    walmartQuery1.data, walmartQuery2.data, walmartQuery3.data,
    instacartQuery1.data, instacartQuery2.data, instacartQuery3.data,
    amazonQuery1.data, amazonQuery2.data, amazonQuery3.data,
  ]);
  
  const activeBrands = apiBrands.length;
  const sov = useMemo(() => {
    if (!apiBrands.length) return { brand: "-", pct: 0 };
    const top = apiBrands[0];
    return { brand: top.brand, pct: top.percentage };
  }, [apiBrands]);

  const topBrands = apiBrands;

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
  const [compareMode, setCompareMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showVisualMap, setShowVisualMap] = useState(true);
  const [showLeftVisualMap, setShowLeftVisualMap] = useState(true);
  const [showRightVisualMap, setShowRightVisualMap] = useState(true);

  const dismiss = (id: string) => setAds(prev => prev.filter(a => a.id !== id));

  const toggleSelect = (id: string) => setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const selectAll = () => setSelected(new Set(ads.map(a=>a.id)));
  const hideSelected = () => setAds(prev => prev.filter(a => !selected.has(a.id)));

  const sortedAds = useMemo(() => {
    // Sorting is now handled by the backend (in api_ads_cards endpoint)
    // This ensures consistent ordering across all pages, not just the current page
    return ads;
  }, [ads]);

  const applyFilters = () => adsQuery.refetch();
  const resetFilters = () => setFilters({ clients: [], types: [], search: "", keywords: [], datePreset: { type: "lifetime" } });

  const downloadCSV = () => {
    const rows = [
      ["retailer","client","brand","ad_type","keyword","timestamp"],
      ...ads.map(a => [a.retailer,a.client,a.brand,a.ad_type,a.keyword,a.timestamp])
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
            <button onClick={() => navigate("/brands")} className="px-3 py-2 rounded-md bg-white/10 text-white border border-white/30 hover:bg-white/20 focus-visible:ring-2" aria-label="View brand gallery">Brand Gallery</button>
            <button onClick={()=>{ setCompareMode(v=>{ const next = !v; if (next) { setLeftFilters({ ...filters }); setRightFilters({ ...filters }); } return next; }); }} className="px-3 py-2 rounded-md bg-white/10 text-white border border-white/30 hover:bg-white/20 focus-visible:ring-2" aria-pressed={compareMode} aria-label="Toggle compare mode">Compare Mode</button>
            <button onClick={downloadCSV} className="px-3 py-2 rounded-md bg-white text-[#111827] hover:bg-gray-50 focus-visible:ring-2" aria-label="Download CSV">Download CSV</button>
            <button onClick={()=>{
              const win = window.open('', '_blank', 'width=900,height=700');
              if (!win) return;
              const rows = ads.map(a => `<tr><td>${a.retailer}</td><td>${a.client}</td><td>${a.brand}</td><td>${a.ad_type}</td><td>${a.keyword}</td><td>${a.timestamp}</td></tr>`).join('');
              win.document.write(`<!doctype html><html><head><title>Ads Report</title><style>body{font-family:system-ui,sans-serif;padding:24px} table{width:100%;border-collapse:collapse} th,td{border:1px solid #e5e7eb;padding:8px;font-size:12px} th{background:#f3f4f6;text-align:left}</style></head><body><h1>Ads Report</h1><table><thead><tr><th>Retailer</th><th>Client</th><th>Brand</th><th>Type</th><th>Keyword</th><th>Timestamp</th></tr></thead><tbody>${rows}</tbody></table><script>window.onload=()=>window.print()</script></body></html>`);
              win.document.close();
            }} className="px-3 py-2 rounded-md bg-white text-[#111827] hover:bg-gray-50 focus-visible:ring-2" aria-label="Download PDF">Download PDF</button>
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
                    if (ad.ad_type === "Skyscraper") return null;
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
                    if (ad.ad_type !== "Skyscraper") return null;
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

            {adsQuery.hasNextPage && (
              <div className="flex justify-center py-6">
                <Button onClick={()=> adsQuery.fetchNextPage() } disabled={adsQuery.isFetchingNextPage}>Load More</Button>
              </div>
            )}
          </section>
        )}

        {compareMode && (
          <section className="grid md:grid-cols-2 gap-4">
            {(() => {
              // Merge left ads from all 3 queries
              const leftAllCards = [
                ...(leftAdsQuery1.data?.pages.flatMap(p=>p.cards) || []),
                ...(leftAdsQuery2.data?.pages.flatMap(p=>p.cards) || []),
                ...(leftAdsQuery3.data?.pages.flatMap(p=>p.cards) || []),
              ];
              const leftAds = leftAllCards.map((c,i)=>({ ...c, id: `L-${c.retailer}-${c.client}-${c.ad_type}-${c.brand}-${c.keyword}-${c.timestamp}-${i}`})) as Ad[];

              // Merge right ads from all 3 queries
              const rightAllCards = [
                ...(rightAdsQuery1.data?.pages.flatMap(p=>p.cards) || []),
                ...(rightAdsQuery2.data?.pages.flatMap(p=>p.cards) || []),
                ...(rightAdsQuery3.data?.pages.flatMap(p=>p.cards) || []),
              ];
              const rightAds = rightAllCards.map((c,i)=>({ ...c, id: `R-${c.retailer}-${c.client}-${c.ad_type}-${c.brand}-${c.keyword}-${c.timestamp}-${i}`})) as Ad[];

              const leftTs = leftAds.map(a=>a.timestamp);
              const rightTs = rightAds.map(a=>a.timestamp);
              return (
                <>
                  <div className="space-y-4">
                    <h2 className="text-white font-semibold">Left View</h2>
                    <Filters retailer={primaryRetailer} clients={clientsResp?.clients||[]} availableAdTypes={availableAdTypes} value={lf} onChange={(v)=>setLeftFilters(v)} onApply={()=>{leftAdsQuery1.refetch(); leftAdsQuery2.refetch(); leftAdsQuery3.refetch();}} onReset={()=>setLeftFilters({ clients: [], types: [], search: '', keywords: [], datePreset: { type: 'lifetime' } })} />
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
                    <Filters retailer={primaryRetailer} clients={clientsResp?.clients||[]} availableAdTypes={availableAdTypes} value={rf} onChange={(v)=>setRightFilters(v)} onApply={()=>{rightAdsQuery1.refetch(); rightAdsQuery2.refetch(); rightAdsQuery3.refetch();}} onReset={()=>setRightFilters({ clients: [], types: [], search: '', keywords: [], datePreset: { type: 'lifetime' } })} />
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
        <TopBrandModal open={showTopBrandModal} onOpenChange={setShowTopBrandModal} topBrands={topBrands} />
        <AllBrandsModal
          open={showAllBrandsModal}
          onOpenChange={setShowAllBrandsModal}
          brands={topBrands}
          filterParams={{
            retailers: retailers,
            clients: filters.clients || [],
            dateRange: filters.start || filters.end ? { start: filters.start, end: filters.end } : undefined,
            adTypes: filters.types || [],
            keywords: filters.keywords || [],
          }}
        />
      </div>
    </main>
  );
}
