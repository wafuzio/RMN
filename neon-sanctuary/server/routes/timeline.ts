import { RequestHandler } from "express";

const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006";

export const handleTimeline: RequestHandler = async (req, res) => {
  const { retailer, client, advertiser, start, end, term } = req.query;

  if (!retailer) {
    return res.status(400).json({ error: "retailer parameter is required" });
  }

  try {
    const params = new URLSearchParams();
    params.set("retailer", String(retailer));
    
    // Forward all filter parameters
    if (client) params.set("client", String(client));
    if (advertiser) params.set("advertiser", String(advertiser));
    if (start) params.set("start", String(start));
    if (end) params.set("end", String(end));
    if (term) params.set("term", String(term));

    const flaskUrl = `${FLASK_BASE_URL}/api/timeline?${params.toString()}`;

    const response = await fetch(flaskUrl);

    if (!response.ok) {
      console.error("[timeline] Flask returned non-OK status", {
        status: response.status,
        statusText: response.statusText,
      });
      return res.status(response.status).json({
        error: `Failed to fetch timeline from Flask: ${response.statusText}`,
      });
    }

    const data = await response.json() as { timestamps: string[] };

    res.json({
      timestamps: data.timestamps || [],
    });
  } catch (error) {
    console.error("[timeline] Error fetching timeline", {
      message: error instanceof Error ? error.message : String(error),
    });
    res.status(500).json({ error: "Failed to fetch timeline from Flask backend" });
  }
};
