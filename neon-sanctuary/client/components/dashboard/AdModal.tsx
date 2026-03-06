import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { toLocalImageUrl } from "@/utils/imageUrl";
import { formatLocal } from "@/lib/date";
import { normalizeAdType } from "@/lib/utils";
import type { NormBox } from "@/components/media/useOverlayBoxFromImage";
import { Ad } from "./AdCard";
import { useState, useEffect, useRef, useMemo } from "react";

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

  // Debug: log overlay box when it changes
  useEffect(() => {
    if (ad?.video_url && overlayBox) {
      console.log('[Video Overlay]', {
        source: metadataBox ? 'metadata' : 'fallback',
        video_overlay_raw: ad?.video_overlay,
        overlayBox,
        css: {
          top: `${(overlayBox.y * 100).toFixed(1)}%`,
          left: `${(overlayBox.x * 100).toFixed(1)}%`,
          width: `${(overlayBox.w * 100).toFixed(1)}%`,
          height: `${(overlayBox.h * 100).toFixed(1)}%`,
        }
      });
    }
  }, [ad?.video_url, overlayBox, metadataBox, ad?.video_overlay]);

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
              className="rounded-lg overflow-hidden cursor-zoom-in bg-white flex items-center justify-center min-h-[400px]"
              onClick={() => setFullscreenOpen(true)}
            >
              {/* Wrapper div that matches image size exactly for proper video positioning */}
              <div style={{ position: 'relative', display: 'inline-block', isolation: 'isolate' }}>
                <img
                  src={(() => {
                    const url = toLocalImageUrl(ad.image_url);
                    if (!url) return url;
                    try {
                      const u = new URL(url, window.location.origin);
                      u.searchParams.set('thumbnail', 'false');
                      return u.toString();
                    } catch {
                      return url.includes('?') ? `${url}&thumbnail=false` : `${url}?thumbnail=false`;
                    }
                  })()}
                  alt={`${ad.brand} ad`}
                  style={{
                    display: 'block',
                    maxWidth: '100%',
                    maxHeight: '100%',
                    width: 'auto',
                    height: 'auto',
                  }}
                  crossOrigin="anonymous"
                  decoding="async"
                  loading="eager"
                  onLoad={() => setPopupImageLoaded(prev => !prev)}
                />
                {ad.video_url && metadataBox && (
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
                      top: `${metadataBox.y * 100}%`,
                      left: `${metadataBox.x * 100}%`,
                      width: `${metadataBox.w * 100}%`,
                      height: `${metadataBox.h * 100}%`,
                      objectFit: 'fill',
                      zIndex: 2,
                      pointerEvents: 'none',
                      borderRadius: ad.video_overlay?.border_radius ? `${ad.video_overlay.border_radius}px` : undefined,
                    }}
                    crossOrigin="anonymous"
                  />
                )}
              </div>
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
                className="relative max-w-[min(90vw,1100px)] inline-block"
              >
                <img
                  ref={fullscreenImgRef}
                  src={(() => {
                    const url = toLocalImageUrl(ad.image_url);
                    if (!url) return url;
                    try {
                      const u = new URL(url, window.location.origin);
                      u.searchParams.set('thumbnail', 'false');
                      return u.toString();
                    } catch {
                      return url.includes('?') ? `${url}&thumbnail=false` : `${url}?thumbnail=false`;
                    }
                  })()}
                  alt={`${ad.brand} full preview`}
                  style={{
                    display: 'block',
                    maxWidth: '100%',
                    height: 'auto',
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
                {ad.video_url && metadataBox && (
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
                      top: `${metadataBox.y * 100}%`,
                      left: `${metadataBox.x * 100}%`,
                      width: `${metadataBox.w * 100}%`,
                      height: `${metadataBox.h * 100}%`,
                      objectFit: 'fill',
                      zIndex: 2,
                      pointerEvents: 'none',
                      borderRadius: ad.video_overlay?.border_radius ? `${ad.video_overlay.border_radius}px` : undefined,
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
