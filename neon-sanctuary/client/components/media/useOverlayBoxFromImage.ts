import { useLayoutEffect, useState, useEffect } from 'react';

export type NormBox = { x: number; y: number; w: number; h: number };
export type PxBox = { top: number; left: number; width: number; height: number };

export function useOverlayBoxFromImage(
  containerEl: HTMLElement | null,
  imgEl: HTMLImageElement | null,
  box: NormBox | null
): PxBox | null {
  const [px, setPx] = useState<PxBox | null>(null);

  useLayoutEffect(() => {
    if (!containerEl || !imgEl || !box) return;

    const update = () => {
      const c = containerEl.getBoundingClientRect();
      const r = imgEl.getBoundingClientRect();

      // Only update if image has measurable dimensions
      if (r.width > 0 && r.height > 0) {
        const offX = r.left - c.left;
        const offY = r.top - c.top;

        setPx({
          top: offY + box.y * r.height,
          left: offX + box.x * r.width,
          width: box.w * r.width,
          height: box.h * r.height,
        });
      }
    };

    update();

    const ro = new ResizeObserver(() => update());
    ro.observe(containerEl);
    ro.observe(imgEl);
    window.addEventListener('scroll', update, true);

    return () => {
      ro.disconnect();
      window.removeEventListener('scroll', update, true);
    };
  }, [containerEl, imgEl, box]);

  // Additional effect to recalculate when image loads
  useEffect(() => {
    if (!containerEl || !imgEl || !box) return;

    const handleImageLoad = () => {
      const c = containerEl.getBoundingClientRect();
      const r = imgEl.getBoundingClientRect();

      if (r.width > 0 && r.height > 0) {
        const offX = r.left - c.left;
        const offY = r.top - c.top;

        setPx({
          top: offY + box.y * r.height,
          left: offX + box.x * r.width,
          width: box.w * r.width,
          height: box.h * r.height,
        });
      }
    };

    imgEl.addEventListener('load', handleImageLoad);
    return () => {
      imgEl.removeEventListener('load', handleImageLoad);
    };
  }, [containerEl, imgEl, box]);

  return px;
}
