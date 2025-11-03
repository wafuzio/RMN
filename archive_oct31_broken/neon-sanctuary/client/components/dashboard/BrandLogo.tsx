interface BrandLogoProps {
  brand: string;
  className?: string;
  alt?: string;
}

export function BrandLogo({ brand, className = "h-8 w-auto", alt }: BrandLogoProps) {
  const logoUrl = `/api/brand_logo/${encodeURIComponent(brand)}`;

  return (
    <img
      src={logoUrl}
      alt={alt || `${brand} logo`}
      className={`${className} object-contain`}
      crossOrigin="anonymous"
      referrerPolicy="no-referrer"
      style={{ maxHeight: '100%', maxWidth: '100%', display: 'block' }}
      onError={(e) => {
        const target = e.target as HTMLImageElement;
        target.style.display = 'none';
      }}
    />
  );
}
