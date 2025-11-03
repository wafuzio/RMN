import { useState, useEffect } from "react";
import { isAdTypeNotBrand } from "@/lib/brand-utils";

interface BrandLogoProps {
  brand: string;
  className?: string;
  alt?: string;
}

export function BrandLogo({ brand, className = "h-8 w-auto", alt }: BrandLogoProps) {
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
    setLogoUrl(null);

    if (!brand || isAdTypeNotBrand(brand)) {
      setFailed(true);
      return;
    }

    const fetchLogo = async () => {
      try {
        const response = await fetch(`/api/logo/brand/${encodeURIComponent(brand)}`);
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
  }, [brand]);

  if (logoUrl) {
    return (
      <img
        src={logoUrl}
        alt={alt || `${brand} logo`}
        className={`${className} object-contain`}
        onError={() => setFailed(true)}
      />
    );
  }

  if (failed) {
    const initials = brand
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

    const colorIndex = brand.charCodeAt(0) % colors.length;
    const bgColor = colors[colorIndex];

    return (
      <div
        className={`rounded flex items-center justify-center ${bgColor} text-white text-xs font-semibold flex-shrink-0 ${className}`}
        title={brand}
      >
        {initials || "?"}
      </div>
    );
  }

  return null;
}
