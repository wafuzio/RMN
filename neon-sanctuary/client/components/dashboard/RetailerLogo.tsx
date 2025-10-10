import { API_BASE } from "@/lib/api";

interface RetailerLogoProps {
  retailer: string;
  className?: string;
  alt?: string;
}

export function RetailerLogo({ retailer, className = "h-8 w-auto", alt }: RetailerLogoProps) {
  const logoUrl = `${API_BASE}/api/logo/${retailer.toLowerCase()}`;

  return (
    <img
      src={logoUrl}
      alt={alt || `${retailer} logo`}
      className={`${className} object-contain`}
      style={{ maxHeight: '100%', maxWidth: '100%', display: 'block' }}
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
