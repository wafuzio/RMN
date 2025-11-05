import { useState, useRef, useCallback } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { toLocalImageUrl } from "@/utils/imageUrl";
import type { VideoOverlay } from "@shared/api";

export default function VideoOverlayTest() {
  const [modalOpen, setModalOpen] = useState(false);
  const [fullscreenOpen, setFullscreenOpen] = useState(false);
  const [, setRenderKey] = useState(0);

  const popupFrameRef = useRef<HTMLDivElement>(null);
  const popupImgRef = useRef<HTMLImageElement>(null);
  const fullscreenFrameRef = useRef<HTMLDivElement>(null);
  const fullscreenImgRef = useRef<HTMLImageElement>(null);

  // Store overlay positions in refs (won't trigger re-render)
  const popupOverlayRef = useRef<any>(null);
  const fullscreenOverlayRef = useRef<any>(null);

  const imageUrl = "/api/image/walmart/MilkPEP/SBV/walmart__vital_proteins__sbv__milkpep__protein_powder__D2025-11-04_T20-23.16_1.png";
  const videoUrl = "/api/video/walmart/MilkPEP/SBV/walmart__vital_proteins__sbv__milkpep__protein_powder__D2025-11-04_T20-23.16_1.mp4";

  // Test metadata from JSON (should match backend)
  const videoMetadata: VideoOverlay = {
    x: 2,
    y: 19,
    width: 539,
    height: 305,
    image_width: 1078,
    image_height: 341,
  };

  // Calculate overlay position from metadata
  const calculateOverlay = useCallback((metadata: VideoOverlay, imgEl: HTMLImageElement | null, containerEl: HTMLElement | null): any => {
    if (!metadata || !imgEl || !containerEl) return null;

    const containerRect = containerEl.getBoundingClientRect();
    const imgRect = imgEl.getBoundingClientRect();
    
    // Only calculate if image has actual dimensions
    if (imgRect.width === 0 || imgRect.height === 0) {
      console.log('[VideoOverlayTest] Image not ready yet, skipping overlay calc');
      return null;
    }

    const offsetX = imgRect.left - containerRect.left;
    const offsetY = imgRect.top - containerRect.top;
    
    const scaleX = imgRect.width / metadata.image_width;
    const scaleY = imgRect.height / metadata.image_height;

    console.log('[VideoOverlayTest] Overlay calculated:', {
      metadataX: metadata.x,
      metadataY: metadata.y,
      scaleX: scaleX.toFixed(4),
      scaleY: scaleY.toFixed(4),
      offsetX: offsetX.toFixed(0),
      offsetY: offsetY.toFixed(0),
      imgWidth: imgRect.width.toFixed(0),
      imgHeight: imgRect.height.toFixed(0),
    });

    return {
      left: offsetX + (metadata.x * scaleX),
      top: offsetY + (metadata.y * scaleY),
      width: metadata.width * scaleX,
      height: metadata.height * scaleY,
    };
  }, []);

  // Handle image load - recalculate overlay and trigger re-render
  const handlePopupImageLoad = useCallback(() => {
    console.log('[VideoOverlayTest] Popup image loaded');
    popupOverlayRef.current = calculateOverlay(videoMetadata, popupImgRef.current, popupFrameRef.current);
    // Trigger a re-render by updating render key
    setRenderKey(k => k + 1);
  }, [calculateOverlay, videoMetadata]);

  const handleFullscreenImageLoad = useCallback(() => {
    console.log('[VideoOverlayTest] Fullscreen image loaded');
    fullscreenOverlayRef.current = calculateOverlay(videoMetadata, fullscreenImgRef.current, fullscreenFrameRef.current);
    // Trigger a re-render
    setRenderKey(k => k + 1);
  }, [calculateOverlay, videoMetadata]);

  const clampBox = (px: any): any => {
    if (!px) return px;
    return {
      left: Math.max(0, px.left),
      top: Math.max(0, px.top),
      width: Math.max(0, px.width),
      height: Math.max(0, px.height),
    };
  };

  const popupPxClamped = clampBox(popupOverlayRef.current);
  const fullscreenPxClamped = clampBox(fullscreenOverlayRef.current);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 p-8">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-4xl font-bold text-white mb-2">Video Overlay Test</h1>
        <p className="text-slate-300 mb-8">Click the card to open modal with video overlay</p>

        <div className="grid md:grid-cols-2 gap-8">
          {/* Card Preview */}
          <div
            className="bg-white rounded-lg shadow-lg overflow-hidden cursor-pointer hover:shadow-xl transition-shadow"
            onClick={() => setModalOpen(true)}
          >
            <div className="aspect-video bg-gray-100 flex items-center justify-center">
              <img
                src={imageUrl}
                alt="Vital Proteins Ad"
                className="w-full h-full object-cover"
              />
            </div>
            <div className="p-4">
              <h3 className="font-bold text-lg">Vital Proteins</h3>
              <p className="text-sm text-gray-600">Walmart • SBV (Sponsored Brand Video)</p>
              <p className="text-xs text-gray-500 mt-2">protein powder</p>
            </div>
          </div>

          {/* Info Panel */}
          <div className="bg-slate-700 rounded-lg p-6 text-white">
            <h2 className="text-xl font-bold mb-4">Ad Details</h2>
            <div className="space-y-3 text-sm">
              <div>
                <span className="text-slate-300">Brand:</span>
                <span className="ml-2 font-mono text-cyan-300">Vital Proteins</span>
              </div>
              <div>
                <span className="text-slate-300">Retailer:</span>
                <span className="ml-2 font-mono text-cyan-300">Walmart</span>
              </div>
              <div>
                <span className="text-slate-300">Ad Type:</span>
                <span className="ml-2 font-mono text-cyan-300">SBV</span>
              </div>
              <div>
                <span className="text-slate-300">Keyword:</span>
                <span className="ml-2 font-mono text-cyan-300">protein powder</span>
              </div>
              <hr className="border-slate-600 my-4" />
              <div>
                <span className="text-slate-300 block mb-2">Metadata:</span>
                <pre className="text-xs text-orange-300 bg-slate-800 p-2 rounded overflow-auto">
{JSON.stringify(videoMetadata, null, 2)}
                </pre>
              </div>
            </div>
            <Button onClick={() => setModalOpen(true)} className="w-full mt-6">
              Open Modal
            </Button>
          </div>
        </div>
      </div>

      {/* Modal Dialog */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-4xl">
          <DialogTitle className="sr-only">Ad details</DialogTitle>
          <div className="grid md:grid-cols-2 gap-6 items-start">
            {/* Popup View */}
            <div
              ref={popupFrameRef}
              className="rounded-lg overflow-hidden cursor-pointer relative bg-gray-100 flex items-center justify-center min-h-[400px]"
              onClick={() => setFullscreenOpen(true)}
            >
              <img
                ref={popupImgRef}
                src={imageUrl}
                alt="Vital Proteins ad"
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
                onLoad={handlePopupImageLoad}
              />
              {popupPxClamped && (
                <video
                  src={toLocalImageUrl(videoUrl)}
                  autoPlay
                  muted
                  loop
                  playsInline
                  preload="metadata"
                  style={{
                    position: 'absolute',
                    top: `${popupPxClamped.top}px`,
                    left: `${popupPxClamped.left}px`,
                    width: `${popupPxClamped.width}px`,
                    height: `${popupPxClamped.height}px`,
                    objectFit: 'cover',
                    objectPosition: 'center',
                    zIndex: 2,
                    pointerEvents: 'none',
                  }}
                  crossOrigin="anonymous"
                />
              )}
            </div>

            {/* Info Panel */}
            <div className="space-y-3">
              <h3 className="text-2xl font-bold">Vital Proteins</h3>
              <div className="text-sm text-muted-foreground">Walmart • SBV</div>
              <div className="text-sm"><span className="font-semibold">Keyword:</span> protein powder</div>
              <div className="text-sm"><span className="font-semibold">Client:</span> MilkPEP</div>
              <div className="pt-4 flex gap-2">
                <Button onClick={() => setFullscreenOpen(true)}>View Fullscreen</Button>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Fullscreen Modal */}
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
                src={imageUrl}
                alt="Vital Proteins full preview"
                style={{
                  display: 'block',
                  width: '100%',
                  height: 'auto',
                  objectFit: 'contain',
                  cursor: 'pointer',
                }}
                crossOrigin="anonymous"
                decoding="async"
                onClick={() => setFullscreenOpen(false)}
                onLoad={handleFullscreenImageLoad}
              />
              {fullscreenPxClamped && (
                <video
                  src={toLocalImageUrl(videoUrl)}
                  autoPlay
                  muted
                  loop
                  playsInline
                  preload="metadata"
                  style={{
                    position: 'absolute',
                    top: `${fullscreenPxClamped.top}px`,
                    left: `${fullscreenPxClamped.left}px`,
                    width: `${fullscreenPxClamped.width}px`,
                    height: `${fullscreenPxClamped.height}px`,
                    objectFit: 'cover',
                    objectPosition: 'center',
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
    </div>
  );
}
