import { useEffect, useRef, useMemo, useState } from "react";
import { Slider } from "@/components/ui/slider";
import { RETAILERS, generateHeatmapData as generateHeatData } from "@/lib/experiment-data";

const generateHeatmapData = () => {
  const retailers = [...RETAILERS];
  const days = 60;
  const heatData = generateHeatData(days);

  // Group by retailer
  const dataByRetailer = retailers.map((retailer) => 
    heatData
      .filter((cell) => cell.retailer === retailer)
      .map((cell) => ({
        day: cell.day,
        intensity: cell.intensity,
        adCount: cell.adCount,
      }))
  );

  return {
    retailers,
    data: dataByRetailer,
  };
};

export default function AdIntensityHeatTimeline() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { retailers, data } = useMemo(() => generateHeatmapData(), []);
  const [minIntensity, setMinIntensity] = useState(0);
  const [maxIntensity, setMaxIntensity] = useState(100);
  const [hoveredRetailer, setHoveredRetailer] = useState<number | null>(null);
  const [hoveredDay, setHoveredDay] = useState<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.offsetWidth;
    const height = canvas.offsetHeight;
    canvas.width = width;
    canvas.height = height;

    const cellWidth = (width - 150) / 60;
    const cellHeight = height / retailers.length;
    const padding = 150;

    // Draw heatmap with filtered data
    data.forEach((retailerData, rIdx) => {
      retailerData.forEach(({ day, intensity }, dIdx) => {
        const x = padding + day * cellWidth;
        const y = rIdx * cellHeight;

        // Check if within filter range
        const inRange = intensity >= minIntensity && intensity <= maxIntensity;
        const isHovered = hoveredRetailer === rIdx && hoveredDay === day;
        const isRetailerHovered = hoveredRetailer === rIdx;

        // Determine opacity based on selection
        let opacity = 1;
        if (hoveredRetailer !== null && !isRetailerHovered) {
          opacity = 0.3;
        }

        // Color based on intensity with filtering
        let hue = 210;
        let sat = 40;
        let light = 50;

        if (inRange) {
          if (intensity < 33) {
            light = 35;
            sat = 20;
          } else if (intensity < 66) {
            light = 45;
            sat = 50;
          } else {
            light = 55;
            sat = 80;
          }
        } else {
          // Desaturated if filtered out
          light = 30;
          sat = 5;
          opacity *= 0.4;
        }

        ctx.fillStyle = `hsl(${hue}, ${sat}%, ${light}%)`;
        ctx.globalAlpha = opacity;
        ctx.fillRect(x, y, cellWidth - 1, cellHeight - 1);

        // Draw border
        ctx.globalAlpha = 1;
        ctx.strokeStyle = isHovered ? "rgba(255, 255, 255, 0.8)" : "rgba(15, 23, 42, 0.5)";
        ctx.lineWidth = isHovered ? 2 : 0.5;
        ctx.globalAlpha = isHovered ? 1 : 0.6;
        ctx.strokeRect(x, y, cellWidth - 1, cellHeight - 1);
        ctx.globalAlpha = 1;
      });
    });

    // Draw retailer labels
    ctx.fillStyle = "rgba(226, 232, 240, 0.9)";
    ctx.font = "12px Inter, sans-serif";
    ctx.textAlign = "right";
    retailers.forEach((name, idx) => {
      const isHovered = hoveredRetailer === idx;
      ctx.fillStyle = isHovered ? "rgba(59, 130, 246, 1)" : "rgba(226, 232, 240, 0.8)";
      ctx.font = isHovered ? "bold 12px Inter, sans-serif" : "12px Inter, sans-serif";
      ctx.fillText(name, padding - 10, idx * cellHeight + cellHeight / 2 + 4);
    });

    // Draw sparklines
    retailers.forEach((_, rIdx) => {
      const retailerData = data[rIdx];
      const sparklineY = rIdx * cellHeight + cellHeight - 8;

      ctx.strokeStyle = `rgba(139, 92, 246, ${hoveredRetailer === rIdx ? 1 : 0.5})`;
      ctx.lineWidth = hoveredRetailer === rIdx ? 2.5 : 1.5;
      ctx.beginPath();

      retailerData.forEach(({ day, intensity }, idx) => {
        const x = padding + day * cellWidth + cellWidth / 2;
        const y = sparklineY - (intensity / 100) * 8;

        if (idx === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      });
      ctx.stroke();
    });

    // Draw day markers on top
    ctx.strokeStyle = "rgba(148, 163, 184, 0.3)";
    ctx.lineWidth = 1;
    for (let day = 0; day < 60; day += 10) {
      const x = padding + day * cellWidth;
      ctx.beginPath();
      ctx.moveTo(x, -5);
      ctx.lineTo(x, height);
      ctx.stroke();

      ctx.fillStyle = "rgba(148, 163, 184, 0.5)";
      ctx.font = "10px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(`D${day}`, x, height + 15);
    }

  }, [data, retailers, minIntensity, maxIntensity, hoveredRetailer, hoveredDay]);

  // Handle mouse move for hover
  const handleCanvasMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = e.currentTarget;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const cellWidth = (rect.width - 150) / 60;
    const cellHeight = rect.height / retailers.length;
    const padding = 150;

    if (x < padding) {
      setHoveredRetailer(Math.floor(y / cellHeight));
      setHoveredDay(null);
    } else {
      const retailerIdx = Math.floor(y / cellHeight);
      const dayIdx = Math.floor((x - padding) / cellWidth);

      if (retailerIdx >= 0 && retailerIdx < retailers.length && dayIdx >= 0 && dayIdx < 60) {
        setHoveredRetailer(retailerIdx);
        setHoveredDay(dayIdx);
      }
    }
  };

  const handleCanvasMouseLeave = () => {
    setHoveredRetailer(null);
    setHoveredDay(null);
  };

  const hoveredIntensity = hoveredRetailer !== null && hoveredDay !== null
    ? data[hoveredRetailer][hoveredDay].intensity
    : null;

  return (
    <div className="space-y-4">
      <canvas
        ref={canvasRef}
        onMouseMove={handleCanvasMouseMove}
        onMouseLeave={handleCanvasMouseLeave}
        className="w-full h-96 rounded-lg bg-gradient-to-br from-slate-700/50 to-slate-800/50 border border-slate-600/50 cursor-crosshair"
      />

      <div className="space-y-3">
        <div>
          <label className="text-sm font-semibold text-slate-300 block mb-2">
            Intensity Range: {minIntensity} - {maxIntensity}
          </label>
          <div className="flex gap-4">
            <div className="flex-1">
              <div className="text-xs text-slate-500 mb-1">Min</div>
              <Slider
                value={[minIntensity]}
                onValueChange={([v]) => setMinIntensity(Math.min(v, maxIntensity))}
                min={0}
                max={100}
                step={5}
                className="w-full"
              />
            </div>
            <div className="flex-1">
              <div className="text-xs text-slate-500 mb-1">Max</div>
              <Slider
                value={[maxIntensity]}
                onValueChange={([v]) => setMaxIntensity(Math.max(v, minIntensity))}
                min={0}
                max={100}
                step={5}
                className="w-full"
              />
            </div>
          </div>
        </div>

        {hoveredIntensity !== null && (
          <div className="p-3 bg-blue-900/20 border border-blue-600/30 rounded text-sm text-blue-300">
            <strong>{retailers[hoveredRetailer!]}</strong> on Day {hoveredDay} <br />
            Intensity: <span className="font-bold">{hoveredIntensity.toFixed(1)}</span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-3 gap-4 text-sm">
        <div className="bg-slate-700/30 rounded p-3 border border-slate-600/50">
          <div className="text-slate-400">Retailers</div>
          <div className="text-lg font-bold text-slate-200">{retailers.length}</div>
        </div>
        <div className="bg-slate-700/30 rounded p-3 border border-slate-600/50">
          <div className="text-slate-400">Time Period</div>
          <div className="text-lg font-bold text-slate-200">60 days</div>
        </div>
        <div className="bg-slate-700/30 rounded p-3 border border-slate-600/50">
          <div className="text-slate-400">Visible Cells</div>
          <div className="text-lg font-bold text-blue-400">
            {data.flatMap(r => r).filter(d => d.intensity >= minIntensity && d.intensity <= maxIntensity).length}
          </div>
        </div>
      </div>

      <div className="text-xs text-slate-500">
        Hover over cells to see detailed metrics. Use sliders to filter by intensity range.
      </div>
    </div>
  );
}
