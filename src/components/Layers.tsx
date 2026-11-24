import { useRef, useState, type KeyboardEvent } from 'react';
import { LAYERS } from '../data/product';
import { useNear } from '../hooks/useNear';
import anchors from '../data/layersAnchors.json';

type LayerId = (typeof LAYERS)[number]['id'];

/**
 * "Designed in layers": one exploded render of the real ARC parts (design/arc-v4/render_layers.py) with a
 * callout on each exterior part. The callouts are tabs: selecting one (pointer, touch or keyboard) shows that
 * part's notes in the panel. The render is lazily loaded, so it never competes with the opening.
 */
export function Layers() {
  const [active, setActive] = useState<LayerId>('shell');
  const [loaded, setLoaded] = useState(false);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const figure = useRef<HTMLElement>(null);
  // Load the render about one screen before the section arrives.
  const near = useNear(figure);

  // Arrow keys move between the callouts, as in any tab list.
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = LAYERS.findIndex((l) => l.id === active);
    const n = LAYERS.length;
    const next =
      e.key === 'ArrowRight' || e.key === 'ArrowDown' ? (i + 1) % n
      : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? (i - 1 + n) % n
      : e.key === 'Home' ? 0
      : e.key === 'End' ? n - 1
      : -1;
    if (next < 0) return;
    e.preventDefault();
    setActive(LAYERS[next].id);
    tabs.current[next]?.focus();
  };

  const layer = LAYERS.find((l) => l.id === active)!;

  return (
    <section className="layers" id="layers" aria-labelledby="layers-title">
      <div className="layers__inner">
        <header className="layers__head">
          <h2 className="layers__title" id="layers-title">
            Designed in layers.
          </h2>
          <p className="layers__lede">
            The outside of ARC is three parts, each made for its job. Select a part to see why it is built the way it
            is.
          </p>
        </header>

        <figure className="layers__figure" ref={figure}>
          <div className="layers__art">
            <img
              className={`layers__img ${loaded ? 'is-loaded' : ''}`}
              src={near ? '/layers/exploded-1600.webp' : undefined}
              srcSet={
                near
                  ? '/layers/exploded-1000.webp 1000w, /layers/exploded-1600.webp 1600w, /layers/exploded-2400.webp 2400w'
                  : undefined
              }
              onLoad={() => setLoaded(true)}
              sizes="(max-width: 760px) 116vw, (max-width: 1100px) 92vw, 62vw"
              width={2400}
              height={1500}
              loading="lazy"
              decoding="async"
              alt="Exploded view of ARC: the titanium centre spine in front, then the front shell with the sticks and buttons, the back shell with the bumpers and triggers, and the two rubber grips at the back."
            />
            <div className="layers__callouts" role="tablist" aria-label="Parts" onKeyDown={onKey}>
              {LAYERS.map((l, i) => {
                const [x, y] = anchors[l.id];
                const selected = l.id === active;
                return (
                  <button
                    key={l.id}
                    ref={(el) => {
                      tabs.current[i] = el;
                    }}
                    type="button"
                    role="tab"
                    id={`layer-tab-${l.id}`}
                    aria-selected={selected}
                    aria-controls="layer-panel"
                    tabIndex={selected ? 0 : -1}
                    className={`callout ${x > 0.7 ? 'callout--flip' : ''} ${selected ? 'is-active' : ''}`}
                    style={{ left: `${x * 100}%`, top: `${y * 100}%` }}
                    onClick={() => setActive(l.id)}
                  >
                    <span className="callout__dot" aria-hidden="true" />
                    <span className="callout__label">{l.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </figure>

        <div
          className="layers__panel"
          id="layer-panel"
          role="tabpanel"
          aria-labelledby={`layer-tab-${layer.id}`}
          tabIndex={0}
        >
          <div className="layers__copy" key={layer.id}>
            <h3 className="layers__name">{layer.title}</h3>
            <p className="layers__material">{layer.material}</p>
            <p className="layers__body">{layer.body}</p>
            <p className="layers__finish">
              <span className="layers__finish-label">In each finish</span>
              {layer.finishes}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
