import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { Ad } from "./AdCard";

export function AdModal({ open, ad, onOpenChange, onCompare }: { open: boolean; ad: Ad | null; onOpenChange: (v: boolean)=>void; onCompare: (ad: Ad)=>void; }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogTitle className="sr-only">{ad ? `${ad.brand} ad details` : "Ad details"}</DialogTitle>
        {ad && (
          <div className="grid md:grid-cols-2 gap-6">
            <div className="rounded-lg overflow-hidden">
              <img src={api.imageUrl(ad.image_url)} alt={`${ad.brand} full`} className="w-full h-full object-contain" />
            </div>
            <div className="space-y-3">
              <h3 className="text-2xl font-bold">{ad.brand}</h3>
              <div className="text-sm text-muted-foreground">{ad.retailer} • {ad.ad_type}</div>
              <div className="text-sm"><span className="font-semibold">Keyword:</span> {ad.keyword}</div>
              <div className="text-sm"><span className="font-semibold">Client:</span> {ad.client}</div>
              <div className="text-sm"><span className="font-semibold">Date:</span> {new Date(ad.timestamp.replace(" ","T")).toLocaleString()}</div>
              <div className="pt-4 flex gap-2">
                <Button onClick={() => { const a = document.createElement('a'); a.href = api.imageUrl(ad.image_url); a.download = `${ad.brand}-${ad.ad_type}.png`; a.click(); }}>Download</Button>
                <Button variant="secondary" onClick={() => onCompare(ad)}>Compare</Button>
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
