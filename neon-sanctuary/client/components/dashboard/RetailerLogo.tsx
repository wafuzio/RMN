interface RetailerLogoProps {
  retailer: string;
  className?: string;
  alt?: string;
}

const RETAILER_LOGO_URLS: Record<string, string> = {
  instacart: "https://cdn.builder.io/api/v1/image/assets%2F856cf3d807e24856a8ddedcb12249a98%2F1c902f9d5339441f90cf514dd0bacd92",
  kroger: "https://cdn.builder.io/api/v1/image/assets%2F856cf3d807e24856a8ddedcb12249a98%2Fcb0a59f99e9a4e82ae96201c8b6682ab",
};

export function RetailerLogo({ retailer, className = "h-8 w-auto", alt }: RetailerLogoProps) {
  const logoUrl = RETAILER_LOGO_URLS[retailer.toLowerCase()] || `/api/logo/${retailer.toLowerCase()}`;

  return (
    <img
      src={logoUrl}
      alt={alt || `${retailer} logo`}
      className={`${className} object-contain`}
      crossOrigin="anonymous"
      referrerPolicy="no-referrer"
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
