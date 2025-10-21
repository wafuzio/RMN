import { useState, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { toLocalImageUrl } from "@/utils/imageUrl";
import { RetailerLogo } from "@/components/dashboard/RetailerLogo";

// Robust image loader component
function AdImage({ relUrl, alt }: { relUrl?: string; alt?: string }) {
  if (!relUrl) {
    return <div className="fallback-text text-gray-400 text-sm">No image</div>;
  }

  const src = toLocalImageUrl(relUrl);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    setLoaded(false); // reset whenever src changes
  }, [src]);

  return (
    <div className="w-full h-[200px] overflow-hidden rounded-t-lg bg-gray-100 flex items-center justify-center relative">
      <img
        key={src}                          // force a fresh element when URL changes
        src={src}
        alt={alt || 'ad'}
        className="w-full h-full object-cover"
        style={{ display: 'block' }}       // never hide the <img>
        crossOrigin="anonymous"            // Enable CORS for cross-origin images
        referrerPolicy="no-referrer"       // Extra security
        decoding="async"
        loading="lazy"
        onLoad={() => setLoaded(true)}
        onError={() => {
          console.log('img error', src);   // keep temporarily for debugging
          setLoaded(false);
        }}
      />
      {!loaded && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-100">
          <div className="fallback-text text-gray-400 text-sm">Loading...</div>
        </div>
      )}
    </div>
  );
}

const TYPE_STYLES: Record<string, string> = {
  TOA: "bg-blue-500 text-white",
  Carousel: "bg-orange-500 text-white",
  Skyscraper: "bg-indigo-500 text-white",
  Display_Ads: "bg-teal-500 text-white",
  Sponsored_Product: "bg-green-600 text-white",
  Sponsored_Products: "bg-green-600 text-white",
  Sponsored_Brand_Video: "bg-purple-600 text-white",
  Featured_Brand: "bg-pink-600 text-white",
  Sponsored_Carousel: "bg-orange-500 text-white",
  Video_Ads: "bg-purple-600 text-white",
  Top_Banner: "bg-blue-600 text-white",
  SBA: "bg-blue-700 text-white",
  Tile_Takeover: "bg-amber-600 text-white",
  SBV: "bg-purple-700 text-white",
};

export interface Ad {
  id: string;
  retailer: string; client: string; keyword: string; ad_type: string; brand: string; message: string; image_url: string; timestamp: string;
}

export function AdCard({ ad, onRemove, onOpen, draggableProps }: { ad: Ad; onRemove: (id: string)=>void; onOpen: (ad: Ad)=>void; draggableProps?: any; }) {
  const [hidden, setHidden] = useState(false);
  
  if (hidden) return null;

  return (
    <div
      className={cn("card-surface mb-4 break-inside-avoid relative w-full", "group")}
      {...draggableProps}
      role="article"
      aria-label={`Ad card ${ad.brand}`}
    >
      <div className="absolute left-2 top-2 z-20 bg-white/90 border rounded px-1 py-1">
        <span className="sr-only">{ad.retailer}</span>
        <RetailerLogo retailer={ad.retailer} className="h-6 w-auto" />
      </div>
      <button
        aria-label="Remove ad"
        onClick={() => { setHidden(true); onRemove(ad.id); }}
        className="absolute right-2 top-2 h-8 w-8 grid place-items-center rounded-full bg-white/90 border opacity-0 group-hover:opacity-100 transition"
      >
        ×
      </button>
      <div className="cursor-grab absolute left-2 top-2 translate-y-10 opacity-0 group-hover:opacity-100" aria-hidden>⋮⋮</div>
      <button onClick={() => onOpen(ad)} className="text-left">
        <AdImage relUrl={ad.image_url} alt={`${ad.brand} ad`} />
        <div className="p-4">
          <div className="flex items-center justify-between mb-1">
            <div className="font-bold text-[1.2em] text-[#111827]">{ad.brand}</div>
            <Badge className={cn("pill", TYPE_STYLES[ad.ad_type] || "bg-gray-200 text-gray-800 border-none")}>{ad.ad_type.replace(/_/g," ")}</Badge>
          </div>
          <div className="italic text-[#6b7280]">{ad.keyword}</div>
          <div className="text-xs text-right text-[#6b7280] mt-2">{new Date(ad.timestamp.replace(" ","T")).toLocaleString()}</div>
        </div>
      </button>
    </div>
  );
}
