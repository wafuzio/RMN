import { useEffect, useRef, useState, useMemo } from "react";
import { Slider } from "@/components/ui/slider";
import { BRANDS, RETAILERS, generateBrandRetailerConnections } from "@/lib/experiment-data";

interface Node {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  type: "brand" | "retailer";
  radius: number;
  label: string;
}

interface Edge {
  source: string;
  target: string;
  frequency: number;
  startTime: number;
  endTime: number;
  adTypes: string[];
}

const generateBrandRetailerData = () => {
  // Use real brands and retailers from scraper data
  const brands = [...BRANDS];
  const retailers = [...RETAILERS];

  // Create left-aligned brand nodes
  const nodes: Node[] = [
    ...brands.map((b, i) => ({
      id: `brand:${b}`,
      x: -200,
      y: (i - brands.length / 2) * 40 + 20,
      vx: 0,
      vy: 0,
      type: "brand" as const,
      radius: 7,
      label: b,
    })),
    // Create right-aligned retailer nodes
    ...retailers.map((r, i) => ({
      id: `retailer:${r}`,
      x: 200,
      y: (i - retailers.length / 2) * 50 + 30,
      vx: 0,
      vy: 0,
      type: "retailer" as const,
      radius: 9,
      label: r,
    })),
  ];

  // Use real connection data
  const connections = generateBrandRetailerConnections();
  const edges: Edge[] = connections.map((conn) => ({
    source: `brand:${conn.brand}`,
    target: `retailer:${conn.retailer}`,
    frequency: conn.frequency,
    startTime: conn.startDay,
    endTime: conn.endDay,
    adTypes: conn.adTypes,
  }));

  return { nodes, edges };
};

export default function ConstellationMap() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [time, setTime] = useState(50);
  const { nodes: initialNodes, edges } = useMemo(() => generateBrandRetailerData(), []);
  const nodesRef = useRef<Node[]>(initialNodes.map((n) => ({ ...n })));

  const alphaDecay = 0.02;
  const velocityDecay = 0.4;
  const chargeStrength = -150;
  const linkDistance = 120;

  // Filter edges based on current time
  const visibleEdges = useMemo(
    () => edges.filter((e) => time >= e.startTime && time <= e.endTime),
    [time, edges]
  );

  const activeBrands = useMemo(
    () => new Set(visibleEdges.map((e) => e.source)).size,
    [visibleEdges]
  );

  const activeRetailers = useMemo(
    () => new Set(visibleEdges.map((e) => e.target)).size,
    [visibleEdges]
  );

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

    const animate = () => {
      const nodes = nodesRef.current;

      // Apply charge force (repulsion)
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[j].x - nodes[i].x;
          const dy = nodes[j].y - nodes[i].y;
          const dist = Math.hypot(dx, dy) || 1;
          const force = (chargeStrength / (dist * dist)) * 0.008;
          nodes[i].vx -= (force * dx) / dist;
          nodes[i].vy -= (force * dy) / dist;
          nodes[j].vx += (force * dx) / dist;
          nodes[j].vy += (force * dy) / dist;
        }
      }

      // Apply link forces based on visible edges
      visibleEdges.forEach((edge) => {
        const source = nodes.find((n) => n.id === edge.source)!;
        const target = nodes.find((n) => n.id === edge.target)!;

        const dx = target.x - source.x;
        const dy = target.y - source.y;
        const dist = Math.hypot(dx, dy) || 1;

        // Frequency affects link strength
        const freqStrength = (edge.frequency / 100) * 0.15;
        const force = ((dist - linkDistance) / dist) * freqStrength;

        source.vx += (force * dx) / dist;
        source.vy += (force * dy) / dist;
        target.vx -= (force * dx) / dist;
        target.vy -= (force * dy) / dist;
      });

      // Apply velocity decay and lane constraints
      nodes.forEach((node) => {
        node.vx *= velocityDecay;
        node.vy *= velocityDecay;

        // Keep brands on left, retailers on right
        if (node.type === "brand") {
          const targetX = -200;
          node.vx += (targetX - node.x) * 0.01;
        } else {
          const targetX = 200;
          node.vx += (targetX - node.x) * 0.01;
        }

        // Slight vertical damping
        node.vy *= 0.95;

        node.x += node.vx;
        node.y += node.vy;

        // Boundary constraints
        node.y = Math.max(-200, Math.min(200, node.y));
      });

      // Render
      ctx.clearRect(0, 0, width, height);

      // Draw edges
      visibleEdges.forEach((edge) => {
        const source = nodes.find((n) => n.id === edge.source)!;
        const target = nodes.find((n) => n.id === edge.target)!;

        const x1 = centerX + source.x;
        const y1 = centerY + source.y;
        const x2 = centerX + target.x;
        const y2 = centerY + target.y;

        const freqNorm = edge.frequency / 100;
        const opacity = Math.min(0.7, freqNorm * 0.8);
        const lineWidth = 1 + freqNorm * 3;

        // Draw glow
        ctx.strokeStyle = `rgba(59, 130, 246, ${opacity * 0.3})`;
        ctx.lineWidth = lineWidth + 4;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();

        // Draw main line
        ctx.strokeStyle = `rgba(59, 130, 246, ${opacity})`;
        ctx.lineWidth = lineWidth;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      });

      // Draw nodes
      nodes.forEach((node) => {
        const x = centerX + node.x;
        const y = centerY + node.y;

        // Determine if this node has active connections
        const hasActiveConnection =
          node.type === "brand"
            ? visibleEdges.some((e) => e.source === node.id)
            : visibleEdges.some((e) => e.target === node.id);

        const alpha = hasActiveConnection ? 1 : 0.4;

        // Draw glow
        const gradient = ctx.createRadialGradient(x, y, 0, x, y, node.radius * 3);
        if (node.type === "brand") {
          gradient.addColorStop(0, `rgba(139, 92, 246, ${0.3 * alpha})`);
          gradient.addColorStop(1, `rgba(139, 92, 246, 0)`);
        } else {
          gradient.addColorStop(0, `rgba(59, 130, 246, ${0.3 * alpha})`);
          gradient.addColorStop(1, `rgba(59, 130, 246, 0)`);
        }
        ctx.fillStyle = gradient;
        ctx.fillRect(x - node.radius * 3, y - node.radius * 3, node.radius * 6, node.radius * 6);

        // Draw node
        ctx.beginPath();
        ctx.arc(x, y, node.radius, 0, Math.PI * 2);
        ctx.fillStyle = node.type === "brand" ? `rgba(139, 92, 246, ${alpha})` : `rgba(59, 130, 246, ${alpha})`;
        ctx.fill();
        ctx.strokeStyle = `rgba(255, 255, 255, ${0.8 * alpha})`;
        ctx.lineWidth = 2;
        ctx.stroke();

        // Draw label
        ctx.fillStyle = `rgba(226, 232, 240, ${alpha})`;
        ctx.font = "10px Inter, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(node.label, x, y);
      });

      requestAnimationFrame(animate);
    };

    animate();
  }, [visibleEdges]);

  return (
    <div className="space-y-4">
      <canvas
        ref={canvasRef}
        className="w-full h-96 rounded-lg bg-gradient-to-br from-slate-700/50 to-slate-800/50 border border-slate-600/50"
      />

      <div className="space-y-2">
        <label className="text-sm font-semibold text-slate-300">
          Timeline: {time}% — {visibleEdges.length} active connections
        </label>
        <Slider
          value={[time]}
          onValueChange={([v]) => setTime(v)}
          min={0}
          max={100}
          step={1}
          className="w-full"
        />
        <p className="text-xs text-slate-500">
          Purple (left) = Brands | Blue (right) = Retailers | Thicker edges = Higher ad activity
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4 text-sm">
        <div className="bg-slate-700/30 rounded p-3 border border-slate-600/50">
          <div className="text-slate-400">Active Brands</div>
          <div className="text-lg font-bold text-purple-400">{activeBrands}</div>
        </div>
        <div className="bg-slate-700/30 rounded p-3 border border-slate-600/50">
          <div className="text-slate-400">Active Retailers</div>
          <div className="text-lg font-bold text-blue-400">{activeRetailers}</div>
        </div>
        <div className="bg-slate-700/30 rounded p-3 border border-slate-600/50">
          <div className="text-slate-400">Active Edges</div>
          <div className="text-lg font-bold text-emerald-400">{visibleEdges.length}</div>
        </div>
      </div>

      <div className="text-xs text-slate-500 bg-slate-700/20 rounded p-3 border border-slate-600/30">
        <strong>What you're seeing:</strong> Each line represents a brand's advertising activity at a retailer. Thicker lines = more ads running.
        Scrub through time to see when brands ramp up or scale back their presence across channels.
      </div>
    </div>
  );
}
