import { useEffect, useRef, useState, useMemo } from "react";
import { Slider } from "@/components/ui/slider";
import { generateSupplyChainData } from "@/lib/experiment-data";

interface FlowNode {
  id: string;
  layer: number;
  value: string;
  size: number;
  count: number;
}

interface FlowConnection {
  from: string;
  to: string;
  value: number;
  layer: number;
}

const generateFlowData = () => {
  const { nodes, connections } = generateSupplyChainData();
  
  const flowNodes: FlowNode[] = nodes.map((n) => ({
    id: n.id,
    layer: n.layer,
    value: n.value,
    size: 30 + n.count / 3,
    count: n.count,
  }));

  return { nodes: flowNodes, connections };
};

export default function AdSupplyChainMap() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [flowData] = useState(generateFlowData());
  const { nodes, connections } = flowData;
  const [animationTime, setAnimationTime] = useState(0);
  const [flowSpeed, setFlowSpeed] = useState(50);

  useEffect(() => {
    const interval = setInterval(() => {
      setAnimationTime((t) => (t + (flowSpeed / 50)) % 100);
    }, 30);
    return () => clearInterval(interval);
  }, [flowSpeed]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.offsetWidth;
    const height = canvas.offsetHeight;
    canvas.width = width;
    canvas.height = height;

    // Group nodes by layer
    const layers = [[], [], [], []] as FlowNode[][];
    nodes.forEach((node) => {
      layers[node.layer].push(node);
    });

    // Calculate positions
    const layerX = [
      width * 0.1,
      width * 0.35,
      width * 0.65,
      width * 0.9,
    ];

    const nodePositions: Record<string, { x: number; y: number }> = {};

    layers.forEach((layer, layerIdx) => {
      const x = layerX[layerIdx];
      const spacing = height / (layer.length + 1);

      layer.forEach((node, nodeIdx) => {
        nodePositions[node.id] = {
          x,
          y: spacing * (nodeIdx + 1),
        };
      });
    });

    // Draw flow lines using actual connections data
    connections.forEach((conn, idx) => {
      const from = nodePositions[conn.from];
      const to = nodePositions[conn.to];
      if (!from || !to) return;

      const flowProgress = (animationTime + (idx % 20) * 5) % 100 / 100;

      ctx.strokeStyle = `rgba(59, 130, 246, ${0.3 + flowProgress * 0.3})`;
      ctx.lineWidth = 1.5;

      // Draw Bezier curve
      const cpX = (from.x + to.x) / 2;
      const cpY = (from.y + to.y) / 2;

      ctx.beginPath();
      ctx.moveTo(from.x + 30, from.y);
      ctx.quadraticCurveTo(cpX, cpY, to.x - 20, to.y);
      ctx.stroke();

      // Draw flow particle
      const particleProgress = (animationTime / 100 + (idx % 20) * 0.05) % 1;
      const particleX = from.x + 30 + (to.x - from.x - 50) * particleProgress;
      const particleY = from.y + (to.y - from.y) * particleProgress;

      ctx.fillStyle = `rgba(139, 92, 246, ${0.6 - flowProgress * 0.2})`;
      ctx.beginPath();
      ctx.arc(particleX, particleY, 3, 0, Math.PI * 2);
      ctx.fill();
    });

    // Draw nodes
    nodes.forEach((node) => {
      const pos = nodePositions[node.id];

      // Draw glow
      const gradient = ctx.createRadialGradient(pos.x, pos.y, 0, pos.x, pos.y, node.size + 10);
      gradient.addColorStop(0, `rgba(59, 130, 246, 0.3)`);
      gradient.addColorStop(1, `rgba(59, 130, 246, 0)`);
      ctx.fillStyle = gradient;
      ctx.fillRect(pos.x - node.size - 10, pos.y - node.size - 10, (node.size + 10) * 2, (node.size + 10) * 2);

      // Draw node
      const gradient2 = ctx.createRadialGradient(pos.x, pos.y, 0, pos.x, pos.y, node.size);
      gradient2.addColorStop(0, node.layer % 2 === 0 ? "rgba(59, 130, 246, 0.8)" : "rgba(139, 92, 246, 0.8)");
      gradient2.addColorStop(1, node.layer % 2 === 0 ? "rgba(59, 130, 246, 0.4)" : "rgba(139, 92, 246, 0.4)");

      ctx.fillStyle = gradient2;
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, node.size, 0, Math.PI * 2);
      ctx.fill();

      ctx.strokeStyle = "rgba(255, 255, 255, 0.6)";
      ctx.lineWidth = 2;
      ctx.stroke();

      // Draw label
      ctx.fillStyle = "rgba(226, 232, 240, 0.95)";
      ctx.font = "11px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(node.value, pos.x, pos.y);
    });

    // Draw layer labels
    const layerLabels = ["Retailers", "Placements", "Ad Types", "Brands"];
    ctx.fillStyle = "rgba(148, 163, 184, 0.7)";
    ctx.font = "bold 12px Inter, sans-serif";
    ctx.textAlign = "center";

    layerLabels.forEach((label, idx) => {
      ctx.fillText(label, layerX[idx], 30);
    });

  }, [nodes, connections, animationTime]);

  return (
    <div className="space-y-4">
      <canvas
        ref={canvasRef}
        className="w-full h-96 rounded-lg bg-gradient-to-br from-slate-700/50 to-slate-800/50 border border-slate-600/50"
      />
      <div className="space-y-3 mb-4">
        <label className="text-sm font-semibold text-slate-300 block">Flow Speed: {flowSpeed}</label>
        <Slider
          value={[flowSpeed]}
          onValueChange={([v]) => setFlowSpeed(v)}
          min={10}
          max={100}
          step={5}
          className="w-full"
        />
      </div>

      <div className="grid grid-cols-4 gap-4 text-sm">
        <div className="bg-slate-700/30 rounded p-3 border border-slate-600/50">
          <div className="text-slate-400">Retailers</div>
          <div className="text-lg font-bold text-slate-200">{nodes.filter(n => n.layer === 0).length}</div>
        </div>
        <div className="bg-slate-700/30 rounded p-3 border border-slate-600/50">
          <div className="text-slate-400">Placements</div>
          <div className="text-lg font-bold text-slate-200">{nodes.filter(n => n.layer === 1).length}</div>
        </div>
        <div className="bg-slate-700/30 rounded p-3 border border-slate-600/50">
          <div className="text-slate-400">Ad Types</div>
          <div className="text-lg font-bold text-slate-200">{nodes.filter(n => n.layer === 2).length}</div>
        </div>
        <div className="bg-slate-700/30 rounded p-3 border border-slate-600/50">
          <div className="text-slate-400">Brands</div>
          <div className="text-lg font-bold text-slate-200">{nodes.filter(n => n.layer === 3).length}</div>
        </div>
      </div>
      <div className="text-xs text-slate-500">
        Animated flows show the path from retailer through placement, keyword, to creative.
      </div>
    </div>
  );
}
