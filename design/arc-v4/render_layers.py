"""'Designed in layers': an exploded exterior view of the real ARC parts on a light studio stage.

  blender --background --factory-startup --python design/arc-v4/render_layers.py -- [preview|final] [tag]

The parts of arc.blend are moved apart along the controller's depth axis, front to back:
  spine  - the titanium spine with its centre keys, status slit and engraved logo
  front  - the front shell with the sticks, cross pad and face buttons set into it
  back   - the back shell with the bumpers, triggers and port
  grips  - the rubber grips
The film is transparent with a shadow catcher, so the page's own background shows through exactly.
Writes work/layers/<tag>.png (16-bit RGBA master) and src/data/layersAnchors.json (callout positions, 0..1).
"""
import json
import math
import pathlib
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import render_lib as R  # noqa: E402

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
MODE = ARGS[0] if ARGS else 'preview'
TAG = ARGS[1] if len(ARGS) > 1 else MODE
W, H = (2400, 1500) if MODE == 'final' else (960, 600)
SAMPLES = 256 if MODE == 'final' else 32

GROUPS = {
    'spine': ['shell_spine', 'centre_plastic', 'centre_slit', 'home_icon', 'logo', 'menu_icon_-1', 'menu_icon_0',
              'menu_icon_1'] + [f'view_icon{s}' for s in ('', '.001', '.002', '.003', '.004', '.005', '.006', '.007')],
    'front': ['shell_front', 'leftStick_base', 'leftStick_cap', 'rightStick_base', 'rightStick_cap', 'dpad', 'buttons',
              'leftStick_bezel', 'rightStick_bezel', 'dpad_bezel', 'legend_Y', 'legend_B', 'legend_A', 'legend_X'],
    'back': ['shell_back', 'shell_bumper', 'shell_trigger', 'usb_socket', 'logo_rear'],
    'grips': ['shell_grip'],
}
# Offsets in the model's own axes (metres): -Y is towards the face, +Z towards the bumpers.
EXPLODE = {
    'spine': Vector((0, -0.06, 0.004)),
    'front': Vector((0, 0, 0)),
    'back': Vector((0, 0.055, 0.008)),
    'grips': Vector((0, 0.115, -0.055)),
}
# Where each callout points: a part and a point inside its bounding box (fractions of x, y, z).
ANCHORS = {
    'spine': ('shell_spine', (0.5, 0.0, 0.62)),
    'shell': ('shell_back', (0.62, 0.0, 0.55)),
    'grips': ('shell_grip', (0.93, 0.5, 0.4)),
}
POSE = dict(yaw=float(ARGS[2]) if len(ARGS) > 2 else -0.85, tilt=float(ARGS[3]) if len(ARGS) > 3 else 0.55)
CAM = dict(az=0.0, el=0.2, dist=0.92, lens=85)
FILL = 0.76  # the assembly spans this fraction of the image width, centred

scene, pivot, size = R.open_model()
R.set_finish('graphite')
R.cycles(scene, W, H, samples=SAMPLES, transparent=True)
scene.cycles.denoiser = 'OPENIMAGEDENOISE'
scene.cycles.denoising_use_gpu = True
scene.render.image_settings.color_depth = '16'
scene.view_settings.look = 'AgX - Base Contrast'

# Light studio: a pale cool world for reflections, white soft boxes, one faint cobalt edge light (the brand's light).
R.world_color(R.srgb('#dfe5ee'), 0.12)
R.area_light('Key', 1.1, 20, (1, 0.99, 0.97), (-0.55, -0.6, 0.65))
R.area_light('Fill', 1.4, 5, (0.96, 0.98, 1.0), (0.7, -0.45, 0.2))
R.area_light('Top', 1.2, 7, (1, 1, 1), (0.05, 0.15, 0.9))
R.area_light('RimL', 0.25, 12, (1, 1, 1), (-0.6, 0.55, 0.3), size_y=1.0)
R.area_light('RimC', 0.2, 6, R.srgb('#6d9bff'), (0.55, 0.6, 0.15), size_y=0.8)

# Callout anchors: the vertex of each part nearest a point given as fractions of the part's bounding box
# (world axes, before posing), so every callout sits on the part's real surface.
bpy.context.view_layer.update()
anchor_verts = {}
for key, (name, frac) in ANCHORS.items():
    ob = bpy.data.objects[name]
    bb = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    lo_ = Vector([min(p[i] for p in bb) for i in range(3)])
    hi_ = Vector([max(p[i] for p in bb) for i in range(3)])
    target = Vector([lo_[i] + frac[i] * (hi_[i] - lo_[i]) for i in range(3)])
    mw = ob.matrix_world
    best = min(ob.data.vertices, key=lambda v: (mw @ v.co - target).length_squared)
    anchor_verts[key] = (ob, best.index)

# Move the parts apart, in world axes (the model root carries its own rotation and scale).
for group, names in GROUPS.items():
    for n in names:
        ob = bpy.data.objects.get(n)
        if ob is None:
            print('missing part', n)
            continue
        ob.matrix_world = Matrix.Translation(EXPLODE[group]) @ ob.matrix_world
        bpy.context.view_layer.update()

pivot.rotation_euler = (POSE['tilt'], 0, POSE['yaw'])
bpy.context.view_layer.update()

# Shadow catcher under the lowest part.
lo = min((ob.matrix_world @ Vector(c)).z for ob in bpy.data.collections['ARC'].all_objects if ob.type == 'MESH'
         for c in ob.bound_box)
bpy.ops.mesh.primitive_plane_add(size=3, location=(0, 0, lo - 0.045))
bpy.context.active_object.is_shadow_catcher = True

cam = R.camera(lens=CAM['lens'])
# Aim at the middle of the exploded assembly.
meshes = [ob for ob in bpy.data.collections['ARC'].all_objects if ob.type == 'MESH']
pts = [ob.matrix_world @ ob.data.vertices[i].co for ob in meshes for i in range(0, len(ob.data.vertices), 40)]
mid = sum(pts, Vector()) / len(pts)
R.place_camera(cam, mid, CAM['dist'], CAM['az'], CAM['el'])
cam.data.dof.use_dof = True
cam.data.dof.focus_distance = CAM['dist']
cam.data.dof.aperture_fstop = 16


def visible_bounds():
    bpy.context.view_layer.update()
    b = [world_to_camera_view(scene, cam, q) for q in pts]
    return min(p.x for p in b), 1 - max(p.y for p in b), max(p.x for p in b), 1 - min(p.y for p in b)


# Frame it: the assembly's real outline (sampled vertices) centred, spanning FILL of the width.
for _ in range(3):
    x0, y0, x1, y1 = visible_bounds()
    cam.data.lens *= FILL / (x1 - x0)
    x0, y0, x1, y1 = visible_bounds()
    cam.data.shift_x += ((x0 + x1) / 2 - 0.5)
    cam.data.shift_y -= ((y0 + y1) / 2 - 0.5) * H / W

# Callout anchor positions on the image (0..1 from the top left).
anchors = {}
for key, (ob, vi) in anchor_verts.items():
    v = world_to_camera_view(scene, cam, ob.matrix_world @ ob.data.vertices[vi].co)
    anchors[key] = [round(v.x, 4), round(1 - v.y, 4)]
# The assembly's outline on the image, for layout.
anchors['_bounds'] = [round(v, 3) for v in visible_bounds()]
print('ANCHORS', json.dumps(anchors))
(R.ROOT / 'work' / 'layers').mkdir(parents=True, exist_ok=True)
(R.ROOT / 'work' / 'layers' / f'{TAG}.json').write_text(json.dumps(anchors))
if MODE == 'final':
    (R.ROOT / 'src' / 'data' / 'layersAnchors.json').write_text(json.dumps(anchors))

R.render(R.ROOT / 'work' / 'layers' / f'{TAG}.png')
