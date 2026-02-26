import { RequestHandler } from "express";

const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006";

export const handleFlagReview: RequestHandler = async (req, res) => {
  const flaskUrl = `${FLASK_BASE_URL}/api/flag-review`;

  try {
    const response = await fetch(flaskUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "ngrok-skip-browser-warning": "true",
      },
      body: JSON.stringify(req.body),
    });

    const data = await response.json();
    return res.status(response.status).json(data);
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    console.error("[flag-review] Error proxying request", { errorMessage: errorMsg });
    return res.status(502).json({
      error: "Failed to connect to Flask backend",
      details: `Connection error: ${errorMsg}`,
    });
  }
};
