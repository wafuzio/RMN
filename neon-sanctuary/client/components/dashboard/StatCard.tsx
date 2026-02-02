import { cn, formatCompactNumber } from "@/lib/utils";
import { isAdTypeNotBrand } from "@/lib/brand-utils";
import { useState, useEffect, useRef } from "react";

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
  const logoUrlRef = useRef<string | null>(null);
  const valueRef = useRef<HTMLDivElement>(null);
  const [fontSize, setFontSize] = useState<number>(56);

  useEffect(() => {
    // Sanitize brand name - skip if empty, null, or looks like an ad type
    const safeBrand = (brandName && brandName.trim()) || null;
    
    if (!safeBrand || isAdTypeNotBrand(safeBrand)) {
      if (logoUrlRef.current) {
        URL.revokeObjectURL(logoUrlRef.current);
        logoUrlRef.current = null;
      }
      setLogoUrl(null);
      return;
    }

    let isMounted = true;

    const fetchLogo = async () => {
      try {
        // Use the correct API endpoint: /api/logo/brand/<brand_name>
        const apiUrl = `/api/logo/brand/${encodeURIComponent(safeBrand)}`;
        console.debug('[StatCard] Fetching brand logo:', { brandName: safeBrand, url: apiUrl });

        const response = await fetch(apiUrl);
        if (response.ok && isMounted) {
          const blob = await response.blob();
          const objectUrl = URL.createObjectURL(blob);

          // Revoke previous URL if it exists
          if (logoUrlRef.current) {
            URL.revokeObjectURL(logoUrlRef.current);
          }

          logoUrlRef.current = objectUrl;
          console.debug('[StatCard] Brand logo loaded successfully');
          setLogoUrl(objectUrl);
        } else if (isMounted) {
          console.debug('[StatCard] Brand logo not found:', { status: response.status, brandName: safeBrand });
          if (logoUrlRef.current) {
            URL.revokeObjectURL(logoUrlRef.current);
            logoUrlRef.current = null;
          }
          setLogoUrl(null);
        }
      } catch (error) {
        if (isMounted) {
          console.debug("[StatCard] Failed to fetch brand logo:", error);
          if (logoUrlRef.current) {
            URL.revokeObjectURL(logoUrlRef.current);
            logoUrlRef.current = null;
          }
          setLogoUrl(null);
        }
      }
    };

    fetchLogo();

    return () => {
      isMounted = false;
    };
  }, [brandName]);

  useEffect(() => {
    if (!valueRef.current) return;

    const resizeText = () => {
      const element = valueRef.current;
      if (!element) return;

      const maxWidth = element.parentElement?.clientWidth || 300;
      const padding = 32; // account for padding
      const availableWidth = maxWidth - padding;
      let currentFontSize = 56;

      // Reset to initial size for measurement
      element.style.fontSize = `${currentFontSize}px`;
      element.style.whiteSpace = 'nowrap';

      while (element.scrollWidth > availableWidth && currentFontSize > 24) {
        currentFontSize -= 2;
        element.style.fontSize = `${currentFontSize}px`;
      }

      element.style.whiteSpace = '';
      setFontSize(currentFontSize);
    };

    // Run on mount and when value changes
    resizeText();

    // Handle window resize
    const resizeObserver = new ResizeObserver(resizeText);
    if (valueRef.current.parentElement) {
      resizeObserver.observe(valueRef.current.parentElement);
    }

    return () => {
      resizeObserver.disconnect();
    };
  }, [value]);

  return (
    <div
      className={cn(
        "card-surface p-6 flex items-center gap-4",
        onClick && "cursor-pointer hover:shadow-cardHover transition-shadow",
        className
      )}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => e.key === "Enter" && onClick() : undefined}
      aria-label={`${label} statistic`}
    >
      <div className="w-1/2 flex flex-col">
        <div
          ref={valueRef}
          className="leading-tight font-extrabold bg-gradient-to-r from-[#667eea] via-[#7c6eb0] to-[#764ba2] bg-clip-text text-transparent line-clamp-2 overflow-hidden"
          style={{ fontSize: `${fontSize}px` }}
        >
          {formatCompactNumber(value)}
        </div>
        <div className="mt-3 text-sm text-[#6b7280]">{label}</div>
        {hint && <div className="mt-1 text-xs text-[#6b7280]">{hint}</div>}
        {trend && (
          <span className={cn("pill mt-2 w-fit", trend === "up" ? "bg-success text-white" : "bg-warning text-white")} aria-label={`trend ${trend}`}>{trend === "up" ? "▲" : "▼"}</span>
        )}
      </div>
      {logoUrl && (
        <div className="flex-1 flex justify-center items-center">
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
