import { RequestHandler } from "express";

const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006";

export interface AdsStatsResponse {
  total_cards: number;
  total_brands: number;
  top_brand?: string;
  top_brand_sov?: number;
  cards_by_date: Record<string, number>;
}

export const handleAdsStats: RequestHandler = async (req, res) => {
  try {
    const retailers = (req.query.retailers as string)?.split(",").filter(Boolean) || [];
    const clients = (req.query.clients as string)?.split(",").filter(Boolean) || [];
    const { term, advertiser, start, end, types, brands, search } = req.query;

    if (!retailers.length || !clients.length) {
      return res.status(400).json({
        error: "retailers and clients parameters are required (comma-separated)",
      });
    }

    console.debug("[ads-stats] Processing stats request", {
      retailers,
      clients,
      hasDateFilter: !!(start || end),
    });

    // Fetch all cards (with higher page size) to compute stats
    const results: Record<
      string,
      {
        cards: any[];
        total_cards: number;
      }
    > = {};

    const promises = [];

    for (const retailer of retailers) {
      for (const client of clients) {
        const promise = (async () => {
          const params = new URLSearchParams();
          params.set("retailer", retailer);
          params.set("client", client);
          params.set("page", "1");
          params.set("page_size", "1000"); // Get more data for stats
          if (term) params.set("term", String(term));
          if (advertiser) params.set("advertiser", String(advertiser));
          if (start) params.set("start", String(start));
          if (end) params.set("end", String(end));
          if (types) params.set("types", String(types));
          if (brands) params.set("brands", String(brands));
          if (search) params.set("search", String(search));

          const flaskUrl = `${FLASK_BASE_URL}/api/ads/cards?${params.toString()}`;
          const key = `${retailer}:${client}`;

          try {
            const response = await fetch(flaskUrl, {
              headers: {
                "Accept": "application/json",
                "ngrok-skip-browser-warning": "true",
              },
            });
            if (!response.ok) {
              const errorText = await response.text().catch(() => '');
              console.warn("[ads-stats] Flask error for", {
                key,
                status: response.status,
                statusText: response.statusText,
                errorText: errorText.substring(0, 200),
              });
              results[key] = { cards: [], total_cards: 0 };
              return;
            }

            const data = await response.json();
            results[key] = {
              cards: data.cards || [],
              total_cards: data.total_cards || 0,
            };
          } catch (error) {
            const errorMessage = error instanceof Error ? error.message : String(error);
            const errorName = error instanceof Error ? error.name : 'Unknown';
            console.warn("[ads-stats] Fetch error for", {
              key,
              flaskUrl: flaskUrl.split("?")[0],
              errorName,
              errorMessage,
            });
            results[key] = { cards: [], total_cards: 0 };
          }
        })();

        promises.push(promise);
      }
    }

    await Promise.all(promises);

    // Aggregate stats from all results
    const allCards = Object.values(results).flatMap((r) => r.cards);
    const totalCards = Object.values(results).reduce(
      (sum, r) => sum + r.total_cards,
      0
    );

    // Count unique brands
    const brandSet = new Set<string>();
    const brandCounts: Record<string, number> = {};

    for (const card of allCards) {
      if (card.brand && card.brand !== "Unknown") {
        brandSet.add(card.brand);
        brandCounts[card.brand] = (brandCounts[card.brand] || 0) + 1;
      }
    }

    // Find top brand by count (simplified SOV)
    let topBrand: string | undefined;
    let topBrandSov = 0;

    for (const [brand, count] of Object.entries(brandCounts)) {
      if (count > topBrandSov) {
        topBrand = brand;
        topBrandSov = count;
      }
    }

    // Count cards by date
    const cardsByDate: Record<string, number> = {};
    for (const card of allCards) {
      const date =
        card.run_date || (card.timestamp ? card.timestamp.split(" ")[0] : null);
      if (date) {
        cardsByDate[date] = (cardsByDate[date] || 0) + 1;
      }
    }

    const stats: AdsStatsResponse = {
      total_cards: totalCards,
      total_brands: brandSet.size,
      top_brand: topBrand,
      top_brand_sov: topBrandSov,
      cards_by_date: cardsByDate,
    };

    console.debug("[ads-stats] Stats computed", {
      total_cards: stats.total_cards,
      total_brands: stats.total_brands,
      top_brand: stats.top_brand,
    });

    res.json(stats);
  } catch (error) {
    console.error("[ads-stats] Error", {
      message: error instanceof Error ? error.message : String(error),
    });
    res.status(500).json({ error: "Failed to fetch ads stats" });
  }
};
