"""Re-encode rendered WEBP frames at a different quality (Blender's image writer, keeps alpha).

  blender --background --factory-startup --python design/arc-v4/reencode.py -- <src_dir> <dst_dir> <quality> [glob] [width]
"""
import pathlib
import sys

import bpy

args = sys.argv[sys.argv.index('--') + 1:]
src, dst, quality = pathlib.Path(args[0]).resolve(), pathlib.Path(args[1]).resolve(), int(args[2])
pattern = args[3] if len(args) > 3 else '*.webp'
width = int(args[4]) if len(args) > 4 else None
dst.mkdir(parents=True, exist_ok=True)

scene = bpy.context.scene
s = scene.render.image_settings
s.file_format = 'WEBP'
s.color_mode = 'RGBA'
s.quality = quality
# Pixels are stored as-is (no view transform), so the re-encode does not shift colours.
scene.view_settings.view_transform = 'Standard'
scene.view_settings.look = 'None'
scene.view_settings.exposure = 0.0
scene.view_settings.gamma = 1.0
scene.display_settings.display_device = 'sRGB'

for f in sorted(src.glob(pattern)):
    img = bpy.data.images.load(str(f))
    if width and img.size[0] != width:
        img.scale(width, round(img.size[1] * width / img.size[0]))
    img.save_render(str(dst / f.name), scene=scene)
    bpy.data.images.remove(img)
print('re-encoded', len(list(dst.glob(pattern))), 'files to', dst)
