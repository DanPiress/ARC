// Pre-rendered media produced by design/arc-v4/render_scene.py (Blender, Cycles) from the one ARC model.

import journeyPlan from './data/journeyFrames.json';

export type Device = 'desktop' | 'phone';
/**
 * The scroll journeys: one continuous camera move through four chapters (opening, sticks, controls, shoulders).
 * Frames are placed along the move so each step changes the picture by about the same amount
 * (design/arc-v4/plan_journey.py): `progress` is each frame's camera progress (chapter i at i/3) and `keys` the
 * frame index of each chapter.
 */
export const JOURNEY: Record<Device, { frames: number; keys: readonly number[]; progress: readonly number[] }> = {
  desktop: { frames: journeyPlan.desktop.progress.length, ...journeyPlan.desktop },
  phone: { frames: journeyPlan.phone.progress.length, ...journeyPlan.phone },
};
/**
 * Journey image sets per device, smallest first: the same frames at different sizes. The page uses the smallest
 * set that its canvas would not enlarge by more than 10%, so a 1366-1600 px desktop window decodes 1440 px frames
 * as they are (resizing each frame while scrolling cost more than decoding it) and fetches less.
 */
export const JOURNEY_SETS = {
  desktop: [
    { dir: 'desktop-s', w: 1440, h: 900 },
    { dir: 'desktop', w: 1920, h: 1200 },
  ],
  phone: [{ dir: 'phone', w: 828, h: 1794 }],
} as const;
export type JourneySet = (typeof JOURNEY_SETS)[Device][number];
export function pickJourneySet(device: Device, w: number, h: number): JourneySet {
  const sets = JOURNEY_SETS[device];
  return sets.find((s) => Math.max(w / s.w, h / s.h) <= 1.1) ?? sets[sets.length - 1];
}
export const journeyFrame = (dir: string, i: number) => `/journey/${dir}/${String(i).padStart(3, '0')}.webp`;
/** Fractional frame index showing camera progress c (0..1). */
export function journeyFrameAt(device: Device, c: number) {
  const p = JOURNEY[device].progress;
  if (c <= p[0]) return 0;
  if (c >= p[p.length - 1]) return p.length - 1;
  let lo = 0;
  let hi = p.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (p[mid] <= c) lo = mid;
    else hi = mid;
  }
  return lo + (c - p[lo]) / (p[hi] - p[lo]);
}

/** Frames in each configurator turntable: one full turn, 3.75 degrees apart. */
export const TURN_FRAMES = 96;
/**
 * The part of each turntable frame (1200x900) that must stay in view: the product at every angle, as fractions
 * of the frame, centred on cx, cy. The viewer scales this box to fit, so the product fills the viewer.
 */
// Measured: the product's union outline over all frames is 0.718 x 0.698 centred at (0.499, 0.576)
// (work/turn_bounds.py); the box adds a small margin.
export const TURN_SAFE = { w: 0.79, h: 0.77, cx: 0.5, cy: 0.576 };

/**
 * Turntable image sets, smallest first; the same angles at two sizes. The viewer picks the smallest set that is
 * not enlarged by more than 10% on its canvas, so phones and ordinary desktop screens fetch the lighter set and
 * high-density desktop screens the full-size one.
 */
export const TURN_SETS = [
  { dir: 'spin-s', w: 960, h: 720 },
  { dir: 'spin', w: 1200, h: 900 },
] as const;
export type TurnSet = (typeof TURN_SETS)[number];
export const TURN_FULL: TurnSet = TURN_SETS[TURN_SETS.length - 1];
export const turnFrame = (finish: string, i: number, set: TurnSet = TURN_FULL) =>
  `/${set.dir}/${finish}/${String(i).padStart(2, '0')}.webp`;
/** The scale at which a turntable image (iw x ih) is drawn in a w x h canvas: its safe box fitted, centred. */
export const turnScale = (w: number, h: number, iw: number, ih: number) =>
  Math.min(w / (TURN_SAFE.w * iw), h / (TURN_SAFE.h * ih));
export function pickTurnSet(w: number, h: number): TurnSet {
  return TURN_SETS.find((s) => turnScale(w, h, s.w, s.h) <= 1.1) ?? TURN_FULL;
}

/** Fetches a file as a Blob; resolves null on any failure. */
export function fetchBlob(src: string, priority: 'high' | 'low' | 'auto' = 'auto'): Promise<Blob | null> {
  return fetch(src, { priority } as RequestInit)
    .then((r) => (r.ok ? r.blob() : null))
    .catch(() => null);
}

/** Releases a decoded frame's pixels (ImageBitmap); image elements are left to the browser. */
export function releaseFrame(img: Frame) {
  if ('close' in img) img.close();
}
/** Decoded size of a frame in bytes (4 bytes per pixel). */
export const frameBytes = (img: Frame) => {
  const [w, h] = frameSize(img);
  return w * h * 4;
};

/** Loads an image; resolves even on error so one missing frame never blocks the rest. */
export function loadImage(src: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const img = new Image();
    img.decoding = 'async';
    img.onload = () => (img.decode ? img.decode().then(() => resolve(img), () => resolve(img)) : resolve(img));
    img.onerror = () => resolve(null);
    img.src = src;
  });
}

/** A decoded frame (ImageBitmap) or a loaded image element. */
export type Frame = HTMLImageElement | ImageBitmap;
const frameSize = (img: Frame) =>
  img instanceof HTMLImageElement ? [img.naturalWidth, img.naturalHeight] : [img.width, img.height];

/** Draws an image to fill the canvas (like object-fit: cover), keeping focusX of the image in view. */
export function drawCover(ctx: CanvasRenderingContext2D, img: Frame, w: number, h: number, focusX = 0.5, alpha = 1) {
  const [iw, ih] = frameSize(img);
  const s = Math.max(w / iw, h / ih);
  const dw = iw * s;
  const dh = ih * s;
  const dx = Math.min(0, Math.max(w - dw, w / 2 - dw * focusX));
  const dy = (h - dh) / 2;
  ctx.globalAlpha = alpha;
  ctx.drawImage(img, dx, dy, dw, dh);
  ctx.globalAlpha = 1;
}

