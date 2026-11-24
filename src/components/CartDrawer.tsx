import { useEffect, useRef } from 'react';
import { PRODUCT, formatPrice, getColorway, type ColorwayId } from '../data/product';
import { MAX_QTY, type CartItem } from '../hooks/useCart';

interface Props {
  open: boolean;
  onClose: () => void;
  items: CartItem[];
  count: number;
  total: number;
  setQty: (id: ColorwayId, qty: number) => void;
  remove: (id: ColorwayId) => void;
}

export function CartDrawer({ open, onClose, items, count, total, setQty, remove }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const lastFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (open) {
      lastFocus.current = document.activeElement as HTMLElement;
      requestAnimationFrame(() => closeRef.current?.focus());
      document.documentElement.classList.add('no-scroll');
    } else {
      document.documentElement.classList.remove('no-scroll');
      lastFocus.current?.focus?.();
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'Tab' && panelRef.current) {
        const f = panelRef.current.querySelectorAll<HTMLElement>('button:not([disabled]), a[href]');
        if (!f.length) return;
        const first = f[0];
        const last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  return (
    <div className={`cart ${open ? 'is-open' : ''}`} aria-hidden={!open} inert={!open}>
      <div className="cart__scrim" onClick={onClose} />
      <div className="cart__panel" role="dialog" aria-modal="true" aria-labelledby="cart-title" ref={panelRef}>
        <header className="cart__head">
          <div>
            <h2 id="cart-title" className="cart__title">Demo cart</h2>
            <p className="cart__sub">{count === 0 ? 'No items' : `${count} ${count === 1 ? 'item' : 'items'}`}</p>
          </div>
          <button ref={closeRef} type="button" className="icon-btn icon-btn--dark" onClick={onClose} aria-label="Close demo cart">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
          </button>
        </header>

        <p className="cart__notice">
          This is a concept project. The cart is saved in this browser only; there is no checkout and nothing is charged.
        </p>

        {items.length === 0 ? (
          <div className="cart__empty">
            <img src="/renders/thumb-graphite.png" alt="" width={240} height={240} />
            <p className="cart__empty-title">Your demo cart is empty</p>
            <p className="cart__empty-body">Pick a finish in the configurator and add it here to try the cart.</p>
            <a className="btn btn--primary" href="#configure" onClick={onClose}>
              Go to configurator
            </a>
          </div>
        ) : (
          <>
            <ul className="cart__list">
              {items.map((item) => {
                const c = getColorway(item.id);
                return (
                  <li className="line" key={item.id}>
                    <img className="line__thumb" src={`/renders/thumb-${item.id}.png`} alt="" width={240} height={240} />
                    <div className="line__info">
                      <p className="line__name">{PRODUCT.name} {c.name}</p>
                      <p className="line__unit">{formatPrice(PRODUCT.price)} each</p>
                      <div className="qty" role="group" aria-label={`Quantity for ${c.name}`}>
                        <button
                          type="button"
                          onClick={() => setQty(item.id, item.qty - 1)}
                          aria-label={`Decrease ${c.name} quantity`}
                        >
                          −
                        </button>
                        <output aria-live="polite" aria-label={`${c.name} quantity`}>{item.qty}</output>
                        <button
                          type="button"
                          onClick={() => setQty(item.id, item.qty + 1)}
                          disabled={item.qty >= MAX_QTY}
                          aria-label={`Increase ${c.name} quantity`}
                        >
                          +
                        </button>
                      </div>
                    </div>
                    <div className="line__end">
                      <p className="line__total">{formatPrice(item.qty * PRODUCT.price)}</p>
                      <button type="button" className="text-btn text-btn--small" onClick={() => remove(item.id)} aria-label={`Remove ${c.name} from cart`}>
                        Remove
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
            <footer className="cart__foot">
              <div className="cart__total">
                <span>Sample total</span>
                <strong>{formatPrice(total)}</strong>
              </div>
              <button type="button" className="btn btn--primary btn--wide" disabled>
                Checkout unavailable in this demo
              </button>
            </footer>
          </>
        )}
      </div>
    </div>
  );
}
