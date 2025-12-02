import { useState, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { cn, normalizeAdType } from "@/lib/utils";
import { api } from "@/lib/api";
import { toLocalImageUrl } from "@/utils/imageUrl";
import { RetailerLogo } from "@/components/dashboard/RetailerLogo";
import { formatLocal } from "@/lib/date";

// Robust media loader component (handles both images and videos)
function AdMedia({ imageUrl, videoUrl, posterUrl, alt, isTOA, isSBA, adType, slot, priority, mediaHeight, retailer, dimensions }: { imageUrl?: string; videoUrl?: string; posterUrl?: string; alt?: string; isTOA?: boolean; isSBA?: boolean; adType?: string; slot?: string; priority?: boolean; mediaHeight?: string; retailer?: string; dimensions?: { width: number; height: number }; }) {
  const isColumnCard = adType === "Sponsored_Brand_Card" || adType === "Sponsored_Logo";
  const isSponsoredLogo = adType === "Sponsored_Logo";
  const isLeftRailDisplay = adType === "Sponsored_Display" && slot === "left_rail";

  // Apply 40% reduction only for Target's ListingPageBannerAd
  const isTargetListingBanner = retailer?.toLowerCase() === "target" && adType === "ListingPageBannerAd";
  if (isTargetListingBanner && mediaHeight?.endsWith("px")) {
    const pixelValue = parseInt(mediaHeight, 10);
    if (!isNaN(pixelValue)) {
      const reducedHeight = Math.round(pixelValue * 0.6);
      mediaHeight = `${reducedHeight}px`;
    }
  }

  // Apply 25% reduction only for Kroger's TOA ads
  const isKrogerTOA = retailer?.toLowerCase() === "kroger" && adType === "TOA";
  if (isKrogerTOA && mediaHeight?.endsWith("px")) {
    const pixelValue = parseInt(mediaHeight, 10);
    if (!isNaN(pixelValue)) {
      const reducedHeight = Math.round(pixelValue * 0.75);
      mediaHeight = `${reducedHeight}px`;
    }
  }

  // Apply 25% reduction for Skyscraper ads
  const isSkyscraper = adType === "Skyscraper";
  if (isSkyscraper && mediaHeight?.endsWith("px")) {
    const pixelValue = parseInt(mediaHeight, 10);
    if (!isNaN(pixelValue)) {
      const reducedHeight = Math.round(pixelValue * 0.75);
      mediaHeight = `${reducedHeight}px`;
    }
  }

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

  let heightClass = mediaHeight || "h-[200px]";
  let containerClass = "";
  let useAspectRatio = false;
  let aspectRatio: number | undefined;

  // Gallery Cards: use actual dimensions for proper aspect ratio
  const isGalleryCard = adType === "Gallery_Cards";
  if (isGalleryCard && dimensions?.width && dimensions?.height) {
    useAspectRatio = true;
    aspectRatio = dimensions.width / dimensions.height;
    heightClass = ""; // Let aspect-ratio control height
  } else if (isLeftRailDisplay) {
    heightClass = "";
    containerClass = "flex-1";
  } else if (isSponsoredLogo) {
    // Sponsored Logo ads are square with aspect ratio 1:1
    heightClass = "aspect-square";
  } else if (isColumnCard) {
    heightClass = mediaHeight || "h-[160px]";
  } else if (isTOA || isSBA) {
    // Apply 25% reduction for Kroger's TOA ads
    const isKrogerTOA = retailer?.toLowerCase() === "kroger" && adType === "TOA";
    heightClass = mediaHeight || (isKrogerTOA ? "h-[105px]" : "h-[140px]");
  } else if (adType === "Sponsored_Display") {
    heightClass = mediaHeight || "h-[360px]";
  } else if (adType === "Skyscraper") {
    // Skyscraper ads use full default height for image
    heightClass = mediaHeight || "h-[200px]";
  }

  if (hasVideo) {
    const isSponsoredDisplay = adType === "Sponsored_Display";
    const isLeftColumnAd = mediaHeight === '280px';
    const isGalleryCardLeftColumn = isLeftColumnAd && adType === "Gallery_Cards";
    return (
      <div id="video-frame" className={isLeftColumnAd ? "" : cn("video-frame w-full overflow-hidden rounded-t-lg bg-gray-100 flex items-start justify-start relative", containerClass || heightClass)} style={isLeftColumnAd ? { position: 'absolute', top: 0, left: 0, right: 0, height: mediaHeight, margin: 0, padding: 0, backgroundColor: 'rgb(243, 244, 246)' } : {}}>
        <video
          key={`${src}-${mediaKey}`}
          src={src}
          className={cn("h-full w-full", isGalleryCardLeftColumn ? "object-contain" : "object-cover")}
          style={{ display: error ? 'none' : 'block', objectPosition: isGalleryCardLeftColumn ? 'center' : (isSkyscraper ? 'top center' : 'left 20%') }}
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

  const isLeftColumnAd = mediaHeight === '280px';
  const isGalleryCardLeftColumn = isLeftColumnAd && adType === "Gallery_Cards";
  
  // For Gallery Cards with dimensions, use simple width:100% height:auto layout
  const useAutoHeight = isGalleryCard && useAspectRatio;
  
  // Build container style
  const containerStyle: React.CSSProperties = useAutoHeight
    ? { width: '100%' }  // Let image determine height naturally
    : isLeftColumnAd 
      ? { position: 'absolute', top: 0, left: 0, right: 0, height: mediaHeight, margin: 0, padding: 0, backgroundColor: 'rgb(243, 244, 246)' }
      : useAspectRatio && aspectRatio 
        ? { aspectRatio: aspectRatio, width: '100%' }
        : {};

  return (
    <div id="image-frame" className={useAutoHeight ? "w-full overflow-hidden rounded-t-lg" : ((isLeftColumnAd) ? "" : cn("image-frame w-full overflow-hidden rounded-t-lg bg-gray-100 flex items-start justify-start relative", !useAspectRatio && (containerClass || heightClass)))} style={containerStyle}>
      <img
        key={`${src}-${mediaKey}`}
        src={src}
        alt={alt || 'ad'}
        className={useAutoHeight ? "w-full h-auto" : cn("w-full", useAspectRatio ? "h-auto object-contain" : "h-full object-cover")}
        style={{ display: error ? 'none' : 'block', ...(useAutoHeight ? {} : { objectPosition: useAspectRatio ? 'center' : (isSkyscraper ? 'top center' : 'left 20%') }), ...(isLeftColumnAd && !useAutoHeight && { margin: 0, padding: 0 }) }}
        crossOrigin="anonymous"
        referrerPolicy="no-referrer"
        decoding="async"
        loading={priority ? 'eager' : 'lazy'}
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
  Gallery_Cards: "bg-cyan-600 text-white",
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
  retailer: string; client: string; keyword: string; ad_type: string; brand: string; message: string; image_url: string; video_url?: string; video_overlay?: VideoOverlay; poster_url?: string; timestamp: string; slot?: string; card_format?: string; dimensions?: { width: number; height: number };
}

export function AdCard({ ad, onRemove, onOpen, draggableProps, dragIndex, dragOverIndex, currentIndex, priority, isLeftColumn = false }: { ad: Ad; onRemove: (id: string)=>void; onOpen: (ad: Ad)=>void; draggableProps?: any; dragIndex?: number | null; dragOverIndex?: number | null; currentIndex?: number; priority?: boolean; isLeftColumn?: boolean; }) {
  const [hidden, setHidden] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const isBeingDragged = dragIndex === currentIndex;
  const isDropTarget = dragOverIndex === currentIndex;

  // Narrow column cards use stacked vertical layout
  const isColumnCard = ad.ad_type === "Sponsored_Brand_Card" || ad.ad_type === "Sponsored_Logo";
  const isSponsoredLogo = ad.ad_type === "Sponsored_Logo";
  const isLeftRailDisplay = ad.ad_type === "Sponsored_Display" && ad.slot === "left_rail";

  // Apply 40% reduction to container height for Target's ListingPageBannerAd
  const isTargetListingBanner = ad.retailer?.toLowerCase() === "target" && ad.ad_type === "ListingPageBannerAd";
  // Apply 25% + 15% reduction to container height for Kroger's TOA ads
  const isKrogerTOA = ad.retailer?.toLowerCase() === "kroger" && ad.ad_type === "TOA";
  const isGalleryCard = ad.ad_type === "Gallery_Cards";
  const hasGalleryCardDimensions = isGalleryCard && ad.dimensions?.width && ad.dimensions?.height;
  let containerHeight: string | undefined = '420px';
  if (isGalleryCard && isLeftColumn) {
    // For Gallery Cards with dimensions, let height be auto so it shrinks to fit image
    containerHeight = hasGalleryCardDimensions ? undefined : '320px';
  } else if (isTargetListingBanner && isLeftColumn) {
    containerHeight = '252px';
  } else if (isKrogerTOA && isLeftColumn) {
    containerHeight = '268px';
  }

  if (isLeftRailDisplay) {
    console.log('🎯 LEFT RAIL DISPLAY AD:', { ad_type: ad.ad_type, slot: ad.slot, brand: ad.brand });
  }

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

  const getLogoHeight = (retailer: string) => {
    return retailer.toLowerCase() === 'walmart' ? 'h-11' : 'h-8';
  };

  // For Gallery Cards with dimensions, use normal flow (not absolute) so content is below image
  const useFlowLayout = hasGalleryCardDimensions && isLeftColumn;
  
  const contentFrame = (
    <div id="content-frame" className={cn("adcard-content-box card-text w-full flex flex-col flex-shrink-0", isColumnCard ? "p-4 gap-2" : "p-6 gap-3")} style={isLeftColumn && !useFlowLayout ? { position: 'absolute', bottom: 0, left: 0, right: 0, backgroundColor: isSponsoredLogo ? 'rgba(0, 0, 0, 0.6)' : 'rgb(255, 255, 255)', borderBottomLeftRadius: '12px', borderBottomRightRadius: '12px', padding: isSponsoredLogo ? '12px 16px' : '0 16px 16px 16px' } : (useFlowLayout ? { backgroundColor: 'rgb(255, 255, 255)', borderBottomLeftRadius: '12px', borderBottomRightRadius: '12px', padding: '12px 16px 16px 16px' } : {})}>
      {isColumnCard ? (
        <>
          <div className={cn("font-bold text-[1.1em] line-clamp-2 leading-tight", isSponsoredLogo ? "text-white" : "text-[#111827]")}>{ad.brand}</div>
          <div className="flex items-center justify-between gap-2">
            <Badge className={cn("pill text-xs py-1", TYPE_STYLES[ad.ad_type] || "bg-gray-200 text-gray-800 border-none")} style={{ flex: 'none' }}>{normalizeAdType(ad.ad_type)}</Badge>
          </div>
          <div className={cn("italic text-xs line-clamp-1", isSponsoredLogo ? "text-gray-200" : "text-[#6b7280]")}>{ad.keyword}</div>
          <div className={cn("text-xs flex items-center justify-between gap-2", isSponsoredLogo ? "text-gray-200" : "text-[#6b7280]")}>
            <span className="flex-1">
              {ad.timestamp.includes('BADGE_START') ? (
                <span className="line-clamp-1">
                  {ad.timestamp.split('BADGE_START')[0]}
                  <span className="inline-block rounded-full bg-gradient-to-br from-purple-600 to-blue-600 text-white text-xs font-bold px-1.5 py-0.5 mx-0.5 shadow-md border border-white/30 align-text-bottom">
                    Seen ×{ad.timestamp.split('BADGE_START')[1].split('BADGE_END')[0]}
                  </span>
                </span>
              ) : ad.timestamp.startsWith('Seen ') ? (
                <span className="line-clamp-1">{ad.timestamp}</span>
              ) : (
                <span className="line-clamp-1">{formatLocal(ad.timestamp)}</span>
              )}
            </span>
            <div className="flex-none">
              <span className="sr-only">{ad.retailer}</span>
              <RetailerLogo retailer={ad.retailer} className={`${getLogoHeight(ad.retailer)} w-auto`} />
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="flex items-center justify-between w-full">
            <div className="font-bold text-[1.3em] text-[#111827] flex-1">{ad.brand}</div>
            <Badge className={cn("pill flex-none", TYPE_STYLES[ad.ad_type] || "bg-gray-200 text-gray-800 border-none")}>{normalizeAdType(ad.ad_type)}</Badge>
          </div>
          <div className="italic text-[#6b7280] text-sm">{ad.keyword}</div>
          <div className="text-xs text-[#6b7280] flex items-center justify-between gap-2">
            <span className="flex-1">
              {ad.timestamp.includes('BADGE_START') ? (
                <span>
                  {ad.timestamp.split('BADGE_START')[0]}
                  <span className="inline-block rounded-full bg-gradient-to-br from-purple-600 to-blue-600 text-white text-xs font-bold px-2 py-0.5 mx-1 shadow-md border border-white/30">
                    Seen ×{ad.timestamp.split('BADGE_START')[1].split('BADGE_END')[0]}
                  </span>
                  {ad.timestamp.split('BADGE_END')[1]}
                </span>
              ) : ad.timestamp.startsWith('Seen ') ? ad.timestamp : formatLocal(ad.timestamp)}
            </span>
            <div className="flex-none">
              <span className="sr-only">{ad.retailer}</span>
              <RetailerLogo retailer={ad.retailer} className={`${getLogoHeight(ad.retailer)} w-auto`} />
            </div>
          </div>
        </>
      )}
    </div>
  );

  return (
    <div
      id="ad-card-outer"
      className={cn(
        "content-frame break-inside-avoid relative w-full transition-all duration-100 user-select-none",
        !isLeftColumn && "card-surface",
        "group",
        isDragging && "opacity-70 shadow-lg scale-[0.98]",
        isDropTarget && "translate-y-2",
        isLeftRailDisplay && "min-h-[1600px] flex flex-col",
        isLeftColumn && "bg-white rounded-lg cursor-pointer"
      )}
      style={{
        touchAction: 'none',
        ...(isDropTarget && { boxShadow: '0 20px 48px rgba(0, 0, 0, 0.25)' }),
        ...(isLeftRailDisplay && { minHeight: '1600px', display: 'flex', flexDirection: 'column' }),
        ...(isLeftColumn && isSponsoredLogo && { position: 'relative', height: '100%', width: '100%', aspectRatio: '1', display: 'flex', flexDirection: 'column', padding: 0, margin: 0, overflow: 'hidden' }),
        ...(isLeftColumn && !isSponsoredLogo && { position: 'relative', height: containerHeight || 'auto', display: 'block', padding: 0, margin: 0, overflow: 'hidden' })
      }}
      onClick={isLeftColumn ? () => onOpen(ad) : undefined}
      {...enhancedDraggableProps}
      role="article"
      aria-label={`Ad card ${ad.brand}`}
    >
      <button
        aria-label="Remove ad"
        onClick={(e) => { e.stopPropagation(); setHidden(true); onRemove(ad.id); }}
        className="absolute right-2 top-2 h-8 w-8 grid place-items-center rounded-full bg-white/90 border opacity-0 group-hover:opacity-100 transition z-20"
      >
        ×
      </button>
      {isLeftColumn ? (
        <>
          <AdMedia imageUrl={ad.image_url} alt={`${ad.brand} ad`} isTOA={ad.ad_type === "TOA"} isSBA={ad.ad_type === "SBA"} adType={ad.ad_type} slot={ad.slot} priority={priority} mediaHeight={isLeftColumn ? '280px' : undefined} retailer={ad.retailer} dimensions={ad.dimensions} />
          {contentFrame}
        </>
      ) : (
        <button onClick={() => onOpen(ad)} className={cn("text-left select-none w-full", isColumnCard || ad.ad_type === "Sponsored_Display" ? "flex flex-col h-full" : "block")} style={{ touchAction: 'none' }}>
          <AdMedia imageUrl={ad.image_url} alt={`${ad.brand} ad`} isTOA={ad.ad_type === "TOA"} isSBA={ad.ad_type === "SBA"} adType={ad.ad_type} slot={ad.slot} priority={priority} mediaHeight={isLeftColumn ? '280px' : undefined} retailer={ad.retailer} dimensions={ad.dimensions} />
          {contentFrame}
        </button>
      )}
    </div>
  );
}
