import { useEffect, useRef, useMemo, useState } from "react";
import { Slider } from "@/components/ui/slider";

const generatePulseData = () => {
  const retailers = ["Amazon", "Walmart", "Target", "Best Buy"];
  const days = 90;

  return {
    retailers,
    data: retailers.map((r) =>
      Array.from({ length: days }, (_, i) => {
        const baseFreq = Math.sin((i / days) * Math.PI) * 30 + 20;
        const pulses = Math.sin(i / 15) * 25;
        const noise = Math.random() * 10;
        return Math.max(0, baseFreq + pulses + noise);
      })
    ),
  };
};

export default function ChannelPulseLine() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { retailers, data } = useMemo(() => generatePulseData(), []);
  const [sensitivity, setSensitivity] = useState(50);
  const [hoveredDay, setHoveredDay] = useState<number | null>(null);
  const [hoveredRetailer, setHoveredRetailer] = useState<string | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.offsetWidth;
    const height = canvas.offsetHeight;
    canvas.width = width;
    canvas.height = height;

    const padding = 60;
    const graphWidth = width - padding * 2;
    const graphHeight = height - padding * 2;
    const maxValue = 80;

    // Draw grid with sensitivity-based opacity
    ctx.strokeStyle = `rgba(71, 85, 105, ${0.1 + (sensitivity / 100) * 0.2})`;
    ctx.lineWidth = 1;

    for (let i = 0; i <= 5; i++) {
      const y = padding + (graphHeight / 5) * i;
      ctx.beginPath();
      ctx.moveTo(padding, y);
      ctx.lineTo(width - padding, y);
      ctx.stroke();
    }

    // Draw axes
    ctx.strokeStyle = "rgba(148, 163, 184, 0.6)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(padding, padding);
    ctx.lineTo(padding, height - padding);
    ctx.lineTo(width - padding, height - padding);
    ctx.stroke();

    // Colors for each retailer
    const colors = ["#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b"];

    // Draw lines with glow based on sensitivity
    data.forEach((retailerData, retIdx) => {
      const color = colors[retIdx];
      const retailer = retailers[retIdx];
      const isHovered = hoveredRetailer === retailer;
      const glowSize = 8 + (sensitivity / 100) * 4;

      // Draw glow (more pronounced with sensitivity)
      ctx.strokeStyle = `${color}${(0.2 + (sensitivity / 100) * 0.15).toString(16).padStart(2, "0")}`;
      ctx.lineWidth = glowSize;
      ctx.beginPath();

      retailerData.forEach((value, i) => {
        const x = padding + (graphWidth / (retailerData.length - 1)) * i;
        const y = height - padding - (value / maxValue) * graphHeight;

        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      });
      ctx.stroke();

      // Draw main line
      ctx.strokeStyle = color;
      ctx.lineWidth = isHovered ? 3.5 : 2.5;
      ctx.beginPath();

      retailerData.forEach((value, i) => {
        const x = padding + (graphWidth / (retailerData.length - 1)) * i;
        const y = height - padding - (value / maxValue) * graphHeight;

        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      });
      ctx.stroke();

      // Draw pulse points (peaks)
      const peakThreshold = 50 + (100 - sensitivity);
      retailerData.forEach((value, i) => {
        if (i > 0 && i < retailerData.length - 1) {
          const prev = retailerData[i - 1];
          const next = retailerData[i + 1];

          if (value > prev && value > next && value > peakThreshold) {
            const x = padding + (graphWidth / (retailerData.length - 1)) * i;
            const y = height - padding - (value / maxValue) * graphHeight;

            // Draw halo (larger with sensitivity)
            const haloSize = 12 + (sensitivity / 100) * 8;
            ctx.fillStyle = `${color}${(0.2 + (sensitivity / 100) * 0.2).toString(16).padStart(2, "0")}`;
            ctx.beginPath();
            ctx.arc(x, y, haloSize, 0, Math.PI * 2);
            ctx.fill();

            // Draw point
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(x, y, 5 + (sensitivity / 100) * 2, 0, Math.PI * 2);
            ctx.fill();

            // Draw indicator line
            if (hoveredDay === i) {
              ctx.strokeStyle = `${color}80`;
              ctx.lineWidth = 2;
              ctx.setLineDash([4, 4]);
              ctx.beginPath();
              ctx.moveTo(x, padding);
              ctx.lineTo(x, height - padding);
              ctx.stroke();
              ctx.setLineDash([]);
            }
          }
        }
      });
    });

    // Draw day axis labels
    ctx.fillStyle = "rgba(226, 232, 240, 0.8)";
    ctx.font = "11px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";

    for (let d = 0; d < 90; d += 15) {
      const x = padding + (graphWidth / 89) * d;
      ctx.fillText(`D${d}`, x, height - padding + 8);
    }

    // Draw Y-axis labels
    ctx.fillStyle = "rgba(226, 232, 240, 0.8)";
    ctx.font = "11px Inter, sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";

    for (let i = 0; i <= 5; i++) {
      const y = padding + (graphHeight / 5) * i;
      const value = maxValue - (maxValue / 5) * i;
      ctx.fillText(`${value.toFixed(0)}`, padding - 10, y);
    }

    // Draw retailer legend with hover state
    ctx.textAlign = "left";
    retailers.forEach((name, idx) => {
      const isHovered = hoveredRetailer === name;
      ctx.fillStyle = colors[idx];
      ctx.globalAlpha = isHovered ? 1 : 0.7;
      ctx.beginPath();
      ctx.arc(width - 200, 30 + idx * 25, isHovered ? 6 : 4, 0, Math.PI * 2);
      ctx.fill();

      ctx.globalAlpha = 1;
      ctx.fillStyle = isHovered ? "rgba(255, 255, 255, 1)" : "rgba(226, 232, 240, 0.8)";
      ctx.font = isHovered ? "bold 12px Inter, sans-serif" : "12px Inter, sans-serif";
      ctx.fillText(name, width - 185, 33 + idx * 25);
    });

  }, [data, retailers, sensitivity, hoveredDay, hoveredRetailer]);

  const handleCanvasMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = e.currentTarget;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;

    const padding = 60;
    const graphWidth = rect.width - padding * 2;

    if (x >= padding && x <= rect.width - padding) {
      const day = Math.round(((x - padding) / graphWidth) * 89);
      setHoveredDay(Math.max(0, Math.min(89, day)));
    }
  };

  const handleCanvasMouseLeave = () => {
    setHoveredDay(null);
    setHoveredRetailer(null);
  };

  return (
    <div className="space-y-4">
      <canvas
        ref={canvasRef}
        onMouseMove={handleCanvasMouseMove}
        onMouseLeave={handleCanvasMouseLeave}
        onMouseEnter={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const legend = [rect.width - 200, 30];
          // Hover detection for legend will be implicit
        }}
        className="w-full h-96 rounded-lg bg-gradient-to-br from-slate-700/50 to-slate-800/50 border border-slate-600/50 cursor-crosshair"
      />

      <div className="space-y-3">
        <div>
          <label className="text-sm font-semibold text-slate-300 block mb-2">
            Peak Sensitivity: {sensitivity}
          </label>
          <Slider
            value={[sensitivity]}
            onValueChange={([v]) => setSensitivity(v)}
            min={0}
            max={100}
            step={5}
            className="w-full"
          />
          <p className="text-xs text-slate-500 mt-1">Higher sensitivity shows smaller peaks</p>
        </div>

        {hoveredDay !== null && (
          <div className="p-3 bg-blue-900/20 border border-blue-600/30 rounded text-sm text-blue-300">
            <strong>Day {hoveredDay}</strong><br />
            {retailers.map((name, idx) => (
              <div key={name}>
                {name}: <span className="font-semibold">{data[idx][hoveredDay].toFixed(1)}</span>
              </div>
            ))}
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
          <div className="text-lg font-bold text-slate-200">90 days</div>
        </div>
        <div className="bg-slate-700/30 rounded p-3 border border-slate-600/50">
          <div className="text-slate-400">Max Activity</div>
          <div className="text-lg font-bold text-blue-400">80</div>
        </div>
      </div>

      <div className="text-xs text-slate-500">
        Move cursor over chart to see daily values. Larger halos indicate detected peaks.
      </div>
    </div>
  );
}
