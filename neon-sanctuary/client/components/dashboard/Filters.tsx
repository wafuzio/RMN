import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem } from "@/components/ui/command";
import { cn } from "@/lib/utils";

const AD_TYPES: Record<string, string[]> = {
  kroger: ["TOA", "Carousel", "Skyscraper", "Display_Ads"],
  amazon: ["Sponsored_Brand_Video", "Sponsored_Product", "Featured_Brand", "Sponsored_Carousel"],
  instacart: ["Shoppable_Display_Ads", "Video_Ads", "Sponsored_Products"],
  walmart: ["Top_Banner", "SBA", "Tile_Takeover", "SBV"],
};

export interface FiltersState {
  client?: string;
  start?: Date | undefined;
  end?: Date | undefined;
  types: string[];
  search?: string;
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
  const types = AD_TYPES[retailer] || [];
  const selectedTypes = new Set(value.types);

  const dateLabel = useMemo(() => {
    if (value.start && value.end) return `${value.start.toLocaleDateString()} - ${value.end.toLocaleDateString()}`;
    return "Select date range";
  }, [value.start, value.end]);

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
              <CommandEmpty>No client found.</CommandEmpty>
              <CommandGroup>
                {clients.map((c) => (
                  <CommandItem key={c} value={c.toLowerCase()} onSelect={() => { onChange({ ...value, client: c }); setOpenClient(false); }}>
                    {c}
                  </CommandItem>
                ))}
              </CommandGroup>
            </Command>
          </PopoverContent>
        </Popover>
      </div>

      <div className="min-w-[260px]">
        <label className="block text-sm text-[#6b7280] mb-1">Date range</label>
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" className="w-full justify-between">
              {dateLabel}
              <span aria-hidden>▾</span>
            </Button>
          </PopoverTrigger>
          <PopoverContent className="p-0" align="start">
            <div className="p-3">
              <Calendar
                mode="range"
                selected={{ from: value.start, to: value.end }}
                onSelect={(r: any) => onChange({ ...value, start: r?.from, end: r?.to })}
                numberOfMonths={2}
              />
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
        <label className="block text-sm text-[#6b7280] mb-1">Search</label>
        <Input value={value.search || ""} onChange={(e) => onChange({ ...value, search: e.target.value })} placeholder="Keyword or brand" />
      </div>

      <div className="flex gap-2 ml-auto">
        <Button onClick={onApply} className="bg-gradient-to-r from-[#667eea] to-[#764ba2] text-white rounded-md">Apply Filters</Button>
        <Button variant="outline" onClick={onReset} className="bg-gray-50">Reset</Button>
      </div>
    </div>
  );
}
