import { RequestHandler } from "express";
import { AdsCardsResponse, AdCardItem } from "@shared/api";

// Mock ad data - in production, this would come from a database
const generateMockAds = (retailer: string, client: string): AdCardItem[] => {
  const keywords = [
    "ice cream",
    "frozen treats",
    "protein snacks",
    "healthy snacks",
  ];
  const adTypes = ["carousel", "toa", "skyscraper", "template"];

  const ads: AdCardItem[] = [];

  for (let i = 0; i < 48; i++) {
    const date = new Date();
    date.setDate(date.getDate() - Math.floor(Math.random() * 30));

    ads.push({
      retailer,
      client,
      keyword: keywords[Math.floor(Math.random() * keywords.length)],
      ad_type: adTypes[Math.floor(Math.random() * adTypes.length)],
      brand: client,
      message: `Ad ${i + 1} - Promoting ${client} products`,
      image_url: `/api/placeholder-ad-${i + 1}.jpg`,
      timestamp: date.toISOString().replace("T", " ").slice(0, 19),
      run_date: date.toISOString().split("T")[0],
      run_file: `run_${i}.json`,
      ad_index: i,
    });
  }

  return ads;
};

export const handleAds: RequestHandler = (req, res) => {
  const retailer = req.query.retailer as string;
  const client = req.query.client as string;
  const page = Math.max(1, parseInt(req.query.page as string) || 1);
  const pageSize = Math.max(1, parseInt(req.query.page_size as string) || 24);

  console.debug("[ads] Request:", { retailer, client, page, pageSize });

  // Validate required parameters
  if (!retailer || !client) {
    return res
      .status(400)
      .json({ error: "retailer and client parameters are required" });
  }

  // Get all ads for the given retailer and client
  const allAds = generateMockAds(retailer, client);
  console.debug("[ads] Generated ads with image URLs:", {
    count: allAds.length,
    sampleUrl: allAds[0]?.image_url,
  });

  // Apply filters if provided
  let filtered = allAds;

  const search = req.query.search as string | undefined;
  if (search) {
    const searchLower = search.toLowerCase();
    filtered = filtered.filter(
      (ad) =>
        ad.keyword.toLowerCase().includes(searchLower) ||
        ad.message.toLowerCase().includes(searchLower) ||
        ad.brand.toLowerCase().includes(searchLower)
    );
  }

  const term = req.query.term as string | undefined;
  if (term) {
    const termLower = term.toLowerCase();
    filtered = filtered.filter((ad) =>
      ad.keyword.toLowerCase().includes(termLower)
    );
  }

  const types = req.query.types as string | undefined;
  if (types) {
    const typeList = types.split(",").map((t) => t.trim().toLowerCase());
    filtered = filtered.filter((ad) =>
      typeList.includes(ad.ad_type.toLowerCase())
    );
  }

  const startDate = req.query.start as string | undefined;
  const endDate = req.query.end as string | undefined;

  if (startDate || endDate) {
    filtered = filtered.filter((ad) => {
      const adDate = ad.run_date || ad.timestamp.split(" ")[0];
      const match = !(startDate && adDate < startDate) && !(endDate && adDate > endDate);
      return match;
    });
  }

  // Apply pagination
  const startIndex = (page - 1) * pageSize;
  const endIndex = startIndex + pageSize;
  const paginatedAds = filtered.slice(startIndex, endIndex);

  const response: AdsCardsResponse = {
    cards: paginatedAds,
    has_more: endIndex < filtered.length,
    total_cards: filtered.length,
  };

  res.json(response);
};
