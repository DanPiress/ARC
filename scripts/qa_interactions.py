"""Functional checks for the ARC site. Needs the dev or preview server.
Usage: <python> scripts/qa_interactions.py [base_url]
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright, expect

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5173"
OUT = pathlib.Path(__file__).resolve().parent.parent / "qa" / "screenshots" / "interactions"
OUT.mkdir(parents=True, exist_ok=True)
ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  ({detail})" if detail else ""))


def viewer_shot(page):
    return page.locator(".viewer").screenshot()


def settles(locator_expect, timeout=8000):
    """True once a Playwright expectation holds. Waits on the condition rather than a fixed delay:
    under software WebGL a single frame can take more than a second."""
    try:
        locator_expect(timeout)
        return True
    except AssertionError:
        return False


def reaches_top(page, selector, tolerance, timeout=10000):
    try:
        page.wait_for_function(
            f"Math.abs(document.querySelector('{selector}').getBoundingClientRect().top) < {tolerance}", timeout=timeout
        )
        page.wait_for_timeout(400)
    except Exception:
        pass
    return page.evaluate(f"document.querySelector('{selector}').getBoundingClientRect().top")


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=ARGS)

    # ---------- Desktop: opening, chapters, configurator, rotation, cart ----------
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE)
    page.wait_for_load_state("networkidle")
    page.evaluate("localStorage.clear()")
    page.reload()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)

    check("Opening heading visible", page.get_by_role("heading", level=1).is_visible())
    check("Concept status stated in the opening", page.get_by_text("An original controller concept.").is_visible())
    check("Journey canvas showing the first frame", page.locator(".showcase__canvas.is-ready").count() == 1)
    check("Three chapters present", page.locator("article.chapter").count() == 3)

    # Explore ARC scrolls to chapter 1
    page.get_by_role("link", name="Explore ARC").click()
    top = reaches_top(page, "#stage-1", 60, timeout=20000)
    check("Explore ARC reaches chapter 1", abs(top) < 60, f"top={top:.0f}")

    # Rail jumps to chapter 3
    page.get_by_role("button", name="Shoulders").click()
    # Smooth scrolling advances per rendered frame; under software WebGL that can take several seconds.
    top3 = reaches_top(page, "#stage-3", 60, timeout=20000)
    check("Rail button reaches chapter 3", abs(top3) < 60, f"top={top3:.0f}")
    check("Rail marks active step", page.locator(".rail__item.is-active").inner_text().strip() == "Shoulders")

    # Nav link to the finishes configurator
    page.get_by_role("navigation", name="Main").first.get_by_role("link", name="Finishes").click()
    try:
        page.wait_for_function("Math.abs(document.querySelector('#configure').getBoundingClientRect().top) < 80", timeout=6000)
    except Exception:
        pass
    ctop = page.evaluate("document.querySelector('#configure').getBoundingClientRect().top")
    check("URL hash updated", page.url.endswith("#configure"))
    check("Nav Finishes link reaches configurator", abs(ctop) < 80, f"top={ctop:.0f}")
    page.wait_for_timeout(1000)

    # Colour selection (pointer)
    before = viewer_shot(page)
    page.locator("label.swatch:has(input[value=silver])").click()
    page.wait_for_timeout(1400)
    after = viewer_shot(page)
    check("Silver radio checked", page.locator("input[value=silver]").is_checked())
    check("Silver card shows selected state", "is-selected" in page.locator("label.swatch:has(input[value=silver])").get_attribute("class"))
    check("Add button names selection", page.get_by_role("button", name="Add Silver to demo cart").is_visible())
    check("Selected finish named in legend", page.locator(".swatches__current").inner_text() == "Silver")
    check("3D view changes with colour", before != after)
    page.screenshot(path=str(OUT / "desktop-silver.png"))

    # Colour selection (keyboard)
    page.locator("input[value=silver]").focus()
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(1000)
    check("Arrow key selects Ember", page.locator("input[value=ember]").is_checked())
    page.screenshot(path=str(OUT / "desktop-ember-keyboard-focus.png"))

    # Rotation by pointer drag
    reset = page.get_by_role("button", name="Reset view")
    check("Reset disabled at default view", reset.is_disabled())
    box = page.locator(".viewer").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    s0 = viewer_shot(page)
    page.mouse.move(cx, cy)
    page.mouse.down()
    for i in range(1, 11):
        page.mouse.move(cx + i * 18, cy + i * 3)
        page.wait_for_timeout(30)
    page.mouse.up()
    page.wait_for_timeout(1300)
    s1 = viewer_shot(page)
    check("Drag rotates the product", s0 != s1)
    check("Reset enabled after drag", reset.is_enabled())
    page.screenshot(path=str(OUT / "desktop-rotated.png"))
    reset.click()
    check("Reset view returns to default", settles(lambda t: expect(reset).to_be_disabled(timeout=t)))

    # Rotation by keyboard
    page.locator(".viewer").focus()
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    check("Arrow keys rotate the viewer", settles(lambda t: expect(reset).to_be_enabled(timeout=t)))
    page.keyboard.press("Home")
    check("Home key resets the view", settles(lambda t: expect(reset).to_be_disabled(timeout=t)))
    # Quick presses must add up: Right, Right, Left, Left in one burst returns exactly to the start
    # (if each press restarted from the half-finished angle, it would end one step to the left).
    page.locator(".viewer").evaluate(
        "v => ['ArrowRight','ArrowRight','ArrowLeft','ArrowLeft'].forEach(key => v.dispatchEvent(new KeyboardEvent('keydown', {key, bubbles: true})))"
    )
    # Long enough for several software-rendered frames and the whole 0.6 s turn, so a wrong end angle shows.
    page.wait_for_timeout(4500)
    check("Rapid arrow presses accumulate", reset.is_disabled())
    page.get_by_role("button", name="Rotate left").click()
    check("Rotate left button works", settles(lambda t: expect(reset).to_be_enabled(timeout=t)))
    reset.click()
    settles(lambda t: expect(reset).to_be_disabled(timeout=t))

    # Cart: add items
    page.locator("label.swatch:has(input[value=graphite])").click()
    add = page.get_by_role("button", name="Add Graphite to demo cart")
    add.click()
    add.click()
    check("Status message after add", "Added ARC Graphite" in page.locator(".buy__status").inner_text())
    page.locator("label.swatch:has(input[value=ember])").click()
    page.get_by_role("button", name="Add Ember to demo cart").click()
    check("Nav count = 3", page.locator(".nav__count").inner_text() == "3")

    page.locator(".nav__cart").click()
    page.wait_for_timeout(700)
    dialog = page.get_by_role("dialog", name="Demo cart")
    check("Cart dialog opens", dialog.is_visible())
    check("Close button focused on open", settles(lambda t: expect(page.get_by_role("button", name="Close demo cart")).to_be_focused(timeout=t)))
    check("Two cart lines", page.locator(".line").count() == 2)
    thumbs = page.locator(".line__thumb").evaluate_all("els => els.map(e => e.getAttribute('src'))")
    check("Cart thumbnails match the finishes", thumbs == ["/renders/thumb-graphite.png", "/renders/thumb-ember.png"], str(thumbs))
    check("Total $567.00", "$567.00" in page.locator(".cart__total").inner_text())
    check("Demo status notice shown", "nothing is charged" in page.locator(".cart__notice").inner_text())
    page.screenshot(path=str(OUT / "desktop-cart.png"))

    page.get_by_role("button", name="Increase Ember quantity").click()
    check("Increase quantity", page.locator(".line", has_text="Ember").locator("output").inner_text() == "2")
    check("Total updates to $756.00", "$756.00" in page.locator(".cart__total").inner_text())
    page.get_by_role("button", name="Decrease Graphite quantity").click()
    check("Decrease quantity", page.locator(".line", has_text="Graphite").locator("output").inner_text() == "1")
    check("Total updates to $567.00", "$567.00" in page.locator(".cart__total").inner_text())

    # Persistence
    page.reload()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)
    check("Cart count persists after reload", page.locator(".nav__count").inner_text() == "3")
    page.locator(".nav__cart").click()
    page.wait_for_timeout(600)
    check("Cart lines persist after reload", page.locator(".line").count() == 2)

    # Removal and empty state
    page.get_by_role("button", name="Remove Graphite from cart").click()
    check("Remove line", page.locator(".line").count() == 1)
    page.get_by_role("button", name="Decrease Ember quantity").click()
    page.get_by_role("button", name="Decrease Ember quantity").click()
    check("Decreasing to zero removes the line", page.locator(".line").count() == 0)
    page.wait_for_timeout(300)
    check("Empty state shown", page.get_by_text("Your demo cart is empty").is_visible())
    page.screenshot(path=str(OUT / "desktop-cart-empty.png"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(600)
    check("Escape closes cart", not page.locator(".cart").evaluate("e => e.classList.contains('is-open')"))
    check("Focus returns to cart button", page.evaluate("document.activeElement.classList.contains('nav__cart')"))
    page.reload()
    page.wait_for_load_state("networkidle")
    check("Empty cart persists after reload", page.locator(".nav__count").inner_text() == "0")

    # Keyboard focus visibility
    page.evaluate("window.scrollTo(0,0)")
    page.keyboard.press("Tab")
    check("First Tab reaches skip link", page.evaluate("document.activeElement.className") == "skip")
    page.keyboard.press("Tab")
    page.keyboard.press("Tab")
    page.screenshot(path=str(OUT / "desktop-focus-nav.png"))

    check("No console errors (desktop)", not errors, "; ".join(errors[:3]))
    ctx.close()

    # ---------- Phone: first screen, touch rotation, menu ----------
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.goto(BASE)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2500)

    cta = page.get_by_role("link", name="Explore ARC").bounding_box()
    check("Phone: opening action inside the first screen", cta is not None and cta["y"] + cta["height"] < 844, str(cta))

    page.get_by_role("button", name="Open menu").tap()
    page.wait_for_timeout(300)
    check("Mobile menu opens", page.locator("#mobile-menu").is_visible())
    page.screenshot(path=str(OUT / "phone-menu.png"))
    page.locator("#mobile-menu").get_by_role("link", name="Finishes").tap()
    page.wait_for_timeout(1800)
    check("Mobile menu closes after link", not page.locator("#mobile-menu").is_visible())

    viewer = page.locator(".viewer")
    viewer.scroll_into_view_if_needed()
    page.wait_for_timeout(1000)
    box = viewer.bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    cdp = ctx.new_cdp_session(page)
    t0 = viewer_shot(page)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": cx, "y": cy}]})
    for i in range(1, 12):
        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": cx + i * 12, "y": cy}]})
        page.wait_for_timeout(25)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    page.wait_for_timeout(1300)
    t1 = viewer_shot(page)
    check("Touch drag rotates the product", t0 != t1)
    check("Reset enabled after touch drag", page.get_by_role("button", name="Reset view").is_enabled())
    page.screenshot(path=str(OUT / "phone-touch-rotated.png"))
    page.get_by_role("button", name="Reset view").tap()
    try:
        expect(page.get_by_role("button", name="Reset view")).to_be_disabled(timeout=4000)
        reset_ok = True
    except AssertionError:
        reset_ok = False
    check("Reset after touch", reset_ok)

    page.get_by_role("button", name="Add Graphite to demo cart").tap()
    page.locator(".nav__cart").tap()
    page.wait_for_timeout(700)
    page.screenshot(path=str(OUT / "phone-cart.png"))
    overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    check("No horizontal overflow on phone", overflow == 0, f"{overflow}px")
    check("No console errors (phone)", not errors, "; ".join(errors[:3]))
    ctx.close()

    # ---------- Reduced motion ----------
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    page = ctx.new_page()
    page.goto(BASE)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)
    check("Reduced motion uses static journey", page.locator(".showcase--static").count() == 1)
    page.evaluate("document.querySelectorAll('.still img').forEach(i => i.loading = 'eager')")
    page.wait_for_timeout(1000)
    imgs_ok = page.evaluate("[...document.querySelectorAll('.still img')].every(i => i.complete && i.naturalWidth > 0)")
    check("Static stills load", imgs_ok)
    check("Four chapter stills", page.locator(".still img").count() == 4)
    check("Reduced motion keeps the turntable", page.locator(".viewer__canvas").count() == 1)
    page.screenshot(path=str(OUT / "reduced-motion-hero.png"))
    page.locator("#stage-2").scroll_into_view_if_needed()
    page.screenshot(path=str(OUT / "reduced-motion-stage2.png"))
    ctx.close()

    # ---------- No-WebGL fallback (forced with ?static) ----------
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(BASE + "/?static")
    page.wait_for_load_state("networkidle")
    check("Fallback: no canvases", page.locator("canvas").count() == 0)
    page.locator("#configure").scroll_into_view_if_needed()
    page.locator("label.swatch:has(input[value=ember])").click()
    page.wait_for_timeout(500)
    src = page.locator(".viewer__still").get_attribute("src")
    check("Fallback still follows colour", "/spin/ember/" in src, src)
    check("Fallback still loaded", page.locator(".viewer__still").evaluate("i => i.naturalWidth > 0"))
    page.screenshot(path=str(OUT / "fallback-config.png"))
    ctx.close()

    browser.close()

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
