"""Render research candidates in an isolated Blender background process.

This does not open, modify or save any existing Blender project.
Run with Blender --background --factory-startup --python <this file>.
"""
from pathlib import Path
import json
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent / 'candidates'

def point_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()

for name in ['innerscene-controller', 'innerscene-gamepad']:
    path = ROOT / f'{name}.glb'
    if not path.exists():
        continue
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(path))
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    corners = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    lower = Vector(tuple(min(c[i] for c in corners) for i in range(3)))
    upper = Vector(tuple(max(c[i] for c in corners) for i in range(3)))
    centre = (lower + upper) / 2
    scale = 2.7 / max(upper - lower)
    root = bpy.data.objects.new('Review normalization', None)
    bpy.context.collection.objects.link(root)
    top_objects = [o for o in list(bpy.context.scene.objects) if o != root and o.parent is None]
    for obj in top_objects:
        obj.parent = root
    root.scale = (scale,) * 3
    root.location = -centre * scale
    bpy.context.view_layer.update()
    bottom = min((o.matrix_world @ Vector(c)).z for o in meshes for c in o.bound_box)
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, bottom - 0.025))
    floor = bpy.context.object
    material = bpy.data.materials.new('Neutral review floor')
    material.diffuse_color = (0.17, 0.18, 0.20, 1)
    floor.data.materials.append(material)
    world = bpy.data.worlds.new('Neutral studio world')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.45, 0.45, 0.45, 1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.5
    bpy.context.scene.world = world
    for label, loc, power, size in [
        ('Soft key', (-3, -4, 6), 650, 4),
        ('Soft fill', (4, 1, 3), 380, 3),
        ('Rear separation', (-2, 4, 4), 500, 3),
    ]:
        data = bpy.data.lights.new(label, 'AREA')
        data.energy = power
        data.shape = 'DISK'
        data.size = size
        obj = bpy.data.objects.new(label, data)
        bpy.context.collection.objects.link(obj)
        obj.location = loc
        point_at(obj, (0, 0, 0))
    cam_data = bpy.data.cameras.new('Review camera')
    cam = bpy.data.objects.new('Review camera', cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (2.8, -4, 4.0)
    point_at(cam, (0, 0, 0))
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = 3.65
    scene = bpy.context.scene
    scene.camera = cam
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 20
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 800
    scene.render.resolution_y = 800
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(ROOT / f'{name}-studio.png')
    scene.view_settings.view_transform = 'AgX'
    bpy.ops.render.render(write_still=True)
    summary = {
        'source_file': path.name,
        'mesh_count': len(meshes),
        'mesh_names': [o.name for o in meshes],
        'materials': [m.name for m in bpy.data.materials if m.name != 'Neutral review floor'],
        'triangles': sum(len(o.data.loop_triangles) or sum(len(p.vertices)-2 for p in o.data.polygons) for o in meshes),
        'dimensions_before_normalization': list(upper-lower),
        'render': f'{name}-studio.png',
    }
    (ROOT / f'{name}-inspection.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
