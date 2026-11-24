"""Decoded-frame budget, release and loading-failure checks for the journey and the turntable.

Usage: <python> scripts/qa_cache.py [url]
Run against the dev server (http://localhost:5173) as well, to include React StrictMode's effect replay.
The page publishes its cache size on each canvas (data-decoded, data-budget, data-decoded-by, data-drawn); these
checks read them while the page is driven hard. Headless Chromium on this computer; not a physical phone.
"""
import re
import sys
import time

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4173"
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""), flush=True)


# Samples the cache on every animation frame and keeps the worst case.
WATCH = """() => {
  window.__worst = { turn: 0, journey: 0, turnBudget: 0, journeyBudget: 0 };
  const tick = () => {
    const t = document.querySelector('.viewer__canvas'), j = document.querySelector('.showcase__canvas');
    const w = window.__worst;
    if (t && t.dataset.decoded) { w.turn = Math.max(w.turn, +t.dataset.decoded); w.turnBudget = +t.dataset.budget; }
    if (j && j.dataset.decoded) { w.journey = Math.max(w.journey, +j.dataset.decoded); w.journeyBudget = +j.dataset.budget; }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}"""
NONBLANK = """(sel) => { const c = document.querySelector(sel); const o = new OffscreenCanvas(32, 32); const x = o.getContext('2d');
  x.drawImage(c, 0, 0, 32, 32); const d = x.getImageData(0, 0, 32, 32).data; let s = 0, a = 0;
  for (let i = 0; i < d.length; i += 4) { s += d[i] + d[i + 1] + d[i + 2]; a += d[i + 3]; } return { light: s / 1024 / 3, alpha: a / 1024 }; }"""


def ds(page, sel):
    return page.locator(sel).evaluate("c => ({ ...c.dataset })")


def by_finish(d):
    return {k: int(v) for k, v in (p.split(":") for p in d.get("decodedBy", "").split(",") if p)}


def turn_drawn(page):
    return ds(page, ".viewer__canvas").get("drawn", "")


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for name, kw in (("desktop", dict(viewport={"width": 1440, "height": 900})),
                     ("phone-size", dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True))):
        print(f"\n== {name}")
        ctx = browser.new_context(**kw)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE)
        page.wait_for_function("document.querySelector('.showcase__canvas.is-ready')", timeout=20000)
        page.evaluate(WATCH)

        # Journey: scroll through it quickly and slowly; the decoded set must stay within budget.
        height = page.evaluate("document.querySelector('#design').offsetHeight")
        for y in range(0, height, 140):
            page.mouse.wheel(0, 140)
            page.wait_for_timeout(16)
        page.wait_for_timeout(1500)
        for y in range(0, height, 900):
            page.evaluate(f"window.scrollTo(0, {y})")
            page.wait_for_timeout(60)
        w = page.evaluate("window.__worst")
        check(f"{name}: journey decoded frames never exceed budget ({w['journey']} <= {w['journeyBudget']})",
              0 < w["journey"] <= w["journeyBudget"])

        # Configurator: the journey releases its frames off screen.
        page.evaluate("document.querySelector('#configure').scrollIntoView({ behavior: 'instant' })")
        page.wait_for_function("document.querySelector('.viewer__canvas.is-ready')", timeout=20000)
        page.wait_for_timeout(3000)
        j = ds(page, ".showcase__canvas")
        check(f"{name}: journey keeps at most 3 decoded frames while off screen ({j.get('decoded')})", int(j["decoded"]) <= 3)
        t = ds(page, ".viewer__canvas")
        budget = int(t["budget"])
        check(f"{name}: turntable uses the lighter image set on this screen ({t.get('set')})", t.get("set") == "spin-s")

        # Turntable: fast spins, flicks and keyboard turns stay within budget and keep drawing.
        viewer = page.locator(".viewer")
        box = viewer.bounding_box()
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.evaluate(WATCH)
        if name == "desktop":
            for direction in (1, -1, 1):
                page.mouse.move(cx - direction * 300, cy)
                page.mouse.down()
                for i in range(15):
                    page.mouse.move(cx - direction * 300 + direction * i * 40, cy)
                    page.wait_for_timeout(16)
                page.mouse.up()
                page.wait_for_timeout(1100)
        viewer.focus()
        for _ in range(9):
            page.keyboard.press("ArrowLeft")  # through zero into negative angles (wrapping)
            page.wait_for_timeout(90)
        page.wait_for_timeout(1200)
        drawn = turn_drawn(page)
        check(f"{name}: wrapped negative angle draws a real frame ({drawn})", re.fullmatch(r"graphite:\d+", drawn or "") is not None)
        page.keyboard.press("Home")
        page.wait_for_timeout(1000)
        check(f"{name}: reset draws frame 0 ({turn_drawn(page)})", turn_drawn(page) == "graphite:0")
        w = page.evaluate("window.__worst")
        check(f"{name}: turntable decoded frames never exceed budget during turns ({w['turn']} <= {budget})", 0 < w["turn"] <= budget)

        # Finish switches release the previous finish's frames (apart from one at the current angle).
        for fin in ("silver", "ember", "graphite", "silver"):
            page.locator(f"label.swatch input[value={fin}]").evaluate("e => e.click()")
            page.wait_for_timeout(700)
        page.wait_for_timeout(2500)
        t = ds(page, ".viewer__canvas")
        counts = by_finish(t)
        check(f"{name}: after switching, other finishes keep at most one decoded frame ({counts})",
              all(n <= 1 for f, n in counts.items() if f != "silver") and counts.get("silver", 0) > 1)
        check(f"{name}: the canvas shows the selected finish ({t.get('drawn')})", t.get("drawn", "").startswith("silver:"))
        w = page.evaluate("window.__worst")
        check(f"{name}: budget held through finish switches ({w['turn']} <= {budget})", w["turn"] <= budget)
        dec_bytes = int(t["decodedBytes"])
        print(f"   turntable decoded: {t['decoded']} frames, {dec_bytes / 1e6:.1f} MB; compressed kept: {int(t['compressedBytes']) / 1e6:.1f} MB")

        # Resize: new decoded copies at the new size; the view stays drawn and within budget.
        before = page.locator(".viewer__canvas").evaluate("c => [c.width, c.height]")
        page.set_viewport_size({"width": kw["viewport"]["width"] - 120, "height": kw["viewport"]["height"]})
        page.wait_for_timeout(250)
        mid = page.evaluate(NONBLANK, ".viewer__canvas")
        page.wait_for_timeout(1500)
        after = page.locator(".viewer__canvas").evaluate("c => [c.width, c.height]")
        t = ds(page, ".viewer__canvas")
        check(f"{name}: resize keeps the turntable drawn ({before} -> {after})", after != before and mid["alpha"] > 20 and t.get("drawn", "").startswith("silver:"))
        check(f"{name}: budget held after resize ({t['decoded']} <= {budget})", int(t["decoded"]) <= budget)
        page.set_viewport_size(kw["viewport"])

        # Back to the journey: it decodes around the current position again.
        page.evaluate("document.querySelector('#stage-2').scrollIntoView({ behavior: 'instant' })")
        page.wait_for_timeout(1500)
        j = ds(page, ".showcase__canvas")
        check(f"{name}: journey re-decodes when back on screen ({j.get('decoded')})", int(j["decoded"]) > 3)
        check(f"{name}: no page errors", not errors, "; ".join(errors))
        ctx.close()

    # Deep links: a URL ending in #configure or #stage-2 opens at that section; a reload keeps its own position.
    print("\n== deep links")
    for name, kw in (("desktop", dict(viewport={"width": 1440, "height": 900})),
                     ("phone-size", dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)),
                     ("reduced motion", dict(viewport={"width": 1440, "height": 900}, reduced_motion="reduce"))):
        ctx = browser.new_context(**kw)
        page = ctx.new_page()
        for anchor in ("configure", "stage-2"):
            page.goto(f"{BASE}/#{anchor}")
            page.wait_for_timeout(1500)
            top = page.evaluate(f"document.getElementById('{anchor}').getBoundingClientRect().top")
            check(f"{name}: /#{anchor} opens at that section (its top at {top:.0f} px)", abs(top) <= 4)
        page.goto(f"{BASE}/#configure")
        page.wait_for_function("document.querySelector('.viewer__canvas.is-ready')", timeout=20000)
        check(f"{name}: the turntable loads after opening at #configure", True)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(600)
        page.reload()
        page.wait_for_timeout(1500)
        y = page.evaluate("scrollY")
        check(f"{name}: a reload keeps the browser's restored position, not the anchor (scrollY {y:.0f})", y < 50)
        ctx.close()

    # Opening-frame failure: the journey shows its neighbouring frame instead of staying hidden.
    print("\n== failures")
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.route(re.compile(r".*/journey/desktop(-s)?/000\.webp$"), lambda route: route.abort())
    t0 = time.monotonic()
    page.goto(BASE)
    try:
        page.wait_for_function("document.querySelector('.showcase__canvas.is-ready')", timeout=10000)
        ok = True
    except Exception:
        ok = False
    check(f"Opening frame blocked: the journey still appears ({time.monotonic() - t0:.1f} s)", ok)
    page.wait_for_timeout(400)
    px = page.evaluate(NONBLANK, ".showcase__canvas")
    check(f"Opening frame blocked: the canvas shows a real image (mean level {px['light']:.0f})", px["light"] > 8)
    ctx.close()

    # Selected turntable's first frame blocked, everything else delayed: the viewer still becomes usable.
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()

    def turn_route(route):
        if re.search(r"/graphite/00\.webp$", route.request.url):
            return route.abort()
        time.sleep(0.03)
        route.continue_()

    page.route(re.compile(r".*/spin(-s)?/.*\.webp$"), turn_route)
    page.goto(BASE)
    page.evaluate("document.querySelector('#configure').scrollIntoView({ behavior: 'instant' })")
    try:
        page.wait_for_function("document.querySelector('.viewer__canvas.is-ready')", timeout=15000)
        ok = True
    except Exception:
        ok = False
    check("Turntable first frame blocked: the viewer shows the nearest angle", ok and turn_drawn(page).startswith("graphite:"), turn_drawn(page) if ok else "")
    # Rapid switching while files are still arriving must not throw or leave the canvas on another finish.
    for fin in ("silver", "ember", "graphite", "ember"):
        page.locator(f"label.swatch input[value={fin}]").evaluate("e => e.click()")
        page.wait_for_timeout(120)
    page.wait_for_timeout(4000)
    check("Slow loading + rapid switches: the canvas shows the selected finish", turn_drawn(page).startswith("ember:"), turn_drawn(page))
    ctx.close()
    browser.close()

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
