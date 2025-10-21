import { useMemo, useRef, useState, useEffect } from "react";
import { useRetailers, useClients, useAds } from "@/hooks/useRetailAds";
import { StatCard } from "@/components/dashboard/StatCard";
import { RetailerSelector } from "@/components/dashboard/RetailerSelector";
import { Filters, FiltersState } from "@/components/dashboard/Filters";
import { Timeline } from "@/components/dashboard/Timeline";
import { Ad, AdCard } from "@/components/dashboard/AdCard";
import { AdModal } from "@/components/dashboard/AdModal";
import { SkeletonGrid } from "@/components/dashboard/SkeletonGrid";
import { TemporalVisualMap } from "@/components/visual/TemporalVisualMap";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
  return {
    makeProps: (index: number) => ({
      draggable: true,
      onDragStart: () => { dragIndex.current = index; },
      onDragOver: (e: any) => { e.preventDefault?.(); },
      onDrop: () => {
        if (dragIndex.current === null) return;
        const from = dragIndex.current;
        const to = index;
        const next = items.slice();
        const [moved] = next.splice(from, 1);
        next.splice(to, 0, moved as any);
        setItems(next);
        dragIndex.current = null;
      },
    }),
  } as const;
}

export default function Index() {
  const [retailers, setRetailers] = useState<("kroger"|"amazon"|"instacart"|"walmart")[]>(["kroger"]);
  const { data: retailersData } = useRetailers();
  const enabledRetailers = useMemo(() => new Set(retailersData?.retailers || []), [retailersData]);

  // Use first selected retailer for single-retailer operations (filters, clients)
  const primaryRetailer = retailers[0];

  const [filters, setFilters] = useState<FiltersState>({ types: [], search: "", keywords: [], datePreset: { type: "lifetime" } });
  const [leftFilters, setLeftFilters] = useState<FiltersState | null>(null);
  const [rightFilters, setRightFilters] = useState<FiltersState | null>(null);
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
        const f = saved.filters as Partial<FiltersState> & { start?: string; end?: string };
        const parsedStart = f.start ? new Date(f.start) : undefined;
        const parsedEnd = f.end ? new Date(f.end) : undefined;
        const start = parsedStart && isFinite(+parsedStart) ? parsedStart : undefined;
        const end = parsedEnd && isFinite(+parsedEnd) ? parsedEnd : undefined;
        const parsed: FiltersState = {
          types: Array.isArray(f.types) ? f.types : [],
          search: typeof f.search === "string" ? f.search : "",
          keywords: Array.isArray(f.keywords) ? f.keywords : [],
          client: typeof f.client === "string" ? f.client : undefined,
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
    if (clientsResp?.clients.length && !filters.client) {
      setFilters(prev => ({ ...prev, client: clientsResp.clients[0] }));
    }
  }, [clientsResp, filters.client]);

  // Fetch ads for each possible retailer (must call hooks unconditionally)
  const krogerQuery = useAds({
    retailer: "kroger",
    client: filters.client,
    start: filters.start ? filters.start.toISOString().slice(0,10) : undefined,
    end: filters.end ? filters.end.toISOString().slice(0,10) : undefined,
    types: filters.types,
    search: (filters.keywords && filters.keywords.length) ? filters.keywords.join(",") : filters.search,
  });
  const walmartQuery = useAds({
    retailer: "walmart",
    client: filters.client,
    start: filters.start ? filters.start.toISOString().slice(0,10) : undefined,
    end: filters.end ? filters.end.toISOString().slice(0,10) : undefined,
    types: filters.types,
    search: (filters.keywords && filters.keywords.length) ? filters.keywords.join(",") : filters.search,
  });
  const instacartQuery = useAds({
    retailer: "instacart",
    client: filters.client,
    start: filters.start ? filters.start.toISOString().slice(0,10) : undefined,
    end: filters.end ? filters.end.toISOString().slice(0,10) : undefined,
    types: filters.types,
    search: (filters.keywords && filters.keywords.length) ? filters.keywords.join(",") : filters.search,
  });
  const amazonQuery = useAds({
    retailer: "amazon",
    client: filters.client,
    start: filters.start ? filters.start.toISOString().slice(0,10) : undefined,
    end: filters.end ? filters.end.toISOString().slice(0,10) : undefined,
    types: filters.types,
    search: (filters.keywords && filters.keywords.length) ? filters.keywords.join(",") : filters.search,
  });
  
  // Map selected retailers to their queries
  const queryMap = {
    kroger: krogerQuery,
    walmart: walmartQuery,
    instacart: instacartQuery,
    amazon: amazonQuery,
  };
  const retailerQueries = retailers.map(r => queryMap[r]);
  
  // For backwards compatibility, keep adsQuery as the primary retailer's query
  const adsQuery = retailerQueries[0];

  const lf = leftFilters ?? filters;
  const rf = rightFilters ?? filters;
  const leftAdsQuery = useAds({
    retailer: primaryRetailer,
    client: lf.client,
    start: lf.start ? lf.start.toISOString().slice(0,10) : undefined,
    end: lf.end ? lf.end.toISOString().slice(0,10) : undefined,
    types: lf.types,
    search: lf.search,
  });
  const rightAdsQuery = useAds({
    retailer: primaryRetailer,
    client: rf.client,
    start: rf.start ? rf.start.toISOString().slice(0,10) : undefined,
    end: rf.end ? rf.end.toISOString().slice(0,10) : undefined,
    types: rf.types,
    search: rf.search,
  });

  const flatAds: Ad[] = useMemo(() => {
    // Merge cards from all selected retailers with deduplication
    try {
      const allCards = retailerQueries.flatMap(query => 
        query.data?.pages?.flatMap(p => p.cards || []) || []
      );
      
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
  }, [krogerQuery.data, walmartQuery.data, instacartQuery.data, amazonQuery.data, retailers]);

  const [ads, setAds] = useState<Ad[]>([]);
  // sync local ads list with fetched pages (enables reordering/dismiss)
  // Force clear when filters change to prevent stale data mixing
  useEffect(() => { 
    setAds(flatAds); 
  }, [flatAds]);
  
  // Clear ads when date filters change to force fresh render
  useEffect(() => {
    setAds([]);
  }, [filters.start, filters.end]);

  const dnd = useDnD(ads, setAds);

  const timestamps = useMemo(() => flatAds.map(a => a.timestamp), [flatAds]);

  const totalCards = retailerQueries.reduce((sum, query) => 
    sum + (query.data?.pages?.[0]?.total_cards || 0), 0
  );
  const activeRetailers = retailersData?.count || 0;
  const sov = useMemo(() => {
    const countByBrand: Record<string, number> = {};
    for (const a of flatAds) countByBrand[a.brand] = (countByBrand[a.brand]||0)+1;
    const entries = Object.entries(countByBrand).sort((a,b)=>b[1]-a[1]);
    if (!entries.length) return { brand: "-", pct: 0 };
    const top = entries[0];
    const pct = Math.round((top[1] / flatAds.length) * 100);
    return { brand: top[0], pct: isFinite(pct) ? pct : 0 };
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
  const [compareMode, setCompareMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const dismiss = (id: string) => setAds(prev => prev.filter(a => a.id !== id));

  const toggleSelect = (id: string) => setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const selectAll = () => setSelected(new Set(ads.map(a=>a.id)));
  const hideSelected = () => setAds(prev => prev.filter(a => !selected.has(a.id)));

  const applyFilters = () => adsQuery.refetch();
  const resetFilters = () => setFilters({ types: [], search: "", keywords: [], datePreset: { type: "lifetime" } });

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
    <main className="min-h-screen py-6 pb-32 md:pb-48 pr-4 md:pr-8 pl-8 sm:pl-10 md:pl-14 lg:pl-16">
      <div className="w-full max-w-[1400px] mx-auto">
        <header className="flex flex-wrap items-center gap-3 mb-6">
          <div className="flex items-center gap-3">
            <img src={GaleLogo} alt="GALE" className="h-8 w-auto" />
            <h1 className="text-white text-2xl font-extrabold">Retail Ad Monitoring</h1>
          </div>
          <div className="ml-auto flex items-center gap-2">
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
              <StatCard value={activeRetailers} label="Active Retailers" />
              <StatCard value={`${sov.brand}`} label="Top Brand by SOV" hint={`${sov.pct}%`} />
              <StatCard value={""} label="Ad Volume Trend" trend={trend} />
            </div>

            <RetailerSelector value={retailers} onChange={setRetailers} enabledRetailers={enabledRetailers} />

            <Filters
              retailer={primaryRetailer}
              clients={clientsResp?.clients || []}
              value={filters}
              onChange={setFilters}
              onApply={applyFilters}
              onReset={resetFilters}
            />

            <Timeline timestamps={timestamps} onRangeChange={(from, to) => setFilters(v => ({ ...v, start: from, end: to, datePreset: { type: "custom" } }))} />

            <div className="card-surface p-2">
              <TemporalVisualMap ads={ads} onRangeChange={(from,to)=> setFilters(v=>({ ...v, start: from, end: to }))} />
            </div>

            <div className="card-surface p-3 flex items-center gap-4">
              <div className="flex items-center gap-2">
                <Checkbox checked={selected.size === ads.length && ads.length>0} onCheckedChange={(v)=> v ? selectAll() : setSelected(new Set())} aria-label="Select all" />
                <span className="text-sm text-[#111827]">Select All</span>
              </div>
              <Button variant="outline" onClick={hideSelected}>Hide Selected</Button>
              <div className="ml-auto text-sm text-white/80">{ads.length} results</div>
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
              <div className="columns-1 sm:columns-1 md:columns-2 lg:columns-2 xl:columns-3 gap-4">
                {ads.map((ad, idx) => (
                  <div key={ad.id} className="break-inside-avoid" onClickCapture={(e)=>{ const target = e.target as HTMLElement; if (target?.closest('input[type=\"checkbox\"]')) e.stopPropagation(); }}>
                    <div className="absolute z-10 m-2">
                      <input aria-label="Select ad" type="checkbox" className="h-4 w-4" checked={selected.has(ad.id)} onChange={()=>toggleSelect(ad.id)} />
                    </div>
                    <AdCard ad={ad} onRemove={dismiss} onOpen={setModalAd} draggableProps={dnd.makeProps(idx)} />
                  </div>
                ))}
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
              const leftAds = (leftAdsQuery.data?.pages.flatMap(p=>p.cards) || []).map((c,i)=>({ ...c, id: `L-${c.retailer}-${c.client}-${c.ad_type}-${c.brand}-${c.keyword}-${c.timestamp}-${i}`})) as Ad[];
              const rightAds = (rightAdsQuery.data?.pages.flatMap(p=>p.cards) || []).map((c,i)=>({ ...c, id: `R-${c.retailer}-${c.client}-${c.ad_type}-${c.brand}-${c.keyword}-${c.timestamp}-${i}`})) as Ad[];
              const leftTs = leftAds.map(a=>a.timestamp);
              const rightTs = rightAds.map(a=>a.timestamp);
              return (
                <>
                  <div className="space-y-4">
                    <h2 className="text-white font-semibold">Left View</h2>
                    <Filters retailer={primaryRetailer} clients={clientsResp?.clients||[]} value={lf} onChange={(v)=>setLeftFilters(v)} onApply={()=>leftAdsQuery.refetch()} onReset={()=>setLeftFilters({ types: [], search: '', keywords: [], datePreset: { type: 'lifetime' } })} />
                    <Timeline timestamps={leftTs} onRangeChange={(from,to)=> setLeftFilters(prev=>({ ...prev, start: from, end: to, datePreset: { type: 'custom' } }))} />
                    <div className="card-surface p-2">
                      <TemporalVisualMap ads={leftAds} onRangeChange={(from,to)=> setLeftFilters(prev=>({ ...prev, start: from, end: to, datePreset: { type: 'custom' } }))} />
                    </div>
                  </div>
                  <div className="space-y-4">
                    <h2 className="text-white font-semibold">Right View</h2>
                    <Filters retailer={primaryRetailer} clients={clientsResp?.clients||[]} value={rf} onChange={(v)=>setRightFilters(v)} onApply={()=>rightAdsQuery.refetch()} onReset={()=>setRightFilters({ types: [], search: '', keywords: [], datePreset: { type: 'lifetime' } })} />
                    <Timeline timestamps={rightTs} onRangeChange={(from,to)=> setRightFilters(prev=>({ ...prev, start: from, end: to, datePreset: { type: 'custom' } }))} />
                    <div className="card-surface p-2">
                      <TemporalVisualMap ads={rightAds} onRangeChange={(from,to)=> setRightFilters(prev=>({ ...prev, start: from, end: to, datePreset: { type: 'custom' } }))} />
                    </div>
                  </div>
                  <div className="col-span-full card-surface p-3 text-center">Exit Comparison to view full visual maps.</div>
                </>
              );
            })()}
          </section>
        )}

        <AdModal open={!!modalAd} ad={modalAd} onOpenChange={(v)=>!v && setModalAd(null)} onCompare={(ad)=>{ setModalAd(null); setCompareMode(true); }} />
      </div>
    </main>
  );
}
