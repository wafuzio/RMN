import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { cn } from "@/lib/utils";
import { useAds } from "@/hooks/useRetailAds";

const AD_TYPES: Record<string, string[]> = {
  kroger: ["TOA", "Carousel", "Skyscraper", "Display_Ads"],
  amazon: ["Sponsored_Brand_Video", "Sponsored_Product", "Featured_Brand", "Sponsored_Carousel"],
  instacart: ["Shoppable_Display_Ads", "Video_Ads", "Sponsored_Products"],
  walmart: ["Top_Banner", "SBA", "Tile_Takeover", "SBV"],
};

type DatePresetType =
  | "today"
  | "yesterday"
  | "last_week"
  | "last_x_days"
  | "last_x_months"
  | "mtd"
  | "ytd"
  | "last_52_weeks"
  | "lifetime"
  | "custom";

export interface FiltersState {
  client?: string;
  start?: Date | undefined;
  end?: Date | undefined;
  types: string[];
  search?: string;
  keywords?: string[];
  datePreset?: { type: DatePresetType; days?: number; months?: number };
}

export function Filters({
  retailer,
  clients,
  value,
  onChange,
  onApply,
  onReset,
}: {
  retailer: string;
  clients: string[];
  value: FiltersState;
  onChange: (next: FiltersState) => void;
  onApply: () => void;
  onReset: () => void;
}) {
  const [openClient, setOpenClient] = useState(false);
  const [openKeywords, setOpenKeywords] = useState(false);
  const [openDate, setOpenDate] = useState(false);
  const [xDays, setXDays] = useState<number>(value.datePreset?.days || 7);
  const [xMonths, setXMonths] = useState<number>(value.datePreset?.months || 1);
  const types = AD_TYPES[retailer] || [];
  const selectedTypes = new Set(value.types);

  // Fetch a broad sample of ads for the selected client to derive available keywords
  const keywordsQuery = useAds({
    retailer,
    client: value.client as string,
    pageSize: 200,
  });
  const availableKeywords = useMemo(() => {
    const pages = keywordsQuery.data?.pages || [];
    const set = new Set<string>();
    for (const p of pages) for (const c of p.cards || []) if (c.keyword?.trim()) set.add(c.keyword.trim());
    return Array.from(set).sort((a,b)=>a.localeCompare(b));
  }, [keywordsQuery.data]);
  const selectedKeywords = new Set(value.keywords || []);

  // Date helpers
  const startOfToday = () => { const d = new Date(); d.setHours(0,0,0,0); return d; };
  const addDays = (d: Date, n: number) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
  const subDays = (d: Date, n: number) => addDays(d, -n);
  const subMonths = (d: Date, n: number) => { const x = new Date(d); x.setMonth(x.getMonth() - n); return x; };
  const startOfMonth = (d: Date) => { const x = new Date(d); x.setDate(1); x.setHours(0,0,0,0); return x; };
  const startOfYear = (d: Date) => { const x = new Date(d); x.setMonth(0,1); x.setHours(0,0,0,0); return x; };

  const applyPreset = (type: DatePresetType, opts?: { days?: number; months?: number }) => {
    const today = startOfToday();
    let from: Date | undefined = undefined;
    let to: Date | undefined = undefined;
    switch (type) {
      case "today":
        from = today; to = today; break;
      case "yesterday":
        from = subDays(today, 1); to = subDays(today, 1); break;
      case "last_week":
        from = subDays(today, 6); to = today; break; // last 7 days incl. today
      case "last_x_days": {
        const n = Math.max(1, opts?.days ?? xDays);
        from = subDays(today, n - 1); to = today; break;
      }
      case "last_x_months": {
        const n = Math.max(1, opts?.months ?? xMonths);
        from = subMonths(today, n); from.setDate(1); to = today; break;
      }
      case "mtd":
        from = startOfMonth(today); to = today; break;
      case "ytd":
        from = startOfYear(today); to = today; break;
      case "last_52_weeks":
        from = subDays(today, 52 * 7 - 1); to = today; break;
      case "lifetime":
        from = undefined; to = undefined; break;
      case "custom":
        from = value.start; to = value.end; break;
    }
    onChange({
      ...value,
      start: from,
      end: to,
      datePreset: { type, days: opts?.days ?? (type === "last_x_days" ? xDays : undefined), months: opts?.months ?? (type === "last_x_months" ? xMonths : undefined) },
    });
  };

  const dateLabel = useMemo(() => {
    const p = value.datePreset?.type;
    if (p && p !== "custom") {
      if (p === "last_x_days") return `Last ${value.datePreset?.days ?? xDays} days`;
      if (p === "last_x_months") return `Last ${value.datePreset?.months ?? xMonths} months`;
      const map: Record<DatePresetType, string> = {
        today: "Today",
        yesterday: "Yesterday",
        last_week: "Last 7 days",
        mtd: "Month to date",
        ytd: "Year to date",
        last_52_weeks: "Last 52 weeks",
        lifetime: "Lifetime",
        last_x_days: "",
        last_x_months: "",
        custom: "",
      } as const;
      if (map[p]) return map[p];
    }
    if (value.start && value.end) return `${value.start.toLocaleDateString()} - ${value.end.toLocaleDateString()}`;
    return "Select date range";
  }, [value.start, value.end, value.datePreset, xDays, xMonths]);

  return (
    <div className="card-surface p-4 flex flex-wrap items-end gap-3">
      <div className="flex-1 min-w-[220px]">
        <label className="block text-sm text-[#6b7280] mb-1">Client</label>
        <Popover open={openClient} onOpenChange={setOpenClient}>
          <PopoverTrigger asChild>
            <Button variant="outline" className="w-full justify-between">
              {value.client || "Select client"}
              <span aria-hidden>▾</span>
            </Button>
          </PopoverTrigger>
          <PopoverContent className="p-0 w-[280px]" align="start">
            <Command filter={(v, s) => (v.includes(s.toLowerCase()) ? 1 : 0)}>
              <CommandInput placeholder="Search client..." />
              <CommandList>
                <CommandEmpty>No client found.</CommandEmpty>
                <CommandGroup>
                  {clients.map((c) => (
                    <CommandItem key={c} value={c.toLowerCase()} onSelect={() => { onChange({ ...value, client: c }); setOpenClient(false); }}>
                      {c}
                    </CommandItem>
                  ))}
                </CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </div>

      <div className="min-w-[260px]">
        <label className="block text-sm text-[#6b7280] mb-1">Date range</label>
        <Popover open={openDate} onOpenChange={setOpenDate}>
          <PopoverTrigger asChild>
            <Button variant="outline" className="w-full justify-between whitespace-nowrap overflow-hidden text-ellipsis">
              {dateLabel}
              <span aria-hidden>▾</span>
            </Button>
          </PopoverTrigger>
          <PopoverContent className="p-0 w-[380px] max-w-[90vw]" align="start">
            <div className="grid grid-cols-1 gap-0 md:grid-cols-2">
              <div className="p-3 border-r md:block">
                <div className="space-y-1">
                  <button className="w-full text-left px-2 py-1.5 rounded hover:bg-accent" onClick={() => { applyPreset("today"); setOpenDate(false); }}>Today</button>
                  <button className="w-full text-left px-2 py-1.5 rounded hover:bg-accent" onClick={() => { applyPreset("yesterday"); setOpenDate(false); }}>Yesterday</button>
                  <button className="w-full text-left px-2 py-1.5 rounded hover:bg-accent" onClick={() => { applyPreset("last_week"); setOpenDate(false); }}>Last 7 days</button>
                  <div className="px-2 py-1.5">
                    <div className="text-sm mb-2">Last X days</div>
                    <div className="flex items-center gap-2">
                      <Input type="number" min={1} value={xDays} onChange={(e)=> setXDays(Math.max(1, Number(e.target.value)||1))} className="w-24 h-8" />
                      <Button size="sm" onClick={() => { applyPreset("last_x_days", { days: xDays }); setOpenDate(false); }}>Apply</Button>
                    </div>
                  </div>
                  <div className="px-2 py-1.5">
                    <div className="text-sm mb-2">Last X months</div>
                    <div className="flex items-center gap-2">
                      <Input type="number" min={1} value={xMonths} onChange={(e)=> setXMonths(Math.max(1, Number(e.target.value)||1))} className="w-24 h-8" />
                      <Button size="sm" onClick={() => { applyPreset("last_x_months", { months: xMonths }); setOpenDate(false); }}>Apply</Button>
                    </div>
                  </div>
                  <button className="w-full text-left px-2 py-1.5 rounded hover:bg-accent" onClick={() => { applyPreset("mtd"); setOpenDate(false); }}>Month to date</button>
                  <button className="w-full text-left px-2 py-1.5 rounded hover:bg-accent" onClick={() => { applyPreset("ytd"); setOpenDate(false); }}>Year to date</button>
                  <button className="w-full text-left px-2 py-1.5 rounded hover:bg-accent" onClick={() => { applyPreset("last_52_weeks"); setOpenDate(false); }}>Last 52 weeks</button>
                  <button className="w-full text-left px-2 py-1.5 rounded hover:bg-accent" onClick={() => { applyPreset("lifetime"); setOpenDate(false); }}>Lifetime</button>
                  <button className="w-full text-left px-2 py-1.5 rounded hover:bg-accent" onClick={() => { applyPreset("custom"); }}>Custom…</button>
                </div>
              </div>
              <div className="p-3">
                <Calendar
                  mode="range"
                  selected={{ from: value.start, to: value.end }}
                  onSelect={(r: any) => {
                    onChange({ ...value, start: r?.from, end: r?.to, datePreset: { type: "custom" } });
                  }}
                  numberOfMonths={2}
                />
                <div className="flex justify-end gap-2 mt-2">
                  <Button variant="outline" size="sm" onClick={() => setOpenDate(false)}>Close</Button>
                  <Button size="sm" onClick={() => { setOpenDate(false); }}>Apply</Button>
                </div>
              </div>
            </div>
          </PopoverContent>
        </Popover>
      </div>

      <div className="flex-1 min-w-[280px]">
        <label className="block text-sm text-[#6b7280] mb-1">Ad types</label>
        <div className="flex flex-wrap gap-2">
          {types.map((t) => (
            <label key={t} className="inline-flex items-center gap-2 px-3 py-2 rounded-md border bg-white">
              <Checkbox
                checked={selectedTypes.has(t)}
                onCheckedChange={(checked) => {
                  const next = new Set(value.types);
                  if (checked) next.add(t); else next.delete(t);
                  onChange({ ...value, types: Array.from(next) });
                }}
                aria-label={`toggle ${t}`}
              />
              <span className="text-sm">{t.replaceAll("_", " ")}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="flex-1 min-w-[220px]">
        <label className="block text-sm text-[#6b7280] mb-1">Search terms</label>
        <Popover open={openKeywords} onOpenChange={setOpenKeywords}>
          <PopoverTrigger asChild>
            <button className={cn(
              "w-full min-h-[38px] px-3 py-2 text-left border rounded-md bg-white hover:bg-gray-50",
              selectedKeywords.size ? "flex flex-wrap gap-2" : ""
            )} aria-haspopup="listbox">
              {selectedKeywords.size === 0 ? (
                <span className="text-sm text-gray-500">Select keywords</span>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {(value.keywords || []).map((k) => (
                    <span key={k} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-gray-100 text-sm">
                      {k}
                      <button
                        aria-label={`Remove ${k}`}
                        className="ml-1 text-gray-500 hover:text-gray-700"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          const next = (value.keywords || []).filter(x => x !== k);
                          onChange({ ...value, keywords: next });
                        }}
                      >×</button>
                    </span>
                  ))}
                </div>
              )}
            </button>
          </PopoverTrigger>
          <PopoverContent className="p-0 w-[320px]" align="start">
            <Command filter={(v, s) => (v.includes(s.toLowerCase()) ? 1 : 0)}>
              <CommandInput placeholder="Search keywords..." />
              <CommandList>
                <CommandEmpty>No keywords found.</CommandEmpty>
                <CommandGroup>
                  {availableKeywords.map((k) => (
                    <CommandItem
                      key={k}
                      value={k.toLowerCase()}
                      onSelect={() => {
                        const next = new Set(value.keywords || []);
                        if (next.has(k)) next.delete(k); else next.add(k);
                        onChange({ ...value, keywords: Array.from(next) });
                      }}
                    >
                      <div className="mr-2">
                        <Checkbox checked={selectedKeywords.has(k)} aria-label={`toggle ${k}`} />
                      </div>
                      <span>{k}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </div>

      <div className="flex gap-2 ml-auto">
        <Button onClick={onApply} className="bg-gradient-to-r from-[#667eea] to-[#764ba2] text-white rounded-md">Apply Filters</Button>
        <Button variant="outline" onClick={onReset} className="bg-gray-50">Reset</Button>
      </div>
    </div>
  );
}
