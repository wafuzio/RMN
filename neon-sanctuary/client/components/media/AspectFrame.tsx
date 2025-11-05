import React, { useState } from 'react';

export function AspectFrame({
  src,
  children,
  className,
  onImageLoad,
  onClick,
}: {
  src: string;
  children?: React.ReactNode;
  className?: string;
  onImageLoad?: (w: number, h: number) => void;
  onClick?: () => void;
}) {
  const [ratio, setRatio] = useState<number | null>(null);

  return (
    <div className={className} style={{ position: 'relative', width: '100%' }} onClick={onClick}>
      <div
        style={{
          position: 'relative',
          width: '100%',
          aspectRatio: ratio ? String(ratio) : '16/9',
          overflow: 'hidden',
        }}
      >
        <img
          src={src}
          alt=""
          onLoad={(e) => {
            const el = e.currentTarget;
            if (el.naturalWidth && el.naturalHeight) {
              const r = el.naturalWidth / el.naturalHeight;
              setRatio(r);
              onImageLoad?.(el.naturalWidth, el.naturalHeight);
            }
          }}
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            display: 'block',
          }}
          crossOrigin="anonymous"
          decoding="async"
          loading="eager"
        />
        {children}
      </div>
    </div>
  );
}
