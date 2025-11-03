import { RequestHandler } from "express";

const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006";

export const handleAdsProxy: RequestHandler = async (req, res) => {
  const { retailer, client, page, page_size, term, advertiser, start, end, types, brands, search } = req.query;

  if (!retailer || !client) {
    console.warn("[ads-proxy] Missing required parameters", { retailer, client });
    return res.status(400).json({ error: "retailer and client are required" });
  }

  // Build Flask URL with all query parameters
  const params = new URLSearchParams();
  params.set("retailer", String(retailer));
  params.set("client", String(client));
  if (page) params.set("page", String(page));
  if (page_size) params.set("page_size", String(page_size));
  if (term) params.set("term", String(term));
  if (advertiser) params.set("advertiser", String(advertiser));
  if (start) params.set("start", String(start));
  if (end) params.set("end", String(end));
  if (types) params.set("types", String(types));
  if (brands) params.set("brands", String(brands));
  if (search) params.set("search", String(search));

  const flaskUrl = `${FLASK_BASE_URL}/api/ads/cards?${params.toString()}`;

  try {
    console.debug("[ads-proxy] Proxying request to Flask", {
      flaskUrl: flaskUrl.replace(/[?&](retailer|client)=[^&]*/g, "..."),
      hasDateFilter: !!(start || end),
      start,
      end,
    });

    const response = await fetch(flaskUrl, {
      headers: {
        "Accept": "application/json",
        "ngrok-skip-browser-warning": "true",
      },
    });

    if (!response.ok) {
      const errorText = await response.text().catch(() => '');
      console.error("[ads-proxy] Flask returned non-OK status", {
        status: response.status,
        statusText: response.statusText,
        errorText: errorText.substring(0, 200),
      });
      return res.status(response.status).json({
        error: `Failed to fetch ads from Flask: ${response.statusText}`,
      });
    }

    const data = await response.json();
    console.debug("[ads-proxy] Successfully fetched ads from Flask", {
      count: (data as any).cards?.length || 0,
    });
    res.json(data);
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    const errorName = error instanceof Error ? error.name : 'Unknown';
    console.error("[ads-proxy] Error proxying request", {
      flaskUrl: flaskUrl.split("?")[0],
      errorName,
      errorMessage,
      flaskBaseUrl: FLASK_BASE_URL,
    });
    res.status(500).json({ error: "Failed to fetch ads from Flask backend" });
  }
};
