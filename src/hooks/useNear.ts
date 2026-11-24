import { useEffect, useState, type RefObject } from 'react';

/**
 * True once the element comes within about one screen of the viewport, then stays true. Used to start loading
 * section images late: the browser's own lazy loading starts much further away, while the reader is still in
 * the journey and its frames are loading.
 */
export function useNear(ref: RefObject<Element | null>): boolean {
  const [near, setNear] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver !== 'function') return setNear(true);
    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        setNear(true);
        io.disconnect();
      },
      { rootMargin: '0px 0px 100% 0px' },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [ref]);
  return near;
}
