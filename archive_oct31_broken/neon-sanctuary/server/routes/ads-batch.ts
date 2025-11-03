import { RequestHandler } from "express";

const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006";

export interface BatchAdsRequest {
  retailers: string[];
  clients: string[];
  page?: number;
  page_size?: number;
  term?: string;
  advertiser?: string;
  start?: string;
  end?: string;
  types?: string[];
  brands?: string[];
  search?: string;
}

export interface BatchAdsResponse {
  [key: string]: {
    cards: any[];
    has_more: boolean;
    total_cards: number;
  };
}

export const handleAdsBatch: RequestHandler = async (req, res) => {
  try {
    const retailers = (req.query.retailers as string)?.split(",").filter(Boolean) || [];
    const clients = (req.query.clients as string)?.split(",").filter(Boolean) || [];
    const page = parseInt(req.query.page as string) || 1;
    const page_size = parseInt(req.query.page_size as string) || 24;
    const { term, advertiser, start, end, types, brands, search } = req.query;

    if (!retailers.length || !clients.length) {
      return res.status(400).json({
        error: "retailers and clients parameters are required (comma-separated)",
      });
    }

    console.debug("[ads-batch] Processing batch request", {
      retailers,
      clients,
      page,
      page_size,
      hasDateFilter: !!(start || end),
    });

    // Fetch data for each retailer/client combination in parallel
    const results: BatchAdsResponse = {};
    const promises = [];

    for (const retailer of retailers) {
      for (const client of clients) {
        const promise = (async () => {
          const params = new URLSearchParams();
          params.set("retailer", retailer);
          params.set("client", client);
          params.set("page", String(page));
          params.set("page_size", String(page_size));
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
              console.warn("[ads-batch] Flask error for", {
                key,
                status: response.status,
                statusText: response.statusText,
                errorText: errorText.substring(0, 200),
              });
              results[key] = { cards: [], has_more: false, total_cards: 0 };
              return;
            }

            const data = await response.json();
            results[key] = data;
          } catch (error) {
            const errorMessage = error instanceof Error ? error.message : String(error);
            const errorName = error instanceof Error ? error.name : 'Unknown';
            console.error("[ads-batch] Fetch error for", {
              key,
              flaskUrl: flaskUrl.split("?")[0],
              errorName,
              errorMessage,
            });
            results[key] = { cards: [], has_more: false, total_cards: 0 };
          }
        })();

        promises.push(promise);
      }
    }

    // Wait for all requests to complete
    await Promise.all(promises);

    console.debug("[ads-batch] Batch response ready", {
      keys: Object.keys(results),
      totalCards: Object.values(results).reduce(
        (sum: number, r: any) => sum + (r.cards?.length || 0),
        0
      ),
    });

    res.json(results);
  } catch (error) {
    console.error("[ads-batch] Error", {
      message: error instanceof Error ? error.message : String(error),
    });
    res.status(500).json({ error: "Failed to fetch batch ads" });
  }
};
