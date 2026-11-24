"""Builds the 1200x630 link-preview image (public/og/arc-share.jpg) from the first desktop journey frame.

Lays the render out with the site's own type (Archivo from Google Fonts) in headless Chromium and saves a JPEG
screenshot. Run with the webapp-testing Python (Playwright):  python design/share/make_share.py [source.webp]
"""
import base64, pathlib, sys
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "public/journey/desktop/000.webp"
OUT = ROOT / "public/og/arc-share.jpg"

img = "data:image/webp;base64," + base64.b64encode(SRC.read_bytes()).decode()
HTML = f"""<!doctype html><html><head>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,100..900&display=block" rel="stylesheet">
<style>
  html, body {{ margin: 0; width: 1200px; height: 630px; overflow: hidden; background: #04070d; }}
  .frame {{ position: absolute; inset: 0; background: url({img}) no-repeat; background-size: 1200px 750px;
           background-position: 0 -42px; }}
  .shade {{ position: absolute; inset: 0;
           background: linear-gradient(90deg, rgba(4,7,13,.92) 0%, rgba(4,7,13,.72) 30%, rgba(4,7,13,0) 58%); }}
  .copy {{ position: absolute; left: 64px; top: 0; bottom: 0; display: flex; flex-direction: column;
          justify-content: center; font-family: Archivo, sans-serif; color: #e9f0ff; }}
  .mark {{ position: absolute; left: 64px; top: 52px; font: 800 30px/1 Archivo; font-stretch: 125%;
          letter-spacing: .06em; color: #e9f0ff; }}
  h1 {{ margin: 0; font-weight: 900; font-stretch: 125%; font-size: 86px; line-height: .92; letter-spacing: -.01em; }}
  p {{ margin: 26px 0 0; font-size: 27px; font-weight: 400; color: #c9d5ee; }}
  .note {{ position: absolute; left: 64px; bottom: 46px; font: 400 18px/1 Archivo; color: #9aabc8; }}
</style></head><body>
  <div class="frame"></div><div class="shade"></div>
  <div class="mark">ARC</div>
  <div class="copy"><h1>YOUR<br>NEXT<br>MOVE.</h1><p>An original controller concept.</p></div>
  <div class="note">A design study. Not a real product.</div>
</body></html>"""

OUT.parent.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--disable-gpu"])
    page = b.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
    page.set_content(HTML, wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(300)
    page.screenshot(path=str(OUT), type="jpeg", quality=86)
    b.close()
print(OUT, OUT.stat().st_size // 1024, "KB")
