import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { BrandLogo } from "@/components/dashboard/BrandLogo";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, ArrowLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import { BrandDetailModal } from "@/components/dashboard/BrandDetailModal";
import GaleLogo from "../../../web/assets/logos/GALE.svg";

export default function Brands() {
  const navigate = useNavigate();
  const allRetailers = ["kroger", "amazon", "instacart", "walmart"] as const;
  const [selectedRetailers, setSelectedRetailers] = useState<Array<typeof allRetailers[number]>>(
    [...allRetailers]
  );
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedBrand, setSelectedBrand] = useState<string | null>(null);

  const { data: brandsData, isLoading } = useQuery({
    queryKey: ["brands", selectedRetailers],
    queryFn: () => api.getBrands(selectedRetailers),
    staleTime: 1000 * 60 * 10,
  });

  const filteredBrands = useMemo(() => {
    if (!brandsData?.brands) return [];

    // First filter by search term
    let filtered = brandsData.brands;
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      filtered = filtered.filter(b => b.brand.toLowerCase().includes(term));
    }

    // Sort alphabetically by brand name
    return [...filtered].sort((a, b) => a.brand.toLowerCase().localeCompare(b.brand.toLowerCase()));
  }, [brandsData?.brands, searchTerm]);

  const toggleRetailer = (retailer: typeof allRetailers[number]) => {
    setSelectedRetailers((prev) => {
      if (prev.includes(retailer)) {
        return prev.filter(r => r !== retailer);
      } else {
        return [...prev, retailer];
      }
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
              {filteredBrands.map((brand) => (
                <button
                  key={brand.brand}
                  onClick={() => setSelectedBrand(brand.brand)}
                  className="group bg-white rounded-xl shadow-sm hover:shadow-lg transition-all duration-200 p-6 flex flex-col items-center justify-center gap-4 cursor-pointer hover:scale-105"
                >
                  <div className="flex items-center justify-center h-24 w-24 flex-shrink-0 group-hover:scale-110 transition-transform duration-200">
                    <BrandLogo brand={brand.brand} className="h-20 w-20" />
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
          <BrandDetailModal
            brand={selectedBrand}
            retailers={selectedRetailers}
            onOpenChange={(open) => !open && setSelectedBrand(null)}
          />
        )}
      </div>
    </main>
  );
}
