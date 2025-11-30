import { useState, useRef, useEffect } from "react";
import { Slider } from "@/components/ui/slider";

export default function InventoryCaptureFunnel() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [inventory, setInventory] = useState(100);
  const [competitors, setCompetitors] = useState(35);
  const [brand, setBrand] = useState(20);

  // Enforce constraints
  const maxCompetitors = Math.max(0, inventory * 0.85);
  const maxBrand = Math.max(0, inventory - competitors);
  const constrainedCompetitors = Math.min(competitors, maxCompetitors);
  const constrainedBrand = Math.min(brand, maxBrand);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.offsetWidth;
    const height = canvas.offsetHeight;
    canvas.width = width;
    canvas.height = height;

    const startY = 40;
    const endY = height - 40;
    const funnelHeight = endY - startY;
    const centerX = width / 2;

    // Calculate proportions
    const compProp = Math.min(constrainedCompetitors / inventory, 0.85);
    const brandProp = constrainedBrand > 0 ? Math.min(constrainedBrand / maxBrand, 1) : 0;

    // Funnel widths based on proportions
    const topWidth = 200;
    const bottomWidth = topWidth * 0.2;

    // Level 1: Total Inventory
    const level1Width = topWidth;
    const level1Top = startY;
    const level1Bottom = startY + funnelHeight * 0.25;

    ctx.fillStyle = "rgba(148, 163, 184, 0.15)";
    ctx.beginPath();
    ctx.moveTo(centerX - level1Width / 2, level1Top);
    ctx.lineTo(centerX + level1Width / 2, level1Top);
    ctx.lineTo(centerX + (level1Width - (level1Width - bottomWidth) * 0.25) / 2, level1Bottom);
    ctx.lineTo(centerX - (level1Width - (level1Width - bottomWidth) * 0.25) / 2, level1Bottom);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = "rgba(148, 163, 184, 0.5)";
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.fillStyle = "rgba(226, 232, 240, 0.95)";
    ctx.font = "bold 14px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Total Inventory", centerX, level1Top + 20);
    ctx.font = "bold 16px Inter, sans-serif";
    ctx.fillStyle = "rgba(226, 232, 240, 1)";
    ctx.fillText(inventory.toFixed(0), centerX, level1Top + 42);

    // Level 2: Competitor Activity
    const level2Width = topWidth - (topWidth - bottomWidth) * 0.25;
    const level2Top = level1Bottom;
    const level2Bottom = startY + funnelHeight * 0.55;
    const compAmount = constrainedCompetitors;

    ctx.fillStyle = `rgba(239, 68, 68, ${0.2 + compProp * 0.25})`;
    ctx.beginPath();
    ctx.moveTo(centerX - level1Width / 2, level1Bottom);
    ctx.lineTo(centerX + level1Width / 2, level1Bottom);
    ctx.lineTo(centerX + (level2Width - (level2Width - bottomWidth) * 0.25) / 2, level2Bottom);
    ctx.lineTo(centerX - (level2Width - (level2Width - bottomWidth) * 0.25) / 2, level2Bottom);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = `rgba(239, 68, 68, ${0.5 + compProp * 0.4})`;
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.fillStyle = "rgba(226, 232, 240, 0.95)";
    ctx.font = "bold 14px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Competitor Activity", centerX, level2Top + 18);
    ctx.font = "bold 14px Inter, sans-serif";
    ctx.fillStyle = "rgba(226, 232, 240, 0.85)";
    ctx.fillText(`${compAmount.toFixed(0)} (${(compProp * 100).toFixed(1)}%)`, centerX, level2Top + 42);

    // Level 3: Your Brand
    const level3Width = level2Width - (level2Width - bottomWidth) * 0.25;
    const level3Top = level2Bottom;
    const level3Bottom = endY;
    const brandAmount = constrainedBrand;

    ctx.fillStyle = `rgba(59, 130, 246, ${0.2 + brandProp * 0.35})`;
    ctx.beginPath();
    ctx.moveTo(centerX - level2Width / 2, level2Bottom);
    ctx.lineTo(centerX + level2Width / 2, level2Bottom);
    ctx.lineTo(centerX + level3Width / 2, level3Bottom);
    ctx.lineTo(centerX - level3Width / 2, level3Bottom);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = `rgba(59, 130, 246, ${0.6 + brandProp * 0.4})`;
    ctx.lineWidth = 2.5;
    ctx.stroke();

    ctx.fillStyle = "rgba(226, 232, 240, 0.95)";
    ctx.font = "bold 14px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Your Brand Capture", centerX, level3Top + 16);
    ctx.font = "bold 18px Inter, sans-serif";
    ctx.fillStyle = "rgba(59, 130, 246, 1)";
    ctx.fillText(brandAmount.toFixed(0), centerX, level3Top + 42);

  }, [inventory, constrainedCompetitors, constrainedBrand]);

  const remaining = Math.max(0, inventory - constrainedCompetitors - constrainedBrand);
  const marketShare = maxBrand > 0 ? ((constrainedBrand / maxBrand) * 100) : 0;
  const competitorPct = inventory > 0 ? ((constrainedCompetitors / inventory) * 100) : 0;

  return (
    <div className="space-y-6">
      <canvas
        ref={canvasRef}
        className="w-full h-80 rounded-lg bg-gradient-to-br from-slate-700/50 to-slate-800/50 border border-slate-600/50"
      />

      <div className="space-y-4">
        <div>
          <label className="text-sm font-semibold text-slate-300 block mb-3">
            Total Category Inventory: <span className="text-blue-400">{inventory.toFixed(0)}</span>
          </label>
          <Slider
            value={[inventory]}
            onValueChange={([v]) => setInventory(Math.max(50, v))}
            min={50}
            max={300}
            step={5}
            className="w-full"
          />
          <p className="text-xs text-slate-500 mt-2">Adjust total market size (50-300)</p>
        </div>

        <div>
          <label className="text-sm font-semibold text-slate-300 block mb-3">
            Competitor Activity: <span className="text-red-400">{constrainedCompetitors.toFixed(0)}</span> ({competitorPct.toFixed(1)}%)
          </label>
          <Slider
            value={[constrainedCompetitors]}
            onValueChange={([v]) => setCompetitors(v)}
            min={0}
            max={maxCompetitors}
            step={2}
            className="w-full"
          />
          <p className="text-xs text-slate-500 mt-2">Competitive pressure (can't exceed {maxCompetitors.toFixed(0)})</p>
        </div>

        <div>
          <label className="text-sm font-semibold text-slate-300 block mb-3">
            Your Brand Capture: <span className="text-blue-400">{constrainedBrand.toFixed(0)}</span>
          </label>
          <Slider
            value={[constrainedBrand]}
            onValueChange={([v]) => setBrand(v)}
            min={0}
            max={maxBrand}
            step={2}
            className="w-full"
          />
          <p className="text-xs text-slate-500 mt-2">Your market share (remaining capacity: {remaining.toFixed(0)})</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="bg-slate-700/30 rounded p-4 border border-slate-600/50 hover:border-slate-500/50 transition">
          <div className="text-xs text-slate-400 mb-1">Uncaptured</div>
          <div className="text-2xl font-bold text-slate-300">{remaining.toFixed(0)}</div>
          <div className="text-xs text-slate-500 mt-1">{remaining > 0 ? ((remaining / inventory) * 100).toFixed(1) : "0"}% available</div>
        </div>
        <div className="bg-slate-700/30 rounded p-4 border border-blue-600/30 hover:border-blue-500/50 transition">
          <div className="text-xs text-slate-400 mb-1">Your Market Share</div>
          <div className="text-2xl font-bold text-blue-400">{marketShare.toFixed(1)}%</div>
          <div className="text-xs text-slate-500 mt-1">of available inventory</div>
        </div>
        <div className="bg-slate-700/30 rounded p-4 border border-red-600/30 hover:border-red-500/50 transition">
          <div className="text-xs text-slate-400 mb-1">Competition Intensity</div>
          <div className="text-2xl font-bold text-red-400">{competitorPct.toFixed(1)}%</div>
          <div className="text-xs text-slate-500 mt-1">market saturation</div>
        </div>
      </div>
    </div>
  );
}
