import { RequestHandler } from "express";

const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006";

export const handleBrands: RequestHandler = async (req, res) => {
  const { retailer } = req.query;

  if (!retailer) {
    return res.status(400).json({ error: "retailer is required" });
  }

  try {
    const params = new URLSearchParams();
    params.set("retailer", String(retailer));
    params.set("client", "all");
    params.set("page_size", "100000");

    const flaskUrl = `${FLASK_BASE_URL}/api/ads/cards?${params.toString()}`;

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
