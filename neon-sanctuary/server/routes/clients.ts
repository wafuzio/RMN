import { RequestHandler } from "express";
import { ClientsResponse } from "@shared/api";
import * as fs from "fs";
import * as path from "path";

export const handleClients: RequestHandler = (req, res) => {
  const retailer = req.query.retailer as string;

  if (!retailer) {
    return res.status(400).json({ error: "retailer parameter is required" });
  }

  try {
    // Dynamically read clients from the output filesystem
    const outputRoot = path.join(process.cwd(), "output");
    const retailerDir = path.join(outputRoot, retailer.toLowerCase());

    if (!fs.existsSync(retailerDir)) {
      return res.json({
        clients: [],
        count: 0,
      });
    }

    const items = fs.readdirSync(retailerDir, { withFileTypes: true });
    const clients: string[] = [];

    for (const item of items) {
      if (item.isDirectory()) {
        // Check if this directory has a "runs" subdirectory or JSON files
        const runsDir = path.join(retailerDir, item.name, "runs");
        if (fs.existsSync(runsDir)) {
          // This is a valid client with runs
          clients.push(item.name);
        }
      }
    }

    // Sort clients alphabetically
    clients.sort();

    const response: ClientsResponse = {
      clients,
      count: clients.length,
    };
    res.json(response);
  } catch (error) {
    console.error("[clients] Error reading clients from filesystem", {
      retailer,
      error: error instanceof Error ? error.message : String(error),
    });
    res.status(500).json({ error: "Failed to fetch clients" });
  }
};
