import { RequestHandler } from "express";

const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006";

export const handleAdsProxy: RequestHandler = async (req, res) => {
  const { retailer, client, page, page_size, term, advertiser, start, end, types, search } = req.query;

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
  if (search) params.set("search", String(search));

  const flaskUrl = `${FLASK_BASE_URL}/api/ads/cards?${params.toString()}`;

  console.log(" [ads-proxy] Full request to Flask:", flaskUrl);
  console.debug("[ads-proxy] Proxying to Flask", {
    retailer,
    client,
    types,
    flaskUrl: flaskUrl.split("?")[0], // Don't log full URL for security
  });

  try {
    console.debug("[ads-proxy] Proxying request to Flask", {
      flaskUrl: flaskUrl.replace(/[?&](retailer|client)=[^&]*/g, "..."),
      hasDateFilter: !!(start || end),
      start,
      end,
    });

    const response = await fetch(flaskUrl);

    if (!response.ok) {
      console.error("[ads-proxy] Flask returned non-OK status", {
        status: response.status,
        statusText: response.statusText,
      });
      return res.status(response.status).json({
        error: `Failed to fetch ads from Flask: ${response.statusText}`,
      });
    }

    // Validate content-type before parsing JSON to prevent "body stream already read" errors
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      console.error("[ads-proxy] Response is not JSON", {
        contentType,
        status: response.status,
      });
      return res.status(500).json({
        error: `Invalid response type from Flask: expected JSON, got ${contentType}`,
      });
    }

    const data = await response.json();
    console.debug("[ads-proxy] Successfully fetched ads from Flask", {
      count: (data as any).cards?.length || 0,
    });
    return res.json(data);
  } catch (error) {
    console.error("[ads-proxy] Error proxying request", {
      flaskUrl: flaskUrl.split("?")[0],
      message: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : undefined,
    });
    return res.status(500).json({ error: "Failed to fetch ads from Flask backend" });
  }
};
