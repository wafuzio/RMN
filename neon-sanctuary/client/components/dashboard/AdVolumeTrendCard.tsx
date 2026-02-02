import { useMemo } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

function groupBy<T>(arr: T[], key: (t: T) => string) {
  const map = new Map<string, T[]>();
  for (const item of arr) {
    const k = key(item);
    map.set(k, (map.get(k) || []).concat(item));
  }
  return map;
}

interface AdVolumeTrendPoint {
  label: string;
  count: number;
  index: number;
  date: Date;
}

export function AdVolumeTrendCard({ timestamps }: { timestamps: string[] }) {
  const points: AdVolumeTrendPoint[] = useMemo(() => {
    if (!timestamps || timestamps.length === 0) {
      console.log('[AdVolumeTrend] No timestamps provided');
      return [];
    }

    console.log(`[AdVolumeTrend] Processing ${timestamps.length} timestamps`);

    // Parse dates
    const dates = timestamps
      .filter(t => t && typeof t === 'string')
      .map(t => {
        const normalized = t.includes('T') ? t : t.replace(" ", "T");
        return new Date(normalized);
      })
      .filter(d => !isNaN(d.getTime()));

    if (dates.length === 0) {
      console.log('[AdVolumeTrend] No valid dates after parsing');
      return [];
    }

    // Group by day
    const format = (d: Date) => d.toISOString().slice(0, 10);
    const grouped = groupBy(dates, format);

    // Exclude today's date
    const today = new Date().toISOString().slice(0, 10);

    const result = Array.from(grouped.entries())
      .filter(([k]) => k !== today)
      .map(([k, vals]) => ({ label: k, count: vals.length, date: vals[0] }))
      .sort((a, b) => +a.date - +b.date);

    console.log(`[AdVolumeTrend] Grouped into ${result.length} unique days:`, result.map(r => r.label));

    if (result.length === 0) return [];

    // Calculate index (first date = 100)
    const baselineCount = result[0].count || 1;
    return result.map(p => ({
      ...p,
      index: Math.round((p.count / baselineCount) * 100),
    }));
  }, [timestamps]);

  if (points.length === 0) {
    return (
      <div className="card-surface p-6 h-40 flex items-center justify-center text-gray-400 text-sm">
        No data available
      </div>
    );
  }

  const firstDate = points[0]?.label || "Start";
  const lastDate = points[points.length - 1]?.label || "End";

  return (
    <div className="card-surface p-6 flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-sm text-[#6b7280]">Ad Volume Trend</div>
          <div className="text-xs text-[#6b7280] mt-1">
            {firstDate} to {lastDate}
          </div>
        </div>
      </div>
      
      <ResponsiveContainer width="100%" height={60}>
        <LineChart
          data={points}
          margin={{ top: 8, right: 0, left: 0, bottom: 0 }}
        >
          <XAxis
            dataKey="label"
            tick={false}
            tickLine={false}
            axisLine={false}
            height={0}
          />
          <YAxis
            hide={true}
            domain={[0, 'auto']}
          />
          <Tooltip
            contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '0.5rem' }}
            labelStyle={{ color: '#fff' }}
            formatter={(value) => [`${value}`, 'Index']}
            cursor={false}
          />
          <Line
            type="monotone"
            dataKey="index"
            stroke="url(#adVolumeTrendGradient)"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={true}
          />
          <defs>
            <linearGradient id="adVolumeTrendGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#667eea" />
              <stop offset="100%" stopColor="#764ba2" />
            </linearGradient>
          </defs>
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
