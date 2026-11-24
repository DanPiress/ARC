import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import gsap from 'gsap';
import { COLORWAYS, PRODUCT, formatPrice, getColorway, type ColorwayId } from '../data/product';
import {
  TURN_FRAMES,
  TURN_FULL,
  TURN_SAFE,
  fetchBlob,
  frameBytes,
  loadImage,
  pickTurnSet,
  releaseFrame,
  turnFrame,
  turnScale,
  type Frame,
  type TurnSet,
} from '../media';

interface Props {
  colorway: ColorwayId;
  onColorway: (id: ColorwayId) => void;
  onAdd: () => void;
  addedNote: string;
  /** False when ?static is set: a still image instead of the turntable. */
  live: boolean;
  reducedMotion: boolean;
}

/** One keyboard/button step: 22.5 degrees (six turntable frames). */
const STEP = Math.PI / 8;
/** The angle between two rendered frames; resting angles snap to a multiple of this so the view rests sharp. */
const FRAME_ANGLE = (2 * Math.PI) / TURN_FRAMES;
const onFrame = (yaw: number) => Math.round(yaw / FRAME_ANGLE) * FRAME_ANGLE;
const wrap = (k: number) => ((k % TURN_FRAMES) + TURN_FRAMES) % TURN_FRAMES;
/** Load order for a turn: every 12th frame first, then 6th, 3rd and the rest, so it can turn early. */
const COARSE_TO_FINE = (() => {
  const out: number[] = [];
  for (const stride of [12, 6, 3, 1]) for (let k = 0; k < TURN_FRAMES; k += stride) if (!out.includes(k)) out.push(k);
  return out;
})();
/** Unselected finishes fetch every fourth frame, so switching to them can turn straight away. */
const PREVIEW = COARSE_TO_FINE.filter((k) => k % 4 === 0);

/**
 * Decoded-frame budget. Compressed files are kept for every fetched frame (about 50-90 KB each); decoded copies,
 * cropped and scaled to the canvas, are kept only for:
 *   the frames being drawn, a ring around the current angle (longer in the direction of travel), the angle a
 *   keyboard turn or flick is heading for, regularly spaced anchors of the selected finish (something close to
 *   show during a fast spin), and the current angle of each other finish (so switching shows at once).
 * Everything else is released, and the list is cut to BUDGET frames, nearest first.
 */
const CACHE = {
  phone: { budget: 24, ahead: 6, behind: 3, anchor: 12 },
  desktop: { budget: 36, ahead: 8, behind: 5, anchor: 6 },
};
const MAX_DECODES = 4;
const FETCHERS = 3;

interface Decoded {
  img: Frame;
  gen: number;
  /** The part of the source image this copy holds, in source pixels. */
  sx: number;
  sy: number;
  sw: number;
  sh: number;
  /** Decoded exactly at drawing size for canvas generation `gen`: drawn as a plain copy at (dx, dy). */
  fitted: boolean;
  dx: number;
  dy: number;
  bytes: number;
}

export function Configurator({ colorway, onColorway, onAdd, addedNote, live, reducedMotion }: Props) {
  const viewerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const colorRef = useRef(colorway);
  colorRef.current = colorway;
  const rot = useRef({ yaw: 0 });
  const drag = useRef<{ id: number; x: number; vx: number; t: number } | null>(null);
  // Where keyboard/button rotation is heading, so quick repeated presses add up
  // instead of each restarting from the half-finished animated angle.
  const aim = useRef({ yaw: 0 });
  const [turnSet, setTurnSet] = useState<TurnSet | null>(null);
  const setRef = useRef<TurnSet | null>(null);
  const [nearViewer, setNearViewer] = useState(false);
  const [ready, setReady] = useState(false);
  const readyRef = useRef(false);
  const [rotated, setRotated] = useState(false);
  const c = getColorway(colorway);
  // Phones and tablets have no arrow keys to mention.
  const [touchOnly] = useState(() => typeof matchMedia === 'function' && matchMedia('(hover: none) and (pointer: coarse)').matches);
  const [cfg] = useState(() => (typeof matchMedia === 'function' && matchMedia('(max-width: 760px)').matches ? CACHE.phone : CACHE.desktop));

  // Everything the turntable has loaded. It lives in a ref, so it survives effect cleanup (including StrictMode's
  // setup replay): compressed files and in-flight requests are never lost; decoded copies are released on unmount.
  const store = useRef({
    /** Compressed files per finish; undefined = not fetched yet, null = the request failed. */
    blobs: {} as Record<string, (Blob | null | undefined)[]>,
    pending: new Map<string, Promise<Blob | null>>(),
    decoded: new Map<string, Decoded>(),
    decoding: new Set<string>(),
    /** Bumped when the canvas size changes (decoded copies are sized to it). */
    gen: 0,
    wanted: new Set<string>(),
    order: [] as string[],
    plan: '',
    dir: 1,
    lastYaw: 0,
    raf: 0,
    stats: '',
  });

  const position = () => wrap((rot.current.yaw / (2 * Math.PI)) * TURN_FRAMES);
  const keyOf = (finish: string, k: number) => `${finish}:${wrap(k)}`;

  /** Publishes the cache size on the canvas (read by the QA scripts). */
  const report = () => {
    const st = store.current;
    const canvas = canvasRef.current;
    if (!canvas) return;
    let bytes = 0;
    const by: Record<string, number> = {};
    for (const [key, e] of st.decoded) {
      bytes += e.bytes;
      const fin = key.split(':')[0];
      by[fin] = (by[fin] ?? 0) + 1;
    }
    let compressed = 0;
    for (const list of Object.values(st.blobs)) for (const b of list) compressed += b ? b.size : 0;
    const stats = `${st.decoded.size}|${bytes}|${compressed}`;
    if (stats === st.stats) return;
    st.stats = stats;
    Object.assign(canvas.dataset, {
      decoded: String(st.decoded.size),
      decodedBytes: String(bytes),
      decodedBy: Object.entries(by).map(([f, n]) => `${f}:${n}`).join(','),
      budget: String(cfg.budget),
      compressedBytes: String(compressed),
      set: setRef.current?.dir ?? '',
    });
  };

  /** Works out which frames should be decoded now, releases the rest and starts the missing decodes. */
  const plan = (force = false) => {
    const st = store.current;
    const sel = colorRef.current;
    const x = position();
    const r = wrap(Math.round(x));
    const tweening = gsap.isTweening(rot.current);
    const target = tweening ? wrap(Math.round((aim.current.yaw / (2 * Math.PI)) * TURN_FRAMES)) : -1;
    const signature = `${sel}|${Math.floor(x)}|${r}|${st.dir}|${target}|${st.gen}`;
    if (!force && signature === st.plan) return;
    st.plan = signature;
    const order: string[] = [];
    const add = (fin: string, k: number) => {
      const key = keyOf(fin, k);
      if (!order.includes(key) && st.blobs[fin]?.[wrap(k)]) order.push(key);
    };
    add(sel, Math.floor(x));
    add(sel, Math.floor(x) + 1);
    for (let d = 1; d <= cfg.ahead; d++) {
      add(sel, r + st.dir * d);
      if (d <= cfg.behind) add(sel, r - st.dir * d);
    }
    if (target >= 0) for (const d of [0, 1, -1, 2, -2]) add(sel, target + d);
    // Other finishes: the nearest fetched frame to this angle (they preload every fourth).
    for (const fin of COLORWAYS.map((o) => o.id)) {
      if (fin === sel) continue;
      const d = [0, 1, -1, 2, -2, 3, -3].find((o) => st.blobs[fin]?.[wrap(r + o)]);
      if (d !== undefined) add(fin, r + d);
    }
    const anchors: number[] = [];
    for (let k = 0; k < TURN_FRAMES; k += cfg.anchor) anchors.push(k);
    const dist = (k: number) => Math.min(wrap(k - r), wrap(r - k));
    anchors.sort((a, b) => dist(a) - dist(b)).forEach((k) => add(sel, k));
    st.order = order.slice(0, cfg.budget);
    st.wanted = new Set(st.order);
    for (const [key, e] of st.decoded) {
      if (st.wanted.has(key)) continue;
      releaseFrame(e.img);
      st.decoded.delete(key);
    }
    pump();
    report();
  };

  /** Starts decodes for wanted frames that have no copy at the current canvas size, a few at a time. */
  const pump = () => {
    const st = store.current;
    for (const key of st.order) {
      if (st.decoding.size >= MAX_DECODES) return;
      const e = st.decoded.get(key);
      if (!e || e.gen !== st.gen) decode(key);
    }
  };

  const decode = (key: string) => {
    const st = store.current;
    const canvas = canvasRef.current;
    const set = setRef.current;
    const [fin, ks] = key.split(':');
    const blob = st.blobs[fin]?.[Number(ks)];
    const g = st.gen;
    const id = `${g}|${key}`;
    if (!blob || !canvas || !set || !canvas.width || !canvas.height || st.decoding.has(id)) return;
    st.decoding.add(id);
    const w = canvas.width;
    const h = canvas.height;
    const s = turnScale(w, h, set.w, set.h);
    const d = Math.min(1, s); // never decode larger than the file itself
    // The part of the image inside the canvas, in source pixels.
    const vx = TURN_SAFE.cx * set.w - w / 2 / s;
    const vy = TURN_SAFE.cy * set.h - h / 2 / s;
    const sx = Math.max(0, Math.floor(vx));
    const sy = Math.max(0, Math.floor(vy));
    const sw = Math.min(set.w, Math.ceil(vx + w / s)) - sx;
    const sh = Math.min(set.h, Math.ceil(vy + h / s)) - sy;
    const done = (img: Frame | null, crop: [number, number, number, number], fitted: boolean) => {
      st.decoding.delete(id);
      if (!img) {
        // An undecodable file counts as failed, so it is not retried in a loop.
        st.blobs[fin][Number(ks)] = null;
        plan(true);
      } else {
        if (g !== st.gen || !st.wanted.has(key) || !canvasRef.current) {
          releaseFrame(img);
        } else {
          const old = st.decoded.get(key);
          if (old) releaseFrame(old.img);
          const [cx0, cy0, cw, ch] = crop;
          st.decoded.set(key, {
            img,
            gen: g,
            sx: cx0,
            sy: cy0,
            sw: cw,
            sh: ch,
            fitted,
            dx: Math.round(w / 2 + (cx0 - TURN_SAFE.cx * set.w) * s),
            dy: Math.round(h / 2 + (cy0 - TURN_SAFE.cy * set.h) * s),
            bytes: frameBytes(img),
          });
          report();
          if (fin === colorRef.current) schedule();
        }
      }
      pump();
    };
    const whole = () =>
      loadImage(URL.createObjectURL(blob)).then((img) => {
        if (img) URL.revokeObjectURL(img.src);
        done(img, [0, 0, set.w, set.h], false);
      });
    if (typeof createImageBitmap !== 'function') return void whole();
    createImageBitmap(blob, sx, sy, sw, sh, {
      resizeWidth: Math.max(1, Math.round(sw * d)),
      resizeHeight: Math.max(1, Math.round(sh * d)),
      resizeQuality: 'high',
    })
      .then((img) => done(img, [sx, sy, sw, sh], d === s))
      .catch(whole);
  };

  /**
   * Draws the current angle. Between two rendered angles the neighbouring frames are blended (they are 3.75
   * degrees apart, so this reads as continuous rotation); if a neighbour is not decoded yet, the nearest decoded
   * frame is shown. Returns false, leaving the canvas untouched, when this finish has nothing decoded yet.
   */
  const draw = () => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    const set = setRef.current;
    if (!canvas || !ctx || !set || !canvas.width) return false;
    const st = store.current;
    plan();
    const fin = colorRef.current;
    const x = position();
    const i0 = Math.floor(x) % TURN_FRAMES;
    const f = x - Math.floor(x);
    const w = canvas.width;
    const h = canvas.height;
    const s = turnScale(w, h, set.w, set.h);
    const place = (e: Decoded) => {
      if (e.fitted && e.gen === st.gen) ctx.drawImage(e.img, e.dx, e.dy);
      else ctx.drawImage(e.img, w / 2 + (e.sx - TURN_SAFE.cx * set.w) * s, h / 2 + (e.sy - TURN_SAFE.cy * set.h) * s, e.sw * s, e.sh * s);
    };
    const shown = (what: string) => {
      if (canvas.dataset.drawn !== what) canvas.dataset.drawn = what;
      return true;
    };
    const a = st.decoded.get(keyOf(fin, i0));
    const b = st.decoded.get(keyOf(fin, i0 + 1));
    if (a && b && f > 0.002 && f < 0.998) {
      ctx.clearRect(0, 0, w, h);
      // A true mix of two transparent frames: (1 - f) of one plus f of the other ('lighter' adds them),
      // so the soft shadow keeps its density mid-blend.
      ctx.globalAlpha = 1 - f;
      place(a);
      ctx.globalCompositeOperation = 'lighter';
      ctx.globalAlpha = f;
      place(b);
      ctx.globalCompositeOperation = 'source-over';
      ctx.globalAlpha = 1;
      return shown(`${fin}:${i0}+${wrap(i0 + 1)}`);
    }
    const r = Math.round(x);
    for (let d = 0; d <= TURN_FRAMES / 2; d++) {
      const k = st.decoded.has(keyOf(fin, r + d)) ? r + d : r - d;
      const e = st.decoded.get(keyOf(fin, k));
      if (!e) continue;
      ctx.clearRect(0, 0, w, h);
      place(e);
      return shown(`${fin}:${wrap(k)}`);
    }
    return false;
  };

  /** Draws on the next animation frame (after a decode lands) and reveals the canvas on its first frame. */
  const schedule = () => {
    const st = store.current;
    if (st.raf) return;
    st.raf = requestAnimationFrame(() => {
      st.raf = 0;
      if (draw() && !readyRef.current) {
        readyRef.current = true;
        setReady(true);
      }
    });
  };

  // Pick the image set for this screen before anything loads (the viewer is far below the first screen).
  useEffect(() => {
    if (!live || !viewerRef.current) return;
    const r = viewerRef.current.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const set = pickTurnSet(r.width * dpr, r.height * dpr);
    setRef.current = set;
    setTurnSet(set);
  }, [live]);

  // Size the canvas to its box (sharp on high-density screens). A new size makes new decoded copies; the old
  // ones stay drawable (scaled) until each is replaced, so resizing never blanks the view.
  useEffect(() => {
    if (!live || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ro = new ResizeObserver(() => {
      const r = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = Math.round(r.width * dpr);
      const h = Math.round(r.height * dpr);
      if (w === canvas.width && h === canvas.height) return;
      canvas.width = w;
      canvas.height = h;
      store.current.gen++;
      plan(true);
      draw();
    });
    ro.observe(canvas);
    return () => ro.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live]);

  // Load the turntables only as the viewer approaches, so nothing competes with the opening screen.
  useEffect(() => {
    if (!live || !viewerRef.current) return;
    if (typeof IntersectionObserver === 'undefined') {
      setNearViewer(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        setNearViewer(true);
        observer.disconnect();
      },
      { rootMargin: '400px' },
    );
    observer.observe(viewerRef.current);
    return () => observer.disconnect();
  }, [live]);

  // A finish change draws the new finish at the same angle as soon as one of its frames is decoded. Until then the
  // previous image stays up for the few milliseconds a decode takes; a finish with no files yet hides the canvas
  // until its first frame arrives. (A layout effect, so the new finish is on the canvas before the browser paints.)
  useLayoutEffect(() => {
    if (!live) return;
    plan(true);
    if (draw()) {
      readyRef.current = true;
      setReady(true);
    } else if (!store.current.blobs[colorway]?.some(Boolean)) {
      readyRef.current = false;
      setReady(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, colorway]);

  // Fetch compressed files, a few at a time, rechecking priority before each request so a newly selected finish
  // goes ahead of background frames. Results are stored even if this effect has been cleaned up meanwhile.
  useEffect(() => {
    if (!live || !nearViewer || !turnSet) return;
    let cancelled = false;
    const st = store.current;
    const next = () => {
      const selected = colorRef.current;
      const order = [selected, ...COLORWAYS.map((finish) => finish.id).filter((id) => id !== selected)];
      for (const id of order) {
        const list = st.blobs[id] ?? (st.blobs[id] = new Array(TURN_FRAMES).fill(undefined));
        const wanted = id === selected ? COARSE_TO_FINE : PREVIEW;
        const index = wanted.find((k) => list[k] === undefined && !st.pending.has(turnFrame(id, k, turnSet)));
        if (index !== undefined) return { id, index, selected: id === selected };
      }
      return null;
    };
    const request = (id: string, index: number, priority: 'high' | 'auto' | 'low') => {
      const src = turnFrame(id, index, turnSet);
      const existing = st.pending.get(src);
      if (existing) return existing;
      const req = fetchBlob(src, priority);
      st.pending.set(src, req);
      req.then((blob) => {
        st.blobs[id][index] = blob;
        st.pending.delete(src);
        plan(true);
        report();
        if (id === colorRef.current) schedule();
      });
      return req;
    };
    const fetcher = async () => {
      while (!cancelled) {
        const job = next();
        if (!job) return;
        await request(job.id, job.index, job.selected ? 'auto' : 'low');
      }
    };
    (async () => {
      // The frame at the current angle of the selected finish goes first, alone, so the viewer shows quickly
      // on a slow connection; then a few requests run in parallel.
      const sel = colorRef.current;
      const list = st.blobs[sel] ?? (st.blobs[sel] = new Array(TURN_FRAMES).fill(undefined));
      const first = wrap(Math.round(position()));
      if (list[first] === undefined) await request(sel, first, 'high');
      if (!cancelled) for (let i = 0; i < FETCHERS; i++) fetcher();
    })();
    return () => {
      cancelled = true;
    };
    // Restarts when the finish changes, so a newly selected finish loads its remaining frames.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, nearViewer, colorway, turnSet]);

  useEffect(
    () => () => {
      gsap.killTweensOf(rot.current);
      drag.current = null;
      const st = store.current;
      cancelAnimationFrame(st.raf);
      st.raf = 0;
      st.decoded.forEach((e) => releaseFrame(e.img));
      st.decoded.clear();
      st.decoding.clear();
      st.plan = '';
      st.stats = '';
      readyRef.current = false;
    },
    [],
  );

  const applyRot = () => {
    const st = store.current;
    const dy = rot.current.yaw - st.lastYaw;
    if (Math.abs(dy) > 1e-6) st.dir = dy > 0 ? 1 : -1;
    st.lastYaw = rot.current.yaw;
    draw();
    setRotated(Math.abs(rot.current.yaw) > 0.01);
  };

  const turnTo = (target: number) => {
    const yaw = onFrame(target);
    aim.current = { yaw };
    gsap.killTweensOf(rot.current);
    if (reducedMotion) {
      rot.current.yaw = yaw;
      applyRot();
      return;
    }
    gsap.to(rot.current, { yaw, duration: 0.6, ease: 'power3.out', onUpdate: applyRot });
    plan(true); // start decoding around the destination now
  };

  const rotateBy = (dy: number) => {
    // Continue from the pending target while a turn is animating, otherwise from the current angle
    // (which may have changed by dragging).
    // (getTweensOf also sees a tween created this frame that has not rendered yet.)
    const from = gsap.getTweensOf(rot.current).length ? aim.current : rot.current;
    turnTo(from.yaw + dy);
  };

  const reset = () => turnTo(0);

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (!live) return;
    gsap.killTweensOf(rot.current);
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      /* pointer already released */
    }
    drag.current = { id: e.pointerId, x: e.clientX, vx: 0, t: performance.now() };
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    const dx = e.clientX - d.x;
    const now = performance.now();
    d.vx = dx / Math.max(1, now - d.t);
    d.x = e.clientX;
    d.t = now;
    // Vertical drags remain available for native page scrolling.
    rot.current.yaw += dx * 0.009;
    applyRot();
  };
  const endPointer = (e: PointerEvent<HTMLDivElement>, cancelled: boolean) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    drag.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
    gsap.killTweensOf(rot.current);
    if (!cancelled && !reducedMotion && Math.abs(d.vx) > 0.05) {
      // A little carry after a flick, ending exactly on a rendered frame.
      aim.current = { yaw: onFrame(rot.current.yaw + d.vx * 4) };
      gsap.to(rot.current, { yaw: aim.current.yaw, duration: 0.9, ease: 'power3.out', onUpdate: applyRot });
      plan(true);
      return;
    }
    // Otherwise ease the last fraction of a frame, so the view always rests on one sharp frame.
    aim.current = { yaw: onFrame(rot.current.yaw) };
    gsap.to(rot.current, { yaw: aim.current.yaw, duration: reducedMotion ? 0 : 0.2, ease: 'power2.out', onUpdate: applyRot });
  };

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const map: Record<string, number> = {
      ArrowLeft: -STEP,
      ArrowRight: STEP,
    };
    if (map[e.key]) {
      e.preventDefault();
      rotateBy(map[e.key]);
    } else if (e.key === 'Home' || e.key === '0') {
      e.preventDefault();
      reset();
    }
  };

  return (
    <section className="config" id="configure" aria-labelledby="config-title">
      <div className="config__inner">
        <div className="config__head">
          <h2 id="config-title" className="config__title">Choose your finish</h2>
          <p className="config__lede">One shell, three finishes. Turn it to see every side.</p>
        </div>

        <div className="config__viewer">
          <div
            ref={viewerRef}
            className={`viewer ${live ? 'viewer--live' : 'viewer--still'}`}
            tabIndex={live ? 0 : -1}
            role={live ? 'application' : undefined}
            aria-roledescription={live ? 'turntable' : undefined}
            aria-label={live ? `ARC in ${c.name}. Drag, or use the left and right arrow keys to turn it. Home resets the view.` : undefined}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={(e) => endPointer(e, false)}
            onPointerCancel={(e) => endPointer(e, true)}
            onKeyDown={onKey}
          >
            {live ? (
              // No placeholder image: the turntable starts loading 400 px before the viewer scrolls into view
              // and the canvas fades in with its first frame (a lazy <img> would still load with the opening
              // screen on phones, where Chrome's lazy-load distance is about 2500 px).
              <canvas ref={canvasRef} className={`viewer__canvas ${ready ? 'is-ready' : ''}`} />
            ) : (
              <img
                className="viewer__still"
                src={turnFrame(colorway, 0, TURN_FULL)}
                alt={`ARC controller in ${c.name}`}
                width={TURN_FULL.w}
                height={TURN_FULL.h}
                loading="lazy"
              />
            )}
          </div>
          <div className="viewer__tools">
            {live ? (
              <>
                <p className="viewer__hint">{touchOnly ? 'Drag to turn it' : 'Drag or use the arrow keys to turn it'}</p>
                <div className="viewer__buttons">
                  <button type="button" className="icon-btn" onClick={() => rotateBy(-STEP)} aria-label="Rotate left">
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 7 4 12l5 5M4.5 12H15a5 5 0 0 1 0 10" /></svg>
                  </button>
                  <button type="button" className="icon-btn" onClick={() => rotateBy(STEP)} aria-label="Rotate right">
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 7 5 5-5 5M19.5 12H9a5 5 0 0 0 0 10" /></svg>
                  </button>
                  <button type="button" className="text-btn" onClick={reset} disabled={!rotated}>
                    Reset view
                  </button>
                </div>
              </>
            ) : (
              <p className="viewer__hint">A still render of the same model. Load the page without ?static to turn it.</p>
            )}
          </div>
        </div>

        <div className="config__panel">
          <fieldset className="swatches">
            <legend className="swatches__legend">
              Finish <span className="swatches__current">{c.name}</span>
            </legend>
            <div className="swatches__row">
              {COLORWAYS.map((o) => (
                <label key={o.id} className={`swatch ${o.id === colorway ? 'is-selected' : ''}`}>
                  <input
                    type="radio"
                    name="colorway"
                    value={o.id}
                    checked={o.id === colorway}
                    onChange={() => onColorway(o.id)}
                  />
                  <span
                    className="swatch__chip"
                    aria-hidden="true"
                    style={{ ['--a' as string]: o.swatch[0], ['--b' as string]: o.swatch[1] }}
                  />
                  <span className="swatch__name">{o.name}</span>
                </label>
              ))}
            </div>
            <p className="swatches__desc">{c.description}</p>
          </fieldset>

          <div className="buy">
            <p className="buy__price">
              <span className="buy__amount">{formatPrice(PRODUCT.price)}</span>
              <span className="buy__note">Sample price. Demo cart only, nothing is charged.</span>
            </p>
            <button type="button" className="btn btn--primary btn--wide" onClick={onAdd}>
              Add {c.name} to demo cart
            </button>
            <p className="buy__status" role="status" aria-live="polite">
              {addedNote}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
