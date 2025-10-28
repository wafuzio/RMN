import { useState, useEffect } from "react";
import { isAdTypeNotBrand } from "@/lib/brand-utils";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

interface BrandSovEntry {
  brand: string;
  count: number;
  percentage: number;
}

interface TopBrandModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  topBrands: BrandSovEntry[];
}

function BrandLogoImage({ brandName }: { brandName: string }) {
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
    setLogoUrl(null);

    if (!brandName || isAdTypeNotBrand(brandName)) {
      setFailed(true);
      return;
    }

    const fetchLogo = async () => {
      try {
        const response = await fetch(`/api/logo/brand/${encodeURIComponent(brandName)}`);
        if (response.ok) {
          const blob = await response.blob();
          const url = URL.createObjectURL(blob);
          setLogoUrl(url);
        } else {
          setFailed(true);
        }
      } catch (error) {
        console.error("Failed to fetch brand logo:", error);
        setFailed(true);
      }
    };

    fetchLogo();

    return () => {
      if (logoUrl) {
        URL.revokeObjectURL(logoUrl);
      }
    };
  }, [brandName]);

  if (logoUrl) {
    return (
      <img
        src={logoUrl}
        alt={`${brandName} logo`}
        className="h-10 w-auto object-contain"
        onError={() => setFailed(true)}
      />
    );
  }

  if (failed) {
    const initials = brandName
      .split(/\s+/)
      .slice(0, 2)
      .map(word => word[0]?.toUpperCase())
      .join("");

    const colors = [
      "bg-blue-500",
      "bg-purple-500",
      "bg-pink-500",
      "bg-indigo-500",
      "bg-cyan-500",
      "bg-teal-500",
      "bg-emerald-500",
      "bg-orange-500",
    ];

    const colorIndex = brandName.charCodeAt(0) % colors.length;
    const bgColor = colors[colorIndex];

    return (
      <div
        className={`h-10 w-10 rounded flex items-center justify-center ${bgColor} text-white text-sm font-semibold flex-shrink-0`}
        title={brandName}
      >
        {initials || "?"}
      </div>
    );
  }

  return null;
}

export function TopBrandModal({ open, onOpenChange, topBrands }: TopBrandModalProps) {
  const displayBrands = topBrands.slice(0, 5);
  const remainingCount = topBrands.length > 5 ? topBrands.slice(5).reduce((sum, b) => sum + b.count, 0) : 0;
  const totalCount = topBrands.reduce((sum, b) => sum + b.count, 0);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Top Brands by Share of Voice</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          {displayBrands.map((brand, idx) => {
            const percentage = totalCount > 0 ? Math.round((brand.count / totalCount) * 100) : 0;
            return (
              <div key={brand.brand} className="flex items-center justify-between p-3 border border-gray-200 rounded-md">
                <div className="flex items-center gap-3 flex-1">
                  <div className="font-semibold bg-gradient-to-r from-[#667eea] via-[#7c6eb0] to-[#764ba2] bg-clip-text text-transparent w-8">#{idx + 1}</div>
                  <div className="flex-shrink-0">
                    <BrandLogoImage brandName={brand.brand} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-gray-900">{brand.brand}</div>
                    <div className="text-xs text-gray-500">{brand.count} ads</div>
                  </div>
                </div>
                <div className="text-right flex-shrink-0">
                  <div className="font-extrabold text-xl bg-gradient-to-r from-[#667eea] via-[#7c6eb0] to-[#764ba2] bg-clip-text text-transparent leading-none">{percentage}%</div>
                </div>
              </div>
            );
          })}
          {remainingCount > 0 && (
            <div className="flex items-center justify-between p-3 border border-gray-200 rounded-md bg-gray-50">
              <div className="flex items-center gap-3 flex-1">
                <div className="font-semibold bg-gradient-to-r from-[#667eea] via-[#7c6eb0] to-[#764ba2] bg-clip-text text-transparent w-8">6+</div>
                <div className="flex-1">
                  <div className="font-medium text-gray-900">All Others</div>
                  <div className="text-xs text-gray-500">{remainingCount} ads</div>
                </div>
              </div>
              <div className="text-right">
                <div className="font-extrabold text-xl bg-gradient-to-r from-[#667eea] via-[#7c6eb0] to-[#764ba2] bg-clip-text text-transparent leading-none">
                  {Math.round((remainingCount / totalCount) * 100)}%
                </div>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
