import { RequestHandler } from "express";

// Generate a simple SVG placeholder image
function generatePlaceholderSVG(index: number): string {
  const colors = [
    "#FF6B6B",
    "#4ECDC4",
    "#45B7D1",
    "#FFA07A",
    "#98D8C8",
    "#F7DC6F",
    "#BB8FCE",
    "#85C1E2",
  ];
  const color = colors[index % colors.length];

  return `
    <svg width="400" height="300" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <style>
          .placeholder-text { font-family: Arial, sans-serif; font-size: 24px; font-weight: bold; fill: white; text-anchor: middle; }
          .placeholder-bg { fill: ${color}; }
        </style>
      </defs>
      <rect class="placeholder-bg" width="400" height="300"/>
      <text class="placeholder-text" x="200" y="140">Ad ${index + 1}</text>
      <text class="placeholder-text" x="200" y="170" style="font-size: 16px;">Placeholder Image</text>
    </svg>
  `.trim();
}

export const handlePlaceholderAd: RequestHandler = (req, res) => {
  const { id } = req.params;

  if (!id) {
    console.warn("[placeholder] Missing ad ID");
    return res.status(400).json({ error: "Ad ID is required" });
  }

  try {
    const adIndex = parseInt(id, 10) - 1;
    if (isNaN(adIndex) || adIndex < 0) {
      console.warn("[placeholder] Invalid ad ID:", id);
      return res.status(400).json({ error: "Invalid ad ID" });
    }

    const svg = generatePlaceholderSVG(adIndex);
    console.debug("[placeholder] Generated SVG for ad:", id);

    res.set("Content-Type", "image/svg+xml");
    res.set("Cache-Control", "public, max-age=3600");
    res.set("Access-Control-Allow-Origin", "*");
    res.send(svg);
  } catch (error) {
    console.error("[placeholder] Error generating placeholder:", {
      id,
      message: error instanceof Error ? error.message : String(error),
    });
    res.status(500).json({ error: "Failed to generate placeholder image" });
  }
};
