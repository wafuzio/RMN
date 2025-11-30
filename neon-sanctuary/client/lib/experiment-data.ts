/**
 * Shared realistic data for experiments based on actual scraper output structure.
 * This provides consistent dummy data that mirrors real ad monitoring data.
 */

// Real retailers from the scraper
export const RETAILERS = ["Amazon", "Walmart", "Kroger", "Target", "Instacart"] as const;
export type Retailer = typeof RETAILERS[number];

// Real clients/brands from the scraper
export const BRANDS = [
  "Halo Top",
  "Proactiv", 
  "Land O Frost",
  "Curology",
  "Orgain",
  "Blue Bunny",
  "Boost",
  "Sour Cream",
] as const;
export type Brand = typeof BRANDS[number];

// Ad types from the scraper
export const AD_TYPES = ["TOA", "Skyscraper", "Carousel", "SBV", "SP"] as const;
export type AdType = typeof AD_TYPES[number];

// Placements
export const PLACEMENTS = ["Top of Search", "Side Rail", "In-Grid", "Product Detail", "Homepage"] as const;
export type Placement = typeof PLACEMENTS[number];

// Keywords from actual scraper runs
export const KEYWORDS = [
  "ice cream",
  "acne treatment", 
  "lunch meat",
  "protein powder",
  "skincare",
  "frozen dessert",
  "nutritional drink",
  "dairy",
] as const;

// Generate realistic ad activity data
export interface AdActivity {
  brand: Brand;
  retailer: Retailer;
  adType: AdType;
  placement: Placement;
  keyword: string;
  frequency: number;
  date: string;
  impressions: number;
}

// Generate 60 days of activity data
export function generateActivityData(days: number = 60): AdActivity[] {
  const activities: AdActivity[] = [];
  const now = new Date();
  
  for (let d = 0; d < days; d++) {
    const date = new Date(now);
    date.setDate(date.getDate() - d);
    const dateStr = date.toISOString().split('T')[0];
    
    // Each brand has varying activity per day
    BRANDS.forEach((brand, brandIdx) => {
      // Simulate varying activity levels
      const baseActivity = 2 + Math.sin(d / 7 * Math.PI) * 2;
      const numAds = Math.floor(baseActivity + Math.random() * 3);
      
      for (let a = 0; a < numAds; a++) {
        const retailer = RETAILERS[(brandIdx + a) % RETAILERS.length];
        const adType = AD_TYPES[Math.floor(Math.random() * AD_TYPES.length)];
        const placement = PLACEMENTS[Math.floor(Math.random() * PLACEMENTS.length)];
        const keyword = KEYWORDS[brandIdx % KEYWORDS.length];
        
        activities.push({
          brand,
          retailer,
          adType,
          placement,
          keyword,
          frequency: Math.floor(10 + Math.random() * 90),
          date: dateStr,
          impressions: Math.floor(1000 + Math.random() * 50000),
        });
      }
    });
  }
  
  return activities;
}

// Brand-Retailer connection data for constellation map
export interface BrandRetailerEdge {
  brand: Brand;
  retailer: Retailer;
  frequency: number;
  adTypes: AdType[];
  startDay: number;
  endDay: number;
}

export function generateBrandRetailerConnections(): BrandRetailerEdge[] {
  const edges: BrandRetailerEdge[] = [];
  
  BRANDS.forEach((brand, brandIdx) => {
    // Each brand connects to 2-4 retailers
    const numConnections = 2 + Math.floor(Math.random() * 3);
    const shuffledRetailers = [...RETAILERS].sort(() => Math.random() - 0.5);
    
    for (let i = 0; i < numConnections; i++) {
      const retailer = shuffledRetailers[i];
      const startDay = Math.floor(Math.random() * 30);
      const duration = 20 + Math.floor(Math.random() * 40);
      
      edges.push({
        brand,
        retailer,
        frequency: 20 + Math.floor(Math.random() * 80),
        adTypes: AD_TYPES.slice(0, 1 + Math.floor(Math.random() * 3)) as AdType[],
        startDay,
        endDay: Math.min(60, startDay + duration),
      });
    }
  });
  
  return edges;
}

// Share of Voice data
export interface SOVData {
  retailer: Retailer;
  sov: number;
  trend: "up" | "down" | "stable";
  adCount: number;
}

export function generateSOVData(): SOVData[] {
  const total = 100;
  let remaining = total;
  const trends: Array<"up" | "down" | "stable"> = ["up", "down", "stable"];
  
  return RETAILERS.map((retailer, idx) => {
    const isLast = idx === RETAILERS.length - 1;
    const sov = isLast ? remaining : Math.floor(remaining * (0.2 + Math.random() * 0.3));
    remaining -= sov;
    
    return {
      retailer,
      sov,
      trend: trends[Math.floor(Math.random() * 3)],
      adCount: Math.floor(50 + Math.random() * 200),
    };
  }).sort((a, b) => b.sov - a.sov);
}

// Heatmap data for intensity timeline
export interface HeatmapCell {
  retailer: Retailer;
  day: number;
  intensity: number;
  adCount: number;
}

export function generateHeatmapData(days: number = 60): HeatmapCell[] {
  const cells: HeatmapCell[] = [];
  
  RETAILERS.forEach((retailer, rIdx) => {
    for (let day = 0; day < days; day++) {
      // Create wave patterns with some randomness
      const wave = Math.sin((day + rIdx * 5) / 10 * Math.PI) * 30;
      const noise = Math.random() * 20;
      const base = 40 + rIdx * 5;
      
      cells.push({
        retailer,
        day,
        intensity: Math.max(0, Math.min(100, base + wave + noise)),
        adCount: Math.floor(5 + Math.random() * 30),
      });
    }
  });
  
  return cells;
}

// Funnel data for inventory capture
export interface FunnelStage {
  name: string;
  total: number;
  captured: number;
  competitors: number;
}

export function generateFunnelData(): FunnelStage[] {
  return [
    { name: "Total Inventory", total: 1000, captured: 350, competitors: 450 },
    { name: "Visible Placements", total: 800, captured: 280, competitors: 380 },
    { name: "Premium Positions", total: 400, captured: 150, competitors: 180 },
    { name: "Top of Search", total: 150, captured: 55, competitors: 70 },
    { name: "Featured Spots", total: 50, captured: 18, competitors: 25 },
  ];
}

// Timeline pulse data
export interface PulseEvent {
  retailer: Retailer;
  timestamp: number;
  intensity: number;
  adType: AdType;
}

export function generatePulseData(hours: number = 24): PulseEvent[] {
  const events: PulseEvent[] = [];
  
  for (let h = 0; h < hours; h++) {
    RETAILERS.forEach((retailer) => {
      // More activity during business hours
      const hourOfDay = h % 24;
      const isBusinessHours = hourOfDay >= 8 && hourOfDay <= 20;
      const baseIntensity = isBusinessHours ? 60 : 20;
      
      if (Math.random() > 0.3) {
        events.push({
          retailer,
          timestamp: h,
          intensity: baseIntensity + Math.random() * 40,
          adType: AD_TYPES[Math.floor(Math.random() * AD_TYPES.length)],
        });
      }
    });
  }
  
  return events;
}

// Radar metrics for competitive analysis
export interface RadarMetrics {
  entity: string;
  metrics: {
    shareOfVoice: number;
    creativeDiversity: number;
    retailPenetration: number;
    frequencyIntensity: number;
    timeDominance: number;
    seasonality: number;
  };
}

export function generateRadarData(): RadarMetrics[] {
  return [
    {
      entity: "Your Brand",
      metrics: {
        shareOfVoice: 65 + Math.random() * 20,
        creativeDiversity: 70 + Math.random() * 15,
        retailPenetration: 80 + Math.random() * 15,
        frequencyIntensity: 55 + Math.random() * 25,
        timeDominance: 60 + Math.random() * 20,
        seasonality: 45 + Math.random() * 30,
      },
    },
    {
      entity: "Competitor A",
      metrics: {
        shareOfVoice: 45 + Math.random() * 25,
        creativeDiversity: 50 + Math.random() * 20,
        retailPenetration: 60 + Math.random() * 20,
        frequencyIntensity: 65 + Math.random() * 20,
        timeDominance: 40 + Math.random() * 25,
        seasonality: 55 + Math.random() * 25,
      },
    },
    {
      entity: "Competitor B",
      metrics: {
        shareOfVoice: 35 + Math.random() * 20,
        creativeDiversity: 40 + Math.random() * 25,
        retailPenetration: 45 + Math.random() * 25,
        frequencyIntensity: 50 + Math.random() * 25,
        timeDominance: 55 + Math.random() * 20,
        seasonality: 35 + Math.random() * 30,
      },
    },
  ];
}

// Supply chain flow data
export interface FlowConnection {
  from: string;
  to: string;
  value: number;
  layer: number;
}

export function generateSupplyChainData(): {
  nodes: Array<{ id: string; layer: number; value: string; count: number }>;
  connections: FlowConnection[];
} {
  const nodes = [
    ...RETAILERS.map((r) => ({ id: r, layer: 0, value: r, count: Math.floor(50 + Math.random() * 100) })),
    ...PLACEMENTS.map((p) => ({ id: p, layer: 1, value: p, count: Math.floor(30 + Math.random() * 70) })),
    ...AD_TYPES.map((t) => ({ id: t, layer: 2, value: t, count: Math.floor(20 + Math.random() * 50) })),
    ...BRANDS.slice(0, 5).map((b) => ({ id: b, layer: 3, value: b, count: Math.floor(10 + Math.random() * 40) })),
  ];

  const connections: FlowConnection[] = [];

  // Retailers → Placements
  RETAILERS.forEach((r) => {
    PLACEMENTS.slice(0, 2 + Math.floor(Math.random() * 3)).forEach((p) => {
      connections.push({ from: r, to: p, value: Math.floor(10 + Math.random() * 40), layer: 0 });
    });
  });

  // Placements → Ad Types
  PLACEMENTS.forEach((p) => {
    AD_TYPES.slice(0, 2 + Math.floor(Math.random() * 2)).forEach((t) => {
      connections.push({ from: p, to: t, value: Math.floor(5 + Math.random() * 25), layer: 1 });
    });
  });

  // Ad Types → Brands
  AD_TYPES.forEach((t) => {
    BRANDS.slice(0, 3 + Math.floor(Math.random() * 2)).forEach((b) => {
      connections.push({ from: t, to: b, value: Math.floor(3 + Math.random() * 15), layer: 2 });
    });
  });

  return { nodes, connections };
}

// Mosaic tile data
export interface MosaicTile {
  id: number;
  brand: Brand;
  retailer: Retailer;
  adType: AdType;
  frequency: number;
  intensity: number;
  color: string;
}

const TILE_COLORS = ["#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#06b6d4", "#ef4444", "#84cc16"];

export function generateMosaicData(): MosaicTile[] {
  return Array.from({ length: 24 }, (_, i) => ({
    id: i,
    brand: BRANDS[i % BRANDS.length],
    retailer: RETAILERS[i % RETAILERS.length],
    adType: AD_TYPES[i % AD_TYPES.length],
    frequency: Math.floor(10 + Math.random() * 90),
    intensity: Math.random(),
    color: TILE_COLORS[i % TILE_COLORS.length],
  }));
}

// Wind tunnel / keyword pressure data
export interface KeywordPressure {
  keyword: string;
  yourPressure: number;
  competitorPressure: number;
  trend: number;
}

export function generateKeywordPressureData(): KeywordPressure[] {
  return KEYWORDS.map((keyword) => ({
    keyword,
    yourPressure: 30 + Math.random() * 50,
    competitorPressure: 20 + Math.random() * 60,
    trend: -20 + Math.random() * 40,
  }));
}
