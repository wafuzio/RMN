import { useState, useEffect, useRef, RefObject } from 'react';

/**
 * Hook to detect if an element is in the viewport.
 * Uses IntersectionObserver for efficient scroll-based detection.
 * 
 * @param options - IntersectionObserver options
 * @returns [ref, isInViewport] - Ref to attach to element and boolean indicating visibility
 */
export function useInViewport<T extends HTMLElement = HTMLDivElement>(
  options: IntersectionObserverInit = {}
): [RefObject<T>, boolean] {
  const ref = useRef<T>(null);
  const [isInViewport, setIsInViewport] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        setIsInViewport(entry.isIntersecting);
      },
      {
        root: null, // viewport
        rootMargin: '100px', // Load slightly before entering viewport
        threshold: 0,
        ...options,
      }
    );

    observer.observe(element);

    return () => {
      observer.disconnect();
    };
  }, [options.root, options.rootMargin, options.threshold]);

  return [ref, isInViewport];
}
