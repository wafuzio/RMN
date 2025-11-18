import React from 'react';
import { cn } from '@/lib/utils';
import { isAdTypeNotBrand } from "@/lib/brand-utils";

type BrandLogoProps = {
  brand: string;
  className?: string;
  size?: number;         // rendered box (CSS & width/height attrs)
  eager?: boolean;       // make true for the first few logos above the fold
  logoUrl?: string;      // if you already have a URL; otherwise, derive inside
};

function initials(name: string) {
  const parts = (name || '').trim().split(/\s+/);
  const a = parts[0]?.[0] || '';
  const b = parts[1]?.[0] || '';
  return (a + b).toUpperCase() || '•';
}

function getColorForBrand(brand: string) {
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
  return colors[colorIndex];
}

function getLogoUrl(brand: string): string {
  return `/api/logo/brand/${encodeURIComponent(brand)}`;
}

export const BrandLogo = React.memo(function BrandLogo({ 
  brand, 
  className, 
  size = 120, 
  eager = false, 
  logoUrl 
}: BrandLogoProps) {
  // Validate brand - show initials for invalid brands
  if (!brand || isAdTypeNotBrand(brand)) {
    const bgColor = getColorForBrand(brand || '');
    return (
      <div
        className={cn('rounded flex items-center justify-center text-white text-xs font-semibold flex-shrink-0', bgColor, className)}
        style={{ width: size, height: size }}
        title={brand}
        aria-label={`${brand} logo`}
      >
        {initials(brand)}
      </div>
    );
  }

  const src = logoUrl || getLogoUrl(brand);

  // Add thumbnail width parameter for optimization
  let urlStr = src;
  try {
    const u = new URL(src, window.location.origin);
    // force width for thumbnails; 2x for retina
    if (!u.searchParams.has('w')) u.searchParams.set('w', String(size * 2));
    // keep DPR stable; remove if your CDN handles DPR automatically
    if (!u.searchParams.has('dpr')) u.searchParams.set('dpr', '1');
    urlStr = u.toString();
  } catch {
    // if src is not absolute, best-effort append ?w=
    urlStr = src.includes('?') ? `${src}&w=${size * 2}` : `${src}?w=${size * 2}`;
  }

  return (
    <img
      src={urlStr}
      alt={`${brand} logo`}
      width={size}
      height={size}
      loading={eager ? 'eager' : 'lazy'}
      decoding="async"
      {...(eager ? { fetchpriority: 'high' as const } : { fetchpriority: 'low' as const })}
      className={cn('object-contain rounded bg-white', className)}
      onError={(e) => {
        // Fallback to initials on error
        const target = e.currentTarget;
        const parent = target.parentElement;
        if (parent) {
          const bgColor = getColorForBrand(brand);
          const fallback = document.createElement('div');
          fallback.className = `rounded flex items-center justify-center ${bgColor} text-white text-xs font-semibold flex-shrink-0`;
          fallback.style.width = `${size}px`;
          fallback.style.height = `${size}px`;
          fallback.title = brand;
          fallback.textContent = initials(brand);
          parent.replaceChild(fallback, target);
        }
      }}
    />
  );
});
