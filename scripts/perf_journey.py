"""Journey smoothness while scrolling: how often the frames a position needs were not decoded in time (misses),
how far the drawn position moves per animation frame, and animation-frame pacing.

Usage: <python> scripts/perf_journey.py <url> <label>   -> qa/perf/journey-<label>.json
Desktop 1440x900 scrolls with the mouse wheel (smoothed by Lenis, as for a reader); phone size (390x844, DPR 2,
touch) scrolls continuously, like a finger. Each scenario runs after the journey's frames have loaded.
Headless Chromium on this computer: not a physical phone, and frame pacing here does not predict a phone's.
"""
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

URL, LABEL = sys.argv[1], sys.argv[2]
DESK = [int(v) for v in (sys.argv[3] if len(sys.argv) > 3 else "1440x900").split("x")]  # desktop viewport
OUT = pathlib.Path(__file__).resolve().parent.parent / "qa" / "perf" / f"journey-{LABEL}.json"

PROBE = """() => {
  const c = document.querySelector('.showcase__canvas');
  const s = window.__s = { xs: [], dt: [], t0: performance.now(), on: true };
  let last = performance.now();
  const tick = (t) => { if (!s.on) return; s.dt.push(t - last); last = t; s.xs.push(+c.dataset.x || 0); requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
  s.m0 = +c.dataset.misses || 0; s.d0 = +c.dataset.draws || 0;
}"""
STOP = """() => { const c = document.querySelector('.showcase__canvas'); const s = window.__s; s.on = false;
  const steps = s.xs.slice(1).map((x, i) => Math.abs(x - s.xs[i])).filter((d) => d > 0.001);
  steps.sort((a, b) => a - b);
  const q = (p) => steps.length ? +steps[Math.min(steps.length - 1, Math.floor(p * steps.length))].toFixed(3) : 0;
  const dt = s.dt.slice(5);
  return { draws: (+c.dataset.draws) - s.d0, misses: (+c.dataset.misses) - s.m0, moving: steps.length,
    step_median: q(0.5), step_p95: q(0.95), step_max: q(1), frames: dt.length,
    long_frames: dt.filter((d) => d > 25).length, budget: +c.dataset.budget, decoded: +c.dataset.decoded }; }"""

res = {}
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    for dev, kw in (("desktop", dict(viewport={"width": DESK[0], "height": DESK[1]})),
                    ("phone-size", dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True))):
        ctx = b.new_context(**kw)
        page = ctx.new_page()
        page.goto(URL)
        page.wait_for_function("document.querySelector('.showcase__canvas.is-ready')", timeout=20000)
        # Let every journey frame arrive (local server), so misses measure decoding, not the network.
        count, same = -1, 0
        while same < 4:
            page.wait_for_timeout(500)
            n = page.evaluate("performance.getEntriesByType('resource').filter(e => e.name.includes('/journey/')).length")
            same = same + 1 if n == count else 0
            count = n
        page.wait_for_timeout(1000)
        height = page.evaluate("document.querySelector('#design').offsetHeight - innerHeight")
        for speed in ("steady", "fast"):
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(1500)
            page.evaluate(PROBE)
            if dev == "desktop":
                notch, gap = (100, 70) if speed == "steady" else (200, 35)
                for _ in range(int(height / notch / 0.9) + 4):
                    page.mouse.wheel(0, notch)
                    page.wait_for_timeout(gap)
            else:
                px = 10 if speed == "steady" else 28  # per animation frame: about 600 and 1700 px/s
                page.evaluate(f"""() => new Promise((done) => {{ const end = {height};
                  const go = () => {{ if (scrollY >= end - 1) return done(); scrollBy(0, {px}); requestAnimationFrame(go); }}; go(); }})""")
            page.wait_for_timeout(1500)
            r = page.evaluate(STOP)
            res[f"{dev} {speed}"] = r
            print(f"{LABEL:8} {dev:10} {speed:6} misses {r['misses']:4}/{r['draws']:4} moving frames; position step per "
                  f"frame median {r['step_median']} p95 {r['step_p95']} max {r['step_max']}; long frames {r['long_frames']}/{r['frames']}; "
                  f"decoded {r['decoded']}/{r['budget']}", flush=True)
        ctx.close()
    b.close()
OUT.write_text(json.dumps(res, indent=1))
