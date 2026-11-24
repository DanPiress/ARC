// Smooth wheel scrolling (Lenis) driven by the GSAP ticker, so the page text, the scroll journey and
// ScrollTrigger all move from one interpolated scroll position. Touch scrolling stays native.
import Lenis from 'lenis';
import 'lenis/dist/lenis.css';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

let lenis: Lenis | null = null;

const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

/** Starts smooth scrolling; returns a cleanup function. */
export function startSmoothScroll(): () => void {
  const instance = new Lenis({
    lerp: 0.085, // glide: each wheel notch eases out over roughly half a second
    wheelMultiplier: 0.9,
    autoToggle: true, // pauses while the cart or menu sets overflow: hidden on <html>
    allowNestedScroll: true, // the cart panel keeps its own scrolling
  });
  lenis = instance;
  instance.on('scroll', ScrollTrigger.update);
  const tick = (time: number) => instance.raf(time * 1000);
  gsap.ticker.add(tick);
  gsap.ticker.lagSmoothing(0);

  // In-page links glide too. The skip link keeps its native jump, which also moves keyboard focus.
  const onClick = (e: MouseEvent) => {
    const a = (e.target as HTMLElement | null)?.closest?.('a[href^="#"]');
    if (!a || a.classList.contains('skip') || e.defaultPrevented || e.metaKey || e.ctrlKey) return;
    const id = a.getAttribute('href')!.slice(1);
    const target = id === 'top' ? 0 : document.getElementById(id);
    if (target === null) return;
    e.preventDefault();
    // Keep the address bar and Back button behaving like a normal in-page link.
    if (location.hash !== `#${id}`) history.pushState(null, '', `#${id}`);
    // force: links inside the cart run while the page is still locked; the lock lifts as it closes.
    instance.scrollTo(target, { duration: 1.4, easing: easeInOut, force: true });
  };
  document.addEventListener('click', onClick);

  // Keyboard page scrolling glides the same way (native key scrolling was cut short by Lenis and jumped).
  // Keys aimed at controls (the turntable, buttons, links, form fields, the cart) keep their own behaviour.
  const onKey = (e: KeyboardEvent) => {
    if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || instance.isStopped) return;
    const t = e.target as HTMLElement | null;
    if (t?.closest?.('input, textarea, select, button, a, [contenteditable], [role="application"], .cart, .nav')) return;
    const page = window.innerHeight * 0.85;
    const deltas: Record<string, number> = {
      ArrowDown: 110,
      ArrowUp: -110,
      PageDown: page,
      PageUp: -page,
      ' ': e.shiftKey ? -page : page,
    };
    let to: number | null = null;
    if (e.key in deltas) to = instance.targetScroll + deltas[e.key];
    else if (e.key === 'Home') to = 0;
    else if (e.key === 'End') to = instance.limit;
    if (to === null) return;
    e.preventDefault();
    instance.scrollTo(Math.max(0, Math.min(instance.limit, to)), { duration: 0.7, easing: easeInOut });
  };
  window.addEventListener('keydown', onKey);

  return () => {
    window.removeEventListener('keydown', onKey);
    document.removeEventListener('click', onClick);
    gsap.ticker.remove(tick);
    gsap.ticker.lagSmoothing(500, 33);
    instance.destroy();
    if (lenis === instance) lenis = null;
  };
}

/** Scrolls an element to the top of the viewport, gliding when smooth scrolling is running. */
export function scrollToElement(el: HTMLElement, smooth: boolean) {
  if (lenis) lenis.scrollTo(el, { duration: smooth ? 1.4 : 0, immediate: !smooth, easing: easeInOut, force: true });
  else el.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'start' });
}
