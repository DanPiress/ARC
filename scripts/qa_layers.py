"""Checks for the "Designed in layers" section and the simplified footer, with screenshots.

Usage: <python> scripts/qa_layers.py [url] [tag]
Desktop (1440x900), phone size (390x844 at DPR 2, touch) and reduced motion, in headless Chromium on this
computer (not a physical phone). Screenshots go to qa/screenshots/<tag>/layers-*.png.
"""
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4173"
TAG = sys.argv[2] if len(sys.argv) > 2 else "v10"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "qa" / "screenshots" / TAG
OUT.mkdir(parents=True, exist_ok=True)
ANCHORS = json.loads((ROOT / "src" / "data" / "layersAnchors.json").read_text())
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""), flush=True)


LAYERS_REQUESTS = "performance.getEntriesByType('resource').filter(e => e.name.includes('/layers/')).map(e => e.name.split('/').pop())"

CONFIGS = (
    ("desktop", dict(viewport={"width": 1440, "height": 900})),
    ("phone-size", dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)),
    ("reduced motion", dict(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")),
    ("tablet", dict(viewport={"width": 900, "height": 1100}, has_touch=True)),
)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for name, kw in CONFIGS:
        print(f"\n== {name}")
        ctx = browser.new_context(**kw)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(BASE)
        page.wait_for_timeout(1500)
        early = page.evaluate(LAYERS_REQUESTS)
        check(f"{name}: the layers render is not requested with the opening ({early})", not early)

        # The section sits between the journey and the configurator.
        order = page.evaluate("[...document.querySelectorAll('main > section')].map(s => s.id)")
        check(f"{name}: section order journey, why, layers, configurator ({order})", order == ["design", "why", "layers", "configure"])

        page.evaluate("document.getElementById('layers').scrollIntoView({ behavior: 'instant' })")
        page.wait_for_function("(() => { const i = document.querySelector('.layers__img'); return i && i.complete && i.naturalWidth > 0; })()", timeout=15000)
        page.wait_for_timeout(500)
        req = page.evaluate(LAYERS_REQUESTS)
        nat = page.evaluate("document.querySelector('.layers__img').currentSrc.split('/').pop()")
        check(f"{name}: the render loads near the section, one size only ({req}, showing {nat})", len(req) == 1)

        tabs = page.locator(".layers [role=tab]")
        check(f"{name}: three callouts, exposed as tabs", tabs.count() == 3)
        img = page.locator(".layers__img").bounding_box()
        fig = page.locator(".layers__figure").bounding_box()
        vw = page.evaluate("innerWidth")
        worst, small, outside = 0.0, [], []
        for i, key in enumerate(("spine", "shell", "grips")):
            t = tabs.nth(i)
            b = t.bounding_box()
            dot = t.locator(".callout__dot").bounding_box()
            cx, cy = dot["x"] + dot["width"] / 2, dot["y"] + dot["height"] / 2
            ax, ay = img["x"] + ANCHORS[key][0] * img["width"], img["y"] + ANCHORS[key][1] * img["height"]
            worst = max(worst, abs(cx - ax), abs(cy - ay))
            if b["height"] < 44 or b["width"] < 44:
                small.append(key)
            left, right = max(0, fig["x"]), min(vw, fig["x"] + fig["width"])
            if b["x"] < left - 0.5 or b["x"] + b["width"] > right + 0.5:
                outside.append(key)
        check(f"{name}: each callout's dot sits on its part's anchor (worst {worst:.1f} px)", worst <= 1.5)
        check(f"{name}: callout targets are at least 44 px ({small or 'all'})", not small)
        check(f"{name}: callouts stay inside the visible image ({outside or 'all'})", not outside)

        # Pointer or touch selection.
        titles = []
        for i in range(3):
            if kw.get("has_touch"):
                tabs.nth(i).tap()
            else:
                tabs.nth(i).click()
            page.wait_for_timeout(120)
            titles.append(page.locator(".layers__name").inner_text())
            sel = page.evaluate("[...document.querySelectorAll('.layers [role=tab]')].map(t => t.getAttribute('aria-selected'))")
            if sel.count("true") != 1 or sel[i] != "true":
                titles.append("bad selection " + str(sel))
        check(f"{name}: selecting each callout shows its notes ({titles})", titles == ["Centre spine", "Shell", "Grips"])
        lab = page.evaluate("(() => { const p = document.getElementById('layer-panel'); return document.getElementById(p.getAttribute('aria-labelledby'))?.textContent; })()")
        check(f"{name}: the panel is labelled by the selected callout ({lab})", lab == "Grips")

        # Keyboard: arrows move between callouts and focus follows.
        tabs.nth(2).focus()
        page.keyboard.press("ArrowRight")
        k1 = page.evaluate("[document.activeElement.textContent, document.querySelector('.layers__name').textContent]")
        page.keyboard.press("End")
        k2 = page.evaluate("document.activeElement.textContent")
        page.keyboard.press("ArrowLeft")
        k3 = page.evaluate("document.querySelector('.layers__name').textContent")
        tabbable = page.evaluate("[...document.querySelectorAll('.layers [role=tab]')].filter(t => t.tabIndex === 0).length")
        check(f"{name}: arrow keys, Home and End move between callouts ({k1}, {k2}, {k3})",
              k1 == ["Spine", "Centre spine"] and k2 == "Grips" and k3 == "Shell" and tabbable == 1)

        overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        check(f"{name}: no horizontal overflow ({overflow} px)", overflow <= 0)
        anim = page.evaluate("getComputedStyle(document.querySelector('.layers__copy')).animationName")
        if name == "reduced motion":
            check(f"{name}: the panel change does not animate ({anim})", anim == "none")
        # Contrast of the body text on the studio background (WCAG AA 4.5:1).
        ratio = page.evaluate("""(() => {
          const lum = (c) => { const v = c.match(/\\d+/g).slice(0, 3).map(Number).map(x => x / 255).map(x => x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4); return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
          const fg = lum(getComputedStyle(document.querySelector('.layers__body')).color);
          const bg = lum('rgb(227, 232, 239)');
          return (Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05);
        })()""")
        check(f"{name}: body text contrast {ratio:.1f}:1", ratio >= 4.5)

        page.locator(".layers [role=tab]").nth(1).click()
        page.wait_for_timeout(500)
        page.locator("#layers").screenshot(path=str(OUT / f"layers-{name.replace(' ', '-')}.png"))

        # Footer: a short fictional-concept and demo-cart disclosure.
        foot = page.locator(".footer__text").inner_text()
        check(f"{name}: footer is a short disclosure ({len(foot)} chars)",
              "fictional" in foot and "demo" in foot.lower() and "Blender" not in foot and len(foot) < 260)
        if name == "desktop":
            page.locator(".footer").screenshot(path=str(OUT / "footer-desktop.png"))

        # The configurator and cart still work after the new section.
        page.evaluate("document.getElementById('configure').scrollIntoView({ behavior: 'instant' })")
        page.locator("label.swatch input[value=ember]").evaluate("e => e.click()")
        page.locator(".buy .btn--primary").first.click()
        page.wait_for_timeout(400)
        count = page.locator(".nav__count").inner_text()
        check(f"{name}: finish change and add to cart still work (cart {count})", count == "1")
        check(f"{name}: no console or page errors", not errors, "; ".join(errors[:3]))
        ctx.close()

    # The nav's Layers link glides to the section; a /#layers link opens at it.
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(BASE)
    page.wait_for_timeout(800)
    page.get_by_role("navigation", name="Main").first.get_by_role("link", name="Layers").click()
    page.wait_for_timeout(2500)
    top = page.evaluate("document.getElementById('layers').getBoundingClientRect().top")
    check(f"Nav Layers link reaches the section (top {top:.0f} px)", abs(top) < 80)
    page.goto(BASE + "/#layers")
    page.wait_for_timeout(1500)
    top = page.evaluate("document.getElementById('layers').getBoundingClientRect().top")
    check(f"/#layers opens at the section (top {top:.0f} px)", abs(top) <= 4)
    ctx.close()

    # ?static fallback shows the section too.
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(BASE + "/?static")
    page.evaluate("document.getElementById('layers').scrollIntoView({ behavior: 'instant' })")
    try:
        page.wait_for_function("document.querySelector('.layers__img.is-loaded')", timeout=10000)
    except Exception:
        pass
    ok = page.evaluate("document.querySelector('.layers__img').naturalWidth > 0 && document.querySelectorAll('.layers [role=tab]').length === 3")
    check("?static: the layers section and its callouts work", ok)
    ctx.close()
    browser.close()

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
