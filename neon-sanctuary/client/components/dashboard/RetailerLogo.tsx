interface RetailerLogoProps {
  retailer: string;
  className?: string;
  alt?: string;
}

const RETAILER_LOGO_HEIGHTS: Record<string, number> = {
  albertsons: 49,
  food_lion: 58,
  gopuff: 40,
  doordash: 45,
  meijer: 50,
  hyvee: 55,
  ulta: 56,
};

export function RetailerLogo({ retailer, className = "h-8 w-auto", alt }: RetailerLogoProps) {
  const logoUrl = `/api/logo/${retailer.toLowerCase()}`;
  const isFromSelector = className.includes('h-16');
  const heightPx = isFromSelector ? (RETAILER_LOGO_HEIGHTS[retailer.toLowerCase()] || 64) : undefined;

  return (
    <img
      src={logoUrl}
      alt={alt || `${retailer} logo`}
      className={`${className} object-contain`}
      crossOrigin="anonymous"
      referrerPolicy="no-referrer"
      style={{ display: 'block', ...(heightPx && { height: `${heightPx}px`, width: 'auto' }) }}
      onError={(e) => {
        const target = e.target as HTMLImageElement;
        target.style.display = 'none';
        const fallback = document.createElement('span');
        fallback.textContent = retailer.toUpperCase();
        fallback.className = 'font-bold text-sm';
        target.parentNode?.appendChild(fallback);
      }}
    />
  );
}
