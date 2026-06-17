import { RequestHandler } from "express";

const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006";

const HEADERS = {
  "Content-Type": "application/json",
  "ngrok-skip-browser-warning": "true",
};

async function proxyToFlask(
  method: string,
  path: string,
  body?: unknown,
): Promise<{ status: number; data: unknown }> {
  const res = await fetch(`${FLASK_BASE_URL}${path}`, {
    method,
    headers: HEADERS,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  return { status: res.status, data };
}

export const handleGetReviewQueue: RequestHandler = async (_req, res) => {
  try {
    const { status, data } = await proxyToFlask("GET", "/api/review-queue");
    return res.status(status).json(data);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return res.status(502).json({ error: "Flask unavailable", details: msg });
  }
};

export const handleUpdateAdBrand: RequestHandler = async (req, res) => {
  try {
    const { status, data } = await proxyToFlask(
      "PATCH",
      `/api/ads/${req.params.ad_id}/brand`,
      req.body,
    );
    return res.status(status).json(data);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return res.status(502).json({ error: "Flask unavailable", details: msg });
  }
};

export const handleUpdateAdType: RequestHandler = async (req, res) => {
  try {
    const { status, data } = await proxyToFlask(
      "PATCH",
      `/api/ads/${req.params.ad_id}/ad-type`,
      req.body,
    );
    return res.status(status).json(data);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return res.status(502).json({ error: "Flask unavailable", details: msg });
  }
};

export const handleUpdateAdVideoOverlay: RequestHandler = async (req, res) => {
  try {
    const { status, data } = await proxyToFlask(
      "PATCH",
      `/api/ads/${req.params.ad_id}/video-overlay`,
      req.body,
    );
    return res.status(status).json(data);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return res.status(502).json({ error: "Flask unavailable", details: msg });
  }
};

export const handleDeleteAd: RequestHandler = async (req, res) => {
  try {
    const { status, data } = await proxyToFlask(
      "DELETE",
      `/api/ads/${req.params.ad_id}`,
    );
    return res.status(status).json(data);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return res.status(502).json({ error: "Flask unavailable", details: msg });
  }
};

export const handleResolveFlag: RequestHandler = async (req, res) => {
  try {
    const { status, data } = await proxyToFlask(
      "POST",
      `/api/review-queue/${req.params.flag_id}/resolve`,
    );
    return res.status(status).json(data);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return res.status(502).json({ error: "Flask unavailable", details: msg });
  }
};

export const handleDismissFlag: RequestHandler = async (req, res) => {
  try {
    const { status, data } = await proxyToFlask(
      "POST",
      `/api/review-queue/${req.params.flag_id}/dismiss`,
    );
    return res.status(status).json(data);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return res.status(502).json({ error: "Flask unavailable", details: msg });
  }
};
