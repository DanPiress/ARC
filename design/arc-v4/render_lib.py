"""Shared helpers for ARC renders: load the model, finishes, pivot, camera, Cycles GPU setup."""
import math
import pathlib

import bpy
from mathutils import Euler, Matrix, Vector

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent  # project root

FINISHES = {
    # shell colour, shell metal, shell roughness, grip colour, spine colour, spine roughness
    'graphite': ('#1c1f24', 0.0, 0.5, '#131518', '#7c7f84', 0.36),
    'silver': ('#a3a7ad', 1.0, 0.4, '#17191c', '#3e4147', 0.3),
    'ember': ('#6b2a0e', 0.0, 0.48, '#15171a', '#7c7f84', 0.36),
}


def srgb(h):
    h = h.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


def open_model():
    bpy.ops.wm.open_mainfile(filepath=str(HERE / 'arc.blend'))
    scene = bpy.context.scene
    root = bpy.data.objects['ARC_root']
    # Pivot at the product's centre so turning the pivot turns the controller in place.
    bpy.context.view_layer.update()
    pts = []
    for ob in bpy.data.collections['ARC'].all_objects:
        if ob.type in ('MESH', 'CURVE', 'FONT'):
            pts += [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    centre = (lo + hi) / 2
    pivot = bpy.data.objects.new('ARC_pivot', None)
    scene.collection.objects.link(pivot)
    root.location -= centre
    root.parent = pivot
    size = hi - lo
    return scene, pivot, size


def set_finish(name):
    shell, metal, rough, grip, spine, spine_rough = FINISHES[name]

    def bsdf(mat):
        return bpy.data.materials[mat].node_tree.nodes['Principled BSDF']

    def mix_a(mat):
        node = bpy.data.materials[mat].node_tree.nodes['ShellColor']
        return [s for s in node.inputs if s.type == 'RGBA'][0]

    for mat in ('ARC_Shell',):
        mix_a(mat).default_value = (*srgb(shell), 1)
        b = bsdf(mat)
        b.inputs['Metallic'].default_value = metal
        b.inputs['Roughness'].default_value = rough
        b.inputs['Coat Weight'].default_value = 0.0 if metal > 0.5 else 0.12
    bsdf('ARC_Grip').inputs['Base Color'].default_value = (*srgb(grip), 1)
    mix_a('ARC_Spine').default_value = (*srgb(spine), 1)
    bsdf('ARC_Spine').inputs['Roughness'].default_value = spine_rough


def cycles(scene, w, h, samples=128, transparent=False):
    scene.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'
    prefs.refresh_devices()
    for d in prefs.devices:
        d.use = d.type == 'OPTIX'
    scene.cycles.device = 'GPU'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = 'OPTIX'
    scene.cycles.use_adaptive_sampling = True
    scene.render.resolution_x = w
    scene.render.resolution_y = h
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = transparent
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'AgX - Medium High Contrast'
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA' if transparent else 'RGB'


def area_light(name, size, power, color, loc, target=(0, 0, 0), size_y=None):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = power
    ld.color = color
    if size_y:
        ld.shape = 'RECTANGLE'
        ld.size, ld.size_y = size, size_y
    else:
        ld.size = size
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    look_at(ob, Vector(target))
    bpy.context.scene.collection.objects.link(ob)
    return ob


def look_at(ob, target):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def camera(name='Cam', lens=85.0):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.sensor_width = 36
    ob = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.scene.camera = ob
    return ob


def place_camera(cam, target, dist, az, el):
    """Orbit: az 0 = in front (-Y), positive az moves the camera to the right; el above."""
    t = Vector(target)
    cam.location = t + Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))) * dist
    look_at(cam, t)


def world_color(rgb, strength=1.0):
    w = bpy.data.worlds.new('World')
    w.use_nodes = True
    bg = w.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (*rgb, 1)
    bg.inputs['Strength'].default_value = strength
    bpy.context.scene.world = w
    return w


def obj_centre(name):
    ob = bpy.data.objects[name]
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return sum(pts, Vector()) / len(pts)


def render(path):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
