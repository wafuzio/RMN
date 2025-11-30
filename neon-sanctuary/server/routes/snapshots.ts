import { RequestHandler } from "express";
import * as fs from "fs";
import * as path from "path";

interface Snapshot {
  retailer: string;
  pageType: string;
  date: string;
  time: string;
  filename: string;
  imagePath: string;
}

const SNAPSHOTS_BASE_PATH = path.join(process.cwd(), "..", "output", "screen_capture");

export const handleListSnapshots: RequestHandler = (req, res) => {
  const { retailer, pageType, date } = req.query;

  try {
    const snapshots: Snapshot[] = [];

    // Get all retailers
    const retailers = retailer
      ? [String(retailer).toLowerCase()]
      : fs.readdirSync(SNAPSHOTS_BASE_PATH).filter(
          (file) =>
            fs.statSync(path.join(SNAPSHOTS_BASE_PATH, file)).isDirectory() &&
            !file.startsWith(".")
        );

    for (const ret of retailers) {
      const retailerPath = path.join(SNAPSHOTS_BASE_PATH, ret);

      if (!fs.existsSync(retailerPath)) continue;

      // Get all page types in this retailer's folder
      const pageTypes = fs
        .readdirSync(retailerPath)
        .filter(
          (file) =>
            fs.statSync(path.join(retailerPath, file)).isDirectory() &&
            !file.startsWith(".")
        );

      for (const pType of pageTypes) {
        if (pageType && pType !== String(pageType).toLowerCase()) continue;

        const pageTypePath = path.join(retailerPath, pType);

        if (!fs.existsSync(pageTypePath)) continue;

        const files = fs
          .readdirSync(pageTypePath)
          .filter((file) => file.endsWith(".png"));

        for (const file of files) {
          // Parse filename: {retailer}__{pageType}__D{DATE}_{TIME}.png
          const match = file.match(
            /(.+?)__(.+?)__D(\d{4}-\d{2}-\d{2})_(.+?)\.png$/
          );

          if (!match) continue;

          const [, parseRetailer, parsePageType, parseDate, parseTime] = match;
          const snapshotDate = parseDate;

          // Filter by date if provided
          if (date && snapshotDate !== String(date)) continue;

          snapshots.push({
            retailer: parseRetailer.toLowerCase(),
            pageType: pType.toLowerCase(),
            date: snapshotDate,
            time: parseTime,
            filename: file,
            imagePath: `/api/snapshot/${parseRetailer.toLowerCase()}/${pType.toLowerCase()}/${snapshotDate}/${parseTime}`,
          });
        }
      }
    }

    // Sort by date and time descending
    snapshots.sort((a, b) => {
      const dateCompare = b.date.localeCompare(a.date);
      if (dateCompare !== 0) return dateCompare;
      return b.time.localeCompare(a.time);
    });

    res.json({ snapshots });
  } catch (error) {
    console.error("[snapshots] Error listing snapshots", {
      message: error instanceof Error ? error.message : String(error),
    });
    res.status(500).json({ error: "Failed to list snapshots" });
  }
};

export const handleGetSnapshot: RequestHandler = (req, res) => {
  const { retailer, pageType, date, time } = req.params;

  if (!retailer || !pageType || !date || !time) {
    return res
      .status(400)
      .json({ error: "retailer, pageType, date, and time are required" });
  }

  try {
    const pageTypeDir = path.join(SNAPSHOTS_BASE_PATH, retailer, pageType);

    if (!fs.existsSync(pageTypeDir)) {
      return res.status(404).json({ error: "Page type directory not found" });
    }

    // Find the actual file - the filename might have a different pageType in it
    // e.g., directory is "front_pages" but filename has "front_page"
    const files = fs.readdirSync(pageTypeDir).filter((file) => {
      return (
        file.endsWith(".png") &&
        file.includes(`D${date}_${time}`) &&
        file.startsWith(retailer + "__")
      );
    });

    if (files.length === 0) {
      console.error("[snapshots] Snapshot file not found in directory", {
        retailer,
        pageType,
        date,
        time,
        directory: pageTypeDir,
      });
      return res.status(404).json({ error: "Snapshot not found" });
    }

    const snapshotPath = path.join(pageTypeDir, files[0]);

    // Verify the file is within the allowed directory
    const realPath = fs.realpathSync(snapshotPath);
    const allowedPath = fs.realpathSync(SNAPSHOTS_BASE_PATH);

    if (!realPath.startsWith(allowedPath)) {
      return res.status(403).json({ error: "Access denied" });
    }

    // Set cache headers
    res.set("Content-Type", "image/png");
    res.set("Cache-Control", "public, max-age=31536000, immutable");
    res.set("Access-Control-Allow-Origin", "*");

    // Stream the image
    const stream = fs.createReadStream(realPath);
    stream.on("error", (error) => {
      console.error("[snapshots] Error streaming file", { error: String(error) });
      res.status(500).json({ error: "Failed to stream snapshot" });
    });
    stream.pipe(res);
  } catch (error) {
    console.error("[snapshots] Error getting snapshot", {
      retailer,
      pageType,
      date,
      time,
      message: error instanceof Error ? error.message : String(error),
    });
    res.status(500).json({ error: "Failed to get snapshot" });
  }
};
