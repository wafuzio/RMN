/**
 * Shared code between client and server
 * Useful to share types between client and server
 * and/or small pure JS functions that can be used on both client and server
 */

/**
 * Example response type for /api/demo
 */
export interface DemoResponse {
  message: string;
}

// Shared API types
export type Retailer = "kroger" | "instacart" | "walmart" | "amazon";

export interface RetailersResponse { 
  retailers: string[]; 
  count: number; 
}

export interface ClientsResponse { 
  clients: string[]; 
  count: number; 
}

export interface AdCardItem {
  retailer: string;
  client: string;
  keyword: string;
  ad_type: string;
  brand: string | null;
  message: string;
  image_url: string;
  video_url?: string;
  timestamp: string; // YYYY-MM-DD HH:MM:SS
  run_date?: string;
  run_file?: string; // JSON file path for this ad
  ad_index?: number; // Index of ad within its run
  brand_logo_url?: string | null;
  brand_canonical?: string | null;
}

export interface AdsCardsResponse {
  cards: AdCardItem[];
  has_more: boolean;
  total_cards: number;
}

export interface BatchAdsResponse {
  [key: string]: {
    cards: AdCardItem[];
    has_more: boolean;
    total_cards: number;
  };
}

export interface AdsStatsResponse {
  total_cards: number;
  total_brands: number;
  top_brand?: string;
  top_brand_sov?: number;
  cards_by_date: Record<string, number>;
}
