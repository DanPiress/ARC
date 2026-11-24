"""Encode the lossless journey masters (work/journey-v2/<device>/NNN.png or .webp) into the shipped WEBP sets.

  blender --background --factory-startup --python design/arc-v4/encode_journey.py -- <dst_root> [quality] [sets]

Sets: desktop (1920x1200), desktop-s (1440x900, from the desktop masters), phone (828x1794).
Writes <dst_root>/<set>/NNN.webp; use public/journey to ship, or a work folder to compare qualities first.
"""
import pathlib
import sys

import bpy

ROOT = pathlib.Path(__file__).resolve().parents[2]
args = sys.argv[sys.argv.index('--') + 1:]
dst_root = pathlib.Path(args[0]).resolve()
quality = int(args[1]) if len(args) > 1 else 88
SETS = {'desktop': ('desktop', 1920), 'desktop-s': ('desktop', 1440), 'phone': ('phone', 828)}
chosen = args[2].split(',') if len(args) > 2 else list(SETS)
SRC = pathlib.Path(args[3]).resolve() if len(args) > 3 else ROOT / 'work' / 'journey-v2'  # masters root

scene = bpy.context.scene
s = scene.render.image_settings
s.file_format = 'WEBP'
s.color_mode = 'RGB'
s.quality = quality
scene.view_settings.view_transform = 'Standard'  # the masters are already display-referred
scene.view_settings.look = 'None'
scene.view_settings.exposure = 0.0
scene.view_settings.gamma = 1.0
scene.display_settings.display_device = 'sRGB'

for name in chosen:
    src_dev, width = SETS[name]
    src = SRC / src_dev
    out = dst_root / name
    out.mkdir(parents=True, exist_ok=True)
    masters = {}
    for f in sorted(src.glob('*.webp')) + sorted(src.glob('*.png')):
        masters[f.stem] = f  # a PNG master wins over an earlier WEBP one
    for stem, f in sorted(masters.items()):
        img = bpy.data.images.load(str(f))
        if img.size[0] != width:
            img.scale(width, round(img.size[1] * width / img.size[0]))
        img.save_render(str(out / f'{stem}.webp'), scene=scene)
        bpy.data.images.remove(img)
    total = sum(p.stat().st_size for p in out.glob('*.webp'))
    print(f'ENCODED {name}: {len(masters)} frames, {total / 1e6:.2f} MB at q{quality}')
