import { RequestHandler } from "express";

const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006";

export const handleAdsCount: RequestHandler = async (req, res) => {
  const { retailer, client, term, advertiser, brands, types, start, end, search } = req.query;

  if (!retailer || !client) {
    console.warn("[ads-count] Missing required parameters", { retailer, client });
    return res.status(400).json({ error: "retailer and client are required" });
  }

  // Build Flask URL with all query parameters
  const params = new URLSearchParams();
  params.set("retailer", String(retailer));
  params.set("client", String(client));
  if (term) params.set("term", String(term));
  if (advertiser) params.set("advertiser", String(advertiser));
  if (brands) params.set("brands", String(brands));
  if (types) params.set("types", String(types));
  if (start) params.set("start", String(start));
  if (end) params.set("end", String(end));
  if (search) params.set("search", String(search));

  const flaskUrl = `${FLASK_BASE_URL}/api/ads/count?${params.toString()}`;

  try {
    console.debug("[ads-count] Proxying request to Flask", {
      retailer,
      client,
      hasDateFilter: !!(start || end),
    });

    const response = await fetch(flaskUrl);

    if (!response.ok) {
      console.error("[ads-count] Flask returned non-OK status", {
        status: response.status,
        statusText: response.statusText,
      });
      return res.status(response.status).json({
        error: `Failed to fetch ad count from Flask: ${response.statusText}`,
      });
    }

    const data = await response.json();
    console.debug("[ads-count] Successfully fetched count from Flask", {
      total: (data as any).total || 0,
    });
    res.json(data);
  } catch (error) {
    console.error("[ads-count] Error proxying request", {
      flaskUrl: flaskUrl.split("?")[0],
      message: error instanceof Error ? error.message : String(error),
    });
    res.status(500).json({ error: "Failed to fetch ad count from Flask backend" });
  }
};
