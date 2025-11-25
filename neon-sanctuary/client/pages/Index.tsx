import { useMemo, useRef, useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useRetailers, useClients, useAds, useAdCount } from "@/hooks/useRetailAds";
import { useBrands } from "@/hooks/useBrands";
import type { Retailer } from "@/lib/api";
import { useTimeline } from "@/hooks/useTimeline";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { StatCard } from "@/components/dashboard/StatCard";
import { AdVolumeTrendCard } from "@/components/dashboard/AdVolumeTrendCard";
import { RetailerSelector } from "@/components/dashboard/RetailerSelector";
import { Filters, FiltersState } from "@/components/dashboard/Filters";
import { Timeline } from "@/components/dashboard/Timeline";
import { Ad, AdCard } from "@/components/dashboard/AdCard";
import { AdCardGroup } from "@/components/dashboard/AdCardGroup";
import { AdModal } from "@/components/dashboard/AdModal";
import { TopBrandModal } from "@/components/dashboard/TopBrandModal";
import { BrandDetailModal } from "@/components/dashboard/BrandDetailModal";
import { AllBrandsModal } from "@/components/dashboard/AllBrandsModal";
import { SkeletonGrid } from "@/components/dashboard/SkeletonGrid";
import { TemporalVisualMap } from "@/components/visual/TemporalVisualMap";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { aggregateAds, AdGroup, AdCardItem } from "@/lib/aggregateAds";
import GaleLogo from "../../../web/assets/logos/GALE.svg";

// Helper: Format date to YYYY-MM-DD for API
function formatLocalDate(d?: Date) {
  if (!d) return undefined;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

// Helper: Deduplicate and sort arrays for stable query keys
function dedupSorted(arr?: string[]) {
  if (!arr || arr.length === 0) return undefined;
  return Array.from(new Set(arr)).sort();
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

// Helper: Check if ad type should be displayed in narrow column (skyscraper/sponsored brand layout)
function isColumnAdType(ad: any): boolean {
  const columnTypes = ["Skyscraper", "Tile_Takeover", "Sponsored_Brand_Card", "Sponsored_Logo"];
  if (columnTypes.includes(ad.ad_type)) {
    return true;
  }
  // Left rail Sponsored Display ads also go in the column
  if (ad.ad_type === "Sponsored_Display" && ad.slot === "left_rail") {
    return true;
  }
  return false;
}

// Helper: Check if ad group should be displayed in narrow column
function isColumnAdGroup(group: any, ads: any[]): boolean {
  // Check the first instance's properties
  if (group.instances.length > 0) {
    const firstAd = ads.find(a => a.id === group.instances[0].id);
    if (firstAd) {
      return isColumnAdType(firstAd);
    }
  }
  // Fallback to checking just ad_type
  const columnTypes = ["Skyscraper", "Tile_Takeover", "Sponsored_Brand_Card", "Sponsored_Logo"];
  return columnTypes.includes(group.ad_type);
}

export default function Index() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  
  // Parse URL parameters for initial state
  const urlRetailer = searchParams.get("retailer") as Retailer | null;
  const urlClient = searchParams.get("client");
  const urlClients = searchParams.get("clients")?.split(",").filter(Boolean);
  const urlTypes = searchParams.get("types")?.split(",").filter(Boolean);
  const urlKeywords = searchParams.get("keywords")?.split(",").filter(Boolean);
  const urlDays = searchParams.get("days");
  const urlStart = searchParams.get("start");
  const urlEnd = searchParams.get("end");

  const [retailers, setRetailers] = useState<Retailer[]>(() => {
    return urlRetailer ? [urlRetailer] : ["kroger"];
  });
  const { data: retailersData } = useRetailers();
  const enabledRetailers = useMemo(() => new Set(retailersData?.retailers || []), [retailersData]);

  // Use first selected retailer for single-retailer operations (filters, clients)
  const primaryRetailer = retailers[0];

  // Initialize with URL params or last 52 weeks date range
  const [filters, setFilters] = useState<FiltersState>(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    // Parse date range from URL
    let start: Date | undefined;
    let end: Date | undefined;
    let datePreset: FiltersState["datePreset"] = { type: "last_52_weeks" };
    
    if (urlStart || urlEnd) {
      start = urlStart ? new Date(urlStart) : undefined;
      end = urlEnd ? new Date(urlEnd) : today;
      datePreset = { type: "custom" };
    } else if (urlDays) {
      const days = parseInt(urlDays, 10);
      if (!isNaN(days) && days > 0) {
        start = new Date(today);
        start.setDate(start.getDate() - (days - 1));
        end = today;
        datePreset = { type: "custom" };
      }
    } else {
      start = new Date(today);
      start.setDate(start.getDate() - (52 * 7 - 1)); // 364 days ago
      end = today;
    }
    
    return {
      clients: urlClients || (urlClient ? [urlClient] : []),
      types: urlTypes || [],
      search: "",
      keywords: urlKeywords || [],
      start,
      end,
      datePreset,
      groupIdentical: true
    };
  });
  const [leftFilters, setLeftFilters] = useState<FiltersState | null>(null);
  const [rightFilters, setRightFilters] = useState<FiltersState | null>(null);
  const [sortBy, setSortBy] = useState<"latest" | "oldest" | "name">("latest");

  // Fetch clients for ALL selected retailers and merge them
  // NOTE: We fetch for each selected retailer and combine the results
  const krogerClients = useClients(retailers.includes("kroger") ? "kroger" : undefined);
  const amazonClients = useClients(retailers.includes("amazon") ? "amazon" : undefined);
  const instacartClients = useClients(retailers.includes("instacart") ? "instacart" : undefined);
  const walmartClients = useClients(retailers.includes("walmart") ? "walmart" : undefined);
  const targetClients = useClients(retailers.includes("target") ? "target" : undefined);
  const albertsonsClients = useClients(retailers.includes("albertsons") ? "albertsons" : undefined);
  const foodLionClients = useClients(retailers.includes("food_lion") ? "food_lion" : undefined);
  const gopuffClients = useClients(retailers.includes("gopuff") ? "gopuff" : undefined);
  const doordashClients = useClients(retailers.includes("doordash") ? "doordash" : undefined);
  const meijerClients = useClients(retailers.includes("meijer") ? "meijer" : undefined);
  const hyveeClients = useClients(retailers.includes("hyvee") ? "hyvee" : undefined);
  const ultaClients = useClients(retailers.includes("ulta") ? "ulta" : undefined);

  const allClientsList = useMemo(() => {
    const merged = new Set<string>();
    const queries = [
      krogerClients, amazonClients, instacartClients, walmartClients, targetClients,
      albertsonsClients, foodLionClients, gopuffClients, doordashClients, meijerClients, hyveeClients, ultaClients
    ];
    queries.forEach(query => {
      if (query.data?.clients) {
        query.data.clients.forEach(client => merged.add(client));
      }
    });
    return Array.from(merged).sort();
  }, [
    krogerClients.data?.clients?.join(","),
    amazonClients.data?.clients?.join(","),
    instacartClients.data?.clients?.join(","),
    walmartClients.data?.clients?.join(","),
    targetClients.data?.clients?.join(","),
    albertsonsClients.data?.clients?.join(","),
    foodLionClients.data?.clients?.join(","),
    gopuffClients.data?.clients?.join(","),
    doordashClients.data?.clients?.join(","),
    meijerClients.data?.clients?.join(","),
    hyveeClients.data?.clients?.join(","),
    ultaClients.data?.clients?.join(","),
  ]);

  // For backward compatibility with single-retailer logic, keep primary retailer reference
  const { data: clientsResp } = useClients(primaryRetailer);

  // Restore last session state
  useEffect(() => {
    try {
      const raw = localStorage.getItem("retail-dashboard:last-state:v2"); // Changed to v2 to invalidate old state
      if (!raw) return;
      const saved = JSON.parse(raw) as any;
      if (Array.isArray(saved.retailers) && saved.retailers.length) {
        setRetailers(saved.retailers);
      }
      if (saved.filters && typeof saved.filters === "object") {
        const f = saved.filters as Partial<FiltersState> & { start?: string; end?: string; client?: string };
        const datePreset = f.datePreset || { type: "last_52_weeks" };
        
        // Recompute dates based on preset type (don't rely on stored dates for relative presets)
        let start: Date | undefined;
        let end: Date | undefined;
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        
        if (datePreset.type === "lifetime") {
          start = undefined;
          end = undefined;
        } else if (datePreset.type === "last_52_weeks") {
          start = new Date(today);
          start.setDate(start.getDate() - (52 * 7 - 1));
          end = today;
        } else if (datePreset.type === "custom" && f.start && f.end) {
          // Only use stored dates for custom preset
          const parsedStart = new Date(f.start);
          const parsedEnd = new Date(f.end);
          start = isFinite(+parsedStart) ? parsedStart : undefined;
          end = isFinite(+parsedEnd) ? parsedEnd : undefined;
        } else {
          // For other presets, default to last 52 weeks
          start = new Date(today);
          start.setDate(start.getDate() - (52 * 7 - 1));
          end = today;
        }
        
        const parsed: FiltersState = {
          types: Array.isArray(f.types) ? f.types : [],
          search: typeof f.search === "string" ? f.search : "",
          keywords: Array.isArray(f.keywords) ? f.keywords : [],
          clients: Array.isArray(f.clients) ? f.clients : (typeof f.client === "string" ? [f.client] : []),
          start,
          end,
          datePreset,
          groupIdentical: f.groupIdentical ?? true,
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
      localStorage.setItem("retail-dashboard:last-state:v2", JSON.stringify(toSave));
    } catch {}
  }, [retailers, filters]);

  // Auto-filter clients when available clients change (retailer selection changes)
  // Removes clients that are no longer available in selected retailers
  useEffect(() => {
    if (!filters.clients?.length) return;

    const availableSet = new Set(allClientsList);
    const validClients = filters.clients.filter(c => availableSet.has(c));

    // Only update if some clients were filtered out
    if (validClients.length !== filters.clients.length) {
      setFilters(prev => ({
        ...prev,
        clients: validClients.length > 0 ? validClients : []
      }));
    }
  }, [allClientsList]);

  // Auto-select first client if none selected
  useEffect(() => {
    if (allClientsList.length && !filters.clients?.length) {
      setFilters(prev => ({ ...prev, clients: [allClientsList[0]] }));
    }
  }, [allClientsList, filters.clients?.length]);

  // Handle multiple clients by creating queries for each
  // When all clients are selected, use the special "all" client parameter
  const selectedClients = filters.clients || [];
  const allClientsAvailable = allClientsList;
  const isAllClientsSelected = selectedClients.length > 0 && selectedClients.length === allClientsAvailable.length;

  // If all clients are selected, use "all"; otherwise send comma-separated list
  const selectedClient = isAllClientsSelected
    ? "all"
    : selectedClients.length > 0
    ? selectedClients.join(",")
    : "";

  // PERFORMANCE FIX: Memoize and debounce filter parameters to prevent render loops
  // This stabilizes the filter object identity so useAds doesn't re-run on every render
  // NOTE: Include tz_offset_minutes so backend can adjust date ranges correctly
  // (JavaScript's getTimezoneOffset returns minutes ahead of UTC as negative value)
  const normalizedFilters = useMemo(() => {
    const result = {
      term: filters.keywords?.length ? filters.keywords.join(",") : undefined,
      start: formatLocalDate(filters.start),
      end: formatLocalDate(filters.end),
      tz_offset_minutes: new Date().getTimezoneOffset(), // e.g., -360 for UTC-6
      types: dedupSorted(filters.types),
      search: filters.search?.trim() || undefined,
      sort: sortBy,
    };
    console.log('🔍 normalizedFilters:', result);
    return result;
  }, [
    filters.keywords?.join(","),  // Stable string representation
    filters.start?.getTime(),     // Use epoch for date comparison
    filters.end?.getTime(),
    filters.types?.join(","),     // Stable string representation
    filters.search,
    sortBy,
  ]);

  // Debounce to prevent fetch storms while user is typing/changing filters
  const debouncedFilters = useDebouncedValue(normalizedFilters, 350);

  const isKrogerSelected = retailers.includes("kroger");
  const krogerQuery = useAds({
    retailer: isKrogerSelected ? "kroger" : undefined,
    client: selectedClient,
    ...debouncedFilters,
  });

  const isWalmartSelected = retailers.includes("walmart");
  const walmartQuery = useAds({
    retailer: isWalmartSelected ? "walmart" : undefined,
    client: selectedClient,
    ...debouncedFilters,
  });

  const isInstacartSelected = retailers.includes("instacart");
  const instacartQuery = useAds({
    retailer: isInstacartSelected ? "instacart" : undefined,
    client: selectedClient,
    ...debouncedFilters,
  });

  const isAmazonSelected = retailers.includes("amazon");
  const amazonQuery = useAds({
    retailer: isAmazonSelected ? "amazon" : undefined,
    client: selectedClient,
    ...debouncedFilters,
  });

  const isTargetSelected = retailers.includes("target");
  const targetQuery = useAds({
    retailer: isTargetSelected ? "target" : undefined,
    client: selectedClient,
    ...debouncedFilters,
  });

  // Count queries for total cards (much faster than loading full cards)
  const krogerCountQuery = useAdCount({
    retailer: isKrogerSelected ? "kroger" : undefined,
    client: selectedClient,
    ...debouncedFilters,
  });

  const walmartCountQuery = useAdCount({
    retailer: isWalmartSelected ? "walmart" : undefined,
    client: selectedClient,
    ...debouncedFilters,
  });

  const instacartCountQuery = useAdCount({
    retailer: isInstacartSelected ? "instacart" : undefined,
    client: selectedClient,
    ...debouncedFilters,
  });

  const amazonCountQuery = useAdCount({
    retailer: isAmazonSelected ? "amazon" : undefined,
    client: selectedClient,
    ...debouncedFilters,
  });

  const targetCountQuery = useAdCount({
    retailer: isTargetSelected ? "target" : undefined,
    client: selectedClient,
    ...debouncedFilters,
  });

  // Collect all queries - one per retailer now
  const allQueries = [
    krogerQuery,
    walmartQuery,
    instacartQuery,
    amazonQuery,
    targetQuery,
  ];

  // Build retailer-based query map (for backward compatibility)
  const queryMap = {
    kroger: [krogerQuery],
    walmart: [walmartQuery],
    instacart: [instacartQuery],
    amazon: [amazonQuery],
    target: [targetQuery],
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

  // PERFORMANCE FIX: Memoize compare mode filters
  const leftNormalizedFilters = useMemo(() => ({
    term: lf.keywords?.length ? lf.keywords.join(",") : undefined,
    start: formatLocalDate(lf.start),
    end: formatLocalDate(lf.end),
    types: dedupSorted(lf.types),
    search: lf.search?.trim() || undefined,
    sort: sortBy,
  }), [
    lf.keywords?.join(","),
    lf.start?.getTime(),
    lf.end?.getTime(),
    lf.types?.join(","),
    lf.search,
    sortBy,
  ]);

  const rightNormalizedFilters = useMemo(() => ({
    term: rf.keywords?.length ? rf.keywords.join(",") : undefined,
    start: formatLocalDate(rf.start),
    end: formatLocalDate(rf.end),
    types: dedupSorted(rf.types),
    search: rf.search?.trim() || undefined,
    sort: sortBy,
  }), [
    rf.keywords?.join(","),
    rf.start?.getTime(),
    rf.end?.getTime(),
    rf.types?.join(","),
    rf.search,
    sortBy,
  ]);

  const leftDebouncedFilters = useDebouncedValue(leftNormalizedFilters, 350);
  const rightDebouncedFilters = useDebouncedValue(rightNormalizedFilters, 350);

  // Compare mode: One query per side (use "all" or single client)
  const leftSelectedClient = leftClients.length === 1 ? leftClients[0] : "all";
  const rightSelectedClient = rightClients.length === 1 ? rightClients[0] : "all";

  const leftAdsQuery = useAds({
    retailer: primaryRetailer,
    client: leftSelectedClient,
    ...leftDebouncedFilters,
  });

  const rightAdsQuery = useAds({
    retailer: primaryRetailer,
    client: rightSelectedClient,
    ...rightDebouncedFilters,
  });

  const flatAds: Ad[] = useMemo(() => {
    // Merge cards from all selected retailers (one query per retailer now)
    try {
      const allCards = [
        ...(isKrogerSelected ? (krogerQuery.data?.pages.flatMap(p => p.cards || []) || []) : []),
        ...(isWalmartSelected ? (walmartQuery.data?.pages.flatMap(p => p.cards || []) || []) : []),
        ...(isInstacartSelected ? (instacartQuery.data?.pages.flatMap(p => p.cards || []) || []) : []),
        ...(isAmazonSelected ? (amazonQuery.data?.pages.flatMap(p => p.cards || []) || []) : []),
        ...(isTargetSelected ? (targetQuery.data?.pages.flatMap(p => p.cards || []) || []) : []),
      ];

      // Dedupe using stable IDs (prevents duplicates from pagination/multiple queries)
      // Also filter out ads without valid images (except for Sponsored_Logo which may use placeholder)
      const uniq = new Map<string, Ad>();
      for (let i = 0; i < allCards.length; i++) {
        const c = allCards[i] as any;

        // Skip ads without valid images (has_image: false or missing image_url)
        // Exception: Allow Sponsored_Logo ads through even with placeholder images
        const isSponsoredLogo = c.ad_type === "Sponsored_Logo";
        if (!isSponsoredLogo && (c.has_image === false || !c.image_url || c.image_url.includes('placeholder'))) {
          continue;
        }
        
        const id = buildAdId(c, i);
        if (!uniq.has(id)) {
          const ad = { ...c, id } as Ad;
          uniq.set(id, ad);
        }
        // else duplicate from another page/query; ignore it
      }

      const result = Array.from(uniq.values());

      return result;
    } catch (error) {
      console.error('Error in flatAds:', error);
      return [];
    }
  }, [
    krogerQuery.data,
    walmartQuery.data,
    instacartQuery.data,
    amazonQuery.data,
    targetQuery.data,
    retailers
  ]);

  // Derive available ad types from the fetched data
  // Use a ref to persist types across filter changes so dropdown always shows all types
  const allSeenTypesRef = useRef<Set<string>>(new Set());

  const availableAdTypes = useMemo(() => {
    const typeSet = new Set<string>();

    // Add types from current flatAds (already filtered by selected retailers)
    for (const ad of flatAds) {
      if (ad.ad_type?.trim()) {
        typeSet.add(ad.ad_type.trim());
      }
    }

    // Also add types from raw query responses for selected retailers only
    const selectedQueriesData = [
      ...(isKrogerSelected ? [krogerQuery.data] : []),
      ...(isWalmartSelected ? [walmartQuery.data] : []),
      ...(isInstacartSelected ? [instacartQuery.data] : []),
      ...(isAmazonSelected ? [amazonQuery.data] : []),
      ...(isTargetSelected ? [targetQuery.data] : []),
    ];

    for (const queryData of selectedQueriesData) {
      if (queryData?.pages) {
        for (const page of queryData.pages) {
          for (const ad of page.cards || []) {
            if (ad.ad_type?.trim()) {
              typeSet.add(ad.ad_type.trim());
            }
          }
        }
      }
    }

    return Array.from(typeSet).sort();
  }, [
    flatAds,
    isKrogerSelected,
    isWalmartSelected,
    isInstacartSelected,
    isAmazonSelected,
    isTargetSelected,
    krogerQuery.data,
    walmartQuery.data,
    instacartQuery.data,
    amazonQuery.data,
    targetQuery.data,
  ]);

  // Derive available keywords from the fetched data, filtered by selected clients
  const availableKeywords = useMemo(() => {
    const keywordSet = new Set<string>();
    const selectedClientSet = new Set(filters.clients || []);

    for (const ad of flatAds) {
      // Only include keywords from ads matching the selected clients
      if (selectedClientSet.size === 0 || selectedClientSet.has(ad.client)) {
        if (ad.keyword?.trim()) {
          keywordSet.add(ad.keyword.trim());
        }
      }
    }
    return Array.from(keywordSet).sort();
  }, [flatAds, filters.clients]);

  // Auto-filter ad types when available types change (retailer selection changes)
  // Removes ad types that are no longer available in selected retailers
  useEffect(() => {
    if (!filters.types?.length) return;

    const availableSet = new Set(availableAdTypes);
    const validTypes = filters.types.filter(t => availableSet.has(t));

    // Only update if some types were filtered out
    if (validTypes.length !== filters.types.length) {
      setFilters(prev => ({
        ...prev,
        types: validTypes
      }));
    }
  }, [availableAdTypes, filters.types?.length]);

  const [ads, setAds] = useState<Ad[]>([]);
  // sync local ads list with fetched pages (enables reordering/dismiss)
  // Force clear when filters change to prevent stale data mixing
  useEffect(() => { 
    setAds(flatAds); 
  }, [flatAds]);
  
  // Clear ads when date filters change
  useEffect(() => {
    setAds([]);
  }, [filters.start, filters.end]);

  const dnd = useDnD(ads, setAds);

  // Fetch all timestamps for timeline visualization (not limited by pagination)
  // Query ALL selected retailers and merge timestamps for accurate volume trend
  const krogerTimeline = useTimeline({
    retailer: isKrogerSelected ? "kroger" : "",
    client: filters.clients?.join(','),
    start: debouncedFilters.start,
    end: debouncedFilters.end,
    term: debouncedFilters.term
  });
  const walmartTimeline = useTimeline({
    retailer: isWalmartSelected ? "walmart" : "",
    client: filters.clients?.join(','),
    start: debouncedFilters.start,
    end: debouncedFilters.end,
    term: debouncedFilters.term
  });
  const instacartTimeline = useTimeline({
    retailer: isInstacartSelected ? "instacart" : "",
    client: filters.clients?.join(','),
    start: debouncedFilters.start,
    end: debouncedFilters.end,
    term: debouncedFilters.term
  });
  const amazonTimeline = useTimeline({
    retailer: isAmazonSelected ? "amazon" : "",
    client: filters.clients?.join(','),
    start: debouncedFilters.start,
    end: debouncedFilters.end,
    term: debouncedFilters.term
  });
  const targetTimeline = useTimeline({
    retailer: isTargetSelected ? "target" : "",
    client: filters.clients?.join(','),
    start: debouncedFilters.start,
    end: debouncedFilters.end,
    term: debouncedFilters.term
  });
  
  // Merge all timeline timestamps
  const timestamps = useMemo(() => {
    const all = [
      ...(krogerTimeline.data || []),
      ...(walmartTimeline.data || []),
      ...(instacartTimeline.data || []),
      ...(amazonTimeline.data || []),
      ...(targetTimeline.data || []),
    ];
    console.log(`[Timeline] Merged ${all.length} timestamps from all retailers`);
    return all;
  }, [krogerTimeline.data, walmartTimeline.data, instacartTimeline.data, amazonTimeline.data, targetTimeline.data]);

  const totalCards = useMemo(() => {
    return [
      krogerCountQuery,
      walmartCountQuery,
      instacartCountQuery,
      amazonCountQuery,
      targetCountQuery,
    ].reduce((sum, query) => sum + (query.data?.total || 0), 0);
  }, [
    krogerCountQuery.data,
    walmartCountQuery.data,
    instacartCountQuery.data,
    amazonCountQuery.data,
    targetCountQuery.data,
  ]);
  
  // Get brand aggregations from dedicated brands endpoint with current filters
  const brandsFilters = {
    client: filters.clients?.join(','),
    start: debouncedFilters.start,
    end: debouncedFilters.end,
    term: debouncedFilters.term,
    types: debouncedFilters.types
  };
  const { data: brandsData } = useBrands(retailers, brandsFilters);
  const apiBrands = brandsData?.brands || [];
  
  const activeBrands = apiBrands.length;
  const sov = useMemo(() => {
    if (!apiBrands.length) return { brand: "-", pct: 0 };
    const top = apiBrands[0];
    return { brand: top.brand, pct: top.percentage };
  }, [apiBrands]);

  const topBrands = apiBrands;


  const [modalAd, setModalAd] = useState<Ad|null>(null);
  const [modalGroup, setModalGroup] = useState<AdGroup|null>(null);
  const [showTopBrandModal, setShowTopBrandModal] = useState(false);
  const [showAllBrandsModal, setShowAllBrandsModal] = useState(false);
  const [selectedBrandForModal, setSelectedBrandForModal] = useState<string | null>(null);
  const [compareMode, setCompareMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showVisualMap, setShowVisualMap] = useState(true);
  const [showLeftVisualMap, setShowLeftVisualMap] = useState(true);
  const [showRightVisualMap, setShowRightVisualMap] = useState(true);

  const dismiss = (id: string) => setAds(prev => prev.filter(a => a.id !== id));

  const handleBrandClick = (brand: string) => {
    setSelectedBrandForModal(brand);
    setShowAllBrandsModal(false);
    setShowTopBrandModal(false);
  };

  const toggleSelect = (id: string) => setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const selectAll = () => setSelected(new Set(ads.map(a=>a.id)));
  const hideSelected = () => setAds(prev => prev.filter(a => !selected.has(a.id)));

  const sortedAds = useMemo(() => {
    // Sorting is now handled by the backend (in api_ads_cards endpoint)
    // This ensures consistent ordering across all pages, not just the current page
    return ads;
  }, [ads]);

  // Aggregate ads if grouping is enabled
  const adGroups = useMemo(() => {
    if (!filters.groupIdentical) return null;
    
    // Convert Ad[] to AdCardItem[]
    const items: AdCardItem[] = sortedAds.map(ad => ({
      id: ad.id,
      retailer: ad.retailer,
      client: ad.client,
      keyword: ad.keyword,
      ad_type: ad.ad_type,
      brand: ad.brand,
      message: ad.message,
      image_url: ad.image_url,
      video_url: ad.video_url,
      poster_url: ad.poster_url,
      timestamp: ad.timestamp,
    }));
    
    return aggregateAds(items);
  }, [sortedAds, filters.groupIdentical]);

  const displayItems = filters.groupIdentical ? adGroups : sortedAds;

  const applyFilters = () => adsQuery.refetch();
  const resetFilters = () => setFilters({ clients: [], types: [], search: "", keywords: [], datePreset: { type: "last_52_weeks" }, groupIdentical: true });

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
            <button onClick={() => navigate("/retail-snapshot")} className="px-3 py-2 rounded-md bg-white/10 text-white border border-white/30 hover:bg-white/20 focus-visible:ring-2" aria-label="View retail snapshots">Retail Snapshot</button>
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
              <AdVolumeTrendCard timestamps={timestamps} />
            </div>

            <RetailerSelector value={retailers} onChange={setRetailers} enabledRetailers={enabledRetailers} />

            <Filters
              retailer={primaryRetailer}
              clients={allClientsList}
              availableAdTypes={availableAdTypes}
              availableKeywords={availableKeywords}
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
                  <TemporalVisualMap 
                    ads={ads} 
                    allTimestamps={timestamps} 
                    onRangeChange={(from,to)=> setFilters(v=>({ ...v, start: from, end: to }))} 
                    onAdClick={setModalAd}
                    retailer={primaryRetailer}
                    client={filters.clients?.join(',')}
                    term={debouncedFilters.term}
                  />
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
                  {filters.groupIdentical && adGroups ? (
                    adGroups.map((group, idx) => {
                      if (isColumnAdGroup(group, ads)) return null;
                      return (
                        <div key={group.group_id}>
                          <AdCardGroup
                            group={group}
                            onRemove={(id) => {
                              // Remove all instances in the group
                              setAds(prev => prev.filter(a => !group.instances.some(inst => inst.id === a.id)));
                            }}
                            onOpen={(g) => {
                              // Open modal with first instance and store group info
                              if (g.instances.length > 0) {
                                const firstAd = ads.find(a => a.id === g.instances[0].id);
                                if (firstAd) {
                                  setModalAd(firstAd);
                                  setModalGroup(g);
                                }
                              }
                            }}
                            draggableProps={dnd.makeProps(idx)}
                            dragIndex={dnd.dragIndex}
                            dragOverIndex={dnd.dragOverIndex}
                            currentIndex={idx}
                            isLeftColumn={true}
                          />
                        </div>
                      );
                    })
                  ) : (
                    sortedAds.map((ad, idx) => {
                      if (isColumnAdType(ad)) return null;
                      return (
                        <div
                          key={ad.id}
                          onClickCapture={(e)=>{ const target = e.target as HTMLElement; if (target?.closest('input[type=\"checkbox\"]')) e.stopPropagation(); }}
                        >
                          <div className="absolute z-10 m-2 opacity-0 group-hover:opacity-100 transition-opacity">
                            <input aria-label="Select ad" type="checkbox" className="h-4 w-4" checked={selected.has(ad.id)} onChange={()=>toggleSelect(ad.id)} />
                          </div>
                          <AdCard ad={ad} onRemove={dismiss} onOpen={setModalAd} draggableProps={dnd.makeProps(idx)} dragIndex={dnd.dragIndex} dragOverIndex={dnd.dragOverIndex} currentIndex={idx} isLeftColumn={true} />
                        </div>
                      );
                    })
                  )}
                </div>
                <div className="space-y-4">
                  {filters.groupIdentical && adGroups ? (
                    adGroups.map((group, idx) => {
                      if (!isColumnAdGroup(group, ads)) return null;
                      return (
                        <div key={group.group_id}>
                          <AdCardGroup 
                            group={group} 
                            onRemove={(id) => {
                              setAds(prev => prev.filter(a => !group.instances.some(inst => inst.id === a.id)));
                            }}
                            onOpen={(g) => {
                              if (g.instances.length > 0) {
                                const firstAd = ads.find(a => a.id === g.instances[0].id);
                                if (firstAd) {
                                  setModalAd(firstAd);
                                  setModalGroup(g);
                                }
                              }
                            }}
                            draggableProps={dnd.makeProps(idx)}
                            dragIndex={dnd.dragIndex}
                            dragOverIndex={dnd.dragOverIndex}
                            currentIndex={idx}
                          />
                        </div>
                      );
                    })
                  ) : (
                    sortedAds.map((ad, idx) => {
                      if (!isColumnAdType(ad)) return null;
                      return (
                        <div
                          key={ad.id}
                          onClickCapture={(e)=>{ const target = e.target as HTMLElement; if (target?.closest('input[type=\"checkbox\"]')) e.stopPropagation(); }}
                          style={ad.ad_type === "Sponsored_Display" && ad.slot === "left_rail" ? { minHeight: '1600px' } : undefined}
                        >
                          <div className="absolute z-10 m-2 opacity-0 group-hover:opacity-100 transition-opacity">
                            <input aria-label="Select ad" type="checkbox" className="h-4 w-4" checked={selected.has(ad.id)} onChange={()=>toggleSelect(ad.id)} />
                          </div>
                          <AdCard ad={ad} onRemove={dismiss} onOpen={setModalAd} draggableProps={dnd.makeProps(idx)} dragIndex={dnd.dragIndex} dragOverIndex={dnd.dragOverIndex} currentIndex={idx} />
                        </div>
                      );
                    })
                  )}
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
              // Get left and right ads from single queries
              const leftAllCards = leftAdsQuery.data?.pages.flatMap(p=>p.cards) || [];
              const leftAds = leftAllCards.map((c,i)=>({ ...c, id: `L-${c.retailer}-${c.client}-${c.ad_type}-${c.brand}-${c.keyword}-${c.timestamp}-${i}`})) as Ad[];

              const rightAllCards = rightAdsQuery.data?.pages.flatMap(p=>p.cards) || [];
              const rightAds = rightAllCards.map((c,i)=>({ ...c, id: `R-${c.retailer}-${c.client}-${c.ad_type}-${c.brand}-${c.keyword}-${c.timestamp}-${i}`})) as Ad[];

              const leftTs = leftAds.map(a=>a.timestamp);
              const rightTs = rightAds.map(a=>a.timestamp);
              return (
                <>
                  <div className="space-y-4">
                    <h2 className="text-white font-semibold">Left View</h2>
                    <Filters retailer={primaryRetailer} clients={clientsResp?.clients||[]} availableAdTypes={availableAdTypes} availableKeywords={availableKeywords} value={lf} onChange={(v)=>setLeftFilters(v)} onApply={()=>{leftAdsQuery.refetch();}} onReset={()=>setLeftFilters({ clients: [], types: [], search: '', keywords: [], datePreset: { type: 'lifetime' } })} />
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
                    <Filters retailer={primaryRetailer} clients={clientsResp?.clients||[]} availableAdTypes={availableAdTypes} availableKeywords={availableKeywords} value={rf} onChange={(v)=>setRightFilters(v)} onApply={()=>{rightAdsQuery.refetch();}} onReset={()=>setRightFilters({ clients: [], types: [], search: '', keywords: [], datePreset: { type: 'lifetime' } })} />
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

        <AdModal open={!!modalAd} ad={modalAd} group={modalGroup} onOpenChange={(v)=>{ if (!v) { setModalAd(null); setModalGroup(null); }}} onCompare={(ad)=>{ setModalAd(null); setModalGroup(null); setCompareMode(true); }} />
        <TopBrandModal
          open={showTopBrandModal}
          onOpenChange={setShowTopBrandModal}
          topBrands={topBrands}
          onRetailerClick={handleBrandClick}
        />
        {selectedBrandForModal && (
          <BrandDetailModal
            brand={selectedBrandForModal}
            retailers={retailers}
            onOpenChange={(open) => {
              if (!open) setSelectedBrandForModal(null);
            }}
          />
        )}
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
          onRetailerClick={handleBrandClick}
        />
      </div>
    </main>
  );
}
