import { RequestHandler } from "express";
import { RetailersResponse } from "@shared/api";

export const handleRetailers: RequestHandler = (_req, res) => {
  const response: RetailersResponse = {
    retailers: ["kroger", "instacart", "walmart", "amazon"],
    count: 4,
  };
  res.json(response);
};
