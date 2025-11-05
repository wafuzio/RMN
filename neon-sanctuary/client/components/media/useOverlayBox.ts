import { useEffect, useMemo, useState } from 'react';

export type NormBox = { x: number; y: number; w: number; h: number };

export function useOverlayBox(
  containerEl: HTMLElement | null,
  naturalW: number | null,
  naturalH: number | null,
  box: NormBox | null
) {
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });

  useEffect(() => {
    if (!containerEl) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      setSize({ w: r.width, h: r.height });
    });
    ro.observe(containerEl);
    return () => ro.disconnect();
  }, [containerEl]);

  return useMemo(() => {
    if (!box || !naturalW || !naturalH || !size.w || !size.h) return null;

    const rImg = naturalW / naturalH;
    const rCon = size.w / size.h;

    let drawnW: number, drawnH: number, offX = 0, offY = 0;

    if (rCon > rImg) {
      drawnH = size.h;
      drawnW = drawnH * rImg;
      offX = (size.w - drawnW) / 2;
    } else {
      drawnW = size.w;
      drawnH = drawnW / rImg;
      offY = (size.h - drawnH) / 2;
    }

    return {
      top: offY + box.y * drawnH,
      left: offX + box.x * drawnW,
      width: box.w * drawnW,
      height: box.h * drawnH,
    } as const;
  }, [box, naturalW, naturalH, size.w, size.h]);
}
