import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { toLocalImageUrl } from "@/utils/imageUrl";
import { formatLocal } from "@/lib/date";
import { normalizeAdType } from "@/lib/utils";
import { useOverlayBoxFromImage, type NormBox } from "@/components/media/useOverlayBoxFromImage";
import { Ad } from "./AdCard";
import { useState, useEffect, useRef, useMemo } from "react";
import type { VideoOverlay } from "@shared/api";

// Ad type-specific video positioning (normalized 0..1)
// Calibrated for Walmart SBV reference image: 1078×341px
// Video slot: 541×311px starting at (2, 15) per calibration guide
const VIDEO_LAYOUTS: Record<string, NormBox> = {
  'SBV': {
    x: 2 / 1078,
    y: 15 / 341,
    w: 541 / 1078,
    h: 311 / 341,
  },
  'Sponsored_Brand_Video': {
    x: 2 / 1078,
    y: 15 / 341,
    w: 541 / 1078,
    h: 311 / 341,
  },
  'Shoppable_Video_Ad': {
    x: 2 / 1078,
    y: 15 / 341,
    w: 541 / 1078,
    h: 311 / 341,
  },
  'default': {
    x: 2 / 1078,
    y: 15 / 341,
    w: 541 / 1078,
    h: 311 / 341,
  }
};

import { AdGroup } from "@/lib/aggregateAds";

export function AdModal({ open, ad, group, onOpenChange, onCompare }: { open: boolean; ad: Ad | null; group?: AdGroup | null; onOpenChange: (v: boolean)=>void; onCompare: (ad: Ad)=>void; }) {
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [fullscreenOpen, setFullscreenOpen] = useState(false);
  const [fullscreenImageLoaded, setFullscreenImageLoaded] = useState(false);
  const [popupImageLoaded, setPopupImageLoaded] = useState(false);
  const [fullscreenImageDimensions, setFullscreenImageDimensions] = useState<{ width: number; height: number } | null>(null);

  const popupFrameRef = useRef<HTMLDivElement>(null);
  const popupImgRef = useRef<HTMLImageElement>(null);

  const fullscreenFrameRef = useRef<HTMLDivElement>(null);
  const fullscreenImgRef = useRef<HTMLImageElement>(null);

  const metadataBox = useMemo<NormBox | null>(() => {
    const vo = ad?.video_overlay;
    if (!vo || !vo.image_width || !vo.image_height) return null;

    return {
      x: vo.x / vo.image_width,
      y: vo.y / vo.image_height,
      w: vo.width / vo.image_width,
      h: vo.height / vo.image_height,
    };
  }, [ad?.video_overlay]);

  const fallbackBox = useMemo<NormBox>(() => {
    const typeKey = normalizeAdType(ad?.ad_type ?? "") || "default";
    return VIDEO_LAYOUTS[typeKey] ?? VIDEO_LAYOUTS['default'];
  }, [ad?.ad_type]);

  const overlayBox = metadataBox ?? fallbackBox;

  const popupPxRaw = useOverlayBoxFromImage(popupFrameRef.current, popupImgRef.current, overlayBox);
  const fullscreenPxRaw = useOverlayBoxFromImage(fullscreenFrameRef.current, fullscreenImgRef.current, overlayBox);
  
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
      console.debug('[Overlay]', {
        source: metadataBox ? 'metadata' : 'fallback',
        natural: `${img.naturalWidth}×${img.naturalHeight}`,
        rendered: `${Math.round(imgRect.width)}×${Math.round(imgRect.height)}`,
        box: overlayBox,
        px: popupPxRaw,
      });
    }
  }, [popupPxRaw, metadataBox, overlayBox]);

  // Apply safety clamps to prevent overflow
  // NOTE: Disabled clamping for video overlays - they need exact dimensions from metadata
  const clampBox = (px: any, containerEl: HTMLElement | null): any => {
    if (!px || !containerEl) return px;
    // Don't clamp - return exact dimensions for pixel-perfect alignment
    return px;
  };

  // Calculate overlay position from metadata if available
  // Memoized to prevent recalculation on every render
  const popupPx = clampBox(popupPxRaw, popupFrameRef.current);
  const fullscreenPx = clampBox(fullscreenPxRaw, fullscreenFrameRef.current);

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

  // Reset image dimensions when modal closes or ad changes
  useEffect(() => {
    if (!fullscreenOpen) {
      setFullscreenImageDimensions(null);
    }
  }, [fullscreenOpen, ad?.id]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-6xl w-[90vw]">
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
          <div className="grid md:grid-cols-[2fr_1fr] gap-6 items-start">
            <div
              ref={popupFrameRef}
              className="rounded-lg overflow-hidden cursor-zoom-in relative bg-white flex items-center justify-center min-h-[400px]"
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
              <div className="text-sm text-muted-foreground">{ad.retailer.charAt(0).toUpperCase() + ad.retailer.slice(1)} • {normalizeAdType(ad.ad_type)}</div>
              <div className="text-sm"><span className="font-semibold">Client:</span> {ad.client}</div>
              
              {/* Show all timestamps with keywords if this is a grouped ad */}
              {group && group.count > 1 ? (
                <div className="text-sm">
                  <div className="font-semibold mb-1">Seen {group.count} times:</div>
                  <div className="max-h-32 overflow-y-auto space-y-1 text-xs bg-muted/30 rounded p-2">
                    {group.instances.map((instance, idx) => (
                      <div key={idx} className="flex justify-between gap-2">
                        <span className="text-muted-foreground italic">{instance.keyword}</span>
                        <span>{formatLocal(instance.timestamp)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <>
                  <div className="text-sm"><span className="font-semibold">Keyword:</span> {ad.keyword}</div>
                  <div className="text-sm"><span className="font-semibold">Date:</span> {formatLocal(ad.timestamp)}</div>
                </>
              )}
              
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
                    maxWidth: fullscreenImageDimensions ? `${fullscreenImageDimensions.width}px` : '100%',
                    objectFit: 'contain',
                    cursor: 'pointer',
                  }}
                  crossOrigin="anonymous"
                  decoding="async"
                  loading="eager"
                  onClick={() => setFullscreenOpen(false)}
                  onLoad={() => {
                    if (fullscreenImgRef.current) {
                      setFullscreenImageDimensions({
                        width: fullscreenImgRef.current.naturalWidth,
                        height: fullscreenImgRef.current.naturalHeight,
                      });
                    }
                    setFullscreenImageLoaded(prev => !prev);
                  }}
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
