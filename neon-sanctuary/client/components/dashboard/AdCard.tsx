import { useState, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { toLocalImageUrl } from "@/utils/imageUrl";
import { RetailerLogo } from "@/components/dashboard/RetailerLogo";
import { parse, format } from "date-fns";

// Robust image loader component
function AdImage({ relUrl, alt }: { relUrl?: string; alt?: string }) {
  if (!relUrl) {
    return <div className="fallback-text text-gray-400 text-sm">No image</div>;
  }

  const src = toLocalImageUrl(relUrl);
  const [loaded, setLoaded] = useState(false);
  const [imgKey, setImgKey] = useState(0);

  useEffect(() => {
    setLoaded(false); // reset whenever src changes
    setImgKey(prev => prev + 1); // force new img element
  }, [src]);

  return (
    <div id="image-frame" className="image-frame w-full h-[200px] overflow-hidden rounded-t-lg bg-gray-100 flex items-center justify-start relative">
      <img
        key={`${src}-${imgKey}`}           // force a fresh element when URL changes
        src={src}
        alt={alt || 'ad'}
        className="h-full object-cover"
        style={{ display: 'block', objectPosition: 'left' }}
        crossOrigin="anonymous"            // Enable CORS for cross-origin images
        referrerPolicy="no-referrer"       // Extra security
        decoding="async"
        loading="lazy"
        draggable={false}
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

function formatDate(timestamp: string | number): string {
  if (!timestamp) {
    return "N/A";
  }

  let parsed: Date | null = null;

  // Try parsing as number (Unix timestamp in seconds or milliseconds)
  if (typeof timestamp === 'number') {
    const ms = timestamp > 9999999999 ? timestamp : timestamp * 1000;
    parsed = new Date(ms);
  } else if (typeof timestamp === 'string') {
    const ts = timestamp.trim();

    // Handle Instacart format: YYYYMMdd_HHMMSS (e.g., 20251015_153000)
    if (/^\d{8}_\d{6}$/.test(ts)) {
      try {
        const year = parseInt(ts.substring(0, 4), 10);
        const month = parseInt(ts.substring(4, 6), 10);
        const day = parseInt(ts.substring(6, 8), 10);
        const hour = parseInt(ts.substring(9, 11), 10);
        const minute = parseInt(ts.substring(11, 13), 10);
        const second = parseInt(ts.substring(13, 15), 10);
        parsed = new Date(year, month - 1, day, hour, minute, second);
        if (!isNaN(parsed.getTime())) {
          // Successfully parsed
        } else {
          parsed = null;
        }
      } catch {
        parsed = null;
      }
    }

    // Handle Walmart format: YYYYMMDDHHmmss (e.g., 20251015153000)
    if (!parsed && /^\d{14}$/.test(ts)) {
      try {
        const year = parseInt(ts.substring(0, 4), 10);
        const month = parseInt(ts.substring(4, 6), 10);
        const day = parseInt(ts.substring(6, 8), 10);
        const hour = parseInt(ts.substring(8, 10), 10);
        const minute = parseInt(ts.substring(10, 12), 10);
        const second = parseInt(ts.substring(12, 14), 10);
        parsed = new Date(year, month - 1, day, hour, minute, second);
        if (!isNaN(parsed.getTime())) {
          // Successfully parsed
        } else {
          parsed = null;
        }
      } catch {
        parsed = null;
      }
    }

    // Try multiple date format patterns if not yet parsed
    if (!parsed) {
      const formats = [
        "yyyy-MM-dd HH:mm:ss",      // 2025-10-21 15:30:00
        "yyyy-MM-dd'T'HH:mm:ss",    // 2025-10-21T15:30:00
        "yyyy-MM-dd'T'HH:mm:ss.SSS", // 2025-10-21T15:30:00.123
        "yyyy-MM-dd'T'HH:mm:ss'Z'",  // 2025-10-21T15:30:00Z
        "MM/dd/yyyy HH:mm:ss",      // 10/21/2025 15:30:00
        "MM/dd/yyyy",               // 10/21/2025
        "yyyy-MM-dd",               // 2025-10-21
        "dd-MM-yyyy",               // 21-10-2025
      ];

      for (const fmt of formats) {
        try {
          const candidate = parse(ts, fmt, new Date());
          if (!isNaN(candidate.getTime())) {
            parsed = candidate;
            break;
          }
        } catch {
          // Try next format
        }
      }
    }

    // If no format matched, try native Date constructor
    if (!parsed) {
      const nativeDate = new Date(ts);
      if (!isNaN(nativeDate.getTime())) {
        parsed = nativeDate;
      }
    }
  }

  if (!parsed || isNaN(parsed.getTime())) {
    return "N/A";
  }

  try {
    return format(parsed, "MMM d, yyyy h:mm a");
  } catch {
    return "N/A";
  }
}

export interface Ad {
  id: string;
  retailer: string; client: string; keyword: string; ad_type: string; brand: string; message: string; image_url: string; timestamp: string;
}

export function AdCard({ ad, onRemove, onOpen, draggableProps, dragIndex, dragOverIndex, currentIndex }: { ad: Ad; onRemove: (id: string)=>void; onOpen: (ad: Ad)=>void; draggableProps?: any; dragIndex?: number | null; dragOverIndex?: number | null; currentIndex?: number; }) {
  const [hidden, setHidden] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const isBeingDragged = dragIndex === currentIndex;
  const isDropTarget = dragOverIndex === currentIndex;

  const enhancedDraggableProps = draggableProps ? {
    ...draggableProps,
    onDragStart: (e: React.DragEvent) => {
      setIsDragging(true);
      draggableProps.onDragStart?.(e);
    },
    onDragEnd: (e: React.DragEvent) => {
      setIsDragging(false);
    },
  } : {};
  
  if (hidden) return null;

  return (
    <div
      id="ad-card-outer"
      className={cn(
        "content-frame card-surface mb-4 break-inside-avoid relative w-full transition-all duration-100 user-select-none",
        "group",
        isDragging && "opacity-70 shadow-lg scale-[0.98]",
        isDropTarget && "translate-y-2"
      )}
      style={{
        touchAction: 'none',
        ...(isDropTarget && { boxShadow: '0 20px 48px rgba(0, 0, 0, 0.25)' })
      }}
      {...enhancedDraggableProps}
      role="article"
      aria-label={`Ad card ${ad.brand}`}
    >
      <button
        aria-label="Remove ad"
        onClick={() => { setHidden(true); onRemove(ad.id); }}
        className="absolute right-2 top-2 h-8 w-8 grid place-items-center rounded-full bg-white/90 border opacity-0 group-hover:opacity-100 transition"
      >
        ×
      </button>
      <button onClick={() => onOpen(ad)} className={cn("text-left select-none", ad.ad_type === "Skyscraper" && "w-full block")} style={{ touchAction: 'none' }}>
        <AdImage relUrl={ad.image_url} alt={`${ad.brand} ad`} />
        <div id="content-frame" className={cn("card-text w-full p-4", ad.ad_type === "Skyscraper" && "flex flex-col")}>
          <div className="flex items-center justify-between mb-1 w-full">
            <div className="font-bold text-[1.2em] text-[#111827]">{ad.brand}</div>
            <div className="relative">
              <Badge className={cn("pill", TYPE_STYLES[ad.ad_type] || "bg-gray-200 text-gray-800 border-none")}>{ad.ad_type.replace(/_/g," ")}</Badge>
              <div className="absolute z-20 bg-white/90 px-1 py-1" style={{ left: '-41px', top: '50%', transform: 'translateY(-50%)' }}>
                <span className="sr-only">{ad.retailer}</span>
                <RetailerLogo retailer={ad.retailer} className="h-6 w-auto" />
              </div>
            </div>
          </div>
          <div className="italic text-[#6b7280]">{ad.keyword}</div>
          <div className="text-xs text-right text-[#6b7280] mt-2">
            {formatDate(ad.timestamp)}
          </div>
        </div>
      </button>
    </div>
  );
}
