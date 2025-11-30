import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import { generateMosaicData } from "@/lib/experiment-data";

const generateMockAds = () => {
  const data = generateMosaicData();
  return data.map((tile) => ({
    id: tile.id,
    brand: tile.brand,
    retailer: tile.retailer,
    adType: tile.adType,
    frequency: tile.frequency,
    color: tile.color,
    intensity: tile.intensity,
  }));
};

type SortBy = "frequency" | "intensity" | "brand";

export default function AdMosaicWall() {
  const ads = useMemo(() => generateMockAds(), []);
  const [sortBy, setSortBy] = useState<SortBy>("frequency");
  const [selectedAd, setSelectedAd] = useState<number | null>(null);

  const sortedAds = useMemo(() => {
    const copy = [...ads];
    if (sortBy === "frequency") {
      copy.sort((a, b) => b.frequency - a.frequency);
    } else if (sortBy === "intensity") {
      copy.sort((a, b) => b.intensity - a.intensity);
    } else {
      copy.sort((a, b) => a.brand.localeCompare(b.brand));
    }
    return copy;
  }, [ads, sortBy]);

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {(["frequency", "intensity", "brand"] as const).map((option) => (
          <motion.button
            key={option}
            onClick={() => setSortBy(option)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              sortBy === option
                ? "bg-gradient-to-r from-blue-600 to-purple-600 text-white"
                : "bg-slate-700/50 text-slate-300 hover:bg-slate-700"
            }`}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            {option.charAt(0).toUpperCase() + option.slice(1)}
          </motion.button>
        ))}
      </div>

      <div className="grid auto-rows-max gap-2" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(80px, 1fr))" }}>
        {sortedAds.map((ad) => (
          <motion.div
            key={ad.id}
            layout
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            transition={{ duration: 0.2 }}
            className="group relative overflow-hidden rounded-lg cursor-pointer hover:z-10"
            onClick={() => setSelectedAd(selectedAd === ad.id ? null : ad.id)}
            style={{
              gridColumn: `span ${Math.ceil((ad.frequency / 100) * 2)}`,
              gridRow: `span ${Math.ceil((ad.intensity + 0.5) * 2)}`,
              minHeight: "80px",
            }}
          >
            <div
              className="w-full h-full flex items-center justify-center relative overflow-hidden"
              style={{ backgroundColor: ad.color + "40" }}
            >
              {/* Animated gradient background */}
              <motion.div
                className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity"
                style={{ backgroundColor: ad.color + "20" }}
              />

              <div className="relative z-10 text-center p-2">
                <div className="text-xs font-bold text-white truncate">{ad.brand}</div>
                <div className="text-9px text-slate-300 mt-1">{ad.frequency}x</div>
              </div>

              {/* Hover/Select overlay */}
              <motion.div
                initial={{ opacity: 0 }}
                whileHover={{ opacity: 1 }}
                animate={{ opacity: selectedAd === ad.id ? 1 : undefined }}
                className="absolute inset-0 bg-gradient-to-br from-white/20 to-black/20 flex items-center justify-center backdrop-blur-sm"
              >
                <div className="text-center">
                  <div className="text-xs font-semibold text-white mb-1">{ad.brand}</div>
                  <div className="text-9px text-slate-200">Frequency: {ad.frequency}x</div>
                  <div className="text-9px text-slate-200">Intensity: {(ad.intensity * 100).toFixed(0)}%</div>
                </div>
              </motion.div>

              {/* Border */}
              <div
                className={`absolute inset-0 rounded-lg border transition-all ${
                  selectedAd === ad.id ? "border-2" : "border"
                }`}
                style={{ borderColor: selectedAd === ad.id ? ad.color + "ff" : ad.color + "60" }}
              />
            </div>
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4 text-sm mt-6">
        <div className="bg-slate-700/30 rounded p-3 border border-slate-600/50">
          <div className="text-slate-400">Total Ads</div>
          <div className="text-lg font-bold text-slate-200">{ads.length}</div>
        </div>
        <div className="bg-slate-700/30 rounded p-3 border border-slate-600/50">
          <div className="text-slate-400">Avg Frequency</div>
          <div className="text-lg font-bold text-blue-400">
            {(ads.reduce((sum, a) => sum + a.frequency, 0) / ads.length).toFixed(0)}
          </div>
        </div>
      </div>
    </div>
  );
}
