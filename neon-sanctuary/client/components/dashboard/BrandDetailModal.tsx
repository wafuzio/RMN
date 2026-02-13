import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { BrandLogo } from "./BrandLogo";
import { Loader2, ArrowLeft } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { AdCard, Ad } from "./AdCard";
import { toLocalImageUrl } from "@/utils/imageUrl";
import { formatLocal } from "@/lib/date";
import { aggregateAds } from "@/lib/aggregateAds";
import { AdCardGroup } from "./AdCardGroup";

interface BrandDetail {
  brand: string;
  total_ads: number;
  retailer_ads: { [retailer: string]: number };
  last_seen: string;
  top_keywords: Array<{ keyword: string; count: number }>;
  top_competitors: Array<{
    brand: string;
    total: number;
    keywords: { [keyword: string]: number };
  }>;
  monthly_activity: Array<{ month: string; count: number }>;
}

interface BrandDetailModalProps {
  brand: string;
  retailers: string[];
  onOpenChange: (open: boolean) => void;
}

type ViewState = { type: 'detail' } | { type: 'retailer-ads'; retailer: string } | { type: 'keyword-ads'; keyword: string } | { type: 'ad-fullsize'; ad: Ad };

export function BrandDetailModal({ brand, retailers, onOpenChange }: BrandDetailModalProps) {
  const [viewState, setViewState] = useState<ViewState>({ type: 'detail' });
  const [previousViewState, setPreviousViewState] = useState<ViewState>({ type: 'detail' });
  const [selectedCompetitors, setSelectedCompetitors] = useState<Set<string>>(new Set());
  const [competitorColorMap, setCompetitorColorMap] = useState<Map<string, string>>(new Map());
  const [imageZoom, setImageZoom] = useState(100);
  const [showZoomedImage, setShowZoomedImage] = useState(false);
  const [adsPage, setAdsPage] = useState(1);
  const [accumulatedAds, setAccumulatedAds] = useState<Ad[]>([]);
  const [adsTotalCards, setAdsTotalCards] = useState(0);
  const prevViewStateRef = useRef(viewState);

  // Reset accumulated ads when view state changes
  useEffect(() => {
    if (prevViewStateRef.current !== viewState) {
      setAdsPage(1);
      setAccumulatedAds([]);
      setAdsTotalCards(0);
      prevViewStateRef.current = viewState;
    }
  }, [viewState]);

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
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes
  });

  const { data: competitorDetails } = useQuery({
    queryKey: ["competitor-details", Array.from(selectedCompetitors), retailers, brandDetail?.top_keywords],
    queryFn: async () => {
      if (selectedCompetitors.size === 0 || !brandDetail?.top_keywords) return {};

      const retailerParam = retailers.join(',');
      const keywordsParam = brandDetail.top_keywords.map(k => k.keyword).join(',');

      // Fetch all competitor details in parallel
      const competitorPromises = Array.from(selectedCompetitors).map(async (competitorBrand) => {
        try {
          const response = await fetch(
            `/api/brand-details?brand=${encodeURIComponent(competitorBrand)}&retailers=${encodeURIComponent(retailerParam)}&keywords=${encodeURIComponent(keywordsParam)}`
          );
          if (response.ok) {
            const data = await response.json();
            return { brand: competitorBrand, data };
          }
        } catch (err) {
          console.error(`Failed to fetch competitor details for ${competitorBrand}:`, err);
        }
        return null;
      });

      const results = await Promise.all(competitorPromises);
      const details: Record<string, BrandDetail> = {};
      results.forEach(result => {
        if (result) {
          details[result.brand] = result.data;
        }
      });

      return details;
    },
    enabled: selectedCompetitors.size > 0 && !!brandDetail?.top_keywords,
  });

  // Fetch a single page of ads at a time instead of exhaustively loading all pages
  const { data: adsPageData, isLoading: adsLoading, isFetching: adsFetching } = useQuery({
    queryKey: ["brand-ads", brand, viewState, adsPage],
    queryFn: async () => {
      if (viewState.type === 'detail') return null;

      // Determine which retailer to query
      let retailer: string | undefined;
      if (viewState.type === 'retailer-ads') {
        retailer = viewState.retailer;
      } else if (brandDetail?.retailer_ads) {
        // For keyword-ads, pick the first retailer (or query all)
        const retailers = Object.keys(brandDetail.retailer_ads);
        retailer = retailers.length === 1 ? retailers[0] : retailers[0];
      }
      if (!retailer) return null;

      const params = new URLSearchParams();
      params.set('retailer', retailer);
      params.set('client', 'all');
      params.set('advertiser', brand);
      params.set('page', String(adsPage));
      params.set('page_size', '48');

      if (viewState.type === 'keyword-ads') {
        params.set('term', viewState.keyword);
      }

      const response = await fetch(`/api/ads/cards?${params.toString()}`);
      if (!response.ok) return null;
      return response.json();
    },
    enabled: viewState.type !== 'detail' && !!brandDetail,
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });

  // Accumulate ads as pages are loaded
  useEffect(() => {
    if (adsPageData?.cards) {
      setAdsTotalCards(adsPageData.total_cards || 0);
      if (adsPage === 1) {
        setAccumulatedAds(adsPageData.cards);
      } else {
        setAccumulatedAds(prev => [...prev, ...adsPageData.cards]);
      }
    }
  }, [adsPageData, adsPage]);

  const filteredAds = accumulatedAds.length > 0 ? accumulatedAds : null;
  const hasMoreAds = adsPageData?.has_more ?? false;

  const loadMoreAds = useCallback(() => {
    setAdsPage(p => p + 1);
  }, []);

  // Aggregate ads for grouped display
  const aggregatedAds = useMemo(() => {
    if (!filteredAds || filteredAds.length === 0) return [];
    return aggregateAds(filteredAds);
  }, [filteredAds]);

  // Unique counts will be shown after clicking into a retailer's ads (when aggregatedAds is populated)

  const handleGoBack = () => setViewState(previousViewState);
  const handleOpenAdFullsize = (ad: Ad) => {
    setPreviousViewState(viewState);
    setViewState({ type: 'ad-fullsize', ad });
    setImageZoom(100);
    setShowZoomedImage(false);
  };
  const handleCloseAdFullsize = () => {
    setViewState(previousViewState);
    setImageZoom(100);
    setShowZoomedImage(false);
  };
  const handleImageZoom = (e: React.WheelEvent) => {
    e.preventDefault();
    const zoomAmount = e.deltaY > 0 ? -10 : 10;
    setImageZoom(prev => Math.max(100, Math.min(500, prev + zoomAmount)));
  };

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
    <>
    <Dialog open={true} onOpenChange={onOpenChange}>
      <DialogContent className={viewState.type === 'ad-fullsize' ? "sm:max-w-6xl max-h-[95vh] overflow-y-auto" : "sm:max-w-4xl max-h-[90vh] overflow-y-auto"}>
        {viewState.type !== 'ad-fullsize' && (
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
                <BrandLogo brand={brand} size={56} className="h-14 w-14" />
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
        )}

        {viewState.type === 'ad-fullsize' && viewState.ad ? (
          <div className="space-y-4">
            <button
              onClick={handleCloseAdFullsize}
              className="flex items-center gap-2 p-2 hover:bg-gray-100 rounded-lg transition-colors mb-4"
              aria-label="Go back to ads"
            >
              <ArrowLeft className="w-5 h-5 text-gray-700" />
              <span className="text-sm font-medium text-gray-700">Back to Ads</span>
            </button>
            <div className="grid md:grid-cols-2 gap-6 bg-gray-50 p-6 rounded-lg">
              <div className="flex items-center justify-center rounded-lg overflow-hidden bg-white cursor-pointer hover:bg-gray-100 transition-colors" onClick={() => { setShowZoomedImage(true); setImageZoom(100); }}>
                <img
                  src={toLocalImageUrl(viewState.ad.image_url)}
                  alt={`${viewState.ad.brand} full`}
                  className="w-full h-full object-contain max-h-[600px]"
                  crossOrigin="anonymous"
                  referrerPolicy="no-referrer"
                />
              </div>
              <div className="space-y-3 flex flex-col justify-center">
                <h3 className="text-3xl font-bold">{viewState.ad.brand}</h3>
                <div className="text-sm text-gray-600">{viewState.ad.retailer} • {viewState.ad.ad_type}</div>
                <div className="text-sm"><span className="font-semibold">Keyword:</span> {viewState.ad.keyword}</div>
                <div className="text-sm"><span className="font-semibold">Client:</span> {viewState.ad.client}</div>
                <div className="text-sm"><span className="font-semibold">Date:</span> {formatLocal(viewState.ad.timestamp)}</div>
                <div className="pt-4 flex gap-2">
                  <Button onClick={async () => {
                    try {
                      const response = await fetch(toLocalImageUrl(viewState.ad.image_url));
                      const blob = await response.blob();
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `${viewState.ad.brand}-${viewState.ad.ad_type}.png`;
                      a.click();
                      URL.revokeObjectURL(url);
                    } catch (error) {
                      console.error('Failed to download image:', error);
                    }
                  }}>Download</Button>
                </div>
              </div>
            </div>
          </div>
        ) : viewState.type !== 'detail' && adsLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
          </div>
        ) : viewState.type !== 'detail' && aggregatedAds ? (
          <div className="space-y-4">
            <div className="text-sm text-gray-500 mb-2">
              Showing {accumulatedAds.length} of {adsTotalCards} ads
            </div>
            <div className="modal-content-box flex flex-col gap-4">
              {aggregatedAds.map((item, idx) => (
                <div key={idx}>
                  {item.count > 1 ? (
                    <AdCardGroup
                      group={item}
                      onRemove={() => {}}
                      onOpen={() => handleOpenAdFullsize(item.cover as any)}
                    />
                  ) : (
                    <div className="cursor-pointer" onClick={() => handleOpenAdFullsize(item.cover as any)}>
                      <AdCard
                        ad={item.cover as any}
                        onRemove={() => {}}
                        onOpen={() => handleOpenAdFullsize(item.cover as any)}
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
            {hasMoreAds && (
              <div className="flex justify-center pt-4">
                <Button
                  onClick={loadMoreAds}
                  disabled={adsFetching}
                  variant="outline"
                  className="w-full max-w-xs"
                >
                  {adsFetching ? (
                    <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading...</>
                  ) : (
                    `Load More (${accumulatedAds.length} of ${adsTotalCards})`
                  )}
                </Button>
              </div>
            )}
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
                    const keywordList = Object.entries(item.keywords)
                      .sort((a, b) => b[1] - a[1])
                      .map(([kw, count]) => `${kw}: ${count}`)
                      .join(', ');

                    return (
                    <div key={idx} className="relative group">
                      <button
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
                          <BrandLogo brand={item.brand} size={32} className="h-8 w-8" />
                        </div>
                        <div className="flex-1 min-w-0 text-left">
                          <p className="font-medium text-gray-900">
                            {item.brand}
                          </p>
                        </div>
                        <span className="text-gray-600 bg-white px-2 py-1 rounded text-xs flex-shrink-0">{item.total}</span>
                      </button>

                      {/* Keyword breakdown tooltip */}
                      <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block bg-gray-900 text-white text-xs rounded-lg p-3 whitespace-nowrap z-50">
                        <div className="font-semibold mb-1">Keywords:</div>
                        <div>{keywordList}</div>
                      </div>
                    </div>
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

    {showZoomedImage && viewState.type === 'ad-fullsize' && viewState.ad && (
      <div
        className="fixed inset-0 z-[9999] bg-black/95 flex items-center justify-center overflow-auto cursor-zoom-out"
        onClick={() => setShowZoomedImage(false)}
        onWheel={handleImageZoom}
      >
        <div className="absolute top-4 right-4 text-white text-sm font-medium bg-black/50 px-3 py-2 rounded pointer-events-none">
          {imageZoom}% • Scroll to zoom • Click to close
        </div>
        <img
          src={toLocalImageUrl(viewState.ad.image_url)}
          alt={`${viewState.ad.brand} zoomed`}
          className="m-auto"
          style={{
            width: `${imageZoom}%`,
            height: 'auto',
            maxHeight: '100vh',
            maxWidth: '100vw',
            objectFit: 'contain',
          }}
          crossOrigin="anonymous"
          referrerPolicy="no-referrer"
          onClick={(e) => e.stopPropagation()}
        />
      </div>
    )}
    </>
  );
}
