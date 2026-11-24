import { useRef, useState } from 'react';
import { WHY } from '../data/product';
import { useNear } from '../hooks/useNear';

/**
 * "Why ARC": the design intention beside one setup image. The image is a real ARC render placed on a generated
 * desk backdrop (design/why-arc/). It loads about one screen before the section; phones get a taller 4:5 crop
 * below the text.
 */
export function Why() {
  const figure = useRef<HTMLElement>(null);
  const near = useNear(figure);
  const [loaded, setLoaded] = useState(false);

  return (
    <section className="why" id="why" aria-labelledby="why-title">
      <div className="why__inner">
        <div className="why__copy">
          <h2 className="why__title" id="why-title">
            {WHY.title}
          </h2>
          <p className="why__body">{WHY.body}</p>
          <p className="why__note">A concept, not a product. The controller in every image is a render.</p>
        </div>
        <figure className="why__figure" ref={figure}>
          <picture>
            <source
              media="(max-width: 760px)"
              srcSet={near ? '/why/setup-p-640.webp 640w, /why/setup-p-1000.webp 1000w' : undefined}
              sizes="calc(100vw - 2.5rem)"
              width={1000}
              height={1250}
            />
            <img
              className={`why__img ${loaded ? 'is-loaded' : ''}`}
              src={near ? '/why/setup-1200.webp' : undefined}
              srcSet={near ? '/why/setup-1200.webp 1200w, /why/setup-1800.webp 1800w' : undefined}
              sizes="(max-width: 1080px) 90vw, 56vw"
              width={1800}
              height={1200}
              loading="lazy"
              decoding="async"
              onLoad={() => setLoaded(true)}
              alt={WHY.alt}
            />
          </picture>
        </figure>
      </div>
    </section>
  );
}
