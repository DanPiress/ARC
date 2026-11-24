import { useCallback, useEffect, useRef, useState } from 'react';
import { Nav } from './components/Nav';
import { Showcase } from './components/Showcase';
import { Configurator } from './components/Configurator';
import { Layers } from './components/Layers';
import { Why } from './components/Why';
import { CartDrawer } from './components/CartDrawer';
import { Footer } from './components/Details';
import { useCart } from './hooks/useCart';
import { useEnvironment } from './hooks/useEnvironment';
import { getColorway, type ColorwayId } from './data/product';
import { scrollToElement, startSmoothScroll } from './smoothScroll';

export default function App() {
  const env = useEnvironment();
  const cart = useCart();
  const [colorway, setColorway] = useState<ColorwayId>('graphite');
  const [cartOpen, setCartOpen] = useState(false);
  const [note, setNote] = useState('');
  const noteTimer = useRef<number>(0);

  const add = useCallback(() => {
    cart.add(colorway);
    setNote(`Added ARC ${getColorway(colorway).name} to the demo cart.`);
    window.clearTimeout(noteTimer.current);
    noteTimer.current = window.setTimeout(() => setNote(''), 4000);
  }, [cart, colorway]);

  useEffect(() => () => window.clearTimeout(noteTimer.current), []);

  // Smooth wheel scrolling for the animated page only; reduced motion and ?static keep native scrolling.
  useEffect(() => {
    if (!env.live || env.reducedMotion) return;
    return startSmoothScroll();
  }, [env.live, env.reducedMotion]);

  // A link such as /#configure opens at that section. The browser tries to jump before React has rendered the
  // page, finds no such element and stays at the top, so the jump is made here once the page exists. A reload or
  // Back/Forward keeps the position the browser restores instead.
  useEffect(() => {
    const id = decodeURIComponent(location.hash.slice(1));
    const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
    if (!id || id === 'top' || (nav && nav.type !== 'navigate')) return;
    let raf = requestAnimationFrame(() => {
      const el = document.getElementById(id);
      if (!el) return;
      scrollToElement(el, false);
      const landed = window.scrollY;
      // Web fonts can shift the layout a little; settle again if the reader has not scrolled meanwhile.
      document.fonts?.ready.then(() => {
        raf = requestAnimationFrame(() => {
          if (Math.abs(window.scrollY - landed) < 2) scrollToElement(el, false);
        });
      });
    });
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <>
      <a className="skip" href="#configure">
        Skip to configurator
      </a>
      <Nav count={cart.count} onOpenCart={() => setCartOpen(true)} />
      <main id="top">
        <Showcase live={env.live} reducedMotion={env.reducedMotion} mobile={env.mobile} />
        <Why />
        <Layers />
        <Configurator
          colorway={colorway}
          onColorway={setColorway}
          onAdd={add}
          addedNote={note}
          live={env.live}
          reducedMotion={env.reducedMotion}
        />
      </main>
      <Footer />
      <CartDrawer
        open={cartOpen}
        onClose={() => setCartOpen(false)}
        items={cart.items}
        count={cart.count}
        total={cart.total}
        setQty={cart.setQty}
        remove={cart.remove}
      />
    </>
  );
}
