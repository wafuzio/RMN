import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { cn } from "@/lib/utils";
import { useAds } from "@/hooks/useRetailAds";

// Helper to format ad type names for display
const formatAdTypeName = (adType: string): string => {
  // Known acronyms that should be fully capitalized
  const acronyms = new Set(["sba", "sbv", "toa"]);

  // Split on underscores first
  const words = adType.split("_");

  return words
    .map((word) => {
      // Insert spaces between camelCase words (e.g., "Curatedcarousel" -> ["Curated", "carousel"])
      const splitWords = word
        .replace(/([a-z])([A-Z])/g, "$1 $2") // Insert space before uppercase letters
        .toLowerCase()
        .split(" ");

      return splitWords
        .map((w) => {
          // Check if this word is a known acronym
          if (acronyms.has(w)) {
            return w.toUpperCase();
          }
          // Capitalize first letter
          return w.charAt(0).toUpperCase() + w.slice(1);
        })
        .join(" ");
    })
    .join(" ");
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
  clients: string[];
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
  availableAdTypes = [],
  value,
  onChange,
  onApply,
  onReset,
}: {
  retailer: string;
  clients: string[];
  availableAdTypes?: string[];
  value: FiltersState;
  onChange: (next: FiltersState) => void;
  onApply: () => void;
  onReset: () => void;
}) {
  const [openClient, setOpenClient] = useState(false);
  const [openKeywords, setOpenKeywords] = useState(false);
  const [openDate, setOpenDate] = useState(false);
  const [openAdTypes, setOpenAdTypes] = useState(false);
  const [xDays, setXDays] = useState<number>(value.datePreset?.days || 7);
  const [xMonths, setXMonths] = useState<number>(value.datePreset?.months || 1);
  const types = availableAdTypes.length > 0 ? availableAdTypes : [];
  const selectedTypes = new Set(value.types);
  const selectedClients = new Set(value.clients || []);

  // Fetch a broad sample of ads for the first selected client to derive available keywords
  const firstClient = value.clients?.[0];
  const keywordsQuery = useAds({
    retailer,
    client: firstClient || "",
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
        <label className="block text-sm text-[#6b7280] mb-1">Clients</label>
        <Popover open={openClient} onOpenChange={setOpenClient}>
          <PopoverTrigger asChild>
            <Button variant="outline" className="w-full justify-between">
              {selectedClients.size === 0 ? "Select clients" : selectedClients.size === clients.length ? "All" : `${selectedClients.size} selected`}
              <span aria-hidden>▾</span>
            </Button>
          </PopoverTrigger>
          <PopoverContent className="p-0 w-[280px]" align="start">
            <Command filter={(v, s) => (v.includes(s.toLowerCase()) ? 1 : 0)}>
              <CommandInput placeholder="Search client..." />
              <CommandList>
                <CommandEmpty>No client found.</CommandEmpty>
                <CommandGroup>
                  <CommandItem
                    key="__all__"
                    value="all"
                    onSelect={() => {
                      if (selectedClients.size === clients.length) {
                        onChange({ ...value, clients: [] });
                      } else {
                        onChange({ ...value, clients: clients.slice() });
                      }
                    }}
                  >
                    <Checkbox checked={selectedClients.size === clients.length} aria-label="Select all clients" />
                    <span className="ml-2 font-semibold">All</span>
                  </CommandItem>
                  {clients.map((c) => (
                    <CommandItem
                      key={c}
                      value={c.toLowerCase()}
                      onSelect={() => {
                        const next = new Set(selectedClients);
                        if (next.has(c)) next.delete(c); else next.add(c);
                        onChange({ ...value, clients: Array.from(next) });
                      }}
                    >
                      <Checkbox checked={selectedClients.has(c)} aria-label={`toggle ${c}`} />
                      <span className="ml-2">{c}</span>
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
          <PopoverContent className="p-0 w-fit" align="start" side="bottom">
            <div className="flex flex-col">
              {/* Header with gradient background */}
              <div className="bg-gradient-to-r from-blue-500 to-blue-600 text-white p-4 flex justify-between items-start rounded-t-lg">
                <div>
                  <div className="text-xs font-medium opacity-90 mb-1">DATE RANGE</div>
                  <div className="text-lg font-semibold">
                    {value.start && value.end ? (
                      <>
                        {value.start.toLocaleDateString("en-US", { month: "short", day: "numeric" })} – {value.end.toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                      </>
                    ) : (
                      "Select dates"
                    )}
                  </div>
                </div>
                <button
                  onClick={() => setOpenDate(false)}
                  className="text-white hover:opacity-80 transition-opacity flex-shrink-0"
                  aria-label="Close"
                >
                  ✕
                </button>
              </div>

              <div className="grid grid-cols-1 gap-0 lg:grid-cols-[180px_1fr]">
                {/* Presets sidebar */}
                <div className="p-3 border-r border-gray-200 max-h-[450px] overflow-y-auto hidden lg:block bg-gray-50">
                  <div className="space-y-1">
                    <button className="w-full text-left px-2 py-1.5 rounded hover:bg-gray-200 text-sm transition-colors" onClick={() => { applyPreset("today"); onApply(); setOpenDate(false); }}>Today</button>
                    <button className="w-full text-left px-2 py-1.5 rounded hover:bg-gray-200 text-sm transition-colors" onClick={() => { applyPreset("yesterday"); onApply(); setOpenDate(false); }}>Yesterday</button>
                    <button className="w-full text-left px-2 py-1.5 rounded hover:bg-gray-200 text-sm transition-colors" onClick={() => { applyPreset("last_week"); onApply(); setOpenDate(false); }}>Last 7 days</button>
                    <div className="px-2 py-1.5">
                      <div className="text-xs font-medium mb-2 text-gray-600">Last X days</div>
                      <div className="flex items-center gap-1">
                        <Input type="number" min={1} value={xDays} onChange={(e)=> setXDays(Math.max(1, Number(e.target.value)||1))} className="w-14 h-7 text-xs" />
                        <Button size="sm" onClick={() => { applyPreset("last_x_days", { days: xDays }); onApply(); setOpenDate(false); }} className="text-xs py-0 h-7 bg-blue-500 hover:bg-blue-600 text-white">Apply</Button>
                      </div>
                    </div>
                    <div className="px-2 py-1.5">
                      <div className="text-xs font-medium mb-2 text-gray-600">Last X months</div>
                      <div className="flex items-center gap-1">
                        <Input type="number" min={1} value={xMonths} onChange={(e)=> setXMonths(Math.max(1, Number(e.target.value)||1))} className="w-14 h-7 text-xs" />
                        <Button size="sm" onClick={() => { applyPreset("last_x_months", { months: xMonths }); onApply(); setOpenDate(false); }} className="text-xs py-0 h-7 bg-blue-500 hover:bg-blue-600 text-white">Apply</Button>
                      </div>
                    </div>
                    <button className="w-full text-left px-2 py-1.5 rounded hover:bg-gray-200 text-sm transition-colors" onClick={() => { applyPreset("mtd"); onApply(); setOpenDate(false); }}>Month to date</button>
                    <button className="w-full text-left px-2 py-1.5 rounded hover:bg-gray-200 text-sm transition-colors" onClick={() => { applyPreset("ytd"); onApply(); setOpenDate(false); }}>Year to date</button>
                    <button className="w-full text-left px-2 py-1.5 rounded hover:bg-gray-200 text-sm transition-colors" onClick={() => { applyPreset("last_52_weeks"); onApply(); setOpenDate(false); }}>Last 52 weeks</button>
                    <button className="w-full text-left px-2 py-1.5 rounded hover:bg-gray-200 text-sm transition-colors" onClick={() => { applyPreset("lifetime"); onApply(); setOpenDate(false); }}>Lifetime</button>
                    <button className="w-full text-left px-2 py-1.5 rounded hover:bg-gray-200 text-sm transition-colors" onClick={() => { applyPreset("custom"); }}>Custom…</button>
                  </div>
                </div>

                {/* Calendar */}
                <div className="p-6 flex flex-col bg-white">
                  <div className="flex gap-8">
                    <div className="flex-1">
                      <div className="text-xs font-medium text-gray-500 mb-2">Start Date</div>
                      <Calendar
                        mode="single"
                        selected={value.start}
                        onSelect={(date) => {
                          if (date) {
                            // If start date is after end date, update end date
                            if (value.end && date > value.end) {
                              onChange({ ...value, start: date, end: date, datePreset: { type: "custom" } });
                            } else {
                              onChange({ ...value, start: date, datePreset: { type: "custom" } });
                            }
                          }
                        }}
                        disabled={{ before: new Date("2020-01-01") }}
                      />
                    </div>
                    <div className="flex-1">
                      <div className="text-xs font-medium text-gray-500 mb-2">End Date</div>
                      <Calendar
                        mode="single"
                        selected={value.end}
                        onSelect={(date) => {
                          if (date) {
                            // If end date is before start date, update start date
                            if (value.start && date < value.start) {
                              onChange({ ...value, start: date, end: date, datePreset: { type: "custom" } });
                            } else {
                              onChange({ ...value, end: date, datePreset: { type: "custom" } });
                            }
                          }
                        }}
                        disabled={{ before: new Date("2020-01-01") }}
                      />
                    </div>
                  </div>
                  <div className="flex justify-end gap-2 mt-4 pt-4 border-t border-gray-200">
                    <Button variant="outline" size="sm" onClick={() => setOpenDate(false)}>Close</Button>
                    <Button size="sm" onClick={() => { onApply(); setOpenDate(false); }} className="bg-blue-500 hover:bg-blue-600 text-white">Apply</Button>
                  </div>
                </div>
              </div>
            </div>
          </PopoverContent>
        </Popover>
      </div>

      <div className="flex-1 min-w-[220px]">
        <label className="block text-sm text-[#6b7280] mb-1">Ad types</label>
        <Popover open={openAdTypes} onOpenChange={setOpenAdTypes}>
          <PopoverTrigger asChild>
            <Button variant="outline" className="w-full justify-between">
              {selectedTypes.size === 0 ? "Select ad types" : `${selectedTypes.size} ad type${selectedTypes.size !== 1 ? 's' : ''}`}
              <span aria-hidden>▾</span>
            </Button>
          </PopoverTrigger>
          <PopoverContent className="p-0 w-[320px]" align="start">
            <div className="p-3 space-y-2 max-h-[400px] overflow-y-auto">
              {types.length === 0 ? (
                <div className="text-sm text-gray-500 py-4 text-center">No ad types available</div>
              ) : (
                types.map((t) => (
                  <label key={t} className="flex items-center gap-2 p-2 rounded hover:bg-gray-50 cursor-pointer">
                    <Checkbox
                      checked={selectedTypes.has(t)}
                      onCheckedChange={(checked) => {
                        const next = new Set(value.types);
                        if (checked) next.add(t); else next.delete(t);
                        onChange({ ...value, types: Array.from(next) });
                      }}
                      aria-label={`toggle ${t}`}
                    />
                    <span className="text-sm">{formatAdTypeName(t)}</span>
                  </label>
                ))
              )}
            </div>
          </PopoverContent>
        </Popover>
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
