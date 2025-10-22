import { useMemo, useState } from "react";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

function groupBy<T>(arr: T[], key: (t: T) => string) {
  const map = new Map<string, T[]>();
  for (const item of arr) {
    const k = key(item);
    map.set(k, (map.get(k) || []).concat(item));
  }
  return map;
}

export interface TimelinePoint { label: string; count: number; date: Date }

export function Timeline({ timestamps, onRangeChange }: { timestamps: string[]; onRangeChange?: (start: Date, end: Date) => void }) {
  const [granularity, setGranularity] = useState<"month"|"week"|"day">("day");

  const points: TimelinePoint[] = useMemo(() => {
    // Filter out invalid/missing timestamps and create valid Date objects
    const dates = timestamps
      .filter(t => t && typeof t === 'string') // Remove null/undefined/non-string
      .map(t => {
        // Handle Instacart format: 20251022_002600 -> 2025-10-22T00:26:00
        if (/^\d{8}_\d{6}$/.test(t)) {
          const date = t.slice(0, 8);
          const time = t.slice(9, 15);
          const yyyy = date.slice(0, 4);
          const mm = date.slice(4, 6);
          const dd = date.slice(6, 8);
          const hh = time.slice(0, 2);
          const min = time.slice(2, 4);
          const ss = time.slice(4, 6);
          return new Date(`${yyyy}-${mm}-${dd}T${hh}:${min}:${ss}`);
        }
        // Walmart format and incomplete timestamps are skipped (no date info available here)
        // Handle Kroger format: 2025-10-13 22:07:10 -> 2025-10-13T22:07:10
        const normalized = t.includes('T') ? t : t.replace(" ", "T");
        return new Date(normalized);
      })
      .filter(d => !isNaN(d.getTime())); // Remove invalid dates

    if (dates.length === 0) return [];

    let format: (d: Date)=>string;
    if (granularity === "month") format = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`;
    else if (granularity === "week") {
      format = d => {
        const tmp = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
        const dayNum = tmp.getUTCDay() || 7; tmp.setUTCDate(tmp.getUTCDate() + 4 - dayNum);
        const yearStart = new Date(Date.UTC(tmp.getUTCFullYear(),0,1));
        const weekNo = Math.ceil((((tmp as any)-(+yearStart))/86400000 + 1)/7);
        return `${tmp.getUTCFullYear()}-W${String(weekNo).padStart(2,"0")}`;
      };
    } else format = d => d.toISOString().slice(0,10);

    const grouped = groupBy(dates, format);
    const result = Array.from(grouped.entries()).map(([k, vals]) => ({ label: k, count: vals.length, date: vals[0] }));
    result.sort((a,b) => +a.date - +b.date);
    return result;
  }, [timestamps, granularity]);

  const [range, setRange] = useState<[number, number]>([0, Math.max(0, (points.length-1))]);

  const min = 0, max = Math.max(0, points.length-1);

  const visible = points.slice(range[0], range[1]+1);

  // Apply date filter when range changes
  const handleRangeChange = (newRange: [number, number]) => {
    setRange(newRange);
    if (onRangeChange && points.length > 0) {
      const startPoint = points[newRange[0]];
      const endPoint = points[newRange[1]];
      if (startPoint && endPoint) {
        onRangeChange(startPoint.date, endPoint.date);
      }
    }
  };

  return (
    <div className="card-surface p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm text-[#6b7280]">Timeline</div>
        <Tabs value={granularity} onValueChange={(v)=>setGranularity(v as any)}>
          <TabsList>
            <TabsTrigger value="month">Month</TabsTrigger>
            <TabsTrigger value="week">Week</TabsTrigger>
            <TabsTrigger value="day">Day</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
      <div className="h-24 w-full flex items-end gap-1 overflow-x-auto" role="img" aria-label="Ad volume over time">
        {visible.map((p, i) => (
          <div key={i} className="flex-1 min-w-[8px] bg-gradient-to-t from-[#764ba2] to-[#667eea] rounded-sm" style={{ height: Math.max(4, (p.count) * 6) }} title={`${p.label}: ${p.count}`} />
        ))}
      </div>
      <div className="mt-3">
        <Slider value={[range[0], range[1]]} min={min} max={max} step={1} onValueChange={(v:any)=> handleRangeChange([v[0], v[1]])} />
        <div className="mt-1 text-xs text-[#6b7280] flex justify-between">
          <span>{points[range[0]]?.label || ""}</span>
          <span>{points[range[1]]?.label || ""}</span>
        </div>
      </div>
    </div>
  );
}
