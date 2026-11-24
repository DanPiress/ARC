import { useEffect, useRef, useState } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { STAGES } from '../data/product';
import {
  JOURNEY,
  drawCover,
  fetchBlob,
  frameBytes,
  journeyFrame,
  journeyFrameAt,
  pickJourneySet,
  loadImage,
  releaseFrame,
  type Device,
  type Frame,
} from '../media';
import { scrollToElement } from '../smoothScroll';

gsap.registerPlugin(ScrollTrigger);

interface Props {
  /** False when ?static is set: plain images, no canvas. */
  live: boolean;
  reducedMotion: boolean;
  mobile: boolean;
}

const STILL_ALT = [
  'ARC controller in graphite floating above a low platform in a dark arched hall lit with cobalt light',
  'Close view of the left thumbstick: a concave dimpled cap in a dark well beside the titanium spine',
  'The control face from above: cross pad, face buttons, sticks and centre spine',
  'Rear three-quarter view showing the triggers, bumpers and textured rubber grips',
];

/**
 * Scroll progress (0..1) to a fractional frame index.
 * The camera slows towards each chapter for reading but never stops dead while the page moves: half of an
 * ease-in-out, half steady motion. Camera progress then maps to frames through the journey's frame table, whose
 * frames are spaced by how much the picture changes, so the cross-fade between neighbours stays small everywhere.
 */
const HOLD = 0.5;
const SEGMENTS = 3;
function journeyPosition(device: Device, p: number) {
  const x = Math.min(1, Math.max(0, p)) * SEGMENTS;
  const i = Math.min(SEGMENTS - 1, Math.floor(x));
  const u = x - i;
  const eased = 0.5 - 0.5 * Math.cos(Math.PI * u);
  const c = u + (eased - u) * HOLD; // camera progress within this transition
  return journeyFrameAt(device, (i + c) / SEGMENTS);
}

export function Showcase({ live, reducedMotion, mobile }: Props) {
  const sectionRef = useRef<HTMLElement>(null);
  const stickyRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [active, setActive] = useState(0);
  const [ready, setReady] = useState(false);
  const animated = live && !reducedMotion;
  const device: Device = mobile ? 'phone' : 'desktop';

  // Scroll journey: 193 pre-rendered frames of one continuous camera move, drawn to a canvas.
  // The drawn position is fractional: while the page moves, each pair of neighbouring frames is
  // cross-blended (they differ by a few pixels, so this reads as continuous motion at any scroll speed),
  // and when scrolling stops the view eases onto the nearest single frame, so it always rests sharp.
  useEffect(() => {
    if (!animated || !canvasRef.current || !sectionRef.current || !stickyRef.current) return;
    const canvas = canvasRef.current;
    const section = sectionRef.current;
    const sticky = stickyRef.current;
    const ctx = canvas.getContext('2d', { alpha: false });
    if (!ctx) return;
    const N = JOURNEY[device].frames;
    // The image set is chosen once, from the canvas size at the start.
    const r0 = canvas.getBoundingClientRect();
    const dpr0 = Math.min(window.devicePixelRatio || 1, 2);
    const set = pickJourneySet(device, r0.width * dpr0, r0.height * dpr0);
    const IW = set.w;
    const IH = set.h;
    canvas.dataset.set = set.dir;
    canvas.dataset.frames = String(N);
    const fx = mobile ? 0.5 : 0.6;
    // Every frame is kept as its compressed file (about 70 KB). Decoded copies are made off the main thread
    // (createImageBitmap from a Blob), already cropped and scaled to the canvas (never larger than the file), so
    // each draw is a plain copy. Decoded copies are kept only for a window around the current position, longer in
    // the direction of travel, plus anchor frames every 24th, so a fast jump always has something close to show
    // while its neighbours decode. Decodes run a few at a time, most urgent first (the frames just ahead), so the
    // frames about to be drawn never wait behind ones that are not needed yet. When the journey is scrolled out of
    // view, all but the frames at the current position are released and fetching pauses until it comes back.
    const blobs: (Blob | null | undefined)[] = new Array(N).fill(undefined);
    const fetched = new Array<number>(N).fill(0); // 0 not requested, 1 requested, 2 settled
    const cache = new Map<number, { img: Frame; kind: 'copy' | 'crop' | 'whole' }>();
    const decoding = new Set<string>(); // `${gen}:${frame}` in flight
    const AHEAD = mobile ? 11 : 14;
    const BEHIND = mobile ? 5 : 6;
    const ANCHOR = 24;
    const MAX_DECODES = 6;
    const BUDGET = AHEAD + BEHIND + 1 + Math.ceil(N / ANCHOR);
    let centre = 0;
    let dir = 1; // direction of travel through the frames
    let turnX = 0; // furthest position reached in that direction
    let wanted: number[] = []; // frames to have decoded, most urgent first
    let active = 0; // decodes in flight
    let cancelled = false;
    let raf = 0;
    let gen = 0; // bumped on resize: decoded copies are sized to the canvas
    let near = true; // the journey is on screen
    let shown = false; // the canvas has been revealed
    const waiting: (() => void)[] = [];
    const state = { p: 0 }; // scroll progress, smoothed by the scrub
    const view = { x: 0 }; // frame position drawn, 0..N-1
    let settle: gsap.core.Tween | null = null;
    let draws = 0;
    let misses = 0;

    const inWindow = (k: number) => {
      const d = (k - centre) * dir;
      return d >= -BEHIND && d <= AHEAD;
    };
    const keep = (k: number) => (near ? k % ANCHOR === 0 || inWindow(k) : Math.abs(k - centre) <= 1);
    // Urgency: frames ahead by their distance, frames behind at double theirs, anchors after the window.
    const plan = () => {
      const list: [number, number][] = [];
      if (near) {
        for (let d = 0; d <= AHEAD; d++) list.push([centre + dir * d, d]);
        for (let d = 1; d <= BEHIND; d++) list.push([centre - dir * d, 2 * d]);
        for (let k = 0; k < N; k += ANCHOR) list.push([k, 100 + Math.abs(k - centre)]);
      } else {
        for (const k of [centre, centre + 1, centre - 1]) list.push([k, Math.abs(k - centre)]);
      }
      wanted = list.filter(([k]) => k >= 0 && k < N).sort((a, b) => a[1] - b[1]).map(([k]) => k);
    };
    const pump = () => {
      for (const k of wanted) {
        if (active >= MAX_DECODES) return;
        if (blobs[k] && !cache.has(k) && !decoding.has(`${gen}:${k}`)) decode(k);
      }
    };
    const report = () => {
      let bytes = 0;
      cache.forEach((e) => (bytes += frameBytes(e.img)));
      Object.assign(canvas.dataset, { decoded: String(cache.size), decodedBytes: String(bytes), budget: String(BUDGET) });
    };
    // The canvas is revealed with the opening frame, or, if that file cannot be loaded, with the first frame
    // that can (the draw always shows the nearest decoded frame).
    const reveal = () => {
      if (shown) return;
      shown = true;
      setReady(true);
    };
    const decode = (k: number) => {
      const blob = blobs[k];
      const w = canvas.width;
      const h = canvas.height;
      const g = gen;
      const id = `${g}:${k}`;
      if (!blob || cache.has(k) || decoding.has(id) || !w || !h) return;
      decoding.add(id);
      active++;
      const done = (entry: { img: Frame; kind: 'copy' | 'crop' | 'whole' } | null) => {
        decoding.delete(id);
        active--;
        if (cancelled) return entry && releaseFrame(entry.img);
        pump();
        if (!entry) return;
        if (g !== gen || !keep(k) || cache.has(k)) return releaseFrame(entry.img);
        cache.set(k, entry);
        report();
        if (k === 0 || blobs[0] === null) reveal();
        if (Math.abs(k - view.x) <= 2 || cache.size === 1) schedule();
      };
      // The same cover crop as drawCover, done once at decode time.
      const s = Math.max(w / IW, h / IH);
      const d = Math.min(1, s);
      const dx = Math.min(0, Math.max(w - IW * s, w / 2 - IW * s * fx));
      const fallback = () =>
        loadImage(URL.createObjectURL(blob)).then((img) => {
          if (img) URL.revokeObjectURL(img.src);
          done(img && { img, kind: 'whole' });
        });
      if (typeof createImageBitmap !== 'function') return void fallback();
      createImageBitmap(blob, -dx / s, (IH - h / s) / 2, w / s, h / s, {
        resizeWidth: Math.round((w / s) * d),
        resizeHeight: Math.round((h / s) * d),
        resizeQuality: 'high',
      })
        .then((img) => done({ img, kind: d === s ? 'copy' : 'crop' }))
        .catch(() => createImageBitmap(blob).then((img) => done({ img, kind: 'whole' }), fallback));
    };
    const prefetch = () => {
      for (const [k, e] of cache) {
        if (!keep(k)) {
          releaseFrame(e.img);
          cache.delete(k);
        }
      }
      report();
      plan();
      pump();
    };
    const size = () => {
      const r = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = Math.round(r.width * dpr);
      const h = Math.round(r.height * dpr);
      if (gen > 0 && w === canvas.width && h === canvas.height) return;
      canvas.width = w;
      canvas.height = h;
      gen++;
      cache.forEach((e) => releaseFrame(e.img));
      cache.clear();
      prefetch();
    };
    const paint = (k: number, alpha = 1) => {
      const e = cache.get(k)!;
      ctx.globalAlpha = alpha;
      if (e.kind === 'copy') ctx.drawImage(e.img, 0, 0);
      else if (e.kind === 'crop') ctx.drawImage(e.img, 0, 0, canvas.width, canvas.height);
      else drawCover(ctx, e.img, canvas.width, canvas.height, fx, alpha);
      ctx.globalAlpha = 1;
    };
    const nearest = (i: number, dir: number) => {
      for (let k = i; k >= 0 && k < N; k += dir) if (cache.has(k)) return k;
      return -1;
    };
    const draw = () => {
      raf = 0;
      const x = Math.min(N - 1, Math.max(0, view.x));
      const i0 = Math.floor(x);
      const f = x - i0;
      draws++;
      if (cache.has(i0) && i0 + 1 < N && cache.has(i0 + 1) && f > 0.002 && f < 0.998) {
        paint(i0);
        paint(i0 + 1, f);
      } else {
        // Exactly on a frame, or a neighbour is still decoding: draw the nearest decoded frame alone.
        const r = Math.round(x);
        const below = nearest(r, -1);
        const above = nearest(r, 1);
        const i = below < 0 ? above : above < 0 ? below : r - below <= above - r ? below : above;
        if (i >= 0) paint(i);
        // A miss: the frames this position needs were not decoded yet (counted for the checks).
        if (i !== r || (f > 0.002 && f < 0.998)) misses++;
      }
      canvas.dataset.x = x.toFixed(2);
      canvas.dataset.draws = String(draws);
      canvas.dataset.misses = String(misses);
      sticky.style.setProperty('--p', state.p.toFixed(4));
      // Direction of travel, with some hysteresis: the small glide back onto a whole frame must not flip it.
      let turned = false;
      if ((x - turnX) * dir > 0) turnX = x;
      else if ((turnX - x) * dir > 0.75) {
        dir = -dir;
        turnX = x;
        turned = true;
      }
      const c = Math.round(x);
      if (c !== centre || turned) {
        centre = c;
        prefetch();
      }
    };
    const schedule = () => {
      if (!raf) raf = requestAnimationFrame(draw);
    };

    size();
    const ro = new ResizeObserver(() => {
      size();
      schedule();
    });
    ro.observe(canvas);

    // Pause fetching and release decoded frames while the journey is off screen (for example in the configurator).
    const io =
      typeof IntersectionObserver === 'function'
        ? new IntersectionObserver(
            ([entry]) => {
              near = entry.isIntersecting;
              prefetch();
              if (near) waiting.splice(0).forEach((wake) => wake());
            },
            // Slightly inside the viewport, so a section that only touches its edge counts as off screen.
            { rootMargin: '-2px 0px' },
          )
        : null;
    io?.observe(section);

    // Load order: opening frame, chapter keys, then coarse to fine (every 24th, 12th and 6th), so the whole
    // journey is roughly playable early; then the rest, nearest to the current position first (slightly ahead
    // of it). A few requests run in parallel.
    const coarse: number[] = [];
    for (const k of JOURNEY[device].keys) coarse.push(k);
    for (const stride of [48, 24, 12, 6]) for (let k = 0; k < N; k += stride) if (!coarse.includes(k)) coarse.push(k);
    let ci = 0;
    /** The next frame to fetch, and whether it belongs to the coarse pass (fetched at normal priority). */
    const pick = (): [number, boolean] => {
      while (ci < coarse.length) {
        const k = coarse[ci++];
        if (!fetched[k]) return [k, true];
      }
      let best = -1;
      let score = Infinity;
      for (let k = 0; k < N; k++) {
        if (fetched[k]) continue;
        const s = Math.abs(k - centre) + (k < centre ? 6 : 0);
        if (s < score) [best, score] = [k, s];
      }
      return [best, false];
    };
    const fetchFrame = (k: number, priority: 'high' | 'auto' | 'low') => {
      fetched[k] = 1;
      return fetchBlob(journeyFrame(set.dir, k), priority).then((blob) => {
        fetched[k] = 2;
        if (cancelled) return blob;
        blobs[k] = blob;
        if (blob && keep(k)) pump();
        return blob;
      });
    };
    const pause = (ms: number) => new Promise((r) => setTimeout(r, ms));
    (async () => {
      // The opening frame goes first, alone. If it fails, its neighbour (nearly identical) is fetched straight
      // away and shown instead (see reveal), and the opening frame is retried twice in the background.
      if (!(await fetchFrame(0, 'high')) && !cancelled) {
        void fetchFrame(1, 'high');
        void (async () => {
          for (const wait of [600, 2500]) {
            await pause(wait);
            if (cancelled || (await fetchFrame(0, 'high'))) return;
          }
        })();
      }
      const worker = async () => {
        while (!cancelled) {
          if (!near) await new Promise<void>((wake) => waiting.push(wake));
          if (cancelled) return;
          const [k, isCoarse] = pick();
          if (k < 0) return;
          await fetchFrame(k, isCoarse ? 'auto' : 'low');
        }
      };
      await Promise.all([worker(), worker(), worker(), worker()]);
    })();

    const st = gsap.to(state, {
      p: 1,
      ease: 'none',
      onUpdate: () => {
        settle?.kill();
        settle = null;
        view.x = journeyPosition(device, state.p);
        // Already inside the animation frame that moved the page: draw now rather than one frame later.
        cancelAnimationFrame(raf);
        draw();
      },
      scrollTrigger: {
        trigger: section,
        start: 'top top',
        end: 'bottom bottom',
        // Lenis already smooths wheel input; a short scrub only evens out touch and keyboard jumps.
        scrub: 0.4,
        // Rest on one sharp frame: glide the last fraction of a frame once the scroll has settled.
        onScrubComplete: () => {
          settle?.kill();
          settle = gsap.to(view, { x: Math.round(view.x), duration: 0.3, ease: 'power2.out', onUpdate: schedule });
        },
      },
    });

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      ro.disconnect();
      io?.disconnect();
      waiting.splice(0).forEach((wake) => wake());
      settle?.kill();
      st.scrollTrigger?.kill();
      st.kill();
      cache.forEach((e) => releaseFrame(e.img));
      cache.clear();
      setReady(false);
    };
  }, [animated, device, mobile]);

  // Which chapter is in view (drives the rail). Works in every mode.
  useEffect(() => {
    const blocks = sectionRef.current?.querySelectorAll<HTMLElement>('[data-stage]');
    if (!blocks) return;
    const triggers = Array.from(blocks).map((el, i) =>
      ScrollTrigger.create({
        trigger: el,
        start: 'top 55%',
        end: 'bottom 55%',
        onToggle: (self) => self.isActive && setActive(i),
      }),
    );
    return () => triggers.forEach((t) => t.kill());
  }, [animated]);

  // One opening sequence for the headline.
  useEffect(() => {
    if (reducedMotion || !sectionRef.current) return;
    const ctx = gsap.context(() => {
      gsap.from('.hero__reveal', { yPercent: 110, duration: 1.2, ease: 'power4.out', stagger: 0.1, delay: 0.2 });
      gsap.from('.hero__fade', { autoAlpha: 0, y: 16, duration: 0.9, ease: 'power2.out', stagger: 0.1, delay: 0.7 });
    }, sectionRef.current);
    return () => ctx.revert();
  }, [reducedMotion]);

  const goTo = (i: number) => {
    const el = sectionRef.current?.querySelectorAll<HTMLElement>('[data-stage]')[i];
    if (el) scrollToElement(el, !reducedMotion);
  };

  const still = (i: number, eager = false) => (
    <figure className="still">
      <picture>
        <source media="(max-width: 760px), (orientation: portrait) and (max-width: 1024px)" srcSet={journeyFrame('phone', JOURNEY.phone.keys[i])} />
        <img src={journeyFrame('desktop', JOURNEY.desktop.keys[i])} alt={STILL_ALT[i]} width={1920} height={1200} loading={eager ? 'eager' : 'lazy'} />
      </picture>
    </figure>
  );

  return (
    <section
      ref={sectionRef}
      className={`showcase ${animated ? 'showcase--live' : 'showcase--static'}`}
      id="design"
      aria-label="ARC product journey"
    >
      {animated && (
        <div className="showcase__sticky" ref={stickyRef}>
          <canvas ref={canvasRef} className={`showcase__canvas ${ready ? 'is-ready' : ''}`} aria-hidden="true" />
          <div className="showcase__shade" aria-hidden="true" />
          <nav className={`rail ${active > 0 ? 'is-visible' : ''}`} aria-label="Chapters">
            {STAGES.map((s, i) => (
              <button
                key={s.id}
                type="button"
                className={`rail__item ${active === i + 1 ? 'is-active' : ''}`}
                aria-current={active === i + 1 ? 'step' : undefined}
                onClick={() => goTo(i + 1)}
              >
                <span className="rail__bar" />
                <span className="rail__label">{s.label}</span>
              </button>
            ))}
          </nav>
        </div>
      )}

      <div className="showcase__content">
        <header className="hero" data-stage="0">
          {!animated && still(0, true)}
          <div className="hero__copy">
            <h1 className="hero__title">
              <span className="mask">
                <span className="hero__reveal">Your</span>
              </span>
              <span className="mask">
                <span className="hero__reveal">next</span>
              </span>
              <span className="mask">
                <span className="hero__reveal">move.</span>
              </span>
            </h1>
            <p className="hero__lede hero__fade">An original controller concept.</p>
            <a
              className="btn btn--primary hero__fade"
              href="#stage-1"
              onClick={(e) => {
                e.preventDefault();
                goTo(1);
              }}
            >
              Explore ARC
            </a>
          </div>
        </header>

        {STAGES.map((s, i) => (
          <article className={`chapter chapter--${s.id}`} data-stage={i + 1} id={`stage-${i + 1}`} key={s.id}>
            {!animated && still(i + 1)}
            <div className="chapter__copy">
              <h2 className="chapter__title">{s.title}</h2>
              <p className="chapter__body">{s.body}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
