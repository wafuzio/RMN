import { RequestHandler } from "express";
import { ClientsResponse } from "@shared/api";

export const handleClients: RequestHandler = (req, res) => {
  const retailer = req.query.retailer as string;

  if (!retailer) {
    return res.status(400).json({ error: "retailer parameter is required" });
  }

  // Mock clients data - in production, this would come from a database
  const clientsByRetailer: Record<string, string[]> = {
    kroger: ["Blue Bunny", "Halo Top", "Jeni's", "Magic Spoon", "MilkPep"],
    instacart: [
      "Blue Bunny",
      "Bomb Pop",
      "Halo Top",
      "Jeni's",
      "Keto Chips",
      "Land O Frost",
      "Magic Spoon",
      "MilkPep",
    ],
    walmart: ["Blue Bunny", "Halo Top", "Jeni's", "Magic Spoon"],
    amazon: ["Blue Bunny", "Halo Top", "MilkPep"],
  };

  const clients = clientsByRetailer[retailer.toLowerCase()] || [];
  const response: ClientsResponse = {
    clients,
    count: clients.length,
  };
  res.json(response);
};
