import { useEffect, useState } from 'react';

const query = (q: string) => (typeof window !== 'undefined' ? window.matchMedia(q) : null);

function useMedia(q: string) {
  const [match, setMatch] = useState(() => !!query(q)?.matches);
  useEffect(() => {
    const m = query(q);
    if (!m) return;
    const on = () => setMatch(m.matches);
    m.addEventListener('change', on);
    return () => m.removeEventListener('change', on);
  }, [q]);
  return match;
}

/**
 * `?static` in the URL forces the plain-image fallback (no canvases), which is handy for checking it.
 * Otherwise the scroll journey and turntable draw pre-rendered frames to 2D canvases, which every browser
 * supports without WebGL or a graphics card.
 */
const forcedStatic = typeof window !== 'undefined' && new URLSearchParams(location.search).has('static');

export function useEnvironment() {
  const reducedMotion = useMedia('(prefers-reduced-motion: reduce)');
  const mobile = useMedia('(max-width: 760px), (orientation: portrait) and (max-width: 1024px)');
  return { live: !forcedStatic, reducedMotion, mobile };
}
