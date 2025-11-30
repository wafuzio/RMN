import { useEffect, useRef, useState, useMemo } from "react";
import { Slider } from "@/components/ui/slider";
import { generateRadarData as generateRadarMetrics } from "@/lib/experiment-data";

const metrics = ["Share of Voice", "Creative Diversity", "Retail Penetration", "Frequency Intensity", "Time Dominance", "Seasonality"];

interface RadarData {
  you: number[];
  competitor1: number[];
  competitor2: number[];
}

const generateRadarData = (seed: number = 0): RadarData => {
  const radarData = generateRadarMetrics();
  const yourBrand = radarData[0];
  const comp1 = radarData[1];
  const comp2 = radarData[2];
  
  const toArray = (m: typeof yourBrand.metrics) => [
    m.shareOfVoice, m.creativeDiversity, m.retailPenetration,
    m.frequencyIntensity, m.timeDominance, m.seasonality
  ];
  
  return {
    you: toArray(yourBrand.metrics).map((v, i) => v + Math.sin(i + seed) * 5),
    competitor1: toArray(comp1.metrics).map((v, i) => v + Math.cos(i + seed) * 5),
    competitor2: toArray(comp2.metrics).map((v, i) => v + Math.sin(i * 0.7 + seed) * 5),
  };
};

export default function CompetitiveRadarRing() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [data, setData] = useState(generateRadarData());
  const [rotation, setRotation] = useState(0);
  const [selectedMetric, setSelectedMetric] = useState<number | null>(null);
  const [polarityShift, setPolarityShift] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setRotation((r) => (r + 0.5) % 360);
    }, 50);
    return () => clearInterval(interval);
  }, []);

  // Update data based on polarity shift
  useEffect(() => {
    const newData = generateRadarData(polarityShift);
    setData(newData);
  }, [polarityShift]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.offsetWidth;
    const height = canvas.offsetHeight;
    canvas.width = width;
    canvas.height = height;

    const centerX = width / 2;
    const centerY = height / 2;
    const maxRadius = Math.min(width, height) / 2.5;
    const numMetrics = metrics.length;

    // Clear with subtle trail
    ctx.fillStyle = "rgba(15, 23, 42, 0.08)";
    ctx.fillRect(0, 0, width, height);

    // Draw concentric rings with labels
    ctx.fillStyle = "rgba(148, 163, 184, 0.5)";
    ctx.font = "10px Inter, sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";

    for (let i = 1; i <= 5; i++) {
      ctx.strokeStyle = `rgba(59, 130, 246, ${0.1 + i * 0.05})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(centerX, centerY, (maxRadius / 5) * i, 0, Math.PI * 2);
      ctx.stroke();

      // Ring labels
      ctx.fillStyle = "rgba(148, 163, 184, 0.6)";
      ctx.fillText(`${i * 20}`, centerX - (maxRadius / 5) * i - 8, centerY);
    }

    // Draw axes
    ctx.strokeStyle = "rgba(59, 130, 246, 0.15)";
    ctx.lineWidth = 1;
    for (let i = 0; i < numMetrics; i++) {
      const angle = (i / numMetrics) * Math.PI * 2 - Math.PI / 2;
      const x = centerX + Math.cos(angle) * maxRadius;
      const y = centerY + Math.sin(angle) * maxRadius;

      ctx.beginPath();
      ctx.moveTo(centerX, centerY);
      ctx.lineTo(x, y);
      ctx.stroke();
    }

    // Draw metric labels
    ctx.fillStyle = "rgba(148, 163, 184, 0.85)";
    ctx.font = "11px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    metrics.forEach((metric, i) => {
      const angle = (i / numMetrics) * Math.PI * 2 - Math.PI / 2;
      const x = centerX + Math.cos(angle) * (maxRadius + 35);
      const y = centerY + Math.sin(angle) * (maxRadius + 35);

      const isSelected = selectedMetric === i;
      ctx.fillStyle = isSelected ? "rgba(59, 130, 246, 1)" : "rgba(148, 163, 184, 0.8)";
      ctx.font = isSelected ? "bold 12px Inter, sans-serif" : "11px Inter, sans-serif";

      ctx.save();
      ctx.translate(x, y);
      ctx.fillText(metric, 0, 0);
      ctx.restore();
    });

    // Draw radar polygons with animations
    const drawRadar = (
      dataPoints: number[],
      color: string,
      label: string,
      alpha: number,
      isSelected: boolean = false
    ) => {
      const lineWidth = isSelected ? 3 : 2;
      const fillAlpha = isSelected ? alpha + 0.1 : alpha;

      ctx.fillStyle = `${color}${(fillAlpha * 255).toString(16).padStart(2, "0")}`;
      ctx.strokeStyle = color;
      ctx.lineWidth = lineWidth;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";

      ctx.beginPath();
      dataPoints.forEach((value, i) => {
        const angle = (i / numMetrics) * Math.PI * 2 - Math.PI / 2;
        const radius = (Math.min(value, 100) / 100) * maxRadius;
        const x = centerX + Math.cos(angle) * radius;
        const y = centerY + Math.sin(angle) * radius;

        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      });
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    };

    // Draw with glow effect on selected
    if (selectedMetric !== null) {
      ctx.globalAlpha = 0.15;
      drawRadar(data.you, "#3b82f6", "You", 0.35, true);
      ctx.globalAlpha = 1;
    }

    drawRadar(data.you, "#3b82f6", "You", 0.25, selectedMetric !== null);
    drawRadar(data.competitor1, "#ef4444", "Competitor 1", 0.18);
    drawRadar(data.competitor2, "#f59e0b", "Competitor 2", 0.12);

    // Draw animated sweep line
    const sweepAngle = (rotation * Math.PI) / 180 - Math.PI / 2;
    const sweepIntensity = 0.3 + Math.abs(Math.cos(sweepAngle)) * 0.4;

    ctx.strokeStyle = `rgba(139, 92, 246, ${sweepIntensity})`;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.lineTo(
      centerX + Math.cos(sweepAngle) * maxRadius,
      centerY + Math.sin(sweepAngle) * maxRadius
    );
    ctx.stroke();

    // Draw sweep glow
    ctx.strokeStyle = `rgba(139, 92, 246, ${sweepIntensity * 0.3})`;
    ctx.lineWidth = 8;
    ctx.stroke();

    // Draw legend with interactive regions
    const legendY = height - 45;
    const items = [
      { label: "You", color: "#3b82f6" },
      { label: "Competitor 1", color: "#ef4444" },
      { label: "Competitor 2", color: "#f59e0b" },
    ];

    let legendX = 30;
    items.forEach(({ label, color }) => {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(legendX, legendY, 5, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = "rgba(226, 232, 240, 0.85)";
      ctx.font = "11px Inter, sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText(label, legendX + 15, legendY);

      legendX += 150;
    });

  }, [data, rotation, selectedMetric]);

  const yourAvg = (data.you.reduce((a, b) => a + b) / data.you.length).toFixed(0);
  const comp1Avg = (data.competitor1.reduce((a, b) => a + b) / data.competitor1.length).toFixed(1);
  const comp2Avg = (data.competitor2.reduce((a, b) => a + b) / data.competitor2.length).toFixed(1);

  return (
    <div className="space-y-4">
      <canvas
        ref={canvasRef}
        className="w-full h-96 rounded-lg bg-gradient-to-br from-slate-700/50 to-slate-800/50 border border-slate-600/50 cursor-crosshair"
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const x = e.clientX - rect.left;
          const y = e.clientY - rect.top;
          const centerX = rect.width / 2;
          const centerY = rect.height / 2;
          const angle = Math.atan2(y - centerY, x - centerX) + Math.PI / 2;
          const normalizedAngle = ((angle + Math.PI * 2) % (Math.PI * 2)) / (Math.PI * 2);
          const metricIndex = Math.floor(normalizedAngle * metrics.length);
          setSelectedMetric(metricIndex < metrics.length ? metricIndex : null);
        }}
        onMouseLeave={() => setSelectedMetric(null)}
      />

      <div className="space-y-3">
        <div>
          <label className="text-sm font-semibold text-slate-300 block mb-2">
            Market Shift: {polarityShift}
          </label>
          <Slider
            value={[polarityShift]}
            onValueChange={([v]) => setPolarityShift(v)}
            min={-100}
            max={100}
            step={5}
            className="w-full"
          />
          <p className="text-xs text-slate-500 mt-1">Adjust competitive landscape (-100 to +100)</p>
        </div>

        {selectedMetric !== null && (
          <div className="p-3 bg-purple-900/20 border border-purple-600/30 rounded text-xs text-purple-300">
            <strong>{metrics[selectedMetric]}</strong><br />
            You: {data.you[selectedMetric].toFixed(1)} | Comp1: {data.competitor1[selectedMetric].toFixed(1)} | Comp2: {data.competitor2[selectedMetric].toFixed(1)}
          </div>
        )}
      </div>

      <div className="grid grid-cols-3 gap-4 text-sm">
        <div className="bg-slate-700/30 rounded p-3 border border-blue-600/30 hover:border-blue-500/50 transition">
          <div className="text-slate-400">Your Average</div>
          <div className="text-lg font-bold text-blue-400">{yourAvg}</div>
        </div>
        <div className="bg-slate-700/30 rounded p-3 border border-red-600/30 hover:border-red-500/50 transition">
          <div className="text-slate-400">Comp1 Average</div>
          <div className="text-lg font-bold text-red-400">{comp1Avg}</div>
        </div>
        <div className="bg-slate-700/30 rounded p-3 border border-amber-600/30 hover:border-amber-500/50 transition">
          <div className="text-slate-400">Comp2 Average</div>
          <div className="text-lg font-bold text-amber-400">{comp2Avg}</div>
        </div>
      </div>
    </div>
  );
}
