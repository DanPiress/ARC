"""Neutral studio review of the Blender ARC model: grey backdrop, soft white light.
  blender --background --factory-startup --python design/arc-v4/render_studio.py -- [tag] [finish]
Writes qa/screenshots/arc-v4/studio/<tag>/<view>.png
"""
import math
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
import render_lib as R  # noqa: E402

args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
TAG = args[0] if args else 'review'
FINISH = args[1] if len(args) > 1 else 'graphite'

scene, pivot, size = R.open_model()
R.set_finish(FINISH)
R.cycles(scene, 1500, 1000, samples=96)
R.world_color(R.srgb('#b4b7bb'), 0.35)

# Floor that catches the shadow, same tone as the backdrop.
bpy.ops.mesh.primitive_plane_add(size=6, location=(0, 0, -size.z / 2 - 0.03))
floor = bpy.context.active_object
fm = bpy.data.materials.new('Floor')
fm.use_nodes = True
fm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (*R.srgb('#9a9da2'), 1)
fm.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 0.8
floor.data.materials.append(fm)

R.area_light('Key', 0.9, 55, (1, 1, 1), (-0.45, -0.5, 0.55))
R.area_light('Fill', 1.2, 12, (1, 1, 1), (0.6, -0.4, 0.15))
R.area_light('RimL', 0.25, 30, (1, 1, 1), (-0.5, 0.45, 0.25), size_y=1.0)
R.area_light('RimR', 0.25, 30, (1, 1, 1), (0.5, 0.45, 0.25), size_y=1.0)
R.area_light('Top', 1.0, 15, (1, 1, 1), (0, 0.1, 0.8))

cam = R.camera(lens=85)
views = {
    'threeq': dict(yaw=0.55, tilt=0.18, az=0.0, el=0.22, dist=0.62, target=Vector((0, 0, 0))),
    'front': dict(yaw=0.0, tilt=0.05, az=0.0, el=0.06, dist=0.6, target=Vector((0, 0, 0))),
    'rear': dict(yaw=math.pi + 0.6, tilt=0.0, az=0.0, el=0.35, dist=0.62, target=Vector((0, 0, 0))),
    'side': dict(yaw=math.pi / 2, tilt=0.0, az=0.0, el=0.08, dist=0.6, target=Vector((0, 0, 0))),
    'top': dict(yaw=0.0, tilt=1.2, az=0.0, el=0.1, dist=0.6, target=Vector((0, 0, 0))),
}
for name, v in views.items():
    pivot.rotation_euler = (v['tilt'], 0, v['yaw'])
    bpy.context.view_layer.update()
    R.place_camera(cam, v['target'], v['dist'], v['az'], v['el'])
    R.render(R.ROOT / 'qa' / 'screenshots' / 'arc-v4' / 'studio' / TAG / f'{name}.png')

# Stick close-up: aim at the left stick cap, low and close.
pivot.rotation_euler = (0.3, 0, 0.15)
bpy.context.view_layer.update()
cam.data.lens = 100
R.place_camera(cam, R.obj_centre('leftStick_cap'), 0.16, -0.45, 0.45)
R.render(R.ROOT / 'qa' / 'screenshots' / 'arc-v4' / 'studio' / TAG / 'stick.png')
