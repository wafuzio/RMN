import { RequestHandler } from "express";
import * as fs from "fs";
import * as path from "path";

interface CarouselBbox {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface CarouselSlide {
  index: number;
  screenshot_file?: string;
  html_file?: string;
  content?: {
    text?: string;
    image_url?: string;
    link?: string;
  };
}

interface CarouselData {
  slides: CarouselSlide[];
  bbox: CarouselBbox | null;
  total_detected: number;
}

interface Snapshot {
  retailer: string;
  pageType: string;
  date: string;
  time: string;
  runId?: string;
  filename: string;
  imagePath: string;
  carousel?: {
    slidesCount: number;
    bbox: CarouselBbox | null;
    slidePaths: string[];
  };
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

        const entries = fs.readdirSync(pageTypePath, { withFileTypes: true });

        for (const entry of entries) {
          // Handle new-style run directories (e.g., 20251202230429)
          if (entry.isDirectory() && /^\d{14}$/.test(entry.name)) {
            const runId = entry.name;
            const runDir = path.join(pageTypePath, runId);
            
            // Look for PNG files in the run directory
            const runFiles = fs.readdirSync(runDir).filter(f => f.endsWith(".png"));
            
            for (const file of runFiles) {
              // Parse filename: {retailer}__{pageType}__D{DATE}_T{TIME}.png
              const match = file.match(
                /(.+?)__(.+?)__D(\d{4}-\d{2}-\d{2})_T(.+?)\.png$/
              );

              if (!match) continue;

              const [, parseRetailer, parsePageType, parseDate, parseTime] = match;
              const snapshotDate = parseDate;

              // Filter by date if provided
              if (date && snapshotDate !== String(date)) continue;

              // Check for carousel data
              const carouselJsonPath = path.join(runDir, "carousel", "slides.json");
              let carouselInfo: Snapshot["carousel"] = undefined;
              
              if (fs.existsSync(carouselJsonPath)) {
                try {
                  const rawData = JSON.parse(fs.readFileSync(carouselJsonPath, "utf-8"));
                  
                  // Handle both old format (array) and new format (object with slides key)
                  const slides: CarouselSlide[] = Array.isArray(rawData) ? rawData : (rawData.slides || []);
                  const bbox = Array.isArray(rawData) ? null : rawData.bbox;
                  
                  // Also scan directory for actual slide files if JSON filenames don't match
                  const carouselDir = path.join(runDir, "carousel");
                  const slideFiles = fs.readdirSync(carouselDir)
                    .filter(f => f.endsWith(".png") && f.includes("hero_slide"))
                    .sort();
                  
                  carouselInfo = {
                    slidesCount: slideFiles.length || slides.length,
                    bbox: bbox,
                    slidePaths: slideFiles.length > 0 
                      ? slideFiles.map(f => `/api/carousel-slide/${parseRetailer.toLowerCase()}/${runId}/${f}`)
                      : slides.map((s: CarouselSlide) => 
                          s.screenshot_file ? `/api/carousel-slide/${parseRetailer.toLowerCase()}/${runId}/${s.screenshot_file}` : ""
                        ).filter(Boolean)
                  };
                } catch (e) {
                  // Ignore carousel parse errors
                }
              }

              snapshots.push({
                retailer: parseRetailer.toLowerCase(),
                pageType: pType.toLowerCase(),
                date: snapshotDate,
                time: parseTime,
                runId,
                filename: file,
                imagePath: `/api/snapshot/${parseRetailer.toLowerCase()}/${pType.toLowerCase()}/${snapshotDate}/T${parseTime}`,
                carousel: carouselInfo,
              });
            }
          }
          // Handle old-style flat PNG files
          else if (entry.isFile() && entry.name.endsWith(".png")) {
            const file = entry.name;
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

    let snapshotPath: string | null = null;

    // First, try to find in old-style flat structure
    const flatFiles = fs.readdirSync(pageTypeDir).filter((file) => {
      return (
        file.endsWith(".png") &&
        file.includes(`D${date}_T${time}`) &&
        file.startsWith(retailer + "__")
      );
    });

    if (flatFiles.length > 0) {
      snapshotPath = path.join(pageTypeDir, flatFiles[0]);
    } else {
      // Try new-style run directories
      const entries = fs.readdirSync(pageTypeDir, { withFileTypes: true });
      
      for (const entry of entries) {
        if (entry.isDirectory() && /^\d{14}$/.test(entry.name)) {
          const runDir = path.join(pageTypeDir, entry.name);
          const runFiles = fs.readdirSync(runDir).filter((file) => {
            return (
              file.endsWith(".png") &&
              file.includes(`D${date}_T${time}`) &&
              file.startsWith(retailer + "__")
            );
          });
          
          if (runFiles.length > 0) {
            snapshotPath = path.join(runDir, runFiles[0]);
            break;
          }
        }
      }
    }

    if (!snapshotPath) {
      console.error("[snapshots] Snapshot file not found in directory", {
        retailer,
        pageType,
        date,
        time,
        directory: pageTypeDir,
      });
      return res.status(404).json({ error: "Snapshot not found" });
    }

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

// Get carousel metadata for a snapshot
export const handleGetCarouselData: RequestHandler = (req, res) => {
  const { retailer, runId } = req.params;

  if (!retailer || !runId) {
    return res.status(400).json({ error: "retailer and runId are required" });
  }

  try {
    // Look for carousel data in the run directory
    const carouselJsonPath = path.join(
      SNAPSHOTS_BASE_PATH,
      retailer,
      "front_pages",
      runId,
      "carousel",
      "slides.json"
    );

    if (!fs.existsSync(carouselJsonPath)) {
      return res.json({ slides: [], bbox: null, total_detected: 0 });
    }

    const carouselData = JSON.parse(fs.readFileSync(carouselJsonPath, "utf-8"));
    
    // Add slide image paths
    if (carouselData.slides) {
      carouselData.slides = carouselData.slides.map((slide: CarouselSlide) => ({
        ...slide,
        imagePath: slide.screenshot_file 
          ? `/api/carousel-slide/${retailer}/${runId}/${slide.screenshot_file}`
          : null
      }));
    }

    res.json(carouselData);
  } catch (error) {
    console.error("[snapshots] Error getting carousel data", {
      retailer,
      runId,
      message: error instanceof Error ? error.message : String(error),
    });
    res.status(500).json({ error: "Failed to get carousel data" });
  }
};

// Serve a carousel slide image
export const handleGetCarouselSlide: RequestHandler = (req, res) => {
  const { retailer, runId, filename } = req.params;

  if (!retailer || !runId || !filename) {
    return res.status(400).json({ error: "retailer, runId, and filename are required" });
  }

  try {
    const slidePath = path.join(
      SNAPSHOTS_BASE_PATH,
      retailer,
      "front_pages",
      runId,
      "carousel",
      filename
    );

    if (!fs.existsSync(slidePath)) {
      return res.status(404).json({ error: "Slide not found" });
    }

    // Verify the file is within the allowed directory
    const realPath = fs.realpathSync(slidePath);
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
      console.error("[snapshots] Error streaming carousel slide", { error: String(error) });
      res.status(500).json({ error: "Failed to stream slide" });
    });
    stream.pipe(res);
  } catch (error) {
    console.error("[snapshots] Error getting carousel slide", {
      retailer,
      runId,
      filename,
      message: error instanceof Error ? error.message : String(error),
    });
    res.status(500).json({ error: "Failed to get carousel slide" });
  }
};
