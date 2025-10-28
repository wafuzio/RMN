import { useState, useMemo } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Search } from "lucide-react";

interface BrandEntry {
  brand: string;
  count: number;
  percentage: number;
}

interface AllBrandsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  brands: BrandEntry[];
  filterParams: {
    retailers: string[];
    clients: string[];
    dateRange?: { start?: Date; end?: Date };
    adTypes: string[];
    keywords: string[];
  };
}

export function AllBrandsModal({
  open,
  onOpenChange,
  brands,
  filterParams,
}: AllBrandsModalProps) {
  const [searchTerm, setSearchTerm] = useState("");

  const filteredBrands = useMemo(() => {
    if (!searchTerm) return brands;
    const term = searchTerm.toLowerCase();
    return brands.filter(b => b.brand.toLowerCase().includes(term));
  }, [brands, searchTerm]);

  const exportAsCSV = () => {
    const headers = [
      "Brand",
      "Ad Count",
      "Percentage",
      "Filter: Retailers",
      "Filter: Clients",
      "Filter: Start Date",
      "Filter: End Date",
      "Filter: Ad Types",
      "Filter: Keywords",
    ];

    const filterValues = [
      filterParams.retailers.join("; ") || "All",
      filterParams.clients.join("; ") || "All",
      filterParams.dateRange?.start?.toISOString().split("T")[0] || "All",
      filterParams.dateRange?.end?.toISOString().split("T")[0] || "All",
      filterParams.adTypes.join("; ") || "All",
      filterParams.keywords.join("; ") || "All",
    ];

    const rows = [
      headers,
      ...filteredBrands.map(b => [
        b.brand,
        b.count.toString(),
        `${b.percentage}%`,
        ...filterValues,
      ]),
    ];

    const csv = rows
      .map(r =>
        r
          .map(x => `"${String(x).replace(/"/g, '""')}"`)
          .join(",")
      )
      .join("\n");

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `brands-export-${new Date().toISOString().split("T")[0]}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const exportAsJSON = () => {
    const data = {
      exportDate: new Date().toISOString(),
      filters: {
        retailers: filterParams.retailers.length > 0 ? filterParams.retailers : "All",
        clients: filterParams.clients.length > 0 ? filterParams.clients : "All",
        startDate: filterParams.dateRange?.start?.toISOString().split("T")[0] || "All",
        endDate: filterParams.dateRange?.end?.toISOString().split("T")[0] || "All",
        adTypes: filterParams.adTypes.length > 0 ? filterParams.adTypes : "All",
        keywords: filterParams.keywords.length > 0 ? filterParams.keywords : "All",
      },
      brands: filteredBrands.map(b => ({
        brand: b.brand,
        adCount: b.count,
        percentage: b.percentage,
      })),
      summary: {
        totalBrands: filteredBrands.length,
        totalAds: filteredBrands.reduce((sum, b) => sum + b.count, 0),
      },
    };

    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `brands-export-${new Date().toISOString().split("T")[0]}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const totalAds = filteredBrands.reduce((sum, b) => sum + b.count, 0);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>All Brands</DialogTitle>
        </DialogHeader>

        <div className="flex items-center gap-2 mb-4">
          <Search className="w-4 h-4 text-gray-500" />
          <Input
            placeholder="Search brands..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="flex-1"
          />
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="space-y-2 pr-4">
            {filteredBrands.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                No brands match your search
              </div>
            ) : (
              filteredBrands.map((brand, idx) => (
                <div
                  key={brand.brand}
                  className="flex items-center justify-between p-3 border border-gray-200 rounded-md hover:bg-gray-50"
                >
                  <div className="flex items-center gap-3 flex-1">
                    <div className="font-semibold text-gray-600 w-8">
                      #{idx + 1}
                    </div>
                    <div className="flex-1">
                      <div className="font-medium text-gray-900">
                        {brand.brand}
                      </div>
                      <div className="text-xs text-gray-500">
                        {brand.count} ads
                      </div>
                    </div>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <div className="font-extrabold text-lg bg-gradient-to-r from-[#667eea] via-[#7c6eb0] to-[#764ba2] bg-clip-text text-transparent">
                      {brand.percentage}%
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="border-t pt-4 mt-4">
          <div className="mb-4 grid grid-cols-2 gap-2 text-sm">
            <div>
              <span className="text-gray-600">Total Brands:</span>
              <span className="ml-2 font-semibold">{filteredBrands.length}</span>
            </div>
            <div>
              <span className="text-gray-600">Total Ads:</span>
              <span className="ml-2 font-semibold">{totalAds}</span>
            </div>
          </div>

          <div className="space-y-2">
            <div className="text-xs text-gray-600 font-semibold mb-2">
              Active Filters:
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs text-gray-600 mb-4">
              {filterParams.retailers.length > 0 && (
                <div>
                  <span className="font-medium">Retailers:</span>{" "}
                  {filterParams.retailers.join(", ")}
                </div>
              )}
              {filterParams.clients.length > 0 && (
                <div>
                  <span className="font-medium">Clients:</span>{" "}
                  {filterParams.clients.join(", ")}
                </div>
              )}
              {filterParams.dateRange?.start && (
                <div>
                  <span className="font-medium">Start Date:</span>{" "}
                  {filterParams.dateRange.start
                    .toISOString()
                    .split("T")[0]}
                </div>
              )}
              {filterParams.dateRange?.end && (
                <div>
                  <span className="font-medium">End Date:</span>{" "}
                  {filterParams.dateRange.end.toISOString().split("T")[0]}
                </div>
              )}
              {filterParams.adTypes.length > 0 && (
                <div>
                  <span className="font-medium">Ad Types:</span>{" "}
                  {filterParams.adTypes.join(", ")}
                </div>
              )}
              {filterParams.keywords.length > 0 && (
                <div>
                  <span className="font-medium">Keywords:</span>{" "}
                  {filterParams.keywords.join(", ")}
                </div>
              )}
            </div>
          </div>

          <div className="flex gap-2">
            <Button onClick={exportAsCSV} variant="outline" className="flex-1">
              Export as CSV
            </Button>
            <Button onClick={exportAsJSON} variant="outline" className="flex-1">
              Export as JSON
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
