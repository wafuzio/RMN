import { useEffect, useRef, useState, useMemo } from "react";
import { motion } from "framer-motion";
import { Slider } from "@/components/ui/slider";
import { RETAILERS, generateSOVData } from "@/lib/experiment-data";

interface Orbiter {
  name: string;
  sov: number;
  angle: number;
  speed: number;
  radius: number;
  adCount: number;
  trend: "up" | "down" | "stable";
}

const generateOrbiters = (distributeEvenly: boolean = false): Orbiter[] => {
  const sovData = generateSOVData();

  if (distributeEvenly) {
    const equal = 100 / RETAILERS.length;
    return sovData.map((data, i) => ({
      name: data.retailer,
      sov: equal / 100,
      angle: (i / RETAILERS.length) * Math.PI * 2,
      speed: 0.008 + Math.random() * 0.005,
      radius: 50 + i * 20,
      adCount: data.adCount,
      trend: data.trend,
    }));
  }

  return sovData.map((data, i) => ({
    name: data.retailer,
    sov: data.sov / 100,
    angle: (i / RETAILERS.length) * Math.PI * 2,
    speed: 0.01 + Math.random() * 0.01,
    radius: 60 + i * 25,
    adCount: data.adCount,
    trend: data.trend,
  }));
};

export default function ShareOfVoiceOrbitals() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [orbiters, setOrbiters] = useState(generateOrbiters());
  const [time, setTime] = useState(0);
  const [selectedRetailer, setSelectedRetailer] = useState<string | null>(null);
  const [distributeEvenly, setDistributeEvenly] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      setTime((t) => t + 1);
      setOrbiters((prev) =>
        prev.map((o) => ({
          ...o,
          angle: (o.angle + o.speed) % (Math.PI * 2),
          // Dynamic SOV based on time (simulate growth/decline)
          sov: Math.max(
            0.05,
            o.sov + Math.sin(time / 100 + o.angle) * 0.002
          ),
        }))
      );
    }, 30);

    return () => clearInterval(interval);
  }, [time]);

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
    const scale = Math.min(width, height) / 400;

    // Clear with subtle fade trail
    ctx.fillStyle = "rgba(15, 23, 42, 0.15)";
    ctx.fillRect(0, 0, width, height);

    // Draw orbital rings
    ctx.strokeStyle = "rgba(59, 130, 246, 0.08)";
    ctx.lineWidth = 1;
    orbiters.forEach((o) => {
      ctx.beginPath();
      ctx.arc(centerX, centerY, o.radius * scale, 0, Math.PI * 2);
      ctx.stroke();
    });

    // Draw center (brand) with pulsing effect
    const centerSize = 15 + Math.sin(time / 20) * 3;
    const centerGradient = ctx.createRadialGradient(
      centerX,
      centerY,
      0,
      centerX,
      centerY,
      centerSize + 5
    );
    centerGradient.addColorStop(0, `rgba(236, 72, 153, ${0.9 + Math.sin(time / 30) * 0.1})`);
    centerGradient.addColorStop(1, `rgba(236, 72, 153, 0.1)`);
    ctx.fillStyle = centerGradient;
    ctx.beginPath();
    ctx.arc(centerX, centerY, centerSize, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = "#ec4899";
    ctx.font = "bold 10px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("YOUR BRAND", centerX, centerY - 2);

    // Draw orbiters with enhanced visuals
    orbiters.forEach((o, idx) => {
      const x = centerX + Math.cos(o.angle) * o.radius * scale;
      const y = centerY + Math.sin(o.angle) * o.radius * scale;
      const size = 8 + o.sov * 25;
      const isSelected = selectedRetailer === o.name;

      // Draw comet tail
      ctx.strokeStyle = `rgba(59, 130, 246, ${(0.3 * o.sov * (isSelected ? 2 : 1))})`;
      ctx.lineWidth = 2 + (isSelected ? 1.5 : 0);
      const tailLength = 35 + Math.sin(time / 15 + idx) * 10;
      ctx.beginPath();
      ctx.moveTo(x, y);
      const tailX = x - Math.cos(o.angle) * tailLength;
      const tailY = y - Math.sin(o.angle) * tailLength;
      ctx.lineTo(tailX, tailY);
      ctx.stroke();

      // Draw pulse rings for selected
      if (isSelected) {
        ctx.strokeStyle = "rgba(59, 130, 246, 0.4)";
        ctx.lineWidth = 1;
        for (let r = 1; r <= 3; r++) {
          const pulseSize = size + r * 5 + Math.sin(time / 10) * 3;
          ctx.beginPath();
          ctx.arc(x, y, pulseSize, 0, Math.PI * 2);
          ctx.stroke();
        }
      }

      // Draw node
      const gradient = ctx.createRadialGradient(x, y, 0, x, y, size);
      gradient.addColorStop(
        0,
        `rgba(59, 130, 246, ${isSelected ? 1 : 0.85 + o.sov * 0.15})`
      );
      gradient.addColorStop(
        1,
        `rgba(59, 130, 246, ${isSelected ? 0.5 : 0.15 + o.sov * 0.15})`
      );
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(x, y, size, 0, Math.PI * 2);
      ctx.fill();

      // Node border (brighter if selected)
      ctx.strokeStyle = `rgba(255, 255, 255, ${isSelected ? 1 : 0.6})`;
      ctx.lineWidth = isSelected ? 2.5 : 2;
      ctx.stroke();

      // Label
      ctx.fillStyle = `rgba(226, 232, 240, ${isSelected ? 1 : 0.9})`;
      ctx.font = `${isSelected ? "bold" : ""} 11px Inter, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(o.name, x, y);

      // SOV label with dynamic color
      const sovColor = o.sov > 0.3 ? "rgba(34, 197, 94, 0.9)" : "rgba(148, 163, 184, 0.8)";
      ctx.fillStyle = sovColor;
      ctx.font = "bold 10px Inter, sans-serif";
      ctx.fillText(`${(o.sov * 100).toFixed(1)}%`, x, y + size + 14);
    });

    // Draw legend
    ctx.fillStyle = "rgba(148, 163, 184, 0.6)";
    ctx.font = "10px Inter, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText("Click orbiter names to highlight", 10, height - 10);

  }, [orbiters, selectedRetailer, time]);

  const totalSOV = orbiters.reduce((sum, o) => sum + o.sov, 0);
  const dominant = orbiters.reduce((max, o) => (o.sov > max.sov ? o : max));

  return (
    <div className="space-y-4">
      <canvas
        ref={canvasRef}
        className="w-full h-96 rounded-lg bg-gradient-to-br from-slate-700/50 to-slate-800/50 border border-slate-600/50 cursor-pointer"
      />

      <div className="space-y-3">
        <div className="flex gap-2 flex-wrap">
          {orbiters.map((o) => (
            <motion.button
              key={o.name}
              onClick={() => setSelectedRetailer(selectedRetailer === o.name ? null : o.name)}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className={`px-3 py-2 rounded text-sm font-medium transition-all ${
                selectedRetailer === o.name
                  ? "bg-blue-600 text-white"
                  : "bg-slate-700/50 text-slate-300 hover:bg-slate-700"
              }`}
            >
              {o.name} {`(${(o.sov * 100).toFixed(1)}%)`}
            </motion.button>
          ))}
        </div>

        <button
          onClick={() => setDistributeEvenly(!distributeEvenly)}
          className="w-full px-4 py-2 rounded bg-slate-700/50 text-slate-300 hover:bg-slate-700 transition text-sm"
        >
          {distributeEvenly ? "Reset to Natural Distribution" : "Distribute Evenly"}
        </button>

        {distributeEvenly && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="p-3 bg-blue-900/20 border border-blue-600/30 rounded text-xs text-blue-300"
          >
            Equal SOV distribution applied. Click retailers to see individual metrics.
          </motion.div>
        )}
      </div>

      <div className="grid grid-cols-3 gap-4 text-sm">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-slate-700/30 rounded p-3 border border-slate-600/50"
        >
          <div className="text-slate-400">Total SOV</div>
          <div className="text-lg font-bold text-slate-200">{(totalSOV * 100).toFixed(1)}%</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-slate-700/30 rounded p-3 border border-slate-600/50"
        >
          <div className="text-slate-400">Dominant</div>
          <div className="text-lg font-bold text-blue-400">{dominant.name}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-slate-700/30 rounded p-3 border border-slate-600/50"
        >
          <div className="text-slate-400">Retailers</div>
          <div className="text-lg font-bold text-emerald-400">{orbiters.length}</div>
        </motion.div>
      </div>
    </div>
  );
}
