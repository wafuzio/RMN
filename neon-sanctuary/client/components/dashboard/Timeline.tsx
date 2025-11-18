import { useMemo, useState, useEffect } from "react";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

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
        // All retailers now use ISO Z format (e.g., "2025-10-27T02:56:54Z")
        // Handle space-separated format (legacy): 2025-10-13 22:07:10 -> 2025-10-13T22:07:10
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

  const [range, setRange] = useState<[number, number]>([0, 0]);

  const min = 0, max = Math.max(0, points.length-1);

  // Update range when points change to ensure right thumb is at the end
  useEffect(() => {
    setRange([0, Math.max(0, points.length - 1)]);
  }, [points.length]);

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
      <div className="space-y-2">
        {points.length === 0 ? (
          <div className="w-full h-32 flex items-center justify-center text-gray-400 text-sm">No data</div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart
              data={points.map((p, i) => ({
                ...p,
                index: points[0] ? Math.round((p.count / points[0].count) * 100) : 100,
                inRange: i >= range[0] && i <= range[1],
              }))}
              margin={{ top: 5, right: 30, left: 0, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 12, fill: '#6b7280' }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                tick={{ fontSize: 12, fill: '#6b7280' }}
                tickLine={false}
                axisLine={false}
                label={{ value: 'Index', angle: -90, position: 'insideLeft', style: { fill: '#6b7280', fontSize: 12 } }}
              />
              <Tooltip
                contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '0.5rem' }}
                labelStyle={{ color: '#fff' }}
                formatter={(value) => [`${value}`, 'Index']}
                cursor={{ stroke: '#667eea', strokeWidth: 1 }}
              />
              <Line
                type="monotone"
                dataKey="index"
                stroke="url(#lineGradient)"
                strokeWidth={3}
                dot={{ fill: '#667eea', r: 5 }}
                activeDot={{ r: 7, fill: '#764ba2' }}
                isAnimationActive={true}
              />
              <defs>
                <linearGradient id="lineGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#667eea" />
                  <stop offset="100%" stopColor="#764ba2" />
                </linearGradient>
              </defs>
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
      <div className="mt-6">
        <div className="relative pt-8 pb-6">
          <div className="absolute top-8 left-0 right-0 h-1 bg-gray-300 rounded-full pointer-events-none" />
          <div
            className="absolute top-8 h-1 bg-gradient-to-r from-[#667eea] to-[#764ba2] rounded-full pointer-events-none"
            style={{
              left: `${(range[0] / max) * 100}%`,
              right: `${100 - (range[1] / max) * 100}%`,
            }}
          />

          {/* Start date label */}
          <div
            className="absolute -top-8 flex items-center justify-center transform -translate-x-1/2 pointer-events-none"
            style={{ left: `${(range[0] / max) * 100}%` }}
          >
            <div className="bg-[#1f2937] text-white px-2 py-1 rounded text-xs font-semibold whitespace-nowrap">
              {points[range[0]]?.label || ""}
            </div>
          </div>

          {/* End date label */}
          <div
            className="absolute -top-8 flex items-center justify-center transform -translate-x-1/2 pointer-events-none"
            style={{ left: `${(range[1] / max) * 100}%` }}
          >
            <div className="bg-[#1f2937] text-white px-2 py-1 rounded text-xs font-semibold whitespace-nowrap">
              {points[range[1]]?.label || ""}
            </div>
          </div>

          <input
            type="range"
            min={min}
            max={max}
            value={range[0]}
            onChange={(e) => {
              const val = Number(e.target.value);
              const newMin = Math.min(val, range[1]);
              handleRangeChange([newMin, range[1]]);
            }}
            className="slider-min absolute w-full h-4 top-6 left-0 appearance-none bg-transparent cursor-pointer"
            style={{
              zIndex: 4,
              pointerEvents: 'auto',
            }}
          />
          <input
            type="range"
            min={min}
            max={max}
            value={range[1]}
            onChange={(e) => {
              const val = Number(e.target.value);
              const newMax = Math.max(val, range[0]);
              handleRangeChange([range[0], newMax]);
            }}
            className="slider-max absolute w-full h-4 top-6 left-0 appearance-none bg-transparent cursor-pointer"
            style={{
              zIndex: 5,
              pointerEvents: 'auto',
            }}
          />
          <style>{`
            .slider-min, .slider-max {
              -webkit-appearance: none;
              appearance: none;
              padding: 0;
            }
            .slider-min::-webkit-slider-thumb,
            .slider-max::-webkit-slider-thumb {
              -webkit-appearance: none;
              appearance: none;
              width: 20px;
              height: 20px;
              border-radius: 50%;
              background: white;
              border: 3px solid #667eea;
              cursor: pointer;
              box-shadow: 0 2px 8px rgba(102, 126, 234, 0.4);
            }
            .slider-min::-webkit-slider-thumb:active,
            .slider-max::-webkit-slider-thumb:active {
              box-shadow: 0 4px 16px rgba(102, 126, 234, 0.8);
            }
            .slider-min::-moz-range-thumb,
            .slider-max::-moz-range-thumb {
              width: 20px;
              height: 20px;
              border-radius: 50%;
              background: white;
              border: 3px solid #667eea;
              cursor: pointer;
              box-shadow: 0 2px 8px rgba(102, 126, 234, 0.4);
            }
            .slider-min::-moz-range-thumb:active,
            .slider-max::-moz-range-thumb:active {
              box-shadow: 0 4px 16px rgba(102, 126, 234, 0.8);
            }
            .slider-min::-moz-range-track {
              background: transparent;
              border: none;
            }
            .slider-max::-moz-range-track {
              background: transparent;
              border: none;
            }
          `}</style>
        </div>

        <div className="mt-8 grid grid-cols-2 gap-6">
          <div>
            <label className="block text-xs text-[#6b7280] font-medium mb-2">Start Date</label>
            <div className="flex items-center border border-gray-300 rounded-lg overflow-hidden bg-white">
              <input
                type="text"
                value={points[range[0]]?.label || ""}
                readOnly
                className="flex-1 px-3 py-2 text-sm focus:outline-none bg-white text-[#111827]"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-[#6b7280] font-medium mb-2">End Date</label>
            <div className="flex items-center border border-gray-300 rounded-lg overflow-hidden bg-white">
              <input
                type="text"
                value={points[range[1]]?.label || ""}
                readOnly
                className="flex-1 px-3 py-2 text-sm focus:outline-none bg-white text-[#111827]"
              />
            </div>
          </div>
        </div>

        <div className="mt-4 text-xs text-[#6b7280]">
          <div className="flex justify-between">
            <span className="font-semibold">{points.slice(range[0], range[1]+1).reduce((sum, p) => sum + p.count, 0)} entries selected</span>
            <span className="text-[#6b7280]">
              {range[0] > 0 && <span className="mr-3">{points.slice(0, range[0]).reduce((sum, p) => sum + p.count, 0)} before</span>}
              {range[1] < points.length - 1 && <span>{points.slice(range[1]+1).reduce((sum, p) => sum + p.count, 0)} after</span>}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
