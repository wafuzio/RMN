import { RequestHandler } from "express";

const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006";

export const handleAdsProxy: RequestHandler = async (req, res) => {
  const { retailer, client, page, page_size, term, advertiser, start, end, types, search } = req.query;

  // Validate required parameters
  const retailerStr = (retailer || "").toString().trim();
  const clientStr = (client || "").toString().trim();

  if (!retailerStr || !clientStr) {
    console.warn("[ads-proxy] Missing required parameters", { retailer: retailerStr, client: clientStr });
    return res.status(400).json({ error: "retailer and client parameters are required" });
  }

  // Build Flask URL with all query parameters
  const params = new URLSearchParams();
  params.set("retailer", retailerStr);
  params.set("client", clientStr);

  // Add optional parameters if they're non-empty
  if (page && String(page).trim()) params.set("page", String(page).trim());
  if (page_size && String(page_size).trim()) params.set("page_size", String(page_size).trim());
  if (term && String(term).trim()) params.set("term", String(term).trim());
  if (advertiser && String(advertiser).trim()) params.set("advertiser", String(advertiser).trim());
  if (start && String(start).trim()) params.set("start", String(start).trim());
  if (end && String(end).trim()) params.set("end", String(end).trim());
  if (types && String(types).trim()) params.set("types", String(types).trim());
  if (search && String(search).trim()) params.set("search", String(search).trim());

  const flaskUrl = `${FLASK_BASE_URL}/api/ads/cards?${params.toString()}`;

  console.log("[ads-proxy] Proxying request", {
    retailer: retailerStr,
    client: clientStr,
    flaskBase: FLASK_BASE_URL,
    hasDateFilter: !!(start || end),
    start,
    end,
  });

  try {
    // Add timeout to fetch request (30 seconds)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);

    let response: Response;
    try {
      response = await fetch(flaskUrl, { signal: controller.signal });
    } finally {
      clearTimeout(timeoutId);
    }

    if (!response.ok) {
      const statusCode = response.status;
      const statusText = response.statusText;
      let errorBody = "";

      try {
        errorBody = await response.text();
      } catch {
        errorBody = "(unable to read response body)";
      }

      console.error("[ads-proxy] Flask returned error status", {
        status: statusCode,
        statusText,
        urlPath: flaskUrl.split("?")[0],
        bodyPreview: errorBody.substring(0, 200),
      });

      return res.status(statusCode).json({
        error: `Flask API error: ${statusCode} ${statusText}`,
        details: statusCode === 500 ? "Flask backend encountered an error" : undefined,
      });
    }

    // Validate content-type before parsing JSON
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      console.error("[ads-proxy] Response is not JSON", {
        contentType,
        status: response.status,
      });
      return res.status(502).json({
        error: `Invalid response from Flask: expected JSON, got ${contentType}`,
      });
    }

    const data = await response.json();

    // Validate response structure - Flask should always return an object with a cards array
    if (!data || typeof data !== 'object') {
      console.error("[ads-proxy] Invalid response structure - not an object", { dataType: typeof data });
      return res.status(502).json({
        error: "Invalid response structure from Flask",
      });
    }

    if (!Array.isArray(data.cards)) {
      console.error("[ads-proxy] Invalid response structure - cards is not an array", {
        dataType: typeof data.cards,
        responseKeys: Object.keys(data)
      });
      return res.status(502).json({
        error: "Invalid response structure from Flask: missing or invalid cards array",
      });
    }

    console.log("[ads-proxy] Success", {
      retailer: retailerStr,
      client: clientStr,
      cardCount: data.cards.length,
      page: data.page || 1,
      hasMore: data.has_more || false,
    });

    return res.json(data);
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    const isAborted = error instanceof Error && error.name === "AbortError";

    if (isAborted) {
      console.error("[ads-proxy] Request timeout", {
        retailer: retailerStr,
        client: clientStr,
        flaskUrl: flaskUrl.split("?")[0],
      });
      return res.status(504).json({ error: "Request to Flask backend timed out" });
    }

    console.error("[ads-proxy] Error proxying request", {
      retailer: retailerStr,
      client: clientStr,
      flaskUrl: flaskUrl.split("?")[0],
      errorName: error instanceof Error ? error.name : "unknown",
      errorMessage: errorMsg,
      errorStack: error instanceof Error ? error.stack : undefined,
    });

    return res.status(502).json({
      error: "Failed to connect to Flask backend",
      details: `Connection error: ${errorMsg}`,
    });
  }
};
