import { cn } from "@/lib/utils";
import { useState, useEffect } from "react";

interface StatCardProps {
  value: string | number;
  label: string;
  hint?: string;
  trend?: "up" | "down" | null;
  className?: string;
  brandName?: string;
  onClick?: () => void;
}

export function StatCard({ value, label, hint, trend, className, brandName, onClick }: StatCardProps) {
  const [logoUrl, setLogoUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!brandName) {
      setLogoUrl(null);
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
  }, [brandName]);

  return (
    <div
      className={cn(
        "card-surface p-6 flex items-start",
        onClick && "cursor-pointer hover:shadow-cardHover transition-shadow",
        className
      )}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => e.key === "Enter" && onClick() : undefined}
      aria-label={`${label} statistic`}
    >
      <div className="flex-1 flex flex-col">
        <div className="flex items-center gap-3">
          <div className="text-[3em] leading-none font-extrabold text-[#111827]">{value}</div>
          {trend && (
            <span className={cn("pill", trend === "up" ? "bg-success text-white" : "bg-warning text-white")} aria-label={`trend ${trend}`}>{trend === "up" ? "▲" : "▼"}</span>
          )}
        </div>
        <div className="mt-2 text-sm text-[#6b7280]">{label}</div>
        {hint && <div className="mt-1 text-xs text-[#6b7280]">{hint}</div>}
      </div>
      {logoUrl && (
        <div className="flex-1 flex justify-center">
          <img
            src={logoUrl}
            alt={`${brandName} logo`}
            className="h-24 w-auto object-contain"
            onError={() => setLogoUrl(null)}
          />
        </div>
      )}
    </div>
  );
}
