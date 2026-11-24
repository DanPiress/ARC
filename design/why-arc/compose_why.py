"""Compose the "Why ARC" setup image: a real ARC turntable render placed on a generated desk backdrop.

  <python> design/why-arc/compose_why.py [preview|final]

The backdrop (generated/setup-v1-0.png) was made with ForgeGUI's cloud image generation (prompt in
PROMPT.txt) and contains no controller. The controller is an unedited ARC render from the configurator's
turntable (source/arc-silver-06.webp): it is toned down for the dark room, given a cobalt rim from the LED
strip and a contact shadow, and placed on the desk. Compositing runs in headless Chromium's software canvas,
so it does not use the laptop's GPU.

preview: work/why/preview.png (whole canvas with crop guides).
final:   public/why/setup-{1800,1200}.webp (3:2, desktop) and setup-p-{1000,640}.webp (4:5, phone).
"""
import base64
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODE = sys.argv[1] if len(sys.argv) > 1 else "preview"

CFG = {
    "bg": "generated/setup-v1-0.png",
    "ctrl": "source/arc-silver-06.webp",
    "W": 2200,               # canvas width; the backdrop is scaled up to it (it is mostly out of focus)
    "cx": 0.55, "cy": 0.47,  # where the controller's centre sits, as fractions of the canvas (on the desk top)
    "width": 0.26,           # controller width as a fraction of the canvas width
    "shadowCut": 0.80,       # render rows below this fraction of the controller's height lose the floor shadow
    "tone": "brightness(0.52) contrast(1.14) saturate(0.85)",
    "crops": {               # aspect, centre x (fraction), outputs [width, quality]
        "setup": [3 / 2, 0.5, [[1800, 0.84], [1200, 0.82]]],
        "setup-p": [4 / 5, 0.55, [[1000, 0.84], [640, 0.82]]],
    },
}


def data_url(path):
    mime = "image/png" if path.suffix == ".png" else "image/webp"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


JS = r"""
async ({ cfg, bg, ctrl, mode }) => {
  const load = (src) => new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = src; });
  const [B, C] = await Promise.all([load(bg), load(ctrl)]);
  const W = cfg.W, H = Math.round(B.height * W / B.width);
  const mk = (w, h) => { const c = document.createElement('canvas'); c.width = w; c.height = h; return [c, c.getContext('2d')]; };

  // 1. The controller alone: find its box from the opaque pixels, and drop the floating floor shadow.
  const [cc, cx] = mk(C.width, C.height);
  cx.drawImage(C, 0, 0);
  const id = cx.getImageData(0, 0, C.width, C.height), d = id.data;
  let x0 = 1e9, y0 = 1e9, x1 = 0, y1 = 0;
  for (let y = 0; y < C.height; y++) for (let x = 0; x < C.width; x++) {
    if (d[(y * C.width + x) * 4 + 3] > 245) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
  }
  // Keep only the controller: its opaque pixels plus a 2 px antialiased edge. Everything else in the render
  // (the floor shadow and the faint shadow-catcher haze) is dropped; the composite draws its own shadow.
  const Wc = C.width, Hc = C.height, R = 2;
  const opaque = new Uint8Array(Wc * Hc);
  for (let i = 0; i < Wc * Hc; i++) opaque[i] = d[i * 4 + 3] > 245 ? 1 : 0;
  let dropped = 0;
  for (let y = 0; y < Hc; y++) for (let x = 0; x < Wc; x++) {
    const k = y * Wc + x;
    if (opaque[k] || !d[k * 4 + 3]) continue;
    let near = false;
    for (let dy = -R; dy <= R && !near; dy++) for (let dx = -R; dx <= R; dx++) {
      const yy = y + dy, xx = x + dx;
      if (yy >= 0 && yy < Hc && xx >= 0 && xx < Wc && opaque[yy * Wc + xx]) { near = true; break; }
    }
    if (!near) { d[k * 4 + 3] = 0; dropped++; }
  }
  const shadowMax = dropped;
  cx.putImageData(id, 0, 0);

  const s = (W * cfg.width) / (x1 - x0);
  const cw = Math.round((x1 - x0) * s), ch = Math.round((y1 - y0) * s);
  // 2. Tone it for the dark room, then add the cobalt rim from the LED strip behind the desk.
  const [tc, tx] = mk(cw, ch);
  tx.filter = cfg.tone;
  tx.drawImage(cc, x0, y0, x1 - x0, y1 - y0, 0, 0, cw, ch);
  tx.filter = 'none';
  tx.globalCompositeOperation = 'source-atop';
  let g = tx.createLinearGradient(0, 0, 0, ch);
  g.addColorStop(0, 'rgba(46,108,255,0.20)'); g.addColorStop(0.4, 'rgba(46,108,255,0.04)'); g.addColorStop(1, 'rgba(4,7,13,0.30)');
  tx.fillStyle = g; tx.fillRect(0, 0, cw, ch);
  g = tx.createLinearGradient(0, 0, cw, 0);
  g.addColorStop(0, 'rgba(4,7,13,0.22)'); g.addColorStop(0.5, 'rgba(4,7,13,0)'); g.addColorStop(1, 'rgba(46,108,255,0.06)');
  tx.fillStyle = g; tx.fillRect(0, 0, cw, ch);
  tx.globalCompositeOperation = 'source-over';
  // Rim: the silhouette minus itself moved down leaves a band along the top edges.
  const band = Math.max(4, Math.round(ch * 0.012));
  const [rc, rx] = mk(cw, ch);
  rx.drawImage(tc, 0, 0);
  rx.globalCompositeOperation = 'source-in'; rx.fillStyle = '#6d9bff'; rx.fillRect(0, 0, cw, ch);
  rx.globalCompositeOperation = 'destination-out'; rx.drawImage(tc, 0, band);
  const [rb, rbx] = mk(cw, ch);
  rbx.filter = `blur(${band * 0.5}px)`; rbx.drawImage(rc, 0, 0);
  rbx.globalCompositeOperation = 'destination-in'; rbx.filter = 'none'; rbx.drawImage(tc, 0, 0);
  tx.globalCompositeOperation = 'lighter'; tx.globalAlpha = 0.55; tx.drawImage(rb, 0, 0);
  tx.globalAlpha = 1; tx.globalCompositeOperation = 'source-over';

  // 3. The scene: backdrop, contact shadow, controller, a faint satin reflection, grain.
  const [oc, ox] = mk(W, H);
  ox.drawImage(B, 0, 0, W, H);
  const px = Math.round(W * cfg.cx - cw / 2), py = Math.round(H * cfg.cy - ch / 2);
  const foot = py + ch;
  const ell = (x, y, rx_, ry, a, blur) => {
    ox.save(); ox.filter = `blur(${blur}px)`; ox.fillStyle = `rgba(0,0,0,${a})`;
    ox.beginPath(); ox.ellipse(x, y, rx_, ry, 0, 0, Math.PI * 2); ox.fill(); ox.restore();
  };
  ell(px + cw * 0.5, foot - ch * 0.04, cw * 0.48, ch * 0.07, 0.55, ch * 0.05);   // broad ambient shadow
  ell(px + cw * 0.12, foot - ch * 0.01, cw * 0.10, ch * 0.022, 0.8, ch * 0.012);  // where the left grip touches
  ell(px + cw * 0.765, foot - ch * 0.235, cw * 0.08, ch * 0.016, 0.75, ch * 0.01);  // where the right grip touches
  ell(px + cw * 0.45, foot - ch * 0.10, cw * 0.38, ch * 0.08, 0.35, ch * 0.04);   // under the body
  // Reflection on the satin desk: the controller flipped below its foot, faded out quickly.
  const [fc, fx] = mk(cw, ch);
  fx.translate(0, ch); fx.scale(1, -1); fx.drawImage(tc, 0, 0);
  fx.setTransform(1, 0, 0, 1, 0, 0); fx.globalCompositeOperation = 'destination-in';
  g = fx.createLinearGradient(0, 0, 0, ch * 0.25); g.addColorStop(0, 'rgba(0,0,0,0.10)'); g.addColorStop(1, 'rgba(0,0,0,0)');
  fx.fillStyle = g; fx.fillRect(0, 0, cw, ch);
  ox.filter = 'blur(3px)'; ox.drawImage(fc, px, foot - ch * 0.02); ox.filter = 'none';
  ox.drawImage(tc, px, py);
  // Shared grain so the clean render sits in the photographic backdrop.
  const [nc, nx] = mk(512, 512);
  const n = nx.createImageData(512, 512);
  let seed = 7;
  for (let i = 0; i < n.data.length; i += 4) { seed = (seed * 16807) % 2147483647; const v = seed % 255; n.data[i] = n.data[i + 1] = n.data[i + 2] = v; n.data[i + 3] = 10; }
  nx.putImageData(n, 0, 0);
  ox.fillStyle = ox.createPattern(nc, 'repeat'); ox.globalCompositeOperation = 'overlay'; ox.fillRect(0, 0, W, H);
  ox.globalCompositeOperation = 'source-over';

  const info = { W, H, box: [x0, y0, x1, y1], shadowMax, ctrl: [px, py, cw, ch] };
  if (mode === 'preview') {
    for (const [name, [aspect, cxf]] of Object.entries(cfg.crops)) {
      const w = Math.round(H * aspect), l = Math.round(Math.min(W - w, Math.max(0, W * cxf - w / 2)));
      ox.strokeStyle = name === 'setup' ? '#ff7a1a' : '#7cff8a'; ox.lineWidth = 4; ox.strokeRect(l, 2, w, H - 4);
    }
    return { info, out: { preview: oc.toDataURL('image/png') } };
  }
  const out = {};
  for (const [name, [aspect, cxf, sizes]] of Object.entries(cfg.crops)) {
    const w = Math.round(H * aspect), l = Math.round(Math.min(W - w, Math.max(0, W * cxf - w / 2)));
    for (const [ow, q] of sizes) {
      const oh = Math.round(ow / aspect);
      const [sc, sx] = mk(ow, oh);
      sx.imageSmoothingQuality = 'high';
      sx.drawImage(oc, l, 0, w, H, 0, 0, ow, oh);
      out[`${name}-${ow}`] = sc.toDataURL('image/webp', q);
    }
  }
  return { info, out };
}
"""

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--disable-gpu"])
    page = browser.new_page()
    page.set_content("<html><body></body></html>")
    res = page.evaluate(JS, {"cfg": CFG, "bg": data_url(HERE / CFG["bg"]), "ctrl": data_url(HERE / CFG["ctrl"]), "mode": MODE})
    browser.close()

print(json.dumps(res["info"]))
dst = ROOT / ("work/why" if MODE == "preview" else "public/why")
dst.mkdir(parents=True, exist_ok=True)
for name, url in res["out"].items():
    ext = "png" if MODE == "preview" else "webp"
    f = dst / f"{name}.{ext}"
    f.write_bytes(base64.b64decode(url.split(",", 1)[1]))
    print(f"WROTE {f.relative_to(ROOT)} {f.stat().st_size // 1024} KB")
