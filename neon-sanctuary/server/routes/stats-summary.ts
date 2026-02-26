import { RequestHandler } from "express";

const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006";

export const handleStatsSummary: RequestHandler = async (req, res) => {
  const { retailers, client } = req.query;

  try {
    const params = new URLSearchParams();
    if (retailers) params.set("retailers", String(retailers));
    if (client) params.set("client", String(client));

    const flaskUrl = `${FLASK_BASE_URL}/api/stats/summary?${params.toString()}`;

    const response = await fetch(flaskUrl, {
      headers: { "ngrok-skip-browser-warning": "true" },
    });

    if (!response.ok) {
      console.error("[stats-summary] Flask returned non-OK status", {
        status: response.status,
        statusText: response.statusText,
      });
      return res.status(response.status).json({
        error: `Failed to fetch stats summary: ${response.statusText}`,
      });
    }

    const data = await response.json();
    res.json(data);
  } catch (error) {
    console.error("[stats-summary] Error fetching stats summary", {
      message: error instanceof Error ? error.message : String(error),
    });
    res.status(500).json({ error: "Failed to fetch stats summary from Flask backend" });
  }
};
