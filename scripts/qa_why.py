"""Checks for the "Why ARC" section and the footer, with screenshots.

Usage: <python> scripts/qa_why.py [url] [tag]
Desktop (1440x900), phone size (390x844, DPR 3, touch) and reduced motion, in headless Chromium on this computer
(not a physical phone). Screenshots go to qa/screenshots/<tag>/why-*.png and footer-*.png.
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4173"
TAG = sys.argv[2] if len(sys.argv) > 2 else "v11"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "qa" / "screenshots" / TAG
OUT.mkdir(parents=True, exist_ok=True)
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""), flush=True)


WHY_REQUESTS = "performance.getEntriesByType('resource').filter(e => e.name.includes('/why/')).map(e => e.name.split('/').pop())"
FOOTER = [("Why ARC", "why"), ("Design", "design"), ("Designed in layers", "layers"), ("Finishes", "configure"), ("Back to top", "top")]

CONFIGS = (
    ("desktop", dict(viewport={"width": 1440, "height": 900}), "setup-"),
    ("phone-size", dict(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True), "setup-p-"),
    ("reduced motion", dict(viewport={"width": 1440, "height": 900}, reduced_motion="reduce"), "setup-"),
)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for name, kw, prefix in CONFIGS:
        print(f"\n== {name}")
        ctx = browser.new_context(**kw)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(BASE)
        page.wait_for_timeout(1500)
        early = page.evaluate(WHY_REQUESTS)
        check(f"{name}: the setup image is not requested with the opening ({early})", not early)
        order = page.evaluate("[...document.querySelectorAll('main > section')].map(s => s.id)")
        check(f"{name}: section order ({order})", order == ["design", "why", "layers", "configure"])

        page.evaluate("document.getElementById('why').scrollIntoView({ behavior: 'instant' })")
        page.wait_for_function("(() => { const i = document.querySelector('.why__img'); return i && i.complete && i.naturalWidth > 0; })()", timeout=15000)
        page.wait_for_timeout(400)
        req = page.evaluate(WHY_REQUESTS)
        cur = page.evaluate("document.querySelector('.why__img').currentSrc.split('/').pop()")
        check(f"{name}: one size of the right crop loads ({req}, showing {cur})", len(req) == 1 and cur.startswith(prefix) and (prefix == "setup-p-" or not cur.startswith("setup-p-")))

        words = len(page.locator(".why__body").inner_text().split())
        check(f"{name}: the intention is about fifty words ({words})", 42 <= words <= 60)
        alt = page.locator(".why__img").get_attribute("alt") or ""
        check(f"{name}: the image has descriptive alt text", len(alt) > 40 and "ARC" in alt)
        c = page.locator(".why__copy").bounding_box()
        f = page.locator(".why__figure").bounding_box()
        if name == "phone-size":
            check(f"{name}: the image sits below the text", f["y"] >= c["y"] + c["height"] - 1)
        else:
            check(f"{name}: the image sits beside the text", f["x"] >= c["x"] + c["width"] - 1 and f["y"] < c["y"] + c["height"])
        overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        check(f"{name}: no horizontal overflow ({overflow} px)", overflow <= 0)
        page.locator("#why").screenshot(path=str(OUT / f"why-{name.replace(' ', '-')}.png"))

        # Footer: links, disclosure and credit.
        foot = page.locator(".footer")
        foot.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        labels = foot.locator("nav[aria-label=Footer] a").all_inner_texts()
        check(f"{name}: footer links ({labels})", labels == [l for l, _ in FOOTER])
        small = foot.locator("nav a").evaluate_all("as => as.filter(a => a.getBoundingClientRect().height < 44).length")
        check(f"{name}: footer link targets are at least 44 px tall", small == 0)
        text = page.locator(".footer__text").inner_text()
        check(f"{name}: disclosure names the concept and the demo cart", "fictional" in text and "demo" in text.lower())
        check(f"{name}: credit line present", "ForgeGUI" in page.locator(".footer__credit").inner_text())
        foot.screenshot(path=str(OUT / f"footer-{name.replace(' ', '-')}.png"))

        # Each footer link reaches its section (Back to top reaches the page top).
        for label, target in FOOTER:
            foot.scroll_into_view_if_needed()
            page.wait_for_timeout(200)
            link = foot.get_by_role("link", name=label, exact=True)
            if kw.get("has_touch"):
                link.tap()
            else:
                link.click()
            page.wait_for_timeout(2200)
            if target == "top":
                y = page.evaluate("scrollY")
                ok, detail = y < 4, f"scrollY {y:.0f}"
            else:
                top = page.evaluate(f"document.getElementById('{target}').getBoundingClientRect().top")
                ok, detail = abs(top) < 80, f"top {top:.0f}"
            check(f"{name}: footer '{label}' reaches #{target} ({detail})", ok)
        hash_ = page.evaluate("location.hash")
        check(f"{name}: the address shows the last link ({hash_})", hash_ in ("#top", ""))
        check(f"{name}: no console or page errors", not errors, "; ".join(errors[:3]))
        ctx.close()

    # /#why opens at the section; Back returns to the previous section.
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(BASE + "/#why")
    page.wait_for_timeout(1500)
    top = page.evaluate("document.getElementById('why').getBoundingClientRect().top")
    check(f"/#why opens at the section (top {top:.0f} px)", abs(top) <= 4)
    page.locator(".footer").scroll_into_view_if_needed()
    page.locator(".footer").get_by_role("link", name="Finishes").click()
    page.wait_for_timeout(2200)
    page.go_back()
    page.wait_for_timeout(1500)
    check(f"Back after a footer link returns the address to #why ({page.evaluate('location.hash')})", page.evaluate("location.hash") == "#why")
    ctx.close()

    # ?static shows the section too.
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(BASE + "/?static")
    page.evaluate("document.getElementById('why').scrollIntoView({ behavior: 'instant' })")
    page.wait_for_function("document.querySelector('.why__img').complete && document.querySelector('.why__img').naturalWidth > 0", timeout=10000)
    check("?static: Why ARC and its image render", True)
    ctx.close()
    browser.close()

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
