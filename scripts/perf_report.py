"""Loading, transfer, decoded-frame and process-memory report for the ARC site, under fixed conditions.

Usage: <python> scripts/perf_report.py [url] [label] [scenario ...]
  scenarios: desktop (1440x900, DPR 1, unthrottled)
             phone-slow (390x844, DPR 2, touch, throttled: 1.6 Mbps down, 0.75 Mbps up, 150 ms RTT, CPU 4x slower)
             phone-warm (390x844, DPR 2, touch, unthrottled)
Writes qa/perf/<label>.json. Every scenario starts a new browser, so the HTTP cache is cold.

All of this runs in headless Chromium on this Windows computer. A phone-sized viewport with throttling is an
emulation: it does not measure a physical phone's decoder, GPU, memory limits or radio.
"""
import json
import pathlib
import statistics
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4173"
LABEL = sys.argv[2] if len(sys.argv) > 2 else "run"
SCENARIOS = sys.argv[3:] or ["desktop", "phone-slow", "phone-warm"]
OUT = pathlib.Path(__file__).resolve().parent.parent / "qa" / "perf"
OUT.mkdir(parents=True, exist_ok=True)

PROFILES = {
    "desktop": dict(viewport={"width": 1440, "height": 900}, device_scale_factor=1, throttle=False),
    "phone-slow": dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, throttle=True),
    "phone-warm": dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, throttle=False),
}

INIT = """
performance.setResourceTimingBufferSize(5000);
window.__marks = {};
const seen = () => {
  if (!__marks.open && document.querySelector('.showcase__canvas.is-ready')) __marks.open = performance.now();
  if (__marks.cfg && !__marks.turn && document.querySelector('.viewer__canvas.is-ready')) __marks.turn = performance.now();
};
new MutationObserver(seen).observe(document, { subtree: true, attributes: true, attributeFilter: ['class'], childList: true });
"""

# Transfer (bytes on the wire, from Resource Timing) by kind, for responses that finished in [t0, t1].
RES = """([t0, t1]) => {
  const out = { journey: 0, spin: 0, other: 0, journeyFiles: 0, spinFiles: {}, total: 0 };
  for (const e of performance.getEntriesByType('resource')) {
    if (e.responseEnd < t0 || e.responseEnd > t1) continue;
    const b = e.transferSize || 0; out.total += b;
    const u = new URL(e.name).pathname;
    const m = u.match(/\\/spin[^/]*\\/(graphite|silver|ember)\\//);
    if (u.includes('/journey/')) { out.journey += b; out.journeyFiles++; }
    else if (m) { out.spin += b; out.spinFiles[m[1]] = (out.spinFiles[m[1]] || 0) + 1; }
    else out.other += b;
  }
  return out;
}"""

DISTINCT = """(kind) => {
  const s = new Set();
  for (const e of performance.getEntriesByType('resource')) {
    const u = new URL(e.name).pathname;
    if (kind === 'journey' ? u.includes('/journey/') : new RegExp('/spin[^/]*/' + kind + '/').test(u)) s.add(u);
  }
  return s.size;
}"""

LAST_END = """(kind) => Math.max(0, ...performance.getEntriesByType('resource')
  .filter(e => new URL(e.name).pathname.includes(kind)).map(e => e.responseEnd))"""

CHANGE = """async (fin) => {
  const c = document.querySelector('.viewer__canvas');
  const o = new OffscreenCanvas(24, 18); const x = o.getContext('2d', { willReadFrequently: true });
  const sig = () => { x.clearRect(0, 0, 24, 18); x.drawImage(c, 0, 0, 24, 18); return x.getImageData(0, 0, 24, 18).data; };
  const base = sig(); const t0 = performance.now();
  document.querySelector(`label.swatch input[value=${fin}]`).click();
  return await new Promise((res) => { const tick = () => {
    const d = sig(); let s = 0; for (let i = 0; i < d.length; i++) s += Math.abs(d[i] - base[i]);
    if (s / d.length > 2 && c.classList.contains('is-ready')) return res(performance.now() - t0);
    if (performance.now() - t0 > 20000) return res(null);
    requestAnimationFrame(tick); }; requestAnimationFrame(tick); });
}"""

PROBE = """() => {
  window.__d = [];
  const c = document.querySelector('.viewer__canvas');
  const o = document.createElement('canvas'); o.width = 96; o.height = 60;
  const x = o.getContext('2d', { willReadFrequently: true });
  let prev = null;
  const token = window.__probe = Math.random();
  const tick = () => {
    if (window.__probe !== token) return;
    x.clearRect(0, 0, 96, 60); x.drawImage(c, 0, 0, 96, 60);
    const d = x.getImageData(0, 0, 96, 60).data;
    if (prev) { let s = 0; for (let i = 0; i < d.length; i++) s += Math.abs(d[i] - prev[i]); window.__d.push(s / d.length); }
    prev = d.slice(); requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}"""

STATS = """() => {
  const c = document.querySelector('.viewer__canvas'); const j = document.querySelector('.showcase__canvas');
  return { turn: c ? { ...c.dataset } : null, journey: j ? { ...j.dataset } : null,
           turnCanvas: c ? [c.width, c.height] : null, journeyCanvas: j ? [j.width, j.height] : null };
}"""


def process_memory():
    """Private bytes and working set summed over the Playwright Chromium processes (Windows)."""
    cmd = ("$p = Get-Process | Where-Object { $_.Path -like '*ms-playwright*' }; "
           "'{0} {1} {2}' -f ($p | Measure-Object PrivateMemorySize64 -Sum).Sum, ($p | Measure-Object WorkingSet64 -Sum).Sum, $p.Count")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True).stdout.split()
    return {"private_mb": round(int(out[0]) / 1e6, 1), "working_set_mb": round(int(out[1]) / 1e6, 1), "processes": int(out[2])}


def wait_until(page, js, arg, ok, timeout_s):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        v = page.evaluate(js, arg)
        if ok(v):
            return True
        page.wait_for_timeout(100)
    return False


def drag_test(page, px, steps, gap):
    box = page.locator(".viewer").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.evaluate(PROBE)
    page.mouse.move(cx - px / 2, cy)
    page.mouse.down()
    for i in range(steps + 1):
        page.mouse.move(cx - px / 2 + i * px / steps, cy)
        page.wait_for_timeout(gap)
    page.mouse.up()
    page.wait_for_timeout(1300)
    d = page.evaluate("window.__probe = false, window.__d")
    moving = [v for v in d if v > 0.05]
    med = statistics.median(moving) if moving else 0
    return {"frames": len(d), "changing": len(moving), "median": round(med, 2), "max": round(max(d, default=0), 2),
            "spikes_over_4x_median": len([v for v in moving if v > 4 * med])}


def run(p, name):
    prof = dict(PROFILES[name])
    throttle = prof.pop("throttle")
    slow = 4 if throttle else 1
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(**prof)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script(INIT)
    cdp = context.new_cdp_session(page)
    cdp.send("Network.enable")
    cdp.send("Network.setCacheDisabled", {"cacheDisabled": False})
    if throttle:
        cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 150,
                                                      "downloadThroughput": 1_600_000 / 8, "uploadThroughput": 750_000 / 8})
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    r = {"scenario": name, "profile": {**prof, "throttled": throttle}}
    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_function("window.__marks && window.__marks.open", timeout=90000)
    t_open = page.evaluate("__marks.open")
    r["opening_visible_ms"] = round(t_open)
    r["transfer_before_opening"] = page.evaluate(RES, [0, t_open])
    r["opening_breakdown"] = page.evaluate("""() => {
      const n = performance.getEntriesByType('navigation')[0];
      const f = performance.getEntriesByType('resource').find(e => /journey\\/\\w+\\/000\\.webp/.test(e.name));
      const first = performance.getEntriesByType('resource').filter(e => /\\/(journey|spin)/.test(e.name))
        .sort((a, b) => a.startTime - b.startTime).slice(0, 4).map(e => [new URL(e.name).pathname, Math.round(e.startTime), Math.round(e.responseEnd)]);
      return { dom_content_loaded: Math.round(n.domContentLoadedEventEnd), frame0_start: f && Math.round(f.startTime),
               frame0_end: f && Math.round(f.responseEnd), first_media_requests: first };
    }""")

    # Stay at the top until the journey has fully arrived.
    frames = page.evaluate("+(document.querySelector('.showcase__canvas')?.dataset.frames) || 193")
    done = wait_until(page, DISTINCT, "journey", lambda n: n >= frames, 40 * slow)
    t_j = page.evaluate(LAST_END, "/journey/")
    r["journey_complete_ms"] = round(t_j) if done else None
    r["transfer_at_top"] = page.evaluate(RES, [0, page.evaluate("performance.now()")])
    r["memory_at_top"] = process_memory()
    r["journey_stats"] = page.evaluate(STATS)["journey"]

    # Jump to the configurator.
    t_cfg = page.evaluate("(document.querySelector('#configure').scrollIntoView({ behavior: 'instant' }), __marks.cfg = performance.now())")
    page.wait_for_function("window.__marks.turn", timeout=60000 * slow)
    r["turntable_usable_ms_after_jump"] = round(page.evaluate("__marks.turn") - t_cfg)
    full = wait_until(page, DISTINCT, "graphite", lambda n: n >= 96, 45 * slow)
    r["selected_finish_complete_ms_after_jump"] = round(page.evaluate(LAST_END, "/graphite/") - t_cfg) if full else None
    wait_until(page, DISTINCT, "silver", lambda n: n >= 24, 20 * slow)
    wait_until(page, DISTINCT, "ember", lambda n: n >= 24, 20 * slow)
    page.wait_for_timeout(1500)
    now = page.evaluate("performance.now()")
    r["transfer_configurator_initial"] = page.evaluate(RES, [t_cfg, now])
    r["memory_configurator_initial"] = process_memory()
    r["turn_stats_initial"] = page.evaluate(STATS)

    # Finish changes.
    changes = {}
    for fin in ("silver", "ember", "graphite"):
        t0 = page.evaluate("performance.now()")
        ms = page.evaluate(CHANGE, fin)
        wait_until(page, DISTINCT, fin, lambda n: n >= 96, 45 * slow)
        page.wait_for_timeout(800)
        changes[fin] = {"shown_ms": round(ms) if ms is not None else None,
                        "transfer": page.evaluate(RES, [t0, page.evaluate("performance.now()")])}
    r["finish_changes"] = changes

    # Fully warmed: a full keyboard turn on every finish, then drags.
    viewer = page.locator(".viewer")
    for fin in ("silver", "ember", "graphite"):
        page.locator(f"label.swatch input[value={fin}]").evaluate("e => e.click()")
        page.wait_for_timeout(400)
        viewer.focus()
        for _ in range(16):
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(120 * slow)
        page.wait_for_timeout(700)
    page.wait_for_timeout(1500)
    r["memory_all_finishes_viewed"] = process_memory()
    r["turn_stats_warm"] = page.evaluate(STATS)
    r["transfer_total"] = page.evaluate(RES, [0, page.evaluate("performance.now()")])
    if not prof.get("has_touch"):
        r["drag_slow"] = drag_test(page, 400, 200, 16)
        r["drag_fast"] = drag_test(page, 700, 20, 16)  # about 96 frames (a full turn) in a third of a second
    r["errors"] = errors
    context.close()
    browser.close()
    return r


results = {"url": BASE, "label": LABEL, "browser": "Playwright headless Chromium on Windows 10 (this computer)", "runs": []}
with sync_playwright() as p:
    for name in SCENARIOS:
        print("running", name, flush=True)
        res = run(p, name)
        results["runs"].append(res)
        print(json.dumps(res, indent=1), flush=True)
path = OUT / f"{LABEL}.json"
# Re-running some scenarios replaces just those in an existing report.
if path.exists():
    old = json.loads(path.read_text())
    ran = {r["scenario"] for r in results["runs"]}
    results["runs"] = [r for r in old["runs"] if r["scenario"] not in ran] + results["runs"]
path.write_text(json.dumps(results, indent=1))
print("wrote", path)
