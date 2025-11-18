import { RequestHandler } from "express";

const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006";

export const handleBrands: RequestHandler = async (req, res) => {
  const { retailer, retailers, client, advertiser, start, end, term } = req.query;
  
  // Handle both 'retailer' (singular) and 'retailers' (plural) for compatibility
  const retailerParam = retailers || retailer;

  if (!retailerParam) {
    return res.status(400).json({ error: "retailer or retailers parameter is required" });
  }

  try {
    const params = new URLSearchParams();
    params.set("retailers", String(retailerParam));
    
    // Forward all filter parameters
    if (client) params.set("client", String(client));
    if (advertiser) params.set("advertiser", String(advertiser));
    if (start) params.set("start", String(start));
    if (end) params.set("end", String(end));
    if (term) params.set("term", String(term));

    // Call Flask /api/brands endpoint directly (optimized for brand aggregation)
    const flaskUrl = `${FLASK_BASE_URL}/api/brands?${params.toString()}`;

    const response = await fetch(flaskUrl);

    if (!response.ok) {
      console.error("[brands] Flask returned non-OK status", {
        status: response.status,
        statusText: response.statusText,
      });
      return res.status(response.status).json({
        error: `Failed to fetch brands from Flask: ${response.statusText}`,
      });
    }

    const data = await response.json() as { brands?: Array<{ brand: string; count: number; percentage: number }> };

    res.json({
      brands: data.brands || [],
    });
  } catch (error) {
    console.error("[brands] Error fetching brands", {
      message: error instanceof Error ? error.message : String(error),
    });
    res.status(500).json({ error: "Failed to fetch brands from Flask backend" });
  }
};
