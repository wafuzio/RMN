import { cn } from "@/lib/utils";
import { Retailer } from "@/lib/api";
import { RetailerLogo } from "@/components/dashboard/RetailerLogo";

const RETAILERS: { id: Retailer; label: string; }[] = [
  { id: "kroger", label: "Kroger" },
  { id: "amazon", label: "Amazon" },
  { id: "instacart", label: "Instacart" },
  { id: "walmart", label: "Walmart" },
];

export function RetailerSelector({ value, onChange, enabledRetailers }: { value: Retailer[]; onChange: (r: Retailer[])=>void; enabledRetailers: Set<string>; }) {
  const toggleRetailer = (retailer: Retailer) => {
    if (value.includes(retailer)) {
      // Remove if already selected (but keep at least one)
      if (value.length > 1) {
        onChange(value.filter(r => r !== retailer));
      }
    } else {
      // Add to selection
      onChange([...value, retailer]);
    }
  };

  return (
    <div className="flex gap-6 overflow-x-auto pb-1" role="group" aria-label="Select retailers">
      {RETAILERS.map(r => {
        const selected = value.includes(r.id);
        const enabled = enabledRetailers.has(r.id);
        return (
          <button
            key={r.id}
            onClick={() => enabled && toggleRetailer(r.id)}
            aria-pressed={selected}
            aria-label={r.label}
            className={cn(
              "relative flex items-center justify-center select-none",
              "transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 rounded-lg",
              !enabled && "cursor-not-allowed",
              enabled && "hover:scale-110",
              selected ? "opacity-100 drop-shadow-[0_0_8px_rgba(59,130,246,0.6)]" : enabled ? "opacity-60" : "opacity-30",
            )}
          >
            <RetailerLogo retailer={r.id} className="h-16 w-auto object-contain" />
          </button>
        );
      })}
    </div>
  );
}
