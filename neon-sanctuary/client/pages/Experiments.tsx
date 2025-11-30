import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ChevronDown, ArrowLeft } from "lucide-react";
import ConstellationMap from "@/components/experiments/ConstellationMap";
import AdIntensityHeatTimeline from "@/components/experiments/AdIntensityHeatTimeline";
import ShareOfVoiceOrbitals from "@/components/experiments/ShareOfVoiceOrbitals";
import AdTypeDNAStrand from "@/components/experiments/AdTypeDNAStrand";
import InventoryCaptureFunnel from "@/components/experiments/InventoryCaptureFunnel";
import ChannelPulseLine from "@/components/experiments/ChannelPulseLine";
import AdMosaicWall from "@/components/experiments/AdMosaicWall";
import CompetitiveRadarRing from "@/components/experiments/CompetitiveRadarRing";
import AdSupplyChainMap from "@/components/experiments/AdSupplyChainMap";
import KeywordWindTunnel from "@/components/experiments/KeywordWindTunnel";

type ExperimentId = "constellation" | "heatmap" | "orbitals" | "dna" | "funnel" | "pulse" | "mosaic" | "radar" | "sankey" | "wind";

const experiments: Array<{ id: ExperimentId; name: string; description: string }> = [
  {
    id: "constellation",
    name: "Constellation Map",
    description: "Brand × Retailer activity graph with weighted edges and temporal scrubbing",
  },
  {
    id: "heatmap",
    name: "Ad Intensity Heat Timeline",
    description: "Calendar-style heatmap with integrated sparklines for ad volume patterns",
  },
  {
    id: "orbitals",
    name: "Share-of-Voice Orbitals",
    description: "Solar system visualization with planets representing retailers",
  },
  {
    id: "dna",
    name: "Ad Type DNA Strand",
    description: "3D double-helix showing ad type × retailer relationships",
  },
  {
    id: "funnel",
    name: "Inventory Capture Funnel",
    description: "Interactive funnel simulator with competitor and brand capture",
  },
  {
    id: "pulse",
    name: "Channel Pulse Line",
    description: "EKG-style visualization of ad activity bursts across channels",
  },
  {
    id: "mosaic",
    name: "Ad Mosaic Wall",
    description: "Responsive masonry grid with dynamic tile sizing by metrics",
  },
  {
    id: "radar",
    name: "Competitive Radar Ring",
    description: "Multi-axis radar chart tracking SOV, diversity, and penetration",
  },
  {
    id: "sankey",
    name: "Ad Supply Chain Map",
    description: "Flow diagram from retailers → placements → keywords → creatives",
  },
  {
    id: "wind",
    name: "Keyword Wind Tunnel",
    description: "Fluid simulation showing competitive pressure in keyword space",
  },
];

const renderExperiment = (id: ExperimentId) => {
  switch (id) {
    case "constellation":
      return <ConstellationMap />;
    case "heatmap":
      return <AdIntensityHeatTimeline />;
    case "orbitals":
      return <ShareOfVoiceOrbitals />;
    case "dna":
      return <AdTypeDNAStrand />;
    case "funnel":
      return <InventoryCaptureFunnel />;
    case "pulse":
      return <ChannelPulseLine />;
    case "mosaic":
      return <AdMosaicWall />;
    case "radar":
      return <CompetitiveRadarRing />;
    case "sankey":
      return <AdSupplyChainMap />;
    case "wind":
      return <KeywordWindTunnel />;
    default:
      return null;
  }
};

export default function Experiments() {
  const navigate = useNavigate();
  const [activeExp, setActiveExp] = useState<ExperimentId>("constellation");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    contentRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [activeExp]);

  const current = experiments.find((e) => e.id === activeExp)!;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <div className="border-b border-slate-700/50 bg-slate-900/80 backdrop-blur-sm sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 py-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => navigate("/")}
                className="p-2 hover:bg-slate-700 rounded-lg transition text-slate-400 hover:text-slate-200"
                title="Back to main dashboard"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
              <div>
                <h1 className="text-3xl font-bold text-white">Experiments</h1>
                <p className="text-slate-400 mt-1">Advanced data visualization concepts</p>
              </div>
            </div>
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="md:hidden p-2 hover:bg-slate-700 rounded-lg transition"
            >
              <ChevronDown className={cn("w-5 h-5 text-slate-400 transition-transform", sidebarOpen && "rotate-180")} />
            </button>
          </div>
        </div>
      </div>

      <div className="flex h-[calc(100vh-80px)]">
        {/* Sidebar */}
        <div
          className={cn(
            "border-r border-slate-700/50 bg-slate-900 overflow-y-auto transition-all duration-300",
            sidebarOpen ? "w-72" : "w-0"
          )}
        >
          <div className="p-6 space-y-3">
            {experiments.map((exp) => (
              <button
                key={exp.id}
                onClick={() => {
                  setActiveExp(exp.id);
                  setSidebarOpen(false);
                }}
                className={cn(
                  "w-full text-left px-4 py-3 rounded-lg transition-all duration-200",
                  activeExp === exp.id
                    ? "bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-lg"
                    : "text-slate-300 hover:bg-slate-800"
                )}
              >
                <div className="font-semibold text-sm">{exp.name}</div>
                <div className="text-xs text-slate-400 mt-1 line-clamp-2">{exp.description}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Main Content */}
        <div className="flex-1 overflow-y-auto">
          <div ref={contentRef} className="max-w-7xl mx-auto px-6 py-8">
            {/* Breadcrumb */}
            <div className="flex items-center gap-2 mb-6 text-sm">
              <button
                onClick={() => setSidebarOpen(true)}
                className="text-slate-400 hover:text-slate-200 transition flex items-center gap-1"
              >
                <ArrowLeft className="w-4 h-4" />
                Labs Menu
              </button>
              <span className="text-slate-600">/</span>
              <span className="text-slate-300 font-medium">{current.name}</span>
            </div>

            {/* Current Experiment Header */}
            <div className="mb-8">
              <h2 className="text-2xl font-bold text-white mb-2">{current.name}</h2>
              <p className="text-slate-400">{current.description}</p>
            </div>

            {/* Experiment Visualization */}
            <div className="rounded-xl border border-slate-700/50 bg-slate-800/50 backdrop-blur-sm overflow-hidden shadow-2xl">
              <div className="p-6 min-h-96">
                {renderExperiment(activeExp)}
              </div>
            </div>

            {/* Footer */}
            <div className="mt-12 text-center">
              <p className="text-slate-500 text-sm">
                Experiment {experiments.indexOf(current) + 1} of {experiments.length}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
