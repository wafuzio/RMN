import { useState, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { cn, normalizeAdType } from "@/lib/utils";
import { api } from "@/lib/api";
import { toLocalImageUrl } from "@/utils/imageUrl";
import { RetailerLogo } from "@/components/dashboard/RetailerLogo";
import { formatLocal } from "@/lib/date";

// Robust media loader component (handles both images and videos)
function AdMedia({ imageUrl, videoUrl, posterUrl, alt, isTOA, isSBA, adType, priority }: { imageUrl?: string; videoUrl?: string; posterUrl?: string; alt?: string; isTOA?: boolean; isSBA?: boolean; adType?: string; priority?: boolean }) {
  // Prefer video if available, otherwise use image, then poster (for Skyscraper ads)
  const hasVideo = !!videoUrl;
  const relUrl = hasVideo ? videoUrl : (imageUrl || posterUrl || null);

  if (!relUrl) {
    return <div className="fallback-text text-gray-400 text-sm">No media</div>;
  }

  let src = toLocalImageUrl(relUrl);
  
  // If toLocalImageUrl returns null, show no media
  if (!src) {
    return <div className="fallback-text text-gray-400 text-sm">No media</div>;
  }
  
  // Add thumbnail sizing for images (not videos) to reduce transfer size
  if (!hasVideo && src) {
    try {
      // This handles both absolute and relative URLs
      const u = new URL(src, window.location.origin);
      // Only set if not already specified
      if (!u.searchParams.has('w')) {
        u.searchParams.set('w', '600');
      }
      src = u.toString();
    } catch {
      // Fallback for very odd paths where URL() might fail
      src = src.includes('?') ? `${src}&w=600` : `${src}?w=600`;
    }
  }
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const [mediaKey, setMediaKey] = useState(0);

  useEffect(() => {
    setLoaded(false);
    setError(false);
    setMediaKey(prev => prev + 1);
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
        loading={priority ? 'eager' : 'lazy'}
        fetchpriority={priority ? 'high' : 'low'}
        draggable={false}
        onLoad={() => {
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


export interface VideoOverlay {
  x: number;
  y: number;
  width: number;
  height: number;
  image_width: number;
  image_height: number;
}

export interface Ad {
  id: string;
  retailer: string; client: string; keyword: string; ad_type: string; brand: string; message: string; image_url: string; video_url?: string; video_overlay?: VideoOverlay; poster_url?: string; timestamp: string;
}

export function AdCard({ ad, onRemove, onOpen, draggableProps, dragIndex, dragOverIndex, currentIndex, priority }: { ad: Ad; onRemove: (id: string)=>void; onOpen: (ad: Ad)=>void; draggableProps?: any; dragIndex?: number | null; dragOverIndex?: number | null; currentIndex?: number; priority?: boolean; }) {
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
        <AdMedia imageUrl={ad.image_url} alt={`${ad.brand} ad`} isTOA={ad.ad_type === "TOA"} isSBA={ad.ad_type === "SBA"} adType={ad.ad_type} priority={priority} />
        <div id="content-frame" className={cn("adcard-content-box card-text w-full p-6 flex flex-col gap-3")}>
          <div className="flex items-center justify-between w-full">
            <div className="font-bold text-[1.3em] text-[#111827]">{ad.brand}</div>
            <div className="relative">
              <Badge className={cn("pill", TYPE_STYLES[ad.ad_type] || "bg-gray-200 text-gray-800 border-none")}>{normalizeAdType(ad.ad_type)}</Badge>
              <div className="absolute z-20 bg-white/90 px-1 py-1" style={{ left: '-41px', top: '50%', transform: 'translateY(-50%)' }}>
                <span className="sr-only">{ad.retailer}</span>
                <RetailerLogo retailer={ad.retailer} className="h-6 w-auto" />
              </div>
            </div>
          </div>
          <div className="italic text-[#6b7280] text-sm">{ad.keyword}</div>
          <div className="text-xs text-right text-[#6b7280]">
            {ad.timestamp.includes('BADGE_START') ? (
              <span>
                {ad.timestamp.split('BADGE_START')[0]}
                <span className="inline-block rounded-full bg-gradient-to-br from-purple-600 to-blue-600 text-white text-xs font-bold px-2 py-0.5 mx-1 shadow-md border border-white/30">
                  Seen ×{ad.timestamp.split('BADGE_START')[1].split('BADGE_END')[0]}
                </span>
                {ad.timestamp.split('BADGE_END')[1]}
              </span>
            ) : ad.timestamp.startsWith('Seen ') ? ad.timestamp : formatLocal(ad.timestamp)}
          </div>
        </div>
      </button>
    </div>
  );
}
