import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { toLocalImageUrl } from "@/utils/imageUrl";
import { formatLocal } from "@/lib/date";
import { Ad } from "./AdCard";
import { useState, useEffect } from "react";

export function AdModal({ open, ad, onOpenChange, onCompare }: { open: boolean; ad: Ad | null; onOpenChange: (v: boolean)=>void; onCompare: (ad: Ad)=>void; }) {
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [fullscreenOpen, setFullscreenOpen] = useState(false);

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
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogTitle className="sr-only">{ad ? `${ad.brand || "Unknown"} ad details` : "Ad details"}</DialogTitle>
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
        {ad && (() => {
          const raw = ad.image_url || ad.poster_url || null;
          const src = toLocalImageUrl(raw) || raw;
          
          const handleImgError = (e: React.SyntheticEvent<HTMLImageElement>) => {
            e.currentTarget.onerror = null; // prevent loop
            const label = encodeURIComponent(`${ad.id || ad.brand || 'noid'}`);
            const base = (window as any).AD_BASE || '';
            e.currentTarget.src = `${base}/api/image/placeholder?text=${label}`;
          };
          
          return (
          <div className="grid md:grid-cols-2 gap-6">
            <div className="rounded-lg overflow-hidden cursor-pointer" onClick={() => setFullscreenOpen(true)}>
              {src ? (
                <img 
                  src={src} 
                  onError={handleImgError}
                  alt={`${ad.brand} full`} 
                  className="w-full h-full object-contain hover:opacity-80 transition-opacity" 
                  crossOrigin="anonymous" 
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center bg-gray-100 text-gray-400">No image</div>
              )}
            </div>
            <div className="space-y-3">
              <h3 className="text-2xl font-bold">{ad.brand || "Unknown Brand"}</h3>
              <div className="text-sm text-muted-foreground">{ad.retailer} • {ad.ad_type}</div>
              <div className="text-sm"><span className="font-semibold">Keyword:</span> {ad.keyword}</div>
              <div className="text-sm"><span className="font-semibold">Client:</span> {ad.client}</div>
              <div className="text-sm"><span className="font-semibold">Date:</span> {formatLocal(ad.timestamp)}</div>
              <div className="pt-4 flex gap-2">
                {src && <Button onClick={() => { const a = document.createElement('a'); a.href = src; a.download = `${ad.brand}-${ad.ad_type}.png`; a.click(); }}>Download</Button>}
                <Button variant="secondary" onClick={() => onCompare(ad)}>Compare</Button>
              </div>
            </div>
          </div>
          );
        })()}
      </DialogContent>

      <Dialog open={fullscreenOpen} onOpenChange={setFullscreenOpen}>
        <DialogContent className="max-w-full w-screen h-screen max-h-screen p-0 border-0 flex items-center justify-center" onClick={() => setFullscreenOpen(false)}>
          <DialogTitle className="sr-only">Full size preview</DialogTitle>
          <div
            className="w-full h-full flex items-center justify-center p-4 bg-black/90"
            onClick={(e) => e.stopPropagation()}
          >
            {(() => {
              const raw = ad?.image_url || ad?.poster_url || null;
              const src = toLocalImageUrl(raw) || raw;
              
              const handleFullscreenError = (e: React.SyntheticEvent<HTMLImageElement>) => {
                e.currentTarget.onerror = null; // prevent loop
                const label = encodeURIComponent(`${ad?.id || ad?.brand || 'noid'}`);
                const base = (window as any).AD_BASE || '';
                e.currentTarget.src = `${base}/api/image/placeholder?text=${label}`;
              };
              
              return src ? (
                <img
                  src={src}
                  onError={handleFullscreenError}
                  alt={`${ad?.brand} full preview`}
                  className="max-w-full max-h-full object-contain cursor-pointer"
                  crossOrigin="anonymous"
                  onClick={() => setFullscreenOpen(false)}
                />
              ) : (
                <div className="text-white">No image available</div>
              );
            })()}
          </div>
        </DialogContent>
      </Dialog>
    </Dialog>
  );
}
