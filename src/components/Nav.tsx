import { useEffect, useState } from 'react';

interface Props {
  count: number;
  onOpenCart: () => void;
}

const LINKS = [
  { href: '#design', label: 'Design' },
  { href: '#layers', label: 'Layers' },
  { href: '#configure', label: 'Finishes' },
];

export function Nav({ count, onOpenCart }: Props) {
  const [scrolled, setScrolled] = useState(false);
  const [menu, setMenu] = useState(false);

  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 24);
    on();
    window.addEventListener('scroll', on, { passive: true });
    return () => window.removeEventListener('scroll', on);
  }, []);

  return (
    <header className={`nav ${scrolled ? 'is-scrolled' : ''} ${menu ? 'menu-open' : ''}`}>
      <div className="nav__inner">
        <a className="nav__brand" href="#top" aria-label="ARC, back to top">
          ARC
        </a>

        <nav className="nav__links" aria-label="Main">
          {LINKS.map((l) => (
            <a key={l.href} href={l.href} onClick={() => setMenu(false)}>
              {l.label}
            </a>
          ))}
        </nav>

        <button
          type="button"
          className="nav__cart"
          onClick={onOpenCart}
          aria-label={`Open demo cart, ${count} ${count === 1 ? 'item' : 'items'}`}
        >
          <span className="nav__cart-label">Cart</span>
          <span className={`nav__count ${count ? 'has-items' : ''}`}>{count}</span>
        </button>

        <button
          type="button"
          className="nav__menu"
          aria-expanded={menu}
          aria-controls="mobile-menu"
          onClick={() => setMenu((m) => !m)}
        >
          <span className="sr-only">{menu ? 'Close menu' : 'Open menu'}</span>
          <span className="nav__menu-icon" aria-hidden="true" />
        </button>
      </div>
      <nav id="mobile-menu" className="nav__drawer" aria-label="Main" hidden={!menu}>
        {LINKS.map((l) => (
          <a key={l.href} href={l.href} onClick={() => setMenu(false)}>
            {l.label}
          </a>
        ))}
      </nav>
    </header>
  );
}
