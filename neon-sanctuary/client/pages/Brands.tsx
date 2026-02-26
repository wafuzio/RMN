import React, { useState, useMemo, Suspense, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useBrands } from "@/hooks/useBrands";
import { BrandLogo } from "@/components/dashboard/BrandLogo";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, ArrowLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import GaleLogo from "../../../web/assets/logos/GALE.svg";
import type { Retailer } from "@/lib/api";

// Lazy load modal for code splitting
const BrandDetailModal = React.lazy(() => import("@/components/dashboard/BrandDetailModal").then(m => ({ default: m.BrandDetailModal })));

export default function Brands() {
  const navigate = useNavigate();
  const allRetailers: Retailer[] = ["kroger", "amazon", "instacart", "walmart", "target"];
  const [selectedRetailers, setSelectedRetailers] = useState<Retailer[]>([...allRetailers]);
  const [searchTerm, setSearchTerm] = useState("");
  const debouncedSearch = useDebouncedValue(searchTerm, 300);
  const [selectedBrand, setSelectedBrand] = useState<string | null>(null);
  const queryClient = useQueryClient();

  // Use dedicated brands hook with built-in caching and deduplication
  const { data: brandsData, isLoading } = useBrands(selectedRetailers);

  const filteredBrands = useMemo(() => {
    if (!brandsData?.brands) return [];

    // Exclude retailer brands
    const excludedBrands = new Set(["Kroger", "Walmart"]);

    // Filter by debounced search term and exclude retailer brands
    let filtered = brandsData.brands.filter(b => !excludedBrands.has(b.brand));
    if (debouncedSearch) {
      const term = debouncedSearch.toLowerCase();
      filtered = filtered.filter(b => b.brand.toLowerCase().includes(term));
    }

    // Sort alphabetically by brand name
    return [...filtered].sort((a, b) => a.brand.toLowerCase().localeCompare(b.brand.toLowerCase()));
  }, [brandsData?.brands, debouncedSearch]);

  // Preload first 8 brand logos for better LCP (only once when data loads)
  useEffect(() => {
    if (!filteredBrands.length || !brandsData) return;

    const preloadLogos = filteredBrands.slice(0, 8);
    const preloadedBrands = new Set<string>();
    
    preloadLogos.forEach((brand) => {
      if (preloadedBrands.has(brand.brand)) return;
      preloadedBrands.add(brand.brand);
      
      const link = document.createElement('link');
      link.rel = 'preload';
      link.as = 'image';
      link.href = `/api/logo/brand/${encodeURIComponent(brand.brand)}?w=240`;
      link.type = 'image/webp';
      link.fetchPriority = 'high';
      link.dataset.brandPreload = brand.brand;
      document.head.appendChild(link);
    });

    // Cleanup function to remove preload hints when component unmounts
    return () => {
      const preloadLinks = document.querySelectorAll('link[data-brand-preload]');
      preloadLinks.forEach(link => link.remove());
    };
  }, [brandsData]); // Only run when initial data loads, not on every filter change

  const toggleRetailer = (retailer: Retailer) => {
    setSelectedRetailers((prev) => {
      // If all retailers are selected, reset: make clicked retailer the only one
      if (prev.length === allRetailers.length) {
        return [retailer];
      }

      // If 0 retailers are selected, make clicked retailer the only one
      if (prev.length === 0) {
        return [retailer];
      }

      // If clicked retailer is not selected, add it
      if (!prev.includes(retailer)) {
        return [...prev, retailer];
      }

      // If clicked retailer is already selected, keep as is (don't deselect)
      return prev;
    });
    setSearchTerm("");
  };

  return (
    <main className="min-h-screen py-6 pb-32 px-4 md:px-8 bg-gray-50">
      <div className="w-full max-w-[1600px] mx-auto">
        <header className="mb-8">
          <div className="flex items-center gap-3 mb-6">
            <button
              onClick={() => navigate("/")}
              className="p-2 hover:bg-gray-200 rounded-lg transition-colors"
              aria-label="Go back to dashboard"
            >
              <ArrowLeft className="w-5 h-5 text-gray-700" />
            </button>
            <img src={GaleLogo} alt="GALE" className="h-8 w-auto" />
            <h1 className="text-gray-900 text-3xl font-extrabold">Brand Gallery</h1>
          </div>

          <div className="bg-white rounded-lg shadow-sm p-6 space-y-6">
            <div>
              <h2 className="text-sm font-semibold text-gray-700 mb-4">Select Retailer</h2>
              <div className="flex flex-wrap gap-3">
                {allRetailers.map((retailer) => (
                  <Button
                    key={retailer}
                    onClick={() => toggleRetailer(retailer)}
                    variant={selectedRetailers.includes(retailer) ? "default" : "outline"}
                    className={cn(
                      "capitalize",
                      selectedRetailers.includes(retailer) && "bg-blue-600 hover:bg-blue-700"
                    )}
                  >
                    {retailer}
                  </Button>
                ))}
              </div>
            </div>

            <div>
              <h2 className="text-sm font-semibold text-gray-700 mb-4">Search Brands</h2>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                <Input
                  placeholder="Search brands..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10 py-2"
                />
              </div>
            </div>
          </div>
        </header>

        {isLoading ? (
          <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-4">
            {Array.from({ length: 18 }).map((_, i) => (
              <div
                key={i}
                className="bg-white rounded-lg shadow-sm p-4 flex flex-col items-center justify-center gap-3 animate-pulse"
              >
                <div className="w-12 h-12 bg-gray-200 rounded" />
                <div className="w-full h-4 bg-gray-200 rounded" />
              </div>
            ))}
          </div>
        ) : filteredBrands.length === 0 ? (
          <div className="bg-white rounded-lg shadow-sm p-12 text-center">
            <p className="text-gray-500 text-lg">
              {searchTerm ? "No brands match your search" : "No brands available"}
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-bold text-gray-900">
                {filteredBrands.length} {filteredBrands.length === 1 ? "Brand" : "Brands"}
              </h2>
            </div>

            <div className="grid grid-cols-4 gap-6">
              {filteredBrands.map((brand, i) => (
                <button
                  key={brand.brand}
                  onClick={() => setSelectedBrand(brand.brand)}
                  className="group bg-white rounded-xl shadow-sm hover:shadow-lg transition-all duration-200 p-3 flex flex-col items-center justify-center gap-2 cursor-pointer hover:scale-105"
                >
                  <div className="flex items-center justify-center h-36 w-36 flex-shrink-0 group-hover:scale-110 transition-transform duration-200">
                    <BrandLogo 
                      brand={brand.brand} 
                      size={120} 
                      eager={i < 8} 
                      className="h-[120px] w-[120px]" 
                    />
                  </div>
                  <div className="text-center space-y-1">
                    <p className="font-bold text-gray-900 text-sm line-clamp-2 group-hover:text-blue-600 transition-colors">
                      {brand.brand}
                    </p>
                    <p className="text-xs text-gray-500">{brand.count} ads</p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {selectedBrand && (
          <Suspense fallback={null}>
            <BrandDetailModal
              brand={selectedBrand}
              retailers={selectedRetailers}
              onOpenChange={(open) => !open && setSelectedBrand(null)}
            />
          </Suspense>
        )}
      </div>
    </main>
  );
}
