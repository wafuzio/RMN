import { useState, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { toLocalImageUrl } from "@/utils/imageUrl";
import { RetailerLogo } from "@/components/dashboard/RetailerLogo";
import { formatLocal } from "@/lib/date";

// Robust media loader component (handles both images and videos)
function AdMedia({ imageUrl, videoUrl, posterUrl, alt, isTOA, isSBA, adType }: { imageUrl?: string; videoUrl?: string; posterUrl?: string; alt?: string; isTOA?: boolean; isSBA?: boolean; adType?: string }) {
  // Prefer video if available, otherwise use image, then poster (for Skyscraper ads)
  const hasVideo = !!videoUrl;
  const relUrl = hasVideo ? videoUrl : (imageUrl || posterUrl || null);

  if (!relUrl) {
    return <div className="fallback-text text-gray-400 text-sm">No media</div>;
  }

  const src = toLocalImageUrl(relUrl);
  
  // If toLocalImageUrl returns null, show no media
  if (!src) {
    return <div className="fallback-text text-gray-400 text-sm">No media</div>;
  }
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const [mediaKey, setMediaKey] = useState(0);

  useEffect(() => {
    setLoaded(false);
    setError(false);
    setMediaKey(prev => prev + 1);
    console.debug('[AdMedia] Loading ' + (hasVideo ? 'video' : 'image') + ':', { original: relUrl, resolved: src });
  }, [src, relUrl, hasVideo]);

  const heightClass = (isTOA || isSBA) ? "h-[120px]" : "h-[200px]";

  if (hasVideo) {
    return (
      <div id="video-frame" className={cn("video-frame w-full overflow-hidden rounded-t-lg bg-gray-100 flex items-start justify-start relative", heightClass)}>
        <video
          key={`${src}-${mediaKey}`}
          src={src}
          className="h-full w-full object-cover"
          style={{ display: error ? 'none' : 'block', objectPosition: 'top left' }}
          crossOrigin="anonymous"
          controls
          preload="metadata"
          onLoadedMetadata={() => {
            console.debug('[AdMedia] Video loaded:', src);
            setLoaded(true);
            setError(false);
          }}
          onError={() => {
            console.error('[AdMedia] Failed to load video:', src);
            setLoaded(false);
            setError(true);
          }}
        />
        {!loaded && !error && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-100">
            <div className="fallback-text text-gray-400 text-sm">Loading...</div>
          </div>
        )}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-100">
            <div className="fallback-text text-gray-400 text-sm">Failed to load video</div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div id="image-frame" className={cn("image-frame w-full overflow-hidden rounded-t-lg bg-gray-100 flex items-start justify-start relative", heightClass)}>
      <img
        key={`${src}-${mediaKey}`}
        src={src}
        alt={alt || 'ad'}
        className="h-full w-full object-cover"
        style={{ display: error ? 'none' : 'block', objectPosition: 'top left' }}
        crossOrigin="anonymous"
        referrerPolicy="no-referrer"
        decoding="async"
        loading="lazy"
        draggable={false}
        onLoad={() => {
          console.debug('[AdMedia] Image loaded:', src);
          setLoaded(true);
          setError(false);
        }}
        onError={(e) => {
          const img = e.currentTarget;

          // First attempt: try placeholder (only if not already a placeholder)
          if (!img.src.includes('/api/image/placeholder')) {
            console.warn('[AdMedia] Image load failed, trying placeholder:', src);
            img.onerror = null; // prevent loop
            // Use a simple label instead of the full URL
            const label = adType || 'ad';
            img.src = `/api/image/placeholder?text=${encodeURIComponent(label)}`;
            setError(false); // Reset error state to try placeholder
          } else {
            // Placeholder also failed, just show error state silently
            setLoaded(false);
            setError(true);
          }
        }}
      />
      {!loaded && !error && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-100">
          <div className="fallback-text text-gray-400 text-sm">Loading...</div>
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-100">
          <div className="fallback-text text-gray-400 text-sm">Failed to load image</div>
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
  retailer: string; client: string; keyword: string; ad_type: string; brand: string; message: string; image_url: string; video_url?: string; poster_url?: string; timestamp: string;
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
        "content-frame card-surface break-inside-avoid relative w-full transition-all duration-100 user-select-none",
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
      <button onClick={() => onOpen(ad)} className={cn("text-left select-none w-full block")} style={{ touchAction: 'none' }}>
        <AdMedia imageUrl={ad.image_url} videoUrl={ad.video_url} posterUrl={ad.poster_url} alt={`${ad.brand} ad`} isTOA={ad.ad_type === "TOA"} isSBA={ad.ad_type === "SBA"} adType={ad.ad_type} />
        <div id="content-frame" className={cn("card-text w-full p-4 flex flex-col")}>
          <div className="flex items-center justify-between mb-1 w-full">
            <div className="font-bold text-[1.2em] text-[#111827]">{ad.brand}</div>
            <div className="relative">
              <Badge className={cn("pill", TYPE_STYLES[ad.ad_type] || "bg-gray-200 text-gray-800 border-none")}>{ad.ad_type.toLowerCase() === "sba" || ad.ad_type.toLowerCase() === "sbv" ? ad.ad_type.toUpperCase() : ad.ad_type.replace(/_/g," ")}</Badge>
              <div className="absolute z-20 bg-white/90 px-1 py-1" style={{ left: '-41px', top: '50%', transform: 'translateY(-50%)' }}>
                <span className="sr-only">{ad.retailer}</span>
                <RetailerLogo retailer={ad.retailer} className="h-6 w-auto" />
              </div>
            </div>
          </div>
          <div className="italic text-[#6b7280]">{ad.keyword}</div>
          <div className="text-xs text-right text-[#6b7280] mt-2">
            {formatLocal(ad.timestamp)}
          </div>
        </div>
      </button>
    </div>
  );
}
