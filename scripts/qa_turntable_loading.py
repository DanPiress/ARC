"""Focused turntable loading and touch-cancellation regression check.

Run against the Vite dev server to include React StrictMode's effect replay:
  <python> scripts/qa_turntable_loading.py [http://localhost:5173]
"""
import hashlib
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5173"
SPIN_PATH = re.compile(r"/spin(?:-s)?/(graphite|silver|ember)/(\d{2})\.webp$")  # either image set
FINISHES = ("graphite", "silver", "ember")
MEDIA = Path(__file__).resolve().parent.parent / "src" / "media.ts"
TURN_FRAMES = int(re.search(r"export const TURN_FRAMES\s*=\s*(\d+)", MEDIA.read_text()).group(1))
COARSE_FRAMES = set(range(0, TURN_FRAMES, 4))


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    print("PASS " + name, flush=True)


def canvas_hash(page):
    pixels = page.locator(".viewer__canvas").evaluate("canvas => canvas.toDataURL()")
    return hashlib.sha256(pixels.encode()).hexdigest()


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        is_mobile=True,
        has_touch=True,
        device_scale_factor=1,
    )
    page = context.new_page()
    errors = []
    requested = []
    loaded = {finish: set() for finish in FINISHES}
    page.on("pageerror", lambda error: errors.append(str(error)))

    def delay_spin(route):
        match = SPIN_PATH.search(urlparse(route.request.url).path)
        if match:
            finish, index = match.group(1), int(match.group(2))
            requested.append((finish, index))
            if index:
                time.sleep(0.06)
        route.continue_()

    def record_response(response):
        match = SPIN_PATH.search(urlparse(response.url).path)
        if match and response.ok:
            loaded[match.group(1)].add(int(match.group(2)))

    def wait_loaded(finish, index, timeout=15000):
        deadline = time.monotonic() + timeout / 1000
        while index not in loaded[finish]:
            if time.monotonic() >= deadline:
                raise AssertionError(f"Timed out loading {finish}/{index:02d}; loaded {sorted(loaded[finish])}")
            page.wait_for_timeout(25)

    def wait_complete(finish, wanted, timeout=30000):
        deadline = time.monotonic() + timeout / 1000
        while not wanted.issubset(loaded[finish]):
            if time.monotonic() >= deadline:
                missing = sorted(wanted - loaded[finish])
                raise AssertionError(f"Timed out completing {finish}; missing {missing}")
            page.wait_for_timeout(25)

    def choose(finish):
        page.locator(f'label.swatch:has(input[value="{finish}"])').tap()
        expect(page.locator(f'input[value="{finish}"]')).to_be_checked()

    page.route(re.compile(r".*/spin(-s)?/.*\.webp$"), delay_spin)
    page.on("response", record_response)
    page.goto(BASE, wait_until="domcontentloaded")
    page.locator(".viewer").wait_for(state="attached")
    page.wait_for_timeout(700)
    # The placeholder still is lazy-loaded since the performance pass, so nothing competes with the opening.
    check("No turntable image loads while the viewer is far below the viewport", not requested)

    # Bring the viewer close, then switch finishes before their delayed turntables finish.
    page.locator("#configure").scroll_into_view_if_needed()
    wait_loaded("graphite", 12)
    check("The first turntable is still incomplete before switching", len(loaded["graphite"]) < TURN_FRAMES)
    for finish in ("silver", "ember", "graphite", "silver"):
        start = len(requested)
        choose(finish)
        deadline = time.monotonic() + 5
        while not any(name == finish and index > 0 for name, index in requested[start:]) and len(loaded[finish]) < TURN_FRAMES:
            if time.monotonic() >= deadline:
                raise AssertionError(f"Selected {finish} did not receive more turntable frames")
            page.wait_for_timeout(25)
        check(f"Selected {finish} receives frames during delayed loading", True)

    wait_complete("silver", set(range(TURN_FRAMES)))
    check(f"The selected finish completes all {TURN_FRAMES} frames after rapid switches", len(loaded["silver"]) == TURN_FRAMES)
    background_start = len(requested)
    for finish in ("graphite", "ember"):
        wait_complete(finish, COARSE_FRAMES)
    background = [(finish, index) for finish, index in requested[background_start:] if finish != "silver"]
    check("Unselected finishes have every fourth frame available", all(COARSE_FRAMES.issubset(loaded[finish]) for finish in ("graphite", "ember")))
    check("Background requests stay on the coarse frame set", all(index in COARSE_FRAMES for _, index in background))
    check("Unselected finishes defer their remaining fine frames", all(len(loaded[finish]) < TURN_FRAMES for finish in ("graphite", "ember")))

    # Selecting each partly loaded finish must resume it through the full turn, not strand its cache.
    for finish in FINISHES:
        choose(finish)
        wait_complete(finish, set(range(TURN_FRAMES)))
        check(f"Selected {finish} resumes through all {TURN_FRAMES} frames", len(loaded[finish]) == TURN_FRAMES)
    page.wait_for_timeout(250)

    reset = page.get_by_role("button", name="Reset view")
    viewer = page.locator(".viewer")
    for finish in FINISHES:
        choose(finish)
        expect(page.locator(".viewer__canvas")).to_have_class(re.compile(r"\bis-ready\b"))
        default = canvas_hash(page)
        page.get_by_role("button", name="Rotate right").tap()
        expect(reset).to_be_enabled()
        page.wait_for_timeout(750)
        check(f"{finish} displays a different rendered angle", canvas_hash(page) != default)
        reset.tap()
        expect(reset).to_be_disabled(timeout=4000)
        # Reset disables as the angle comes within 0.01 rad of zero; let the 0.6 s glide finish before comparing.
        page.wait_for_timeout(700)
        check(f"{finish} reset restores its exact default image", canvas_hash(page) == default)

    # Cancellation releases capture and allows only the short snap to a single sharp frame.
    choose("graphite")
    default = canvas_hash(page)
    viewer.scroll_into_view_if_needed()
    page.wait_for_timeout(150)
    viewer.evaluate("element => element.addEventListener('pointercancel', event => { window.cancelledPointer = event.pointerId; })")
    box = viewer.bounding_box()
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    cdp = context.new_cdp_session(page)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": cx, "y": cy}]})
    for step in range(1, 6):
        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": cx + step * 12, "y": cy}]})
        page.wait_for_timeout(25)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchCancel", "touchPoints": []})
    page.wait_for_timeout(300)
    cancelled = canvas_hash(page)
    check("Touch drag changes the rendered angle before cancellation", cancelled != default)
    check("Pointer cancellation releases capture", viewer.evaluate("element => window.cancelledPointer !== undefined && !element.hasPointerCapture(window.cancelledPointer)"))
    page.wait_for_timeout(1100)
    check("Cancelled touch stays settled after its short frame snap", canvas_hash(page) == cancelled)
    reset.tap()
    expect(reset).to_be_disabled(timeout=4000)
    check("Touch reset restores the exact default image", canvas_hash(page) == default)
    page.wait_for_timeout(1000)
    check("The default image stays settled after touch reset", canvas_hash(page) == default)
    check("No browser errors", not errors)
    context.close()
    browser.close()
