import { useLayoutEffect, useState, useEffect } from 'react';

export type NormBox = { x: number; y: number; w: number; h: number };
export type PxBox = { top: number; left: number; width: number; height: number };

/**
 * Calculate the actual rendered content area of an image with object-fit: contain
 * Returns the position and size of the visible image content within the element
 */
function getImageContentRect(img: HTMLImageElement): { x: number; y: number; width: number; height: number } {
  const elemRect = img.getBoundingClientRect();
  const naturalWidth = img.naturalWidth;
  const naturalHeight = img.naturalHeight;
  
  if (!naturalWidth || !naturalHeight) {
    return { x: 0, y: 0, width: elemRect.width, height: elemRect.height };
  }
  
  const elemAspect = elemRect.width / elemRect.height;
  const imgAspect = naturalWidth / naturalHeight;
  
  let contentWidth: number;
  let contentHeight: number;
  let offsetX: number;
  let offsetY: number;
  
  if (imgAspect > elemAspect) {
    // Image is wider than container - letterbox top/bottom
    contentWidth = elemRect.width;
    contentHeight = elemRect.width / imgAspect;
    offsetX = 0;
    offsetY = (elemRect.height - contentHeight) / 2;
  } else {
    // Image is taller than container - letterbox left/right
    contentHeight = elemRect.height;
    contentWidth = elemRect.height * imgAspect;
    offsetX = (elemRect.width - contentWidth) / 2;
    offsetY = 0;
  }
  
  return {
    x: elemRect.left + offsetX,
    y: elemRect.top + offsetY,
    width: contentWidth,
    height: contentHeight,
  };
}

export function useOverlayBoxFromImage(
  containerEl: HTMLElement | null,
  imgEl: HTMLImageElement | null,
  box: NormBox | null
): PxBox | null {
  const [px, setPx] = useState<PxBox | null>(null);

  useLayoutEffect(() => {
    if (!containerEl || !imgEl || !box) return;

    const update = () => {
      // Get the actual rendered image dimensions
      const imgRect = imgEl.getBoundingClientRect();

      // Only update if image has measurable dimensions
      if (imgRect.width > 0 && imgRect.height > 0) {
        // Position relative to the image element directly
        // (assumes video is in a container that wraps the image tightly)
        setPx({
          top: box.y * imgRect.height,
          left: box.x * imgRect.width,
          width: box.w * imgRect.width,
          height: box.h * imgRect.height,
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
      const imgRect = imgEl.getBoundingClientRect();

      if (imgRect.width > 0 && imgRect.height > 0) {
        setPx({
          top: box.y * imgRect.height,
          left: box.x * imgRect.width,
          width: box.w * imgRect.width,
          height: box.h * imgRect.height,
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
