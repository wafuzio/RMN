import { RequestHandler } from "express";

const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006";

export const handleBrandDetails: RequestHandler = async (req, res) => {
  const { brand, retailers } = req.query;

  if (!brand) {
    return res.status(400).json({ error: "brand parameter is required" });
  }

  // Build Flask URL with all query parameters
  const params = new URLSearchParams();
  params.set("brand", String(brand));
  if (retailers) params.set("retailers", String(retailers));

  const flaskUrl = `${FLASK_BASE_URL}/api/brand-details?${params.toString()}`;

  try {
    console.debug("[brand-details] Proxying request to Flask", {
      brand,
      retailers: retailers || "all",
    });

    const response = await fetch(flaskUrl);

    if (!response.ok) {
      console.error("[brand-details] Flask returned non-OK status", {
        status: response.status,
        statusText: response.statusText,
      });
      return res.status(response.status).json({
        error: `Failed to fetch brand details from Flask: ${response.statusText}`,
      });
    }

    const data = await response.json();
    console.debug("[brand-details] Successfully fetched brand details from Flask", {
      brand,
      total_ads: (data as any).total_ads,
    });

    res.json(data);
  } catch (error) {
    console.error("[brand-details] Error fetching from Flask", {
      message: error instanceof Error ? error.message : String(error),
    });
    res.status(500).json({
      error: "Failed to fetch brand details from Flask backend",
    });
  }
};
