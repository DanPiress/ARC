import { useCallback, useEffect, useMemo, useState } from 'react';
import { COLORWAYS, PRODUCT, type ColorwayId } from '../data/product';

export interface CartItem {
  id: ColorwayId;
  qty: number;
}

const KEY = 'arc-demo-cart-v1';
export const MAX_QTY = 9;

function load(): CartItem[] {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? '[]');
    if (!Array.isArray(raw)) return [];
    return raw
      .filter((i) => COLORWAYS.some((c) => c.id === i?.id) && Number.isInteger(i?.qty) && i.qty > 0)
      .map((i) => ({ id: i.id, qty: Math.min(MAX_QTY, i.qty) }));
  } catch {
    return [];
  }
}

export function useCart() {
  const [items, setItems] = useState<CartItem[]>(load);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(items));
    } catch {
      /* storage unavailable: cart still works for this visit */
    }
  }, [items]);

  // Keep several tabs in step.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => e.key === KEY && setItems(load());
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const add = useCallback((id: ColorwayId) => {
    setItems((list) => {
      const found = list.find((i) => i.id === id);
      if (found) return list.map((i) => (i.id === id ? { ...i, qty: Math.min(MAX_QTY, i.qty + 1) } : i));
      return [...list, { id, qty: 1 }];
    });
  }, []);

  const setQty = useCallback((id: ColorwayId, qty: number) => {
    setItems((list) =>
      qty <= 0 ? list.filter((i) => i.id !== id) : list.map((i) => (i.id === id ? { ...i, qty: Math.min(MAX_QTY, qty) } : i)),
    );
  }, []);

  const remove = useCallback((id: ColorwayId) => setItems((list) => list.filter((i) => i.id !== id)), []);

  const count = useMemo(() => items.reduce((n, i) => n + i.qty, 0), [items]);
  const total = count * PRODUCT.price;

  return { items, add, setQty, remove, count, total };
}
