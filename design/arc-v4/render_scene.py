"""ARC cinematic renders (Cycles, GPU).

  blender --background --factory-startup --python design/arc-v4/render_scene.py -- <mode> [options]

Modes
  keys [device]          the four chapter keyframes for review (device: desktop | phone | both)
  sequence [device]      the scroll journey: every frame between the keyframes -> public/journey/<device>/
  turntable [finish]     configurator 360 turn on a transparent stage -> public/spin/<finish>/
  thumbs                 cart thumbnails per finish -> public/renders/
"""
import json
import math
import pathlib
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import render_lib as R  # noqa: E402

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else ['keys']
MODE = ARGS[0]
OPT = ARGS[1] if len(ARGS) > 1 else None

# ---------------------------------------------------------------- shots
# yaw/tilt turn the product; az/el/dist orbit the camera about the target; shift places the target on the
# frame (lens shift, fraction of the long side); focus 'centre' or 'stick'; key/rim/haze scale the lights.
DESKTOP = [
    dict(yaw=0.68, tilt=0.3, az=0.0, el=0.06, dist=0.74, lens=85, sx=-0.16, sy=-0.065, focus='centre', fstop=11.0, key=1.0, rim=1.0, haze=1.0),
    dict(yaw=0.15, tilt=0.3, az=-0.45, el=0.45, dist=0.15, lens=70, sx=-0.1, sy=-0.02, focus='stick', fstop=8.0, key=1.1, rim=0.7, haze=0.6),
    dict(yaw=-0.08, tilt=-0.9, az=-0.3, el=0.55, dist=0.76, lens=85, sx=-0.13, sy=0.0, focus='centre', fstop=11.0, key=1.1, rim=0.8, haze=0.8),
    dict(yaw=math.pi + 0.55, tilt=0.05, az=0.0, el=0.22, dist=0.74, lens=85, sx=0.17, sy=-0.06, focus='centre', fstop=11.0, key=0.9, rim=1.3, haze=1.0),
]
PHONE = [
    dict(DESKTOP[0], dist=0.5, sx=0.0, sy=0.08),
    dict(DESKTOP[1], dist=0.115, sx=0.0, sy=0.1),
    dict(DESKTOP[2], dist=0.5, sx=0.0, sy=0.1),
    dict(DESKTOP[3], dist=0.52, sx=0.0, sy=0.08),
]
# Desktop matches a 1920 px wide screen 1:1; phone matches a 414 pt wide phone at 2x.
SIZES = {'desktop': (1920, 1200), 'phone': (828, 1794)}
# Where each journey frame sits along the camera move (equal visual change per frame): design/arc-v4/plan_journey.py.
PLAN = R.ROOT / 'src' / 'data' / 'journeyFrames.json'
# Lossless frames are written here; encode them into public/journey/<device>/ once a full set is done.
SEQ_OUT = R.ROOT / 'work' / 'journey-v2'


def ease(t):
    return 0.5 - 0.5 * math.cos(math.pi * t)


def lerp_shot(a, b, t):
    out = {}
    for k, v in a.items():
        out[k] = v + (b[k] - v) * t if isinstance(v, (int, float)) else (v if t < 0.5 else b[k])
    return out


# ---------------------------------------------------------------- materials


def mat(name, color, rough, metal=0.0, emission=None, strength=0.0, spec=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*R.srgb(color), 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    b.inputs['Specular IOR Level'].default_value = spec
    if emission:
        b.inputs['Emission Color'].default_value = (*R.srgb(emission), 1)
        b.inputs['Emission Strength'].default_value = strength
    return m


def link(ob):
    bpy.context.scene.collection.objects.link(ob)
    return ob


def beam_curve(name, pts, w, h, material, cyclic=False):
    """A solid beam swept along a poly path, with a rectangular cross-section (w x h)."""
    prof = bpy.data.curves.new(name + '_prof', 'CURVE')
    sp = prof.splines.new('POLY')
    sp.points.add(3)
    for i, (x, y) in enumerate(((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))):
        sp.points[i].co = (x, y, 0, 1)
    sp.use_cyclic_u = True
    prof_ob = bpy.data.objects.new(name + '_prof', prof)
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_mode = 'OBJECT'
    cu.bevel_object = prof_ob
    cu.use_fill_caps = True
    s = cu.splines.new('POLY')
    s.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        s.points[i].co = (*p, 1)
    s.use_cyclic_u = cyclic
    ob = bpy.data.objects.new(name, cu)
    ob.data.materials.append(material)
    return link(ob)


def arch_points(radius, y, z0, n=64, a0=0.0, a1=math.pi):
    return [(math.cos(a0 + (a1 - a0) * i / (n - 1)) * radius, y, z0 + math.sin(a0 + (a1 - a0) * i / (n - 1)) * radius) for i in range(n)]


def box(name, loc, dims, material, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = dims
    ob.data.materials.append(material)
    bev = ob.modifiers.new('bevel', 'BEVEL')
    bev.width = min(dims) * 0.08
    bev.segments = 3
    return ob


# ---------------------------------------------------------------- environment

FLOOR_Z = -0.11  # world metres; product centre is at the origin


def chamber():
    concrete = mat('Arch', '#0b0f16', 0.55, metal=0.4)
    beam_dark = mat('Beam', '#090c12', 0.45, metal=0.6)
    cobalt = mat('StripBlue', '#2f6dff', 0.3, emission='#3d7bff', strength=18)
    cobalt_dim = mat('StripBlueDim', '#2f6dff', 0.3, emission='#2f6dff', strength=6)
    warm = mat('StripWarm', '#ff8a3a', 0.3, emission='#ff8a3a', strength=3.5)

    # Floor: dark, satin, softly reflective.
    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, FLOOR_Z))
    floor = bpy.context.active_object
    fm = mat('Floor', '#06080c', 0.2, metal=0.0, spec=0.6)
    nt = fm.node_tree
    noise = nt.nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 6.0
    rng = nt.nodes.new('ShaderNodeMapRange')
    rng.inputs['To Min'].default_value = 0.14
    rng.inputs['To Max'].default_value = 0.34
    nt.links.new(noise.outputs['Fac'], rng.inputs['Value'])
    nt.links.new(rng.outputs['Result'], nt.nodes['Principled BSDF'].inputs['Roughness'])
    floor.data.materials.append(fm)

    # Platform: low, modest, reads as a thin ellipse.
    bpy.ops.mesh.primitive_cylinder_add(radius=0.088, depth=0.007, vertices=160, location=(0, 0.02, FLOOR_Z + 0.0035))
    plat = bpy.context.active_object
    plat.data.materials.append(mat('Platform', '#0b0e14', 0.55, metal=0.5))
    bev = plat.modifiers.new('bevel', 'BEVEL')
    bev.width = 0.002
    bev.segments = 3
    bpy.ops.mesh.primitive_torus_add(major_radius=0.0885, minor_radius=0.0008, location=(0, 0.02, FLOOR_Z + 0.0072), major_segments=200)
    bpy.context.active_object.data.materials.append(mat('PlatRim', '#ff8a3a', 0.3, emission='#ff8a3a', strength=0.06))

    # Receding arches: heavy ribs over the hall, each with a light strip housed in a channel on its inner face.
    for i, y in enumerate((0.35, 0.75, 1.2, 1.75, 2.4, 3.2)):
        r = 0.52 + i * 0.03
        beam_curve(f'rib{i}', arch_points(r, y, FLOOR_Z), 0.06, 0.09, concrete)
        # Housing channel lip (slightly larger dark frame) and the recessed strip.
        strip_mat = warm if i == 2 else (cobalt if i % 2 == 0 else cobalt_dim)
        beam_curve(f'ribstrip{i}', arch_points(r - 0.047, y, FLOOR_Z, a0=0.25, a1=math.pi - 0.25), 0.008, 0.014, strip_mat)
    # Longitudinal overhead beams tying the ribs together.
    for x in (-0.3, 0.3):
        beam_curve(f'purlin{x}', [(x, 0.2, 0.36), (x, 3.4, 0.36)], 0.035, 0.035, beam_dark)
    beam_curve('spine_beam', [(0, 0.2, 0.44), (0, 3.4, 0.44)], 0.05, 0.04, beam_dark)

    # Mid-ground pillars at the sides, each with a narrow vertical light slot.
    for i, (x, y, h) in enumerate(((-0.36, 0.6, 0.34), (0.38, 0.8, 0.38), (-0.42, 1.5, 0.42), (0.44, 1.8, 0.4))):
        box(f'pillar{i}', (x, y, FLOOR_Z + h / 2), (0.07, 0.07, h), concrete)
        slot = warm if i == 1 else cobalt_dim
        box(f'slot{i}', (x + (0.036 if x < 0 else -0.036), y - 0.012, FLOOR_Z + h * 0.45), (0.003, 0.008, h * 0.6), slot)

    # Back wall with faint vertical light seams, far behind.
    box('backwall', (0, 3.8, 0.6), (4.0, 0.1, 2.0), mat('Wall', '#070a10', 0.6))
    for x in (-0.9, -0.3, 0.3, 0.9):
        box(f'seam{x}', (x, 3.74, 0.25), (0.006, 0.01, 0.6), cobalt_dim)

    # Foreground framing forms, close to the lens (they fall out of focus).
    box('frameL', (-0.42, -0.32, FLOOR_Z + 0.3), (0.09, 0.09, 0.6), beam_dark, rot=(0, 0, 0.5))
    box('frameR', (0.46, -0.28, FLOOR_Z + 0.25), (0.08, 0.08, 0.5), beam_dark, rot=(0, 0, -0.4))

    # Haze: a large volume with forward scattering, so the beams read as shafts of light.
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 1.4, 0.6))
    vol = bpy.context.active_object
    vol.name = 'Haze'
    vol.scale = (5, 6, 2)
    vm = bpy.data.materials.new('HazeVol')
    vm.use_nodes = True
    vnt = vm.node_tree
    vnt.nodes.remove(vnt.nodes['Principled BSDF'])
    pv = vnt.nodes.new('ShaderNodeVolumePrincipled')
    pv.inputs['Density'].default_value = 0.1
    pv.inputs['Anisotropy'].default_value = 0.55
    pv.inputs['Color'].default_value = (*R.srgb('#b9c8ff'), 1)
    vnt.links.new(pv.outputs['Volume'], vnt.nodes['Material Output'].inputs['Volume'])
    vol.data.materials.append(vm)
    vol.visible_shadow = False

    # Focused beams of cobalt light falling from the roof behind the product.
    for x, y, e in ((-0.35, 1.1, 420), (0.4, 1.6, 360), (0.0, 2.4, 520)):
        ld = bpy.data.lights.new(f'beam{x}', 'SPOT')
        ld.energy = e
        ld.color = R.srgb('#4f86ff')
        ld.spot_size = 0.32
        ld.spot_blend = 0.6
        ld.shadow_soft_size = 0.02
        ob = link(bpy.data.objects.new(f'beam{x}', ld))
        ob.location = (x, y, 1.0)
        R.look_at(ob, Vector((x * 0.6, y - 0.1, FLOOR_Z)))

    # Backlight at the far end of the hall: the ribs and pillars read as layered dark silhouettes against it,
    # and the satin floor picks up a soft reflection of it.
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 3.6, 0.45), rotation=(math.pi / 2, 0, 0))
    glow = bpy.context.active_object
    glow.scale = (2.6, 1.3, 1)
    glow.data.materials.append(mat('BackGlow', '#000000', 1.0, emission='#2c62ff', strength=0.38))
    w = R.world_color(R.srgb('#03060d'), 1.0)
    return w


def product_lights():
    """Neutral key that reveals the surfaces, cobalt rims, a small warm kicker. Parented to a rig turned with the camera."""
    rig = link(bpy.data.objects.new('LightRig', None))
    lights = {}
    for name, size, size_y, power, color, loc in (
        ('Key', 0.35, None, 14, (1, 0.98, 0.96), (-0.3, -0.38, 0.32)),
        ('Fill', 0.5, None, 2.0, (0.85, 0.9, 1.0), (0.4, -0.3, 0.02)),
        ('RimL', 0.05, 0.4, 7, R.srgb('#4a82ff'), (-0.32, 0.3, 0.08)),
        ('RimR', 0.05, 0.4, 7, R.srgb('#4a82ff'), (0.34, 0.28, 0.06)),
        ('Warm', 0.06, None, 0.15, R.srgb('#ff9a55'), (0.25, -0.18, -0.1)),
        ('Top', 0.3, None, 3.0, (0.9, 0.94, 1.0), (0.0, 0.05, 0.4)),
    ):
        ob = R.area_light(name, size, power, color, loc, size_y=size_y)
        ob.parent = rig
        ob.data.use_shadow = True
        # Product lights should not light the haze into a white fog.
        ob.visible_volume_scatter = False
        lights[name] = (ob, power)
    return rig, lights


# ---------------------------------------------------------------- shots


def apply_shot(shot, scene, pivot, cam, rig, lights, w, h):
    pivot.rotation_euler = (shot['tilt'], 0, shot['yaw'])
    bpy.context.view_layer.update()
    target = R.obj_centre('leftStick_cap') if shot['focus'] == 'stick' else Vector((0, 0, 0))
    # Blend the target when interpolating between a centre and a stick shot.
    if 'focus_t' in shot:
        target = Vector((0, 0, 0)).lerp(R.obj_centre('leftStick_cap'), shot['focus_t'])
    cam.data.lens = shot['lens']
    cam.data.shift_x = shot['sx']
    cam.data.shift_y = shot['sy']
    R.place_camera(cam, target, shot['dist'], shot['az'], shot['el'])
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = shot['dist']
    cam.data.dof.aperture_fstop = shot['fstop']
    rig.rotation_euler = (0, 0, shot['az'])
    for name, (ob, power) in lights.items():
        mult = shot['key'] if name in ('Key', 'Fill', 'Top') else shot['rim'] if name.startswith('Rim') else 1.0
        ob.data.energy = power * mult
    scene.render.resolution_x, scene.render.resolution_y = w, h


def shot_at(keys, p):
    """Shot at progress p (0..1) across the keys, eased per segment; focus blends smoothly."""
    segs = len(keys) - 1
    x = min(segs - 1e-6, max(0.0, p * segs))
    i = int(x)
    t = ease(x - i)
    s = lerp_shot(keys[i], keys[i + 1], t)
    fa = 1.0 if keys[i]['focus'] == 'stick' else 0.0
    fb = 1.0 if keys[i + 1]['focus'] == 'stick' else 0.0
    s['focus_t'] = fa + (fb - fa) * t
    return s


def setup_cinematic():
    scene, pivot, size = R.open_model()
    R.set_finish('graphite')
    chamber()
    rig, lights = product_lights()
    cam = R.camera(lens=50)
    cam.data.sensor_fit = 'HORIZONTAL'
    scene.cycles.volume_step_rate = 2.0
    scene.cycles.max_bounces = 6
    return scene, pivot, cam, rig, lights


def run_keys(devices):
    scene, pivot, cam, rig, lights = setup_cinematic()
    R.cycles(scene, 1600, 1000, samples=160)
    for dev in devices:
        keys = DESKTOP if dev == 'desktop' else PHONE
        w, h = SIZES[dev]
        cam.data.sensor_fit = 'HORIZONTAL'  # 36 mm across the width on both devices
        for i, k in enumerate(keys):
            s = dict(k, focus_t=1.0 if k['focus'] == 'stick' else 0.0)
            apply_shot(s, scene, pivot, cam, rig, lights, w, h)
            R.render(R.ROOT / 'qa' / 'screenshots' / 'arc-v4' / 'keys' / f'{dev}-{i}.png')


def shot_at_progress(keys, p):
    """Shot at camera progress p (0..1, chapter i at i/(len-1)), linear within a transition: frame spacing and any
    easing come from the frame plan (src/data/journeyFrames.json) and the page, not from here."""
    segs = len(keys) - 1
    x = min(segs - 1e-9, max(0.0, p * segs))
    i = int(x)
    c = x - i
    if p >= 1.0:
        i, c = segs - 1, 1.0
    s = lerp_shot(keys[i], keys[i + 1], c)
    fa = 1.0 if keys[i]['focus'] == 'stick' else 0.0
    fb = 1.0 if keys[i + 1]['focus'] == 'stick' else 0.0
    s['focus_t'] = fa + (fb - fa) * c
    return s


def run_sequence(devices):
    scene, pivot, cam, rig, lights = setup_cinematic()
    R.cycles(scene, 1920, 1200, samples=SEQ_SAMPLES)
    # OIDN keeps fine detail (knurling, grip pebble) better than OptiX and is steadier frame to frame.
    scene.cycles.denoiser = 'OPENIMAGEDENOISE'
    scene.cycles.denoising_use_gpu = True
    scene.cycles.denoising_prefilter = 'ACCURATE'
    scene.cycles.seed = 0  # same noise pattern on every frame, so neighbouring frames blend cleanly
    # Lossless masters (PNG, light compression: lossless WEBP took longer to write than the frame took to render);
    # the shipped WEBP files are encoded from these with encode_journey.py.
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.image_settings.color_depth = '8'
    scene.render.image_settings.compression = 15
    plan = json.loads(PLAN.read_text())
    for dev in devices:
        keys = DESKTOP if dev == 'desktop' else PHONE
        w, h = SIZES[dev]
        cam.data.sensor_fit = 'HORIZONTAL'
        progress = plan[dev]['progress']
        # Chapters first, then a coarse-to-fine order, so a partial run already covers the whole move.
        n = len(progress)
        order = []
        for stride in (n - 1, 48, 24, 12, 6, 3, 1):
            order += [k for k in range(0, n, stride) if k not in order]
        for k in plan[dev]['keys']:
            if k not in order[:8]:
                order.insert(0, k)
        seen = set()
        for f in order:
            if f in seen:
                continue
            seen.add(f)
            out = SEQ_OUT / dev / f'{f:03d}.png'
            if not FORCE and out.with_suffix('.webp').exists():  # an earlier lossless WEBP master
                continue
            # With a range (sequence <device> <from> <to> [samples]) only those frames are (re)rendered;
            # without one, every missing frame is rendered, so an interrupted run resumes where it stopped.
            if FORCE:
                if not FORCE[0] <= f <= FORCE[1]:
                    continue
            elif out.exists():
                continue
            apply_shot(shot_at_progress(keys, progress[f]), scene, pivot, cam, rig, lights, w, h)
            R.render(out)


def setup_stage():
    scene, pivot, size = R.open_model()
    rig, lights = product_lights()
    for name, (ob, power) in lights.items():
        ob.visible_volume_scatter = True
    R.world_color(R.srgb('#0b1322'), 0.12)
    scene.view_settings.exposure = -0.6
    # Shadow catcher under the product (only the shadow is kept on the transparent film).
    bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, FLOOR_Z + 0.02))
    bpy.context.active_object.is_shadow_catcher = True
    # Soft overhead light to ground it.
    R.area_light('Ground', 0.4, 2.0, (0.9, 0.94, 1.0), (0, 0.02, 0.5))
    cam = R.camera(lens=60)
    return scene, pivot, cam, rig, lights


# rim 0: the cobalt rims sit behind the product, so on a turntable they flood the back shell blue when it faces them;
# a configurator should show the finishes' true colours.
STAGE = dict(tilt=0.22, az=0.0, el=0.16, dist=0.41, lens=60, sx=0.0, sy=0.02, focus='centre', fstop=18.0, key=1.0, rim=0.0, haze=0.0)
TURN_FRAMES = 96  # 3.75 degrees apart, so neighbouring frames blend into continuous rotation
TURN_START = 0.42  # yaw of frame 0: the configurator's opening three-quarter view
# The shipped set was rendered at 1440x1080 / WEBP 88 and downscaled to 1200x900 / WEBP 85 with reencode.py
# (transparent frames compress poorly; 1200 px still displays 1:1 at 125% scaling).
TURN_SIZE = (1200, 900)
# Written here, then copied to public/spin/<finish>/ once a full set is done.
SPIN_OUT = R.ROOT / 'work' / 'spin-hd'


def run_turntable(finishes):
    scene, pivot, cam, rig, lights = setup_stage()
    R.cycles(scene, *TURN_SIZE, samples=96, transparent=True)
    scene.cycles.denoiser = 'OPENIMAGEDENOISE'
    scene.cycles.denoising_use_gpu = True
    scene.cycles.seed = 0
    scene.render.image_settings.file_format = 'WEBP'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.quality = 85
    for fin in finishes:
        R.set_finish(fin)
        for f in range(TURN_FRAMES):
            if FORCE and not FORCE[0] <= f <= FORCE[1]:
                continue
            out = SPIN_OUT / fin / f'{f:02d}.webp'
            s = dict(STAGE, yaw=TURN_START + f / TURN_FRAMES * math.tau, focus_t=0.0)
            apply_shot(s, scene, pivot, cam, rig, lights, *TURN_SIZE)
            R.render(out)


def run_thumbs():
    scene, pivot, cam, rig, lights = setup_stage()
    R.cycles(scene, 480, 480, samples=96, transparent=True)
    for fin in R.FINISHES:
        R.set_finish(fin)
        s = dict(STAGE, yaw=TURN_START, dist=0.42, sy=0.0, focus_t=0.0)
        apply_shot(s, scene, pivot, cam, rig, lights, 480, 480)
        R.render(R.ROOT / 'public' / 'renders' / f'thumb-{fin}.png')


DEVICES = ['desktop', 'phone'] if OPT in (None, 'both') else [OPT]
FORCE = (int(ARGS[2]), int(ARGS[3])) if len(ARGS) > 3 else None
SEQ_SAMPLES = int(ARGS[4]) if len(ARGS) > 4 else 96
if MODE == 'keys':
    run_keys(DEVICES)
elif MODE == 'sequence':
    run_sequence(DEVICES)
elif MODE == 'turntable':
    run_turntable(list(R.FINISHES) if OPT is None else [OPT])
elif MODE == 'thumbs':
    run_thumbs()
