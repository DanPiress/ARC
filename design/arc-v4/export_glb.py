"""Exports an optimised web GLB of the ARC model: decimated meshes, Draco compression, material groups kept.
  blender --background --factory-startup --python design/arc-v4/export_glb.py
Writes design/arc-v4/arc.glb
"""
import pathlib

import bpy

HERE = pathlib.Path(__file__).resolve().parent
bpy.ops.wm.open_mainfile(filepath=str(HERE / 'arc.blend'))

# Fonts and curves become meshes; dense field meshes are decimated to a web budget.
TARGET_RATIO = {'shell_front': 0.12, 'shell_back': 0.12, 'shell_grip': 0.12, 'shell_spine': 0.2,
                'shell_bumper': 0.2, 'shell_trigger': 0.2, 'dpad': 0.15, 'buttons': 0.15, 'centre_plastic': 0.2}
for ob in list(bpy.data.objects):
    if ob.type == 'MESH':
        ratio = TARGET_RATIO.get(ob.name, 0.2 if len(ob.data.vertices) > 20000 else 1.0)
        if ratio < 1.0:
            mod = ob.modifiers.new('decimate', 'DECIMATE')
            mod.ratio = ratio

bpy.ops.export_scene.gltf(
    filepath=str(HERE / 'arc.glb'),
    export_format='GLB',
    export_apply=True,
    export_draco_mesh_compression_enable=True,
    export_draco_mesh_compression_level=7,
    export_yup=True,
    export_texcoords=False,
)
total = sum(len(o.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.polygons) for o in bpy.data.objects if o.type == 'MESH')
print('exported', HERE / 'arc.glb', 'faces', total, 'bytes', (HERE / 'arc.glb').stat().st_size)
