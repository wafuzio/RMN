import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { BrandLogo } from "./BrandLogo";
import { Loader2, ArrowLeft } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { AdCard, Ad } from "./AdCard";

interface BrandDetail {
  brand: string;
  total_ads: number;
  retailer_ads: { [retailer: string]: number };
  last_seen: string;
  top_keywords: Array<{ keyword: string; count: number }>;
  top_competitors: Array<{ brand: string; keyword: string; count: number }>;
  monthly_activity: Array<{ month: string; count: number }>;
}

interface BrandDetailModalProps {
  brand: string;
  retailers: string[];
  onOpenChange: (open: boolean) => void;
}

type ViewState = { type: 'detail' } | { type: 'retailer-ads'; retailer: string } | { type: 'keyword-ads'; keyword: string };

export function BrandDetailModal({ brand, retailers, onOpenChange }: BrandDetailModalProps) {
  const [viewState, setViewState] = useState<ViewState>({ type: 'detail' });
  const [selectedCompetitors, setSelectedCompetitors] = useState<Set<string>>(new Set());
  const [competitorColorMap, setCompetitorColorMap] = useState<Map<string, string>>(new Map());

  const { data: brandDetail, isLoading, error } = useQuery({
    queryKey: ["brand-detail", brand, retailers],
    queryFn: async () => {
      const retailerParam = retailers.join(',');
      const response = await fetch(
        `/api/brand-details?brand=${encodeURIComponent(brand)}&retailers=${encodeURIComponent(retailerParam)}`
      );
      if (!response.ok) throw new Error("Failed to fetch brand details");
      return response.json() as Promise<BrandDetail>;
    },
  });

  const { data: competitorDetails } = useQuery({
    queryKey: ["competitor-details", Array.from(selectedCompetitors), retailers],
    queryFn: async () => {
      if (selectedCompetitors.size === 0) return {};

      const retailerParam = retailers.join(',');
      const details: Record<string, BrandDetail> = {};

      for (const competitorBrand of selectedCompetitors) {
        try {
          const response = await fetch(
            `/api/brand-details?brand=${encodeURIComponent(competitorBrand)}&retailers=${encodeURIComponent(retailerParam)}`
          );
          if (response.ok) {
            details[competitorBrand] = await response.json();
          }
        } catch (err) {
          console.error(`Failed to fetch competitor details for ${competitorBrand}:`, err);
        }
      }

      return details;
    },
    enabled: selectedCompetitors.size > 0,
  });

  const { data: filteredAds, isLoading: adsLoading } = useQuery({
    queryKey: ["brand-ads", brand, viewState],
    queryFn: async () => {
      if (viewState.type === 'detail') return null;

      const allAds: Ad[] = [];

      // Query each retailer (we know which ones have ads from retailer_ads)
      if (brandDetail?.retailer_ads) {
        for (const retailer of Object.keys(brandDetail.retailer_ads)) {
          // Skip retailers we don't want for retailer view
          if (viewState.type === 'retailer-ads' && viewState.retailer !== retailer) {
            continue;
          }

          try {
            const params = new URLSearchParams();
            params.set('retailer', retailer);
            params.set('client', 'all');
            params.set('advertiser', brand); // Filter by brand/advertiser directly

            if (viewState.type === 'keyword-ads') {
              params.set('term', viewState.keyword);
            }

            const response = await fetch(`/api/ads/cards?${params.toString()}`);
            if (response.ok) {
              const data = await response.json();
              allAds.push(...(data.cards || []));
            }
          } catch (err) {
            console.error(`Failed to fetch ads for ${retailer}:`, err);
          }
        }
      }

      return allAds;
    },
    enabled: viewState.type !== 'detail' && !!brandDetail,
  });

  const handleGoBack = () => setViewState({ type: 'detail' });

  const toggleCompetitor = (competitorBrand: string) => {
    setSelectedCompetitors(prev => {
      const newSet = new Set(prev);
      if (newSet.has(competitorBrand)) {
        newSet.delete(competitorBrand);
      } else {
        newSet.add(competitorBrand);
        // Assign a locked color to this competitor on first selection
        if (!competitorColorMap.has(competitorBrand)) {
          setCompetitorColorMap(prevMap => {
            const newMap = new Map(prevMap);
            const colorIndex = newMap.size;
            newMap.set(competitorBrand, competitorColors[colorIndex % competitorColors.length]);
            return newMap;
          });
        }
      }
      return newSet;
    });
  };

  // Color palette for competitors - colors that blend nicely with transparency
  const competitorColors = [
    '#e91e63', // Magenta/Pink
    '#fbbf24', // Amber/Yellow
    '#06b6d4', // Cyan
    '#f97316', // Orange
    '#a855f7', // Purple
    '#ec4899', // Rose
  ];

  const getCompetitorColor = (competitorBrand: string): string => {
    return competitorColorMap.get(competitorBrand) || competitorColors[0];
  };

  // Merge monthly activity data from brand and competitors
  const mergedMonthlyData = () => {
    if (!brandDetail?.monthly_activity) return [];

    // Start with brand's data
    const monthMap = new Map<string, Record<string, number>>();
    brandDetail.monthly_activity.forEach(item => {
      monthMap.set(item.month, { [brand]: item.count });
    });

    // Add competitor data
    if (competitorDetails) {
      Object.entries(competitorDetails).forEach(([compBrand, compDetail]) => {
        (compDetail.monthly_activity || []).forEach(item => {
          const existing = monthMap.get(item.month) || {};
          monthMap.set(item.month, { ...existing, [compBrand]: item.count });
        });
      });
    }

    // Convert to array
    return Array.from(monthMap.entries()).map(([month, data]) => ({
      month,
      ...data,
    }));
  };

  return (
    <Dialog open={true} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center gap-4">
            {viewState.type !== 'detail' && (
              <button
                onClick={handleGoBack}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                aria-label="Go back"
              >
                <ArrowLeft className="w-5 h-5 text-gray-700" />
              </button>
            )}
            <div className="h-16 w-16 flex-shrink-0">
              <BrandLogo brand={brand} className="h-14 w-14" />
            </div>
            <div>
              <DialogTitle className="text-2xl">{brand}</DialogTitle>
              {viewState.type === 'retailer-ads' && (
                <p className="text-sm text-gray-600 mt-1">{viewState.retailer} — All Ads</p>
              )}
              {viewState.type === 'keyword-ads' && (
                <p className="text-sm text-gray-600 mt-1">"{viewState.keyword}" — All Ads</p>
              )}
            </div>
          </div>
        </DialogHeader>

        {viewState.type !== 'detail' && adsLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
          </div>
        ) : viewState.type !== 'detail' && filteredAds ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {filteredAds.map((ad, idx) => (
                <div key={idx}>
                  <AdCard
                    ad={ad}
                    onRemove={() => {}}
                    onOpen={() => {}}
                  />
                </div>
              ))}
            </div>
          </div>
        ) : isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
          </div>
        ) : error ? (
          <div className="text-center py-8 text-red-600">
            Failed to load brand details
          </div>
        ) : brandDetail ? (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-blue-50 rounded-lg p-4">
                <p className="text-sm text-gray-600 font-medium">Total Ads</p>
                <p className="text-3xl font-bold text-blue-600 mt-2">{brandDetail.total_ads}</p>
              </div>
              <div className="bg-green-50 rounded-lg p-4">
                <p className="text-sm text-gray-600 font-medium">Last Seen</p>
                <p className="text-lg font-semibold text-green-700 mt-2">
                  {brandDetail.last_seen ? new Date(brandDetail.last_seen).toLocaleDateString() : "N/A"}
                </p>
              </div>
            </div>

            <div>
              <h3 className="text-lg font-bold text-gray-900 mb-3">Ads by Retailer</h3>
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(brandDetail.retailer_ads).map(([retailer, count]) => (
                  <button
                    key={retailer}
                    onClick={() => setViewState({ type: 'retailer-ads', retailer })}
                    className="bg-gray-50 hover:bg-gray-100 rounded-lg p-3 capitalize transition-colors text-left cursor-pointer"
                  >
                    <p className="text-sm text-gray-600">{retailer}</p>
                    <p className="text-2xl font-bold text-gray-900">{count}</p>
                  </button>
                ))}
              </div>
            </div>

            {brandDetail.top_keywords.length > 0 && (
              <div>
                <h3 className="text-lg font-bold text-gray-900 mb-3">Top Keywords</h3>
                <div className="space-y-2">
                  {brandDetail.top_keywords.map((item, idx) => (
                    <button
                      key={idx}
                      onClick={() => setViewState({ type: 'keyword-ads', keyword: item.keyword })}
                      className="w-full flex items-center justify-between bg-gray-50 hover:bg-gray-100 rounded-lg p-3 transition-colors text-left cursor-pointer"
                    >
                      <span className="font-medium text-gray-900">{item.keyword}</span>
                      <span className="text-sm text-gray-600 bg-white px-2 py-1 rounded">{item.count} ads</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {brandDetail.top_competitors.length > 0 && (
              <div>
                <h3 className="text-lg font-bold text-gray-900 mb-3">Top Competitors on Keywords</h3>
                <p className="text-xs text-gray-600 mb-2">Click a competitor to compare activity on the chart</p>
                <div className="space-y-2">
                  {brandDetail.top_competitors.map((item, idx) => {
                    const isSelected = selectedCompetitors.has(item.brand);
                    const color = getCompetitorColor(item.brand);
                    return (
                    <button
                      key={idx}
                      onClick={() => toggleCompetitor(item.brand)}
                      className="w-full flex items-center gap-3 rounded-lg p-2 text-sm transition-all hover:bg-gray-100"
                      style={isSelected ? {
                        backgroundColor: `${color}20`,
                        border: `2px solid ${color}`,
                      } : {
                        backgroundColor: '#f3f4f6',
                      }}
                    >
                      <div className="h-8 w-8 flex-shrink-0">
                        <BrandLogo brand={item.brand} className="h-8 w-8" />
                      </div>
                      <div className="flex-1 min-w-0 text-left">
                        <p className="font-medium text-gray-900">
                          {item.brand} <span className="text-gray-500 font-normal">— {item.keyword}</span>
                        </p>
                      </div>
                      <span className="text-gray-600 bg-white px-2 py-1 rounded text-xs flex-shrink-0">{item.count}</span>
                    </button>
                  );
                  })}
                </div>
              </div>
            )}

            {brandDetail.monthly_activity && brandDetail.monthly_activity.length > 0 && (
              <div>
                <h3 className="text-lg font-bold text-gray-900 mb-3">Ad Activity - Last 12 Months</h3>
                <div className="bg-gray-50 rounded-lg p-4">
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={mergedMonthlyData()} barGap={selectedCompetitors.size > 0 ? "-20%" : "10%"}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis
                        dataKey="month"
                        tick={{ fontSize: 12 }}
                        angle={-45}
                        textAnchor="end"
                        height={80}
                      />
                      <YAxis tick={{ fontSize: 12 }} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "#ffffff",
                          border: "1px solid #e5e7eb",
                          borderRadius: "6px"
                        }}
                        formatter={(value, name) => [value, name === brand ? `${brand} (Original)` : name]}
                      />
                      {/* Original brand in blue with transparency */}
                      <Bar
                        dataKey={brand}
                        fill="#3b82f6"
                        radius={[8, 8, 0, 0]}
                        fillOpacity={0.6}
                        name={brand}
                      />
                      {/* Competitors with distinct colors and transparency for blending */}
                      {Array.from(selectedCompetitors).map((competitorBrand) => (
                        <Bar
                          key={competitorBrand}
                          dataKey={competitorBrand}
                          fill={getCompetitorColor(competitorBrand)}
                          radius={[8, 8, 0, 0]}
                          fillOpacity={0.6}
                          name={competitorBrand}
                        />
                      ))}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
