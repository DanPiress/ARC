"""Encode the layers master (work/layers/layers.png, RGBA) into web sizes: public/layers/exploded-<w>.webp.
  blender --background --factory-startup --python design/arc-v4/encode_layers.py -- [quality]
"""
import pathlib
import sys

import bpy

ROOT = pathlib.Path(__file__).resolve().parents[2]
args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
quality = int(args[0]) if args else 86
src = ROOT / 'work' / 'layers' / 'layers.png'
dst = ROOT / 'public' / 'layers'
dst.mkdir(parents=True, exist_ok=True)

scene = bpy.context.scene
s = scene.render.image_settings
s.file_format = 'WEBP'
s.color_mode = 'RGBA'
s.quality = quality
scene.view_settings.view_transform = 'Standard'  # store the pixels as rendered
scene.view_settings.look = 'None'
scene.view_settings.exposure = 0.0
scene.view_settings.gamma = 1.0
scene.display_settings.display_device = 'sRGB'

for w in (2400, 1600, 1000):
    img = bpy.data.images.load(str(src))
    if img.size[0] != w:
        img.scale(w, round(img.size[1] * w / img.size[0]))
    out = dst / f'exploded-{w}.webp'
    img.save_render(str(out), scene=scene)
    bpy.data.images.remove(img)
    print('wrote', out, out.stat().st_size)
