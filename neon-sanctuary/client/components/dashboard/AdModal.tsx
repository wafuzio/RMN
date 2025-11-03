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
          <div className="grid md:grid-cols-2 gap-6">
            <div className="rounded-lg overflow-hidden cursor-pointer" onClick={() => setFullscreenOpen(true)}>
              <img src={toLocalImageUrl(ad.image_url)} alt={`${ad.brand} full`} className="w-full h-full object-contain hover:opacity-80 transition-opacity" crossOrigin="anonymous" referrerPolicy="no-referrer" />
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
              <img
                src={toLocalImageUrl(ad.image_url)}
                alt={`${ad?.brand} full preview`}
                className="max-w-full max-h-full object-contain cursor-pointer"
                crossOrigin="anonymous"
                referrerPolicy="no-referrer"
                onClick={() => setFullscreenOpen(false)}
              />
            </div>
          </DialogContent>
        </Dialog>
      )}
    </Dialog>
  );
}
