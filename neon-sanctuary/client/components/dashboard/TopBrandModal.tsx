import { useState, useEffect, useRef, useCallback } from "react";
import { isAdTypeNotBrand } from "@/lib/brand-utils";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PieChart, Pie, Cell, Tooltip } from "recharts";
import type { Retailer } from "@/lib/api";

interface BrandSovEntry {
  brand: string;
  count: number;
  percentage: number;
  retailers?: { [retailer: string]: number };
}

interface FilterParams {
  retailers?: Retailer[];
  clients?: string[];
  dateRange?: { start?: Date; end?: Date };
  adTypes?: string[];
  keywords?: string[];
}

interface TopBrandModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  topBrands: BrandSovEntry[];
  onRetailerClick?: (brand: string) => void;
  filterParams?: FilterParams;
}

function BrandLogoImage({ brandName, size = 64 }: { brandName: string; size?: number }) {
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
    setLogoUrl(null);

    if (!brandName || isAdTypeNotBrand(brandName)) {
      setFailed(true);
      return;
    }

    const fetchLogo = async () => {
      try {
        const response = await fetch(`/api/logo/brand/${encodeURIComponent(brandName)}`);
        if (response.ok) {
          const blob = await response.blob();
          const url = URL.createObjectURL(blob);
          setLogoUrl(url);
        } else {
          setFailed(true);
        }
      } catch (error) {
        console.error("Failed to fetch brand logo:", error);
        setFailed(true);
      }
    };

    fetchLogo();

    return () => {
      if (logoUrl) {
        URL.revokeObjectURL(logoUrl);
      }
    };
  }, [brandName]);

  const sizeStyle = { width: `${size}px`, height: `${size}px` };
  const textSizeClass = size <= 44 ? "text-xs" : size <= 56 ? "text-base" : "text-lg";

  if (logoUrl) {
    return (
      <img
        src={logoUrl}
        alt={`${brandName} logo`}
        className="object-contain flex-shrink-0"
        style={sizeStyle}
        onError={() => setFailed(true)}
      />
    );
  }

  if (failed) {
    const initials = brandName
      .split(/\s+/)
      .slice(0, 2)
      .map(word => word[0]?.toUpperCase())
      .join("");

    const colors = [
      "bg-blue-500",
      "bg-purple-500",
      "bg-pink-500",
      "bg-indigo-500",
      "bg-cyan-500",
      "bg-teal-500",
      "bg-emerald-500",
      "bg-orange-500",
    ];

    const colorIndex = brandName.charCodeAt(0) % colors.length;
    const bgColor = colors[colorIndex];

    return (
      <div
        className={`rounded flex items-center justify-center ${bgColor} text-white ${textSizeClass} font-semibold flex-shrink-0`}
        style={sizeStyle}
        title={brandName}
      >
        {initials || "?"}
      </div>
    );
  }

  return null;
}

// Title-case a brand name: "hello_world" → "Hello World", "proactiv" → "Proactiv"
function capitalizeBrand(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// Helper: SVG arc path for a pie slice
function describeArc(cx: number, cy: number, r: number, startDeg: number, endDeg: number): string {
  const startRad = (startDeg * Math.PI) / 180;
  const endRad = (endDeg * Math.PI) / 180;
  const x1 = cx + r * Math.cos(startRad);
  const y1 = cy - r * Math.sin(startRad);
  const x2 = cx + r * Math.cos(endRad);
  const y2 = cy - r * Math.sin(endRad);
  const sweep = startDeg - endDeg;
  const largeArc = sweep > 180 ? 1 : 0;
  // SVG arc: sweep-flag=1 means clockwise in SVG coords (which is CW visually)
  return `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`;
}

// Fetch an image URL and return a base64 data URI
async function imageToBase64(url: string): Promise<string | null> {
  try {
    const resp = await fetch(url);
    if (!resp.ok) return null;
    const blob = await resp.blob();
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result as string);
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(blob);
    });
  } catch {
    return null;
  }
}

interface ExportFilterParams {
  retailers?: string[];
  clients?: string[];
  dateRange?: { start?: Date; end?: Date };
  adTypes?: string[];
  keywords?: string[];
}

function buildParamsSvg(filterParams?: ExportFilterParams): string {
  const W = 320;
  const lineH = 22;
  const padX = 20;
  let y = 24;

  const formatDate = (d?: Date) => {
    if (!d) return "N/A";
    return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  };

  const rows: { label: string; value: string }[] = [
    {
      label: "Date",
      value: filterParams?.dateRange
        ? `${formatDate(filterParams.dateRange.start)} - ${formatDate(filterParams.dateRange.end)}`
        : "All time",
    },
    { label: "Retailers", value: filterParams?.retailers?.length ? filterParams.retailers.map(r => capitalizeBrand(String(r))).join(", ") : "All" },
    { label: "Keywords", value: filterParams?.keywords?.length ? filterParams.keywords.join(", ") : "All" },
    { label: "Ad Types", value: filterParams?.adTypes?.length ? filterParams.adTypes.join(", ") : "All" },
    { label: "Clients", value: filterParams?.clients?.length ? filterParams.clients.join(", ") : "All" },
  ];

  // Estimate height
  const H = 20 + rows.length * (lineH * 2 + 8) + 10;

  const parts: string[] = [];
  parts.push(`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">`);
  parts.push(`<rect width="${W}" height="${H}" rx="8" fill="#f9fafb" stroke="#e5e7eb" stroke-width="1"/>`);
  parts.push(`<text x="${padX}" y="${y}" font-size="13" font-weight="700" fill="#111827" font-family="Inter, system-ui, sans-serif">Parameters</text>`);
  y += 8;

  for (const row of rows) {
    y += lineH;
    parts.push(`<text x="${padX}" y="${y}" font-size="10" font-weight="600" fill="#6b7280" font-family="Inter, system-ui, sans-serif" text-transform="uppercase" letter-spacing="0.05em">${row.label.toUpperCase()}</text>`);
    y += lineH - 4;
    // Truncate long values
    const val = row.value.length > 45 ? row.value.slice(0, 42) + "..." : row.value;
    parts.push(`<text x="${padX}" y="${y}" font-size="12" font-weight="500" fill="#111827" font-family="Inter, system-ui, sans-serif">${val}</text>`);
    y += 8;
  }

  parts.push(`</svg>`);
  return parts.join("\n");
}

function svgToPngBlob(svgStr: string, w: number, h: number, scale = 2): Promise<Blob | null> {
  return new Promise((resolve) => {
    const blob = new Blob([svgStr], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = w * scale;
      canvas.height = h * scale;
      const ctx = canvas.getContext("2d")!;
      ctx.scale(scale, scale);
      ctx.drawImage(img, 0, 0, w, h);
      URL.revokeObjectURL(url);
      canvas.toBlob((b) => resolve(b), "image/png");
    };
    img.onerror = () => { URL.revokeObjectURL(url); resolve(null); };
    img.src = url;
  });
}

interface ExportChartParams {
  chartData: { name: string; value: number; percentage: number }[];
  pieCx: number;
  pieCy: number;
  pieR: number;
  startAngle: number;
  totalVal: number;
  sliceMidAngles: number[];
  labelLayout: ({ logoX: number; logoY: number; pieEdgeX: number; pieEdgeY: number } | undefined)[];
  allOthersIdx: number;
  allOthersPos: { x: number; y: number } | null;
  W: number;
  H: number;
  LOGO_SIZE: number;
}

async function buildExportSvg(params: ExportChartParams): Promise<string> {
  const { chartData, pieCx, pieCy, pieR, startAngle, totalVal, sliceMidAngles,
    labelLayout, allOthersIdx, allOthersPos, W, H, LOGO_SIZE } = params;

  const parts: string[] = [];
  parts.push(`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">`);
  parts.push(`<rect width="${W}" height="${H}" fill="white"/>`);

  // Draw pie slices
  let cumFrac = 0;
  for (let i = 0; i < chartData.length; i++) {
    const frac = totalVal > 0 ? chartData[i].value / totalVal : 0;
    const sliceStart = startAngle - cumFrac * 360;
    const sliceEnd = startAngle - (cumFrac + frac) * 360;
    cumFrac += frac;
    const color = chartData[i].name === "All Others" ? "#d1d5db" : CHART_COLORS[i % CHART_COLORS.length];
    const d = describeArc(pieCx, pieCy, pieR, sliceStart, sliceEnd);
    parts.push(`<path d="${d}" fill="${color}" stroke="white" stroke-width="1"/>`);
  }

  // "All Others" label inside pie
  if (allOthersPos && allOthersIdx >= 0) {
    parts.push(`<text x="${allOthersPos.x}" y="${allOthersPos.y - 6}" text-anchor="middle" dominant-baseline="middle" fill="#4b5563" font-size="14" font-weight="700" font-family="Inter, system-ui, sans-serif">6+</text>`);
    parts.push(`<text x="${allOthersPos.x}" y="${allOthersPos.y + 10}" text-anchor="middle" dominant-baseline="middle" fill="#6b7280" font-size="11" font-weight="600" font-family="Inter, system-ui, sans-serif">${chartData[allOthersIdx].percentage}%</text>`);
  }

  // Connector lines
  for (let idx = 0; idx < chartData.length; idx++) {
    if (chartData[idx].name === "All Others") continue;
    const pos = labelLayout[idx];
    if (!pos) continue;
    const color = CHART_COLORS[idx % CHART_COLORS.length];
    const elbowX = pos.logoX + LOGO_SIZE / 2 + 6;
    parts.push(`<line x1="${pos.logoX + LOGO_SIZE / 2 + 2}" y1="${pos.logoY}" x2="${elbowX}" y2="${pos.logoY}" stroke="${color}" stroke-width="2" opacity="0.5"/>`);
    parts.push(`<line x1="${elbowX}" y1="${pos.logoY}" x2="${pos.pieEdgeX}" y2="${pos.pieEdgeY}" stroke="${color}" stroke-width="2" opacity="0.5"/>`);
    parts.push(`<circle cx="${pos.pieEdgeX}" cy="${pos.pieEdgeY}" r="3" fill="${color}" opacity="0.7"/>`);
  }

  // Logo images + labels
  for (let idx = 0; idx < chartData.length; idx++) {
    if (chartData[idx].name === "All Others") continue;
    const pos = labelLayout[idx];
    if (!pos) continue;
    const color = CHART_COLORS[idx % CHART_COLORS.length];
    const lx = pos.logoX - LOGO_SIZE / 2;
    const ly = pos.logoY - LOGO_SIZE / 2;

    // Logo box background + border
    parts.push(`<rect x="${lx}" y="${ly}" width="${LOGO_SIZE}" height="${LOGO_SIZE}" rx="8" fill="white" stroke="${color}" stroke-width="3"/>`);

    // Try to embed logo image
    const brandName = chartData[idx].name;
    const logoDataUri = await imageToBase64(`/api/logo/brand/${encodeURIComponent(brandName)}`);
    if (logoDataUri) {
      const pad = 8;
      parts.push(`<image href="${logoDataUri}" x="${lx + pad}" y="${ly + pad}" width="${LOGO_SIZE - pad * 2}" height="${LOGO_SIZE - pad * 2}" preserveAspectRatio="xMidYMid meet"/>`);
    } else {
      // Fallback: brand initials
      const initials = brandName.split(/\s+/).slice(0, 2).map(w => w[0]?.toUpperCase()).join("");
      parts.push(`<text x="${pos.logoX}" y="${pos.logoY}" text-anchor="middle" dominant-baseline="middle" fill="${color}" font-size="16" font-weight="700" font-family="Inter, system-ui, sans-serif">${initials}</text>`);
    }

    // Percentage label below logo
    parts.push(`<text x="${pos.logoX}" y="${ly + LOGO_SIZE + 14}" text-anchor="middle" fill="${color}" font-size="12" font-weight="700" font-family="Inter, system-ui, sans-serif">${chartData[idx].percentage}%</text>`);
  }

  parts.push(`</svg>`);
  return parts.join("\n");
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

async function exportAsSvg(params: ExportChartParams, filterParams?: ExportFilterParams) {
  const svgStr = await buildExportSvg(params);
  const blob = new Blob([svgStr], { type: "image/svg+xml" });
  downloadBlob(blob, "top-brands-chart.svg");
  // Companion parameters image
  const paramsSvg = buildParamsSvg(filterParams);
  const paramsBlob = new Blob([paramsSvg], { type: "image/svg+xml" });
  downloadBlob(paramsBlob, "top-brands-params.svg");
}

async function exportAsPng(params: ExportChartParams, filterParams?: ExportFilterParams, scale = 2) {
  // Chart PNG
  const svgStr = await buildExportSvg(params);
  const chartPng = await svgToPngBlob(svgStr, params.W, params.H, scale);
  if (chartPng) downloadBlob(chartPng, "top-brands-chart.png");
  // Companion parameters PNG
  const paramsSvg = buildParamsSvg(filterParams);
  // Parse dimensions from the SVG
  const wMatch = paramsSvg.match(/width="(\d+)"/);
  const hMatch = paramsSvg.match(/height="(\d+)"/);
  const pw = wMatch ? parseInt(wMatch[1]) : 320;
  const ph = hMatch ? parseInt(hMatch[1]) : 300;
  const paramsPng = await svgToPngBlob(paramsSvg, pw, ph, scale);
  if (paramsPng) downloadBlob(paramsPng, "top-brands-params.png");
}

// Vibrant, accessible color palette for charts
const CHART_COLORS = [
  "#e91e63", // Magenta/Pink
  "#fbbf24", // Amber/Yellow
  "#06b6d4", // Cyan
  "#f97316", // Orange
  "#a855f7", // Purple
];

function PieChartView({
  topBrands,
  onBrandClick,
  onExportParamsReady,
}: {
  topBrands: BrandSovEntry[];
  onBrandClick?: (brand: string) => void;
  onExportParamsReady?: (params: ExportChartParams) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ w: 0, h: 0 });

  const displayBrands = topBrands.slice(0, 5);
  const remainingCount = topBrands.length > 5 ? topBrands.slice(5).reduce((sum, b) => sum + b.count, 0) : 0;
  const totalCount = topBrands.reduce((sum, b) => sum + b.count, 0);

  const chartData = [
    ...displayBrands.map((brand) => ({
      name: brand.brand,
      value: brand.count,
      percentage: totalCount > 0 ? Math.round((brand.count / totalCount) * 100) : 0,
    })),
    ...(remainingCount > 0
      ? [{ name: "All Others", value: remainingCount, percentage: Math.round((remainingCount / totalCount) * 100) }]
      : []),
  ];

  // Observe container size for responsive layout
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setDims({ w: Math.round(width), h: Math.round(height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const W = dims.w || 600;
  const H = dims.h || 450;

  // ── Pie geometry ──
  // Pie center is offset to the right to leave room for labels on the left
  const pieCx = W * 0.60;
  const pieCy = H / 2;
  const pieR = Math.min(W * 0.375, H * 0.525);

  // ── Rotation: orient pie so the LARGEST slice faces right (away from labels)
  // and the many small slices cluster on the left (toward labels).
  // Recharts angles: startAngle goes CCW from 3-o'clock.
  // We want the largest slice centered at 0° (right side).
  // Find the cumulative offset to the midpoint of the largest slice, then
  // set startAngle so that midpoint lands at 0° (3 o'clock).
  const largestIdx = chartData.reduce((best, d, i, arr) =>
    d.value > arr[best].value ? i : best, 0);

  // Cumulative fraction up to the midpoint of the largest slice
  const totalVal = chartData.reduce((s, d) => s + d.value, 0);
  let cumBefore = 0;
  for (let i = 0; i < largestIdx; i++) {
    cumBefore += chartData[i].value / totalVal;
  }
  const largestMidFrac = cumBefore + (chartData[largestIdx].value / totalVal) / 2;
  // We want this midpoint at 0° (right). Recharts startAngle is where slice 0 begins.
  // Slice 0 starts at startAngle and goes CW (startAngle > endAngle).
  // The midpoint of slice `largestIdx` is at startAngle - largestMidFrac*360.
  // We want that to equal 0°, so: startAngle - largestMidFrac*360 = 0
  // → startAngle = largestMidFrac * 360
  const startAngle = largestMidFrac * 360;
  const endAngle = startAngle - 360;

  // ── Compute mid-angle of each slice (in standard math degrees, CCW from right) ──
  const sliceMidAngles = (() => {
    let cum = 0;
    return chartData.map((d) => {
      const frac = totalVal > 0 ? d.value / totalVal : 0;
      const midDeg = startAngle - (cum + frac / 2) * 360;
      cum += frac;
      return midDeg;
    });
  })();

  // ── Leader line + logo positions ──
  // Each logo sits at the END of a leader line that extends from the pie edge
  // outward toward the left. The line has two segments:
  //   1. Radial: from pie edge outward by a fixed amount
  //   2. Horizontal: extends left to a fixed X column
  // The logo is placed at the end of segment 2.
  const LOGO_SIZE = 60;
  const LEADER_LEN = 24; // radial extension beyond pie edge
  const LOGO_COL_X = 10; // left edge X where logos land (logo center = LOGO_COL_X + LOGO_SIZE/2)

  const labelLayout = (() => {
    // Compute raw Y from the pie edge point for each slice
    const raw = sliceMidAngles.map((deg) => {
      const rad = (deg * Math.PI) / 180;
      const edgeX = pieCx + (pieR + LEADER_LEN) * Math.cos(rad);
      const edgeY = pieCy - (pieR + LEADER_LEN) * Math.sin(rad);
      return { edgeX, edgeY, rad, deg };
    });

    // Filter to only brand labels (not "All Others")
    const brandIndices = raw.map((_, i) => i).filter((i) => chartData[i].name !== "All Others");

    // Sort by raw Y so vertical order matches pie order
    brandIndices.sort((a, b) => raw[a].edgeY - raw[b].edgeY);

    // Evenly space logos vertically, centered in the container
    const ITEM_HEIGHT = LOGO_SIZE + 24; // logo + % label + breathing room
    const BOTTOM_PAD = 18; // room for the % label below the last logo
    const totalHeight = brandIndices.length * ITEM_HEIGHT + BOTTOM_PAD;
    const startY = (H - totalHeight) / 2 + ITEM_HEIGHT / 2;

    const positions: { logoX: number; logoY: number; pieEdgeX: number; pieEdgeY: number }[] = new Array(chartData.length);

    brandIndices.forEach((i, slot) => {
      const targetY = startY + slot * ITEM_HEIGHT;

      // Pie edge point (on the circumference)
      const rad = (sliceMidAngles[i] * Math.PI) / 180;
      const pieEdgeX = pieCx + (pieR + 3) * Math.cos(rad);
      const pieEdgeY = pieCy - (pieR + 3) * Math.sin(rad);

      positions[i] = {
        logoX: LOGO_COL_X + LOGO_SIZE / 2,
        logoY: targetY,
        pieEdgeX,
        pieEdgeY,
      };
    });
    return positions;
  })();

  // Position for "All Others" label inside its pie slice (visual centroid)
  const allOthersIdx = chartData.findIndex((d) => d.name === "All Others");
  const allOthersPos = allOthersIdx >= 0 ? (() => {
    const frac = chartData[allOthersIdx].value / totalVal;
    const halfSweep = frac * Math.PI; // half the sweep in radians
    const midDeg = sliceMidAngles[allOthersIdx];
    const rad = (midDeg * Math.PI) / 180;
    // Centroid distance from center = (2/3) * R * sin(halfSweep) / halfSweep
    // For very large slices (>50%), clamp closer to center
    const centroidR = halfSweep > 0.01
      ? (2 / 3) * pieR * (Math.sin(halfSweep) / halfSweep)
      : pieR * 0.5;
    return {
      x: pieCx + centroidR * Math.cos(rad),
      y: pieCy - centroidR * Math.sin(rad),
    };
  })() : null;

  // Pass export params up to parent whenever geometry changes
  useEffect(() => {
    if (dims.w > 0 && onExportParamsReady) {
      onExportParamsReady({
        chartData, pieCx, pieCy, pieR, startAngle, totalVal,
        sliceMidAngles, labelLayout, allOthersIdx, allOthersPos,
        W, H, LOGO_SIZE,
      });
    }
  }, [dims.w, dims.h, topBrands]);

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div className="bg-white p-3 border border-gray-300 rounded-md shadow-lg text-sm">
          <p className="font-semibold text-gray-900 leading-snug">{capitalizeBrand(data.name)}</p>
          <p className="text-gray-700 leading-snug">{data.value} ads ({data.percentage}%)</p>
        </div>
      );
    }
    return null;
  };

  return (
    <div ref={containerRef} className="w-full" style={{ minHeight: "420px", height: "100%", position: "relative" }}>
      {dims.w > 0 && (
        <>
          {/* SVG connector lines + "All Others" label inside pie */}
          <svg
            className="absolute inset-0 pointer-events-none"
            width={W}
            height={H}
            style={{ zIndex: 1 }}
          >
            {chartData.map((_, idx) => {
              if (chartData[idx].name === "All Others") return null;
              const pos = labelLayout[idx];
              if (!pos) return null;
              const color = CHART_COLORS[idx % CHART_COLORS.length];
              // Elbow: horizontal from logo, then straight to pie edge
              const elbowX = pos.logoX + LOGO_SIZE / 2 + 6;
              return (
                <g key={`line-${idx}`}>
                  <line
                    x1={pos.logoX + LOGO_SIZE / 2 + 2}
                    y1={pos.logoY}
                    x2={elbowX}
                    y2={pos.logoY}
                    stroke={color}
                    strokeWidth="2"
                    opacity="0.5"
                  />
                  <line
                    x1={elbowX}
                    y1={pos.logoY}
                    x2={pos.pieEdgeX}
                    y2={pos.pieEdgeY}
                    stroke={color}
                    strokeWidth="2"
                    opacity="0.5"
                  />
                  <circle cx={pos.pieEdgeX} cy={pos.pieEdgeY} r="3" fill={color} opacity="0.7" />
                </g>
              );
            })}
          </svg>

          {/* Logo labels — absolutely positioned at leader line endpoints */}
          {chartData.map((item, idx) => {
            if (item.name === "All Others") return null;
            const pos = labelLayout[idx];
            if (!pos) return null;
            const borderColor = CHART_COLORS[idx % CHART_COLORS.length];
            return (
              <button
                key={item.name}
                onClick={() => onBrandClick?.(item.name)}
                className="absolute flex flex-col items-center group"
                style={{
                  left: pos.logoX - LOGO_SIZE / 2,
                  top: pos.logoY - LOGO_SIZE / 2,
                  zIndex: 2,
                }}
              >
                <div
                  className="relative flex items-center justify-center bg-white rounded-lg shadow-md group-hover:shadow-lg group-hover:scale-105 transition-all overflow-hidden"
                  style={{ width: LOGO_SIZE, height: LOGO_SIZE }}
                >
                  <BrandLogoImage brandName={item.name} size={44} />
                  {/* Border overlay on top of image */}
                  <div
                    className="absolute inset-0 rounded-lg pointer-events-none"
                    style={{ boxShadow: `inset 0 0 0 3px ${borderColor}` }}
                  />
                </div>
                <div className="text-xs font-bold whitespace-nowrap mt-1" style={{ color: borderColor }}>
                  {item.percentage}%
                </div>
              </button>
            );
          })}

          {/* Pie chart — z:3 so tooltip renders above SVG overlay; pointer-events:none on wrapper, auto on pie */}
          <div className="absolute inset-0 pointer-events-none" style={{ zIndex: 3 }}>
            <PieChart width={W} height={H} style={{ pointerEvents: 'auto' }}>
              <Pie
                data={chartData}
                cx={pieCx}
                cy={pieCy}
                labelLine={false}
                outerRadius={pieR}
                fill="#8884d8"
                dataKey="value"
                startAngle={startAngle}
                endAngle={endAngle}
                onClick={(entry) => onBrandClick?.(entry.payload.name)}
                style={{ cursor: "pointer" }}
                label={(props: any) => {
                  if (props.name !== "All Others" || !allOthersPos) return null;
                  return (
                    <g>
                      <text x={allOthersPos.x} y={allOthersPos.y - 6} textAnchor="middle" dominantBaseline="middle" fill="#4b5563" fontSize="14" fontWeight="700">6+</text>
                      <text x={allOthersPos.x} y={allOthersPos.y + 10} textAnchor="middle" dominantBaseline="middle" fill="#6b7280" fontSize="11" fontWeight="600">{chartData[allOthersIdx].percentage}%</text>
                    </g>
                  );
                }}
              >
                {chartData.map((item, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={item.name === "All Others" ? "#d1d5db" : CHART_COLORS[index % CHART_COLORS.length]}
                    style={{ filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.1))" }}
                  />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} wrapperStyle={{ zIndex: 50, backgroundColor: 'white', borderRadius: '6px' }} />
            </PieChart>
          </div>
        </>
      )}
    </div>
  );
}

function ParametersCheatSheet({ filterParams }: { filterParams?: FilterParams }) {
  const formatDate = (date?: Date) => {
    if (!date) return "—";
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  const items = [
    {
      label: "Date",
      value: filterParams?.dateRange
        ? `${formatDate(filterParams.dateRange.start)} – ${formatDate(filterParams.dateRange.end)}`
        : "All time",
      icon: "date",
    },
    {
      label: "Retailers",
      value: filterParams?.retailers?.length ? filterParams.retailers.map(r => capitalizeBrand(r)).join(", ") : "All",
      icon: "retailers",
    },
    {
      label: "Keywords",
      value: filterParams?.keywords?.length ? filterParams.keywords.join(", ") : "All",
      icon: "keywords",
    },
    {
      label: "Ad Types",
      value: filterParams?.adTypes?.length ? filterParams.adTypes.join(", ") : "All",
      icon: "adtypes",
    },
    {
      label: "Clients",
      value: filterParams?.clients?.length ? filterParams.clients.join(", ") : "All",
      icon: "clients",
    },
  ];

  return (
    <div className="bg-gradient-to-b from-gray-50 to-white border border-gray-200 rounded-lg p-4 space-y-4">
      <h4 className="text-sm font-semibold text-gray-900 px-1">Parameters</h4>
      <div className="space-y-3">
        {items.map((item) => (
          <div key={item.label} className="flex gap-3 items-start">
            <div className="flex-shrink-0 w-6 h-6 flex items-center justify-center text-gray-400">
                  {item.icon === "date" && (
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>
                  )}
                  {item.icon === "retailers" && (
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m2 7 4.41-4.41A2 2 0 0 1 7.83 2h8.34a2 2 0 0 1 1.42.59L22 7"/><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><path d="M15 22v-4a2 2 0 0 0-2-2h-2a2 2 0 0 0-2 2v4"/><path d="M2 7h20"/><path d="M22 7v3a2 2 0 0 1-2 2a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 16 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 12 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 8 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 4 12a2 2 0 0 1-2-2V7"/></svg>
                  )}
                  {item.icon === "keywords" && (
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
                  )}
                  {item.icon === "adtypes" && (
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" x2="18" y1="20" y2="10"/><line x1="12" x2="12" y1="20" y2="4"/><line x1="6" x2="6" y1="20" y2="14"/></svg>
                  )}
                  {item.icon === "clients" && (
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                  )}
                </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-semibold text-gray-600 uppercase tracking-wide">{item.label}</div>
              <div className="text-sm text-gray-900 font-medium break-words leading-snug">{item.value}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function TopBrandModal({
  open,
  onOpenChange,
  topBrands,
  onRetailerClick,
  filterParams,
}: TopBrandModalProps) {
  const displayBrands = topBrands.slice(0, 5);
  const remainingCount = topBrands.length > 5 ? topBrands.slice(5).reduce((sum, b) => sum + b.count, 0) : 0;
  const totalCount = topBrands.reduce((sum, b) => sum + b.count, 0);
  const [exportParams, setExportParams] = useState<ExportChartParams | null>(null);
  const [exporting, setExporting] = useState(false);
  const [flaggedBrands, setFlaggedBrands] = useState<Set<string>>(new Set());

  const handleFlagBrand = useCallback((brandName: string) => {
    if (flaggedBrands.has(brandName)) return;
    setFlaggedBrands(prev => new Set(prev).add(brandName));
    fetch('/api/flag-review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'brand', brand_name: brandName, reason: 'User flagged from top brands' }),
    }).catch(() => {
      setFlaggedBrands(prev => { const next = new Set(prev); next.delete(brandName); return next; });
    });
  }, [flaggedBrands]);

  const handleExport = async (format: "svg" | "png") => {
    if (!exportParams) return;
    setExporting(true);
    try {
      if (format === "svg") await exportAsSvg(exportParams, filterParams);
      else await exportAsPng(exportParams, filterParams);
    } finally {
      setExporting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-4xl max-h-screen overflow-y-auto">
        <Tabs defaultValue="list" className="w-full">
          <TabsList className="grid w-full grid-cols-2 mb-2 bg-gray-100 h-8">
            <TabsTrigger value="list" className="text-xs">List View</TabsTrigger>
            <TabsTrigger value="chart" className="text-xs">Chart View</TabsTrigger>
          </TabsList>

          <DialogHeader>
            <DialogTitle>Top Brands by Share of Voice</DialogTitle>
          </DialogHeader>

          <TabsContent value="list" className="space-y-4">
            {displayBrands.map((brand, idx) => {
              const percentage = totalCount > 0 ? Math.round((brand.count / totalCount) * 100) : 0;
              return (
                <button
                  key={brand.brand}
                  onClick={() => onRetailerClick?.(brand.brand)}
                  className="w-full flex items-center gap-4 p-4 border border-gray-200 rounded-lg hover:bg-gray-50 hover:border-gray-300 transition-colors text-left"
                >
                  <div className="font-bold bg-gradient-to-r from-[#e91e63] via-[#06b6d4] to-[#a855f7] bg-clip-text text-transparent text-xl flex-shrink-0 w-6 text-center">
                    #{idx + 1}
                  </div>
                  <div className="flex-shrink-0">
                    <BrandLogoImage brandName={brand.brand} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-gray-900 text-base">{capitalizeBrand(brand.brand)}</div>
                    <div className="text-sm text-gray-500">{brand.count} ads</div>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <button
                      onClick={(e) => { e.stopPropagation(); handleFlagBrand(brand.brand); }}
                      className={`text-[10px] font-medium px-2 py-1 rounded transition ${
                        flaggedBrands.has(brand.brand)
                          ? 'bg-amber-100 text-amber-700'
                          : 'text-gray-300 hover:text-amber-600 hover:bg-amber-50'
                      }`}
                    >
                      {flaggedBrands.has(brand.brand) ? '✓ flagged' : 'needs review'}
                    </button>
                    <div className="text-right">
                      <div className="font-extrabold text-2xl bg-gradient-to-r from-[#e91e63] via-[#06b6d4] to-[#a855f7] bg-clip-text text-transparent leading-none">
                        {percentage}%
                      </div>
                    </div>
                  </div>
                </button>
              );
            })}
            {remainingCount > 0 && (
              <div className="flex items-center gap-4 p-4 border border-gray-200 rounded-lg bg-gray-50">
                <div className="font-bold bg-gradient-to-r from-[#e91e63] via-[#06b6d4] to-[#a855f7] bg-clip-text text-transparent text-xl flex-shrink-0 w-6 text-center">
                  6+
                </div>
                <div className="flex-1">
                  <div className="font-semibold text-gray-900 text-base">All Others</div>
                  <div className="text-sm text-gray-500">{remainingCount} ads</div>
                </div>
                <div className="text-right flex-shrink-0">
                  <div className="font-extrabold text-2xl bg-gradient-to-r from-[#e91e63] via-[#06b6d4] to-[#a855f7] bg-clip-text text-transparent leading-none">
                    {Math.round((remainingCount / totalCount) * 100)}%
                  </div>
                </div>
              </div>
            )}
          </TabsContent>

          <TabsContent value="chart" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
              <div className="lg:col-span-3">
                <PieChartView topBrands={topBrands} onBrandClick={onRetailerClick} onExportParamsReady={setExportParams} />
              </div>
              <div className="lg:col-span-2 flex flex-col items-start gap-4">
                <div className="w-full">
                  <ParametersCheatSheet filterParams={filterParams} />
                </div>
                <div className="flex gap-2 w-full">
                  <button
                    onClick={() => handleExport("svg")}
                    disabled={!exportParams || exporting}
                    className="flex-1 flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
                    {exporting ? "Exporting..." : "SVG"}
                  </button>
                  <button
                    onClick={() => handleExport("png")}
                    disabled={!exportParams || exporting}
                    className="flex-1 flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
                    {exporting ? "Exporting..." : "PNG"}
                  </button>
                </div>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
