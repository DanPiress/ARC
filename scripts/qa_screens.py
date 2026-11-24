"""Capture QA screenshots at desktop and phone sizes. Needs the dev or preview server.
Usage: <python> scripts/qa_screens.py [base_url] [tag]
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5173"
TAG = sys.argv[2] if len(sys.argv) > 2 else "v1"
OUT = pathlib.Path(__file__).resolve().parent.parent / "qa" / "screenshots" / TAG
OUT.mkdir(parents=True, exist_ok=True)

SIZES = {
    "desktop": dict(viewport={"width": 1440, "height": 900}),
    "phone": dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True),
}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    for name, opts in SIZES.items():
        ctx = browser.new_context(**opts)
        page = ctx.new_page()
        errors = []
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2800)
        vh = page.evaluate("innerHeight")
        for i in range(4):
            page.evaluate(f"window.scrollTo({{top: {i * vh}, behavior: 'instant'}})")
            page.wait_for_timeout(3200)
            page.screenshot(path=str(OUT / f"{name}-{i}-stage.png"))
        page.locator("#configure").scroll_into_view_if_needed()
        page.evaluate("document.querySelector('#configure').scrollIntoView({behavior: 'instant'})")
        page.wait_for_timeout(1200)
        page.screenshot(path=str(OUT / f"{name}-4-config.png"))
        # Each finish, captured as the viewer alone for close material comparison.
        for finish in ("graphite", "silver", "ember"):
            page.locator(f"label.swatch:has(input[value={finish}])").click()
            page.wait_for_timeout(1400)
            page.locator(".viewer").screenshot(path=str(OUT / f"{name}-finish-{finish}.png"))
            if finish == "silver":
                # Rotate the fixed-elevation turntable via its supported horizontal keys, then reset.
                viewer = page.locator(".viewer")
                viewer.focus()
                for key in ("ArrowRight",):
                    page.keyboard.press(key)
                page.wait_for_timeout(900)
                viewer.screenshot(path=str(OUT / f"{name}-silver-front.png"))
                for key in ["ArrowLeft"] * 4:
                    page.keyboard.press(key)
                page.wait_for_timeout(900)
                viewer.screenshot(path=str(OUT / f"{name}-silver-profile.png"))
                page.get_by_role("button", name="Reset view").click()
                page.wait_for_timeout(600)
        page.locator("label.swatch:has(input[value=graphite])").click()
        page.evaluate("document.querySelector('.footer').scrollIntoView({behavior: 'instant'})")
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / f"{name}-5-footer.png"))
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        print(f"{name}: horizontal overflow = {overflow}px; errors = {errors}")
        ctx.close()
    browser.close()
