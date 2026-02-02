import { RequestHandler } from "express";

const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006";

export const handleAdTypes: RequestHandler = async (req, res) => {
  const { retailer, client, start, end } = req.query;

  if (!retailer || !client) {
    console.warn("[ads-types] Missing required parameters", { retailer, client });
    return res.status(400).json({ error: "retailer and client are required" });
  }

  // Build Flask URL with all query parameters
  const params = new URLSearchParams();
  params.set("retailer", String(retailer));
  params.set("client", String(client));
  if (start) params.set("start", String(start));
  if (end) params.set("end", String(end));

  const flaskUrl = `${FLASK_BASE_URL}/api/ads/types?${params.toString()}`;

  try {
    console.debug("[ads-types] Proxying request to Flask", {
      retailer,
      client,
      hasDateFilter: !!(start || end),
    });

    const response = await fetch(flaskUrl);

    if (!response.ok) {
      console.error("[ads-types] Flask returned non-OK status", {
        status: response.status,
        statusText: response.statusText,
      });
      return res.status(response.status).json({
        error: `Failed to fetch ad types from Flask: ${response.statusText}`,
      });
    }

    const data = await response.json();
    console.debug("[ads-types] Successfully fetched types from Flask", {
      typesCount: (data as any).types?.length || 0,
    });
    res.json(data);
  } catch (error) {
    console.error("[ads-types] Error proxying request", {
      flaskUrl: flaskUrl.split("?")[0],
      message: error instanceof Error ? error.message : String(error),
    });
    res.status(500).json({ error: "Failed to fetch ad types from Flask backend" });
  }
};
