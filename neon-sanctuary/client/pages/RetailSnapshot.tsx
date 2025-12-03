import { useState, useMemo, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell } from "recharts";
import { X } from "lucide-react";
import GaleLogo from "../../../web/assets/logos/GALE.svg";

type Retailer = "kroger" | "amazon" | "walmart" | "instacart" | "target" | "albertsons" | "food_lion" | "gopuff" | "doordash" | "meijer" | "hyvee" | "ulta";

interface CarouselBbox {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface Snapshot {
  retailer: string;
  pageType: string;
  date: string;
  time: string;
  runId?: string;
  filename: string;
  imagePath: string;
  carousel?: {
    slidesCount: number;
    bbox: CarouselBbox | null;
    slidePaths: string[];
  };
}

const RETAILER_LABELS: Record<Retailer, string> = {
  kroger: "Kroger",
  amazon: "Amazon",
  walmart: "Walmart",
  instacart: "Instacart",
  target: "Target",
  albertsons: "Albertsons",
  food_lion: "Food Lion",
  gopuff: "GoPuff",
  doordash: "DoorDash",
  meijer: "Meijer",
  hyvee: "Hy-Vee",
  ulta: "Ulta",
};

const PAGE_TYPES = [
  { value: "home", label: "Home Page" },
  { value: "frozen_foods", label: "Frozen Foods Department" },
  { value: "produce", label: "Produce Department" },
  { value: "dairy", label: "Dairy Department" },
  { value: "bakery", label: "Bakery Department" },
  { value: "pharmacy", label: "Pharmacy Department" },
  { value: "seasonal", label: "Seasonal Section" },
];

const HOLIDAYS_AND_EVENTS = [
  { week: 1, name: "New Year", color: "#ef4444" },
  { week: 6, name: "Valentine's Day", color: "#ec4899" },
  { week: 12, name: "Spring Break", color: "#10b981" },
  { week: 17, name: "Mother's Day", color: "#f59e0b" },
  { week: 21, name: "Father's Day", color: "#3b82f6" },
  { week: 27, name: "Back to School", color: "#8b5cf6" },
  { week: 36, name: "Labor Day", color: "#06b6d4" },
  { week: 41, name: "Halloween", color: "#f97316" },
  { week: 47, name: "Thanksgiving", color: "#d97706" },
  { week: 50, name: "Black Friday", color: "#000000" },
  { week: 52, name: "Christmas", color: "#dc2626" },
];

const MOCK_KEYWORDS = [
  { keyword: "holiday", frequency: 45, percentage: 12 },
  { keyword: "sale", frequency: 38, percentage: 10 },
  { keyword: "promotion", frequency: 32, percentage: 8 },
  { keyword: "seasonal", frequency: 28, percentage: 7 },
  { keyword: "grocery", frequency: 25, percentage: 7 },
  { keyword: "fresh", frequency: 22, percentage: 6 },
  { keyword: "deals", frequency: 20, percentage: 5 },
  { keyword: "organic", frequency: 18, percentage: 5 },
  { keyword: "limited", frequency: 15, percentage: 4 },
  { keyword: "exclusive", frequency: 14, percentage: 4 },
];

const MOCK_SEASONALITY_DATA = Array.from({ length: 52 }, (_, i) => {
  const week = i + 1;
  const baseActivity = 50 + Math.sin((week / 52) * Math.PI * 2) * 20;
  const event = HOLIDAYS_AND_EVENTS.find(e => e.week === week);
  return {
    week,
    activity: Math.round(baseActivity + (event ? 25 : 0)),
    hasEvent: !!event,
    eventName: event?.name || "",
  };
});

export default function RetailSnapshot() {
  const navigate = useNavigate();
  const [selectedRetailers, setSelectedRetailers] = useState<Retailer[]>([
    "kroger", "amazon", "walmart", "instacart", "target", "albertsons",
    "food_lion", "gopuff", "doordash", "meijer", "hyvee", "ulta"
  ]);
  const [pageType, setPageType] = useState("home");
  const [dateRange, setDateRange] = useState<"day" | "week" | "month" | "quarter" | "year">("day");
  const [selectedDate, setSelectedDate] = useState("2025-11-29");
  const [keywordSearch, setKeywordSearch] = useState("");
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [snapshotsLoading, setSnapshotsLoading] = useState(false);
  const [snapshotsError, setSnapshotsError] = useState<string | null>(null);
  const [selectedSnapshot, setSelectedSnapshot] = useState<Snapshot | null>(null);
  const [carouselSlideIndex, setCarouselSlideIndex] = useState(0);
  const [carouselPlaying, setCarouselPlaying] = useState(true);
  const [expandedSlide, setExpandedSlide] = useState<string | null>(null);

  useEffect(() => {
    const fetchSnapshots = async () => {
      setSnapshotsLoading(true);
      setSnapshotsError(null);

      try {
        const params = new URLSearchParams();
        if (pageType && pageType !== "home") {
          params.append("pageType", pageType);
        }
        if (selectedDate) {
          params.append("date", selectedDate);
        }

        const response = await fetch(`/api/snapshots?${params.toString()}`);
        if (!response.ok) {
          throw new Error("Failed to fetch snapshots");
        }

        const data = await response.json();
        const filtered = data.snapshots.filter((snap: Snapshot) =>
          selectedRetailers.some((r) => r === snap.retailer)
        );
        setSnapshots(filtered);
      } catch (error) {
        console.error("Error fetching snapshots:", error);
        setSnapshotsError(
          error instanceof Error ? error.message : "Failed to load snapshots"
        );
      } finally {
        setSnapshotsLoading(false);
      }
    };

    fetchSnapshots();
  }, [selectedRetailers, pageType, selectedDate]);

  // Reset carousel when snapshot changes
  useEffect(() => {
    setCarouselSlideIndex(0);
    setCarouselPlaying(true);
  }, [selectedSnapshot]);

  // Auto-advance carousel slides
  useEffect(() => {
    if (!selectedSnapshot?.carousel?.slidePaths?.length || !carouselPlaying) return;
    
    const interval = setInterval(() => {
      setCarouselSlideIndex((prev) => 
        (prev + 1) % selectedSnapshot.carousel!.slidePaths.length
      );
    }, 3000); // 3 seconds per slide
    
    return () => clearInterval(interval);
  }, [selectedSnapshot, carouselPlaying]);

  const filteredKeywords = useMemo(() => {
    if (!keywordSearch.trim()) return MOCK_KEYWORDS;
    const term = keywordSearch.toLowerCase();
    return MOCK_KEYWORDS.filter(k => k.keyword.includes(term)).sort((a, b) => b.frequency - a.frequency);
  }, [keywordSearch]);

  const toggleRetailer = (retailer: Retailer) => {
    setSelectedRetailers(prev =>
      prev.includes(retailer) ? prev.filter(r => r !== retailer) : [...prev, retailer]
    );
  };

  const getDateRangeLabel = () => {
    const date = new Date(selectedDate);
    switch (dateRange) {
      case "day":
        return date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" });
      case "week": {
        const weekStart = new Date(date);
        weekStart.setDate(date.getDate() - date.getDay());
        const weekEnd = new Date(weekStart);
        weekEnd.setDate(weekStart.getDate() + 6);
        return `Week of ${weekStart.toLocaleDateString("en-US", { month: "short", day: "numeric" })} - ${weekEnd.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
      }
      case "month":
        return date.toLocaleDateString("en-US", { month: "long", year: "numeric" });
      case "quarter": {
        const quarter = Math.floor(date.getMonth() / 3) + 1;
        return `Q${quarter} ${date.getFullYear()}`;
      }
      case "year":
        return `${date.getFullYear()}`;
      default:
        return "";
    }
  };


  return (
    <main className="min-h-screen py-6 pb-32 md:pb-48 px-4 md:px-8 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      <div className="w-full max-w-[1600px] mx-auto">
        {/* Header */}
        <header className="flex flex-wrap items-center gap-3 mb-6">
          <div className="flex items-center gap-3">
            <img src={GaleLogo} alt="GALE" className="h-8 w-auto" />
            <h1 className="text-white text-2xl font-extrabold">Retail Snapshot</h1>
          </div>
          <div className="ml-auto">
            <button
              onClick={() => navigate("/")}
              className="px-3 py-2 rounded-md bg-white/10 text-white border border-white/30 hover:bg-white/20 focus-visible:ring-2"
            >
              ← Back to Dashboard
            </button>
          </div>
        </header>

        {/* Controls Section */}
        <section className="card-surface p-3 mb-4 space-y-2">
          {/* Page Type and Date Range */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Page Type</label>
              <Select value={pageType} onValueChange={setPageType}>
                <SelectTrigger className="w-full bg-white border-gray-300 h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PAGE_TYPES.map(pt => (
                    <SelectItem key={pt.value} value={pt.value}>{pt.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Date Range</label>
              <Select value={dateRange} onValueChange={(v) => setDateRange(v as typeof dateRange)}>
                <SelectTrigger className="w-full bg-white border-gray-300 h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="day">Single Day</SelectItem>
                  <SelectItem value="week">Week</SelectItem>
                  <SelectItem value="month">Month</SelectItem>
                  <SelectItem value="quarter">Quarter</SelectItem>
                  <SelectItem value="year">Year</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Select Date</label>
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md bg-white text-gray-900 focus-visible:ring-2 focus-visible:ring-offset-2"
              />
            </div>
          </div>

          {/* Retailer Selection */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Select Retailers</label>
            <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-1">
              {Object.entries(RETAILER_LABELS).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => toggleRetailer(key as Retailer)}
                  className={cn(
                    "px-2 py-1 rounded-md border text-xs font-medium transition-colors",
                    selectedRetailers.includes(key as Retailer)
                      ? "bg-blue-600 border-blue-700 text-white"
                      : "bg-white border-gray-300 text-gray-700 hover:bg-gray-50"
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* Screenshot Grid */}
        <section className="card-surface p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            📸 Retailer Top-of-Fold Snapshots
          </h2>

          {selectedRetailers.length === 0 ? (
            <div className="p-10 text-center text-gray-500">
              <p>Please select at least one retailer to view snapshots.</p>
            </div>
          ) : snapshotsLoading ? (
            <div className="p-10 text-center text-gray-500">
              <p>Loading snapshots...</p>
            </div>
          ) : snapshotsError ? (
            <div className="p-10 text-center text-red-500">
              <p>Error loading snapshots: {snapshotsError}</p>
            </div>
          ) : snapshots.length === 0 ? (
            <div className="p-10 text-center text-gray-500">
              <p>No snapshots found for the selected filters.</p>
            </div>
          ) : (
            <div className="columns-1 sm:columns-2 lg:columns-3 xl:columns-4 gap-4 space-y-4">
              {snapshots.map((snapshot, idx) => (
                <button
                  key={`${snapshot.retailer}-${snapshot.date}-${snapshot.time}-${idx}`}
                  onClick={() => setSelectedSnapshot(snapshot)}
                  className="block w-full rounded-lg overflow-hidden border border-gray-200 hover:shadow-lg transition-shadow break-inside-avoid cursor-pointer bg-white"
                >
                  <div className="overflow-hidden relative h-48">
                    <img
                      src={snapshot.imagePath}
                      alt={`${snapshot.retailer} snapshot ${snapshot.date}`}
                      className="w-full h-full object-cover"
                      style={{ objectPosition: "top" }}
                    />
                  </div>
                </button>
              ))}
            </div>
          )}
        </section>

        {/* Insights Section */}
        <section className="card-surface p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">💡 Insights</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg">
              <h3 className="font-semibold text-amber-900 mb-2">Peak Season Identified</h3>
              <p className="text-sm text-amber-800">Weeks 47-52 show highest activity, correlating with holiday promotions</p>
            </div>
            <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
              <h3 className="font-semibold text-green-900 mb-2">Top Keywords Trending</h3>
              <p className="text-sm text-green-800">"Holiday" and "Sale" keywords dominate current messaging</p>
            </div>
            <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <h3 className="font-semibold text-blue-900 mb-2">Multi-Retailer Sync</h3>
              <p className="text-sm text-blue-800">All selected retailers align promotional calendars</p>
            </div>
          </div>
        </section>

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
          {/* Left Column: Keywords Analytics */}
          <div className="lg:col-span-1 card-surface p-6 h-fit">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">📊 Keywords Analytics</h2>

            <Input
              type="text"
              placeholder="Search keywords..."
              value={keywordSearch}
              onChange={(e) => setKeywordSearch(e.target.value)}
              className="mb-4 bg-white border-gray-300"
            />

            <div className="space-y-3 max-h-[600px] overflow-y-auto">
              {filteredKeywords.map((item, idx) => (
                <div key={idx} className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                  <div className="flex items-start justify-between mb-2">
                    <span className="font-medium text-gray-900">{item.keyword}</span>
                    <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">{item.frequency}x</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-gradient-to-r from-blue-500 to-blue-600 h-2 rounded-full"
                      style={{ width: `${item.percentage * 10}%` }}
                    />
                  </div>
                  <p className="text-xs text-gray-500 mt-1">{item.percentage}% of keywords</p>
                </div>
              ))}
            </div>
          </div>

          {/* Right Column: Seasonality Chart and Event Markers */}
          <div className="lg:col-span-2 card-surface p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">📈 52-Week Seasonality & Events</h2>

            <div className="space-y-4">
              {/* Chart */}
              <div className="bg-white p-4 rounded-lg border border-gray-200">
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={MOCK_SEASONALITY_DATA}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="week"
                      tick={{ fontSize: 10 }}
                      interval={Math.floor(52 / 12)}
                      label={{ value: "Week of Year", position: "insideBottomRight", offset: -5 }}
                    />
                    <YAxis label={{ value: "Activity Level", angle: -90, position: "insideLeft" }} />
                    <Tooltip
                      content={({ active, payload }) => {
                        if (!active || !payload?.[0]) return null;
                        const data = payload[0].payload;
                        return (
                          <div className="bg-white p-2 border border-gray-300 rounded shadow">
                            <p className="text-sm font-semibold">Week {data.week}</p>
                            <p className="text-sm">Activity: {data.activity}</p>
                            {data.eventName && <p className="text-sm text-blue-600">{data.eventName}</p>}
                          </div>
                        );
                      }}
                    />
                    <Bar dataKey="activity" fill="#3b82f6" radius={[4, 4, 0, 0]}>
                      {MOCK_SEASONALITY_DATA.map((entry, index) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={entry.hasEvent ? "#ef4444" : "#3b82f6"}
                          opacity={entry.hasEvent ? 1 : 0.7}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Event Markers Legend */}
              <div className="bg-gradient-to-r from-blue-50 to-indigo-50 p-4 rounded-lg border border-blue-200">
                <h3 className="text-sm font-semibold text-gray-900 mb-3">Holiday & Event Calendar</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  {HOLIDAYS_AND_EVENTS.map((event) => (
                    <div key={event.week} className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{ backgroundColor: event.color }}
                      />
                      <div className="text-xs">
                        <p className="font-medium text-gray-900">{event.name}</p>
                        <p className="text-gray-600">Week {event.week}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Snapshot Detail Modal */}
      {selectedSnapshot && (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-lg max-w-6xl w-full max-h-[90vh] overflow-y-auto">
            <div className="flex items-start justify-between p-6 border-b border-gray-200 sticky top-0 bg-white">
              <h2 className="text-2xl font-bold text-gray-900">
                {RETAILER_LABELS[selectedSnapshot.retailer as Retailer] || selectedSnapshot.retailer} - Top of Fold
              </h2>
              <button
                onClick={() => setSelectedSnapshot(null)}
                className="text-gray-500 hover:text-gray-700 transition-colors"
              >
                <X size={24} />
              </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 p-6">
              {/* Left Column: Full Image */}
              <div className="lg:col-span-2">
                <img
                  src={selectedSnapshot.imagePath}
                  alt={`${selectedSnapshot.retailer} snapshot ${selectedSnapshot.date}`}
                  className="w-full h-auto rounded-lg border border-gray-200"
                />
              </div>

              {/* Right Column: Stats */}
              <div className="space-y-4">
                {/* Carousel Slides Section - Top of right column */}
                {selectedSnapshot.carousel && selectedSnapshot.carousel.slidePaths.length > 0 && (
                  <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-semibold text-gray-900">
                        Hero Carousel ({selectedSnapshot.carousel.slidePaths.length} slides)
                      </h3>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setCarouselPlaying(!carouselPlaying)}
                          className={cn(
                            "px-3 py-1 text-xs rounded-full font-medium transition-colors",
                            carouselPlaying 
                              ? "bg-blue-100 text-blue-800" 
                              : "bg-gray-200 text-gray-700"
                          )}
                        >
                          {carouselPlaying ? "⏸ Pause" : "▶ Play"}
                        </button>
                        <span className="text-xs text-gray-500">
                          {carouselSlideIndex + 1}/{selectedSnapshot.carousel.slidePaths.length}
                        </span>
                      </div>
                    </div>
                    
                    {/* Current Slide */}
                    <div className="relative">
                      <img
                        src={selectedSnapshot.carousel.slidePaths[carouselSlideIndex]}
                        alt={`Carousel slide ${carouselSlideIndex + 1}`}
                        className="w-full h-auto rounded-lg border border-gray-300 cursor-pointer hover:opacity-90 transition-opacity"
                        onClick={() => setExpandedSlide(selectedSnapshot.carousel!.slidePaths[carouselSlideIndex])}
                      />
                    </div>
                    
                    {/* Slide Indicators */}
                    <div className="flex justify-center gap-2 mt-3">
                      {selectedSnapshot.carousel.slidePaths.map((_, idx) => (
                        <button
                          key={idx}
                          onClick={() => {
                            setCarouselSlideIndex(idx);
                            setCarouselPlaying(false);
                          }}
                          className={cn(
                            "w-2 h-2 rounded-full transition-colors",
                            idx === carouselSlideIndex 
                              ? "bg-blue-600" 
                              : "bg-gray-300 hover:bg-gray-400"
                          )}
                        />
                      ))}
                    </div>
                  </div>
                )}
                <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                  <p className="text-xs text-gray-600 uppercase tracking-wider font-semibold">Date Captured</p>
                  <p className="text-lg font-bold text-gray-900 mt-1">{selectedSnapshot.date}</p>
                  <p className="text-sm text-gray-600 mt-1">{selectedSnapshot.time}</p>
                </div>

                <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                  <p className="text-xs text-gray-600 uppercase tracking-wider font-semibold">Top Themes</p>
                  <div className="flex flex-wrap gap-2 mt-3">
                    <span className="px-3 py-1 bg-blue-100 text-blue-800 text-sm rounded-full">Seasonal</span>
                    <span className="px-3 py-1 bg-blue-100 text-blue-800 text-sm rounded-full">Promotions</span>
                    <span className="px-3 py-1 bg-blue-100 text-blue-800 text-sm rounded-full">New Items</span>
                  </div>
                </div>

                <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                  <p className="text-xs text-gray-600 uppercase tracking-wider font-semibold">Featured Promos</p>
                  <ul className="mt-3 space-y-2">
                    <li className="flex items-center gap-2">
                      <span className="text-lg">🏷️</span>
                      <span className="text-sm text-gray-900">Flash Sale</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="text-lg">📍</span>
                      <span className="text-sm text-gray-900">Regional Offer</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="text-lg">⭐</span>
                      <span className="text-sm text-gray-900">Featured Brand</span>
                    </li>
                  </ul>
                </div>

                <button
                  onClick={() => setSelectedSnapshot(null)}
                  className="w-full px-4 py-2 bg-gray-200 text-gray-900 rounded-lg hover:bg-gray-300 transition-colors font-medium"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Expanded Slide Lightbox */}
      {expandedSlide && (
        <div 
          className="fixed inset-0 bg-black bg-opacity-90 z-[60] flex items-center justify-center p-4 cursor-pointer"
          onClick={() => setExpandedSlide(null)}
        >
          <button
            onClick={() => setExpandedSlide(null)}
            className="absolute top-4 right-4 text-white hover:text-gray-300 transition-colors"
          >
            <X size={32} />
          </button>
          <img
            src={expandedSlide}
            alt="Expanded carousel slide"
            className="max-w-full max-h-full object-contain"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </main>
  );
}
