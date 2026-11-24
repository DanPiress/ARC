"""Before/after turntable screenshots at normal website size, with a pixel comparison.
Captures the viewer at the front (frame 0), the side (24), the rear (48) and mid-way between frames 0 and 1
(a blended view, held mid-drag) on desktop (1440x900) and phone size (390x844 at DPR 2), for each URL.
Usage: <python> scripts/qa_visual_compare.py <before_url> <after_url>
Writes qa/screenshots/v9/compare-*.png and a side-by-side sheet.
"""
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

SHEET_ONLY = "--sheet-only" in sys.argv  # rebuild the sheet from existing screenshots
args = [a for a in sys.argv[1:] if not a.startswith("--")]
URLS = {"before": args[0], "after": args[1]} if len(args) > 1 else {}
OUT = pathlib.Path(__file__).resolve().parent.parent / "qa" / "screenshots" / "v9"
OUT.mkdir(parents=True, exist_ok=True)
DEVICES = {
    "desktop": dict(viewport={"width": 1440, "height": 900}),
    "phone": dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True),
}
shots = []
if SHEET_ONLY:
    for f in sorted(OUT.glob("compare-*-*-*-*.png")):
        dev, fin, name, label = f.stem.split("-")[1:5]
        shots.append((dev, fin, name, label, f))
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--allow-file-access-from-files"])
    for dev, kw in ({} if SHEET_ONLY else DEVICES).items():
        for label, url in URLS.items():
            ctx = b.new_context(reduced_motion="reduce", **kw)
            page = ctx.new_page()
            page.goto(url)
            page.evaluate("document.querySelector('#configure').scrollIntoView({ behavior: 'instant' })")
            page.wait_for_timeout(6000)
            viewer = page.locator(".viewer")
            for fin in ("graphite", "ember"):
                page.locator(f"label.swatch input[value={fin}]").evaluate("e => e.click()")
                page.wait_for_timeout(4000)
                viewer.focus()
                page.keyboard.press("Home")
                page.wait_for_timeout(500)
                for name, steps in (("front", 0), ("side", 4), ("rear", 8)):
                    page.keyboard.press("Home")
                    for _ in range(steps):
                        page.keyboard.press("ArrowRight")  # 6 frames each
                    page.wait_for_timeout(600)
                    path = OUT / f"compare-{dev}-{fin}-{name}-{label}.png"
                    viewer.screenshot(path=str(path))
                    shots.append((dev, fin, name, label, path))
                # Mid-blend between frames 0 and 1: hold a drag of half a frame (0.0327 rad at 0.009 rad/px).
                page.keyboard.press("Home")
                page.wait_for_timeout(400)
                box = viewer.bounding_box()
                cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                page.mouse.move(cx, cy)
                page.mouse.down()
                page.mouse.move(cx + 3.6, cy)
                page.wait_for_timeout(300)
                path = OUT / f"compare-{dev}-{fin}-blend-{label}.png"
                viewer.screenshot(path=str(path))
                shots.append((dev, fin, "blend", label, path))
                page.mouse.up()
                page.wait_for_timeout(500)
            ctx.close()

    # Pixel comparison and a sheet: before | after for each view.
    rows = {}
    for dev, fin, name, label, path in shots:
        rows.setdefault((dev, fin, name), {})[label] = path.as_uri()
    page = b.new_page(viewport={"width": 1700, "height": 900})
    sheet = OUT / "_sheet.html"  # a file page, so it may load the local screenshots
    sheet.write_text("<body style='margin:0;background:#04070d;color:#e9f0ff;font:14px system-ui'><div id=o></div></body>")
    page.goto(sheet.as_uri())
    metrics = page.evaluate("""async (rows) => {
      const out = {}; const o = document.getElementById('o');
      const load = (u) => new Promise((r) => { const i = new Image(); i.onload = () => r(i); i.src = u; });
      for (const [key, v] of rows) {
        const [a, b] = [await load(v.before), await load(v.after)];
        const w = Math.min(a.width, b.width), h = Math.min(a.height, b.height);
        const ca = new OffscreenCanvas(w, h), cb = new OffscreenCanvas(w, h);
        ca.getContext('2d').drawImage(a, 0, 0); cb.getContext('2d').drawImage(b, 0, 0);
        const da = ca.getContext('2d').getImageData(0, 0, w, h).data, db = cb.getContext('2d').getImageData(0, 0, w, h).data;
        let se = 0, ae = 0, n = 0;
        for (let i = 0; i < da.length; i += 4) for (let j = 0; j < 3; j++) { const e = da[i + j] - db[i + j]; se += e * e; ae += Math.abs(e); n++; }
        out[key] = { mae: +(ae / n).toFixed(2), psnr: +(10 * Math.log10(65025 / (se / n))).toFixed(1), size: [w, h] };
        const row = document.createElement('div'); row.style.cssText = 'display:flex;gap:10px;padding:8px;align-items:center';
        const t = document.createElement('div'); t.style.width = '150px'; t.textContent = key + '  PSNR ' + out[key].psnr + ' dB'; row.append(t);
        for (const img of [a, b]) { img.style.height = '260px'; row.append(img); }
        o.append(row);
      }
      return out;
    }""", [[" ".join(k), v] for k, v in rows.items() if "before" in v and "after" in v])
    page.screenshot(path=str(OUT / "compare-sheet.png"), full_page=True)
    b.close()
for k, v in metrics.items():
    print(f"{k:28} PSNR {v['psnr']:5.1f} dB  mean abs diff {v['mae']:.2f}  ({v['size'][0]}x{v['size'][1]})")
(OUT / "compare-metrics.json").write_text(json.dumps(metrics, indent=1))
print("sheet:", OUT / "compare-sheet.png")
