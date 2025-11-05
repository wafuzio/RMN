import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { toLocalImageUrl } from "@/utils/imageUrl";
import { formatLocal } from "@/lib/date";
import { useOverlayBoxFromImage, type NormBox } from "@/components/media/useOverlayBoxFromImage";
import { Ad } from "./AdCard";
import { useState, useEffect, useRef } from "react";
import type { VideoOverlay } from "@shared/api";

// Ad type-specific video positioning (normalized 0..1)
// Calculated for actual Walmart SBV dimensions: 1078×341px
// Video slot: 544×301px starting at (0, 18)
const VIDEO_LAYOUTS: Record<string, NormBox> = {
  'SBV': {
    x: 0.0,
    y: 0.0528,   // 18 / 341 = 0.0528
    w: 0.5046,   // 544 / 1078 = 0.5046
    h: 0.8827,   // 301 / 341 = 0.8827
  },
  'Sponsored_Brand_Video': {
    x: 0.0,
    y: 0.0528,
    w: 0.5046,
    h: 0.8827,
  },
  'Shoppable_Display_Ad': {
    x: 0.0,
    y: 0.0528,
    w: 0.5046,
    h: 0.8827,
  },
  'Display_Ads': {
    x: 0.0,
    y: 0.0528,
    w: 0.5046,
    h: 0.8827,
  },
  'default': {
    x: 0.0,
    y: 0.0528,
    w: 0.5046,
    h: 0.8827,
  }
};

export function AdModal({ open, ad, onOpenChange, onCompare }: { open: boolean; ad: Ad | null; onOpenChange: (v: boolean)=>void; onCompare: (ad: Ad)=>void; }) {
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [fullscreenOpen, setFullscreenOpen] = useState(false);
  const [fullscreenImageLoaded, setFullscreenImageLoaded] = useState(false);
  const [popupImageLoaded, setPopupImageLoaded] = useState(false);

  const popupFrameRef = useRef<HTMLDivElement>(null);
  const popupImgRef = useRef<HTMLImageElement>(null);

  const fullscreenFrameRef = useRef<HTMLDivElement>(null);
  const fullscreenImgRef = useRef<HTMLImageElement>(null);

  // Calculate video overlay box dynamically based on actual image dimensions
  // Video slot is approximately 544×301px starting at (0, 18) for Walmart SBV ads
  // Add slight padding to ensure full coverage
  const [dynamicBox, setDynamicBox] = useState<NormBox>(VIDEO_LAYOUTS['default']);
  
  useEffect(() => {
    if (popupImgRef.current && popupImgRef.current.naturalWidth > 0) {
      const img = popupImgRef.current;
      const padding = 0; // No padding - use exact slot dimensions
      const newBox = {
        x: 0 / img.naturalWidth,  // Start at left edge
        y: 18 / img.naturalHeight,  // Start at y=18
        w: (544 + padding * 2) / img.naturalWidth,  // Exact width: 544px
        h: (301 + padding * 2) / img.naturalHeight,  // Exact height: 301px
      };
      console.log('Recalculating dynamicBox:', newBox, 'for image:', img.naturalWidth, 'x', img.naturalHeight);
      
      // Small delay to ensure video element has time to render with new dimensions
      setTimeout(() => {
        setDynamicBox(newBox);
      }, 10);
    }
  }, [ad?.id, popupImageLoaded, fullscreenOpen]);
  
  const box: NormBox = dynamicBox;
  const popupPxRaw = useOverlayBoxFromImage(popupFrameRef.current, popupImgRef.current, box);
  const fullscreenPxRaw = useOverlayBoxFromImage(fullscreenFrameRef.current, fullscreenImgRef.current, box);
  
  // Force recalculation when modal opens (handles cached images)
  useEffect(() => {
    if (open && popupImgRef.current) {
      // Trigger a reflow to ensure image dimensions are available
      const img = popupImgRef.current;
      void img.offsetHeight; // Force reflow
      
      // Dispatch resize to trigger overlay recalculation
      setTimeout(() => {
        if (popupFrameRef.current) {
          const event = new Event('resize', { bubbles: true });
          window.dispatchEvent(event);
        }
      }, 0);
    }
  }, [open, ad?.id]);
  
  // Debug: log when overlay calculations change
  useEffect(() => {
    if (popupPxRaw && popupImgRef.current) {
      const img = popupImgRef.current;
      const imgRect = img.getBoundingClientRect();
      console.log('Popup overlay calculated:', popupPxRaw);
      console.log('Image dimensions:', {
        width: imgRect.width,
        height: imgRect.height,
        naturalWidth: img.naturalWidth,
        naturalHeight: img.naturalHeight
      });
      console.log('Ad has video_url?', !!ad?.video_url, ad?.video_url);
      
      // Calculate what the overlay SHOULD be for this specific image
      const expectedY = 18 / img.naturalHeight;
      const expectedW = 544 / img.naturalWidth;
      const expectedH = 301 / img.naturalHeight;
      console.log('Expected normalized coords for this image:', {
        y: expectedY.toFixed(4),
        w: expectedW.toFixed(4),
        h: expectedH.toFixed(4),
        currentY: box.y.toFixed(4),
        currentW: box.w.toFixed(4),
        currentH: box.h.toFixed(4)
      });
    }
  }, [popupPxRaw, ad, box]);

  // Apply safety clamps to prevent overflow
  const clampBox = (px: any, containerEl: HTMLElement | null): any => {
    if (!px || !containerEl) return px;
    const containerRect = containerEl.getBoundingClientRect();
    return {
      left: Math.max(0, px.left),
      top: Math.max(0, px.top),
      width: Math.min(px.width, containerRect.width - Math.max(0, px.left)),
      height: Math.min(px.height, containerRect.height - Math.max(0, px.top)),
    };
  };

  // Calculate overlay position from metadata if available
  const getOverlayFromMetadata = (metadata: VideoOverlay | undefined, imgEl: HTMLImageElement | null, containerEl: HTMLElement | null): any => {
    if (!metadata || !imgEl || !containerEl) return null;

    const containerRect = containerEl.getBoundingClientRect();
    const imgRect = imgEl.getBoundingClientRect();
    
    // Calculate image offset within container (due to objectFit: contain centering)
    const offsetX = imgRect.left - containerRect.left;
    const offsetY = imgRect.top - containerRect.top;
    
    // Calculate scale based on rendered image size vs natural size
    const scaleX = imgRect.width / metadata.image_width;
    const scaleY = imgRect.height / metadata.image_height;

    console.log('[AdModal] Using metadata-based overlay:', {
      metadataX: metadata.x,
      metadataY: metadata.y,
      metadataWidth: metadata.width,
      metadataHeight: metadata.height,
      scaleX,
      scaleY,
      offsetX,
      offsetY,
      imgWidth: imgRect.width,
      imgHeight: imgRect.height,
    });

    return {
      left: offsetX + (metadata.x * scaleX),
      top: offsetY + (metadata.y * scaleY),
      width: metadata.width * scaleX,
      height: metadata.height * scaleY,
    };
  };

  // State to store metadata-based overlay positions
  const [metadataPopupPx, setMetadataPopupPx] = useState<any>(null);
  const [metadataFullscreenPx, setMetadataFullscreenPx] = useState<any>(null);

  // Recalculate metadata-based overlays when image loads or modal state changes
  useEffect(() => {
    if (ad?.video_overlay) {
      console.log('[AdModal] Recalculating metadata overlay for ad:', ad.id);
      const popupOverlay = getOverlayFromMetadata(ad.video_overlay, popupImgRef.current, popupFrameRef.current);
      const fullscreenOverlay = getOverlayFromMetadata(ad.video_overlay, fullscreenImgRef.current, fullscreenFrameRef.current);
      setMetadataPopupPx(popupOverlay);
      setMetadataFullscreenPx(fullscreenOverlay);
    }
  }, [ad?.id, ad?.video_overlay, popupImageLoaded, fullscreenImageLoaded, fullscreenOpen]);

  // Use metadata if available, otherwise use dynamic calculation
  const popupPxRaw_final = ad?.video_overlay && metadataPopupPx
    ? metadataPopupPx
    : popupPxRaw;
  const fullscreenPxRaw_final = ad?.video_overlay && metadataFullscreenPx
    ? metadataFullscreenPx
    : fullscreenPxRaw;

  if (ad?.video_overlay) {
    console.log('[AdModal] Video overlay metadata available for ad:', ad.id);
  } else if (ad?.video_url) {
    console.log('[AdModal] No metadata - using dynamic calculation for ad:', ad.id);
  }

  const popupPx = clampBox(popupPxRaw_final, popupFrameRef.current);
  const fullscreenPx = clampBox(fullscreenPxRaw_final, fullscreenFrameRef.current);

  useEffect(() => {
    if (!ad?.brand) {
      setLogoUrl(null);
      return;
    }

    const fetchLogo = async () => {
      try {
        const response = await fetch(`/api/logo/brand/${encodeURIComponent(ad.brand)}`);
        if (response.ok) {
          const blob = await response.blob();
          const url = URL.createObjectURL(blob);
          setLogoUrl(url);
        } else {
          setLogoUrl(null);
        }
      } catch (error) {
        console.error("Failed to fetch brand logo:", error);
        setLogoUrl(null);
      }
    };

    fetchLogo();

    return () => {
      if (logoUrl) {
        URL.revokeObjectURL(logoUrl);
      }
    };
  }, [ad?.brand]);

  // Force recalculation of popup overlay when image loads
  useEffect(() => {
    if (popupImageLoaded && popupFrameRef.current && popupImgRef.current) {
      // Small delay to ensure image is fully painted
      setTimeout(() => {
        const frame = popupFrameRef.current;
        const img = popupImgRef.current;
        if (frame && img) {
          // Trigger a resize event to force ResizeObserver updates
          const event = new Event('resize', { bubbles: true });
          frame.dispatchEvent(event);
          img.dispatchEvent(event);
        }
      }, 50);
    }
  }, [popupImageLoaded]);

  // Force recalculation of fullscreen overlay when image loads
  useEffect(() => {
    if (fullscreenImageLoaded && fullscreenFrameRef.current && fullscreenImgRef.current) {
      // Small delay to ensure image is fully painted
      setTimeout(() => {
        const frame = fullscreenFrameRef.current;
        const img = fullscreenImgRef.current;
        if (frame && img) {
          // Trigger a resize event to force ResizeObserver updates
          const event = new Event('resize', { bubbles: true });
          frame.dispatchEvent(event);
          img.dispatchEvent(event);
        }
      }, 50);
    }
  }, [fullscreenImageLoaded]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogTitle className="sr-only">{ad ? `${ad.brand} ad details` : "Ad details"}</DialogTitle>
        {logoUrl && (
          <div className="absolute top-4 left-4 z-10">
            <img
              src={logoUrl}
              alt={`${ad?.brand} logo`}
              className="h-16 w-auto object-contain"
              onError={() => setLogoUrl(null)}
            />
          </div>
        )}
        {ad && (
          <div className="grid md:grid-cols-2 gap-6 items-start">
            <div
              ref={popupFrameRef}
              className="rounded-lg overflow-hidden cursor-pointer relative bg-gray-100 flex items-center justify-center min-h-[400px]"
              onClick={() => setFullscreenOpen(true)}
            >
              <img
                ref={popupImgRef}
                src={toLocalImageUrl(ad.image_url)}
                alt={`${ad.brand} ad`}
                style={{
                  display: 'block',
                  maxWidth: '100%',
                  maxHeight: '100%',
                  width: 'auto',
                  height: 'auto',
                  objectFit: 'contain',
                }}
                crossOrigin="anonymous"
                decoding="async"
                loading="eager"
                onLoad={() => setPopupImageLoaded(prev => !prev)}
              />
              {ad.video_url && (
                <video
                  key={`popup-${ad.id}-${popupImageLoaded}`}
                  src={toLocalImageUrl(ad.video_url)}
                  autoPlay
                  muted
                  loop
                  playsInline
                  preload="metadata"
                  style={{
                    position: 'absolute',
                    top: popupPx?.top ?? 0,
                    left: popupPx?.left ?? 0,
                    width: popupPx?.width ?? 0,
                    height: popupPx?.height ?? 0,
                    objectFit: 'fill',
                    display: popupPx ? 'block' : 'none',
                    zIndex: 2,
                    pointerEvents: 'none',
                  }}
                  crossOrigin="anonymous"
                />
              )}
            </div>
            <div className="space-y-3">
              <h3 className="text-2xl font-bold">{ad.brand}</h3>
              <div className="text-sm text-muted-foreground">{ad.retailer} • {ad.ad_type}</div>
              <div className="text-sm"><span className="font-semibold">Keyword:</span> {ad.keyword}</div>
              <div className="text-sm"><span className="font-semibold">Client:</span> {ad.client}</div>
              <div className="text-sm"><span className="font-semibold">Date:</span> {formatLocal(ad.timestamp)}</div>
              <div className="pt-4 flex gap-2">
                <Button onClick={async () => {
                  try {
                    const response = await fetch(toLocalImageUrl(ad.image_url));
                    const blob = await response.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `${ad.brand}-${ad.ad_type}.png`;
                    a.click();
                    URL.revokeObjectURL(url);
                  } catch (error) {
                    console.error('Failed to download image:', error);
                  }
                }}>Download</Button>
                <Button variant="secondary" onClick={() => onCompare(ad)}>Compare</Button>
              </div>
            </div>
          </div>
        )}
      </DialogContent>

      {ad?.image_url && (
        <Dialog open={fullscreenOpen} onOpenChange={setFullscreenOpen}>
          <DialogContent className="max-w-full w-screen h-screen max-h-screen p-0 border-0 flex items-center justify-center" onClick={() => setFullscreenOpen(false)}>
            <DialogTitle className="sr-only">Full size preview</DialogTitle>
            <div
              className="w-full h-full flex items-center justify-center p-4 bg-black/90"
              onClick={(e) => e.stopPropagation()}
            >
              <div
                ref={fullscreenFrameRef}
                className="relative w-full max-w-[min(90vw,1100px)] overflow-hidden"
              >
                <img
                  ref={fullscreenImgRef}
                  src={toLocalImageUrl(ad.image_url)}
                  alt={`${ad.brand} full preview`}
                  style={{
                    display: 'block',
                    width: '100%',
                    height: 'auto',
                    objectFit: 'contain',
                    cursor: 'pointer',
                  }}
                  crossOrigin="anonymous"
                  decoding="async"
                  loading="eager"
                  onClick={() => setFullscreenOpen(false)}
                  onLoad={() => setFullscreenImageLoaded(prev => !prev)}
                />
                {ad.video_url && (
                  <video
                    key={`fullscreen-${ad.id}-${fullscreenImageLoaded}`}
                    src={toLocalImageUrl(ad.video_url)}
                    autoPlay
                    muted
                    loop
                    playsInline
                    preload="metadata"
                    style={{
                      position: 'absolute',
                      top: fullscreenPx?.top ?? 0,
                      left: fullscreenPx?.left ?? 0,
                      width: fullscreenPx?.width ?? 0,
                      height: fullscreenPx?.height ?? 0,
                      objectFit: 'fill',
                      display: fullscreenPx ? 'block' : 'none',
                      zIndex: 2,
                      pointerEvents: 'none',
                    }}
                    crossOrigin="anonymous"
                  />
                )}
              </div>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </Dialog>
  );
}
