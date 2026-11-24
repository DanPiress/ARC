"""Builds the ARC controller in Blender and saves design/arc-v4/arc.blend.

Run (factory startup, background):
  blender --background --factory-startup --python design/arc-v4/build_arc.py

Modelling method
- Every moulded part is a signed distance field (negative inside) built from constructive operations:
  smooth unions for the body, rounded intersections for controlled edge radii, and subtractions for the wells,
  port, bumper pockets and trigger scoops. Parting gaps between parts are real (about 0.3 mm).
- Each field is sampled on a fine grid (0.36 mm for the shell, 0.15 mm for small controls) and meshed with
  OpenVDB, giving smooth, watertight surfaces with consistent seams.
- Legends and wordmarks are real text geometry. Materials live on separate parts (shell, grip, spine, plastic,
  rubber, metal, buttons, liner, legend, accent) so finishes can be swapped coherently.

Raw units: 1 unit = 12 mm. X width, Y height, +Z toward the viewer. The root converts to metres, Z up.
"""
import math
import pathlib

import bpy
import numpy as np
import openvdb as vdb

OUT = pathlib.Path(__file__).resolve().parent
SCALE = 0.012  # raw unit -> metres

# ---------------------------------------------------------------- field helpers (numpy, vectorised)


def sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def smin(a, b, k):
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def smax(a, b, k):
    return -smin(-a, -b, k)


def round_box2(px, py, bx, by, r):
    qx = np.abs(px) - bx + r
    qy = np.abs(py) - by + r
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def round_box3(px, py, pz, bx, by, bz, r):
    qx = np.abs(px) - bx + r
    qy = np.abs(py) - by + r
    qz = np.abs(pz) - bz + r
    out = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2 + np.maximum(qz, 0) ** 2)
    return out + np.minimum(np.maximum(np.maximum(qx, qy), qz), 0) - r


def taper_capsule(px, py, ax, ay, bx, by, ra, rb):
    dx, dy = bx - ax, by - ay
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy), 0, 1)
    return np.hypot(px - ax - dx * t, py - ay - dy * t) - (ra + (rb - ra) * t)


def round_intersect(a, b, r):
    qx = a + r
    qy = b + r
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def rounded_cylinder(px, py, pz, r, half_h, edge):
    """Cylinder along Z, centred at the origin, with rounded rims."""
    d_r = np.hypot(px, py) - r + edge
    d_z = np.abs(pz) - half_h + edge
    return np.hypot(np.maximum(d_r, 0), np.maximum(d_z, 0)) + np.minimum(np.maximum(d_r, d_z), 0) - edge


# ---------------------------------------------------------------- layout (front view, raw units)

LAYOUT = {
    'leftStick': (-3.85, 0.85),
    'rightStick': (2.05, -1.45),
    'dpad': (-2.3, -1.55),
    'face': (3.75, 0.75),
    'home': (0.0, 0.02),
    'menu': (-1.38, 0.98),
    'view': (1.38, 0.98),
    'slit': (0.0, -1.4),
    'logo': (0.0, 2.32),
}
FACE_GAP = 0.9
FACE_R = 0.4
STICK_R, STICK_DEPTH = 1.12, 0.46
SHOULDER = (4.95, 1.95)
GAP = 0.025  # parting gap between mouldings, ~0.3 mm


def gripness(ax, y):
    return sstep(0.8, -3.4, y) * sstep(2.4, 5.2, ax)


def z_front(ax, y):
    return 1.12 - 0.0062 * ax * ax - 0.016 * (y - 0.9) ** 2


def z_back(ax, y):
    return (-0.95 - 1.7 * gripness(ax, y) - 0.5 * sstep(1.0, 2.9, y) * sstep(2.0, 4.2, ax)
            + 0.006 * ax * ax + 0.018 * (y - 0.4) ** 2)


def silhouette(ax, y):
    # Broad upper body with a slight dip at the top centre, rounded shoulders.
    core = round_box2(ax, y - 0.35 + 0.16 * np.exp(-ax * ax / 5), 4.85, 2.95, 1.5)
    shoulder = np.hypot(ax - SHOULDER[0], y - SHOULDER[1]) - 1.72
    # Grips angle outward and taper to a full rounded tip.
    grip = taper_capsule(ax, y, 4.95, 0.3, 5.55, -3.85, 2.02, 1.36)
    return smin(smin(core, shoulder, 1.4), grip, 1.7)


def body_base(ax, y, z):
    d2 = silhouette(ax, y)
    slab = np.maximum(z - z_front(ax, y), z_back(ax, y) - z)
    # Controlled edge radius: crisper around the face and shoulders (a defined top plane), fuller on the grips.
    return round_intersect(d2, slab, 0.5 + 0.42 * gripness(ax, y))


def wells():
    w = [
        (*LAYOUT['leftStick'], STICK_R, STICK_DEPTH, 0.2),
        (*LAYOUT['rightStick'], STICK_R, STICK_DEPTH, 0.2),
        (*LAYOUT['dpad'], 1.06, 0.2, 0.14),
        (*LAYOUT['home'], 0.37, 0.07, 0.04),
    ]
    fx, fy = LAYOUT['face']
    for dx, dy in ((0, FACE_GAP), (FACE_GAP, 0), (0, -FACE_GAP), (-FACE_GAP, 0)):
        w.append((fx + dx, fy + dy, FACE_R + 0.07, 0.1, 0.05))
    return [(x, y, r, d, k, float(z_front(abs(x), y))) for x, y, r, d, k in w]


WELLS = wells()


def bumper_zone(ax, y, z):
    d2 = silhouette(ax, y)
    px, py = ax - SHOULDER[0], y - SHOULDER[1]
    ang = np.arctan2(py, px)
    rad = np.maximum(1.0, np.hypot(px, py))
    along = np.maximum(0.3 - ang, ang - 2.5) * rad
    inner = -(d2 + 0.5)
    depth = np.abs(z + 0.12) - 0.42
    return smax(smax(inner, depth, 0.12), along, 0.35)


def trigger_zone(ax, y, z):
    return round_box3(ax - 4.85, y - 3.05, z + 1.75, 1.35, 1.05, 0.95, 0.4)


def seam_field(ax, y, z):
    return z - (0.5 * (z_front(ax, y) + z_back(ax, y)) + 0.22)


def shell_fields(x, y, z):
    """All shell parts on one grid chunk. Returns dict of signed distances (negative inside)."""
    ax = np.abs(x)
    base = body_base(ax, y, z)
    body = base.copy()
    for wx, wy, r, depth, k, top in WELLS:
        dw = np.maximum(np.hypot(x - wx, y - wy) - r, (top - depth) - z)
        body = smax(body, -dw, k)
    bz = bumper_zone(ax, y, z)
    tz = trigger_zone(ax, y, z)
    body = smax(body, -(bz - 0.04), 0.03)
    body = smax(body, -(tz - 0.04), 0.03)
    port = round_box3(ax, y - 3.14, z + 0.25, 0.45, 0.3, 0.13, 0.1)
    body = smax(body, -port, 0.03)

    seam = seam_field(ax, y, z)
    spine = np.minimum(0.74 + 0.27 * sstep(-2.9, 3.3, y) - ax, seam)
    dx, dy = ax - 5.0, y + 1.35
    grip_front = (dx - 0.95 * dy) / 1.38 + 0.03 * (dx * dx + dy * dy)
    grip_zone = np.maximum(grip_front, np.minimum(-seam, (gripness(ax, y) - 0.32) * 4.0))

    half = GAP / 2
    out = {
        'spine': np.maximum(body, -spine + half),
        'grip': np.maximum(body, -grip_zone + half),
        'front': np.maximum(np.maximum(np.maximum(body, -seam + half), spine + half), grip_zone + half),
        'back': np.maximum(np.maximum(body, seam + half), grip_zone + half),
    }
    # Bumpers: the shoulder surface grown proud inside its zone; triggers likewise, with a finger scoop.
    out['bumper'] = smax(base - 0.09, bz, 0.06)
    grow = 0.08 + 0.22 * sstep(-1.2, -2.4, z)
    trig = smax(base - grow, tz, 0.08)
    scoop = np.sqrt((ax - 4.95) ** 2 + (y - 3.55) ** 2 + (z + 2.55) ** 2) - 0.85
    out['trigger'] = smax(trig, -scoop, 0.18)
    return out


# ---------------------------------------------------------------- meshing


def mesh_field(name, fn, lo, hi, h, keys=None):
    """Samples fn over [lo, hi] at spacing h (chunked along X) and meshes each requested key with OpenVDB."""
    nx, ny, nz = (int(math.ceil((hi[i] - lo[i]) / h)) + 1 for i in range(3))
    ys = (lo[1] + np.arange(ny) * h).astype(np.float32)[None, :, None]
    zs = (lo[2] + np.arange(nz) * h).astype(np.float32)[None, None, :]
    fields = {}
    step = 24
    for i0 in range(0, nx, step):
        i1 = min(nx, i0 + step)
        xs = (lo[0] + np.arange(i0, i1) * h).astype(np.float32)[:, None, None]
        X, Y, Z = np.broadcast_arrays(xs, ys, zs)
        res = fn(X, Y, Z)
        if not isinstance(res, dict):
            res = {name: res}
        for k, v in res.items():
            if keys and k not in keys:
                continue
            if k not in fields:
                fields[k] = np.empty((nx, ny, nz), np.float32)
            fields[k][i0:i1] = v
    objs = {}
    band = 3 * h
    for k, arr in fields.items():
        grid = vdb.FloatGrid(band)
        grid.copyFromArray(np.clip(arr, -band, band), tolerance=0)
        pts, tris, quads = grid.convertToPolygons(isovalue=0.0, adaptivity=0.0)
        pts = np.asarray(pts, np.float64) * h + np.asarray(lo)
        objs[k] = make_mesh(f'{name}_{k}' if k != name else name, pts, np.asarray(quads), np.asarray(tris))
        print(f'meshed {k}: {len(pts)} verts')
    return objs


def make_mesh(name, pts, quads, tris):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(pts))
    me.vertices.foreach_set('co', pts.astype(np.float32).ravel())
    nq, nt = len(quads), len(tris)
    loops = np.concatenate([quads.ravel(), tris.ravel()]).astype(np.int32)
    starts = np.concatenate([np.arange(nq) * 4, nq * 4 + np.arange(nt) * 3]).astype(np.int32)
    me.loops.add(len(loops))
    me.loops.foreach_set('vertex_index', loops)
    me.polygons.add(nq + nt)
    me.polygons.foreach_set('loop_start', starts)
    me.validate()
    me.update(calc_edges=True)
    # OpenVDB winds faces inward for a negative-inside field; flip so normals face out.
    me.flip_normals()
    me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    return ob


# ---------------------------------------------------------------- small controls as fields


def local_box(cx, cy, cz, rx, ry, rz):
    return (cx - rx, cy - ry, cz - rz), (cx + rx, cy + ry, cz + rz)


def stick_fields(cx, cy):
    floor = float(z_front(abs(cx), cy)) - STICK_DEPTH
    top = floor + 1.08  # cap top about 0.6 (7 mm) above the shell surface

    def fn(x, y, z):
        px, py = x - cx, y - cy
        r = np.hypot(px, py)
        # Gimbal skirt: a low convex dome covering the well floor, rising gently to the stem.
        skirt = np.maximum(np.sqrt(r * r + ((z - floor + 0.55) / 0.72) ** 2) - 1.02, floor - 0.06 - z)
        stem = rounded_cylinder(px, py, z - (floor + 0.4), 0.46, 0.4, 0.05)
        base = smin(skirt, stem, 0.16)
        # Cap: a broad puck with a soft outer rim, a raised lip and a clearly concave dish.
        cap = rounded_cylinder(px, py, z - (top - 0.2), 0.86, 0.2, 0.12)
        dish = np.sqrt(r * r + (z - (top + 2.2 - 0.15)) ** 2) - 2.2
        cap = smax(cap, -dish, 0.05)
        return {'base': base, 'cap': cap}

    lo, hi = local_box(cx, cy, floor + 0.5, 1.15, 1.15, 0.75)
    return mesh_field('stick', fn, lo, hi, 0.012)


def dpad_field(cx, cy):
    floor = float(z_front(abs(cx), cy)) - 0.2

    def fn(x, y, z):
        px, py = x - cx, y - cy
        arms = np.minimum(round_box2(px, py, 0.3, 0.86, 0.12), round_box2(px, py, 0.86, 0.3, 0.12))
        zc = floor + 0.14
        slab = np.abs(z - zc) - 0.1
        pad = round_intersect(arms, slab, 0.07)
        # Arms rise slightly to their tips, centre dished.
        dish = np.sqrt(px * px + py * py + (z - (zc + 1.6)) ** 2) - 1.62
        return smax(pad, -dish, 0.05)

    lo, hi = local_box(cx, cy, floor + 0.14, 0.95, 0.95, 0.25)
    return mesh_field('dpad', fn, lo, hi, 0.01)['dpad']


def face_buttons_field():
    fx, fy = LAYOUT['face']
    spots = [(fx, fy + FACE_GAP), (fx + FACE_GAP, fy), (fx, fy - FACE_GAP), (fx - FACE_GAP, fy)]

    def fn(x, y, z):
        d = None
        for bx, by in spots:
            floor = float(z_front(abs(bx), by)) - 0.1
            px, py = x - bx, y - by
            b = rounded_cylinder(px, py, z - (floor + 0.08), FACE_R, 0.11, 0.07)
            crown = np.sqrt(px * px + py * py + (z - (floor + 0.19 - 3.0)) ** 2) - 3.0
            b = smax(b, crown, 0.03)
            d = b if d is None else np.minimum(d, b)
        return d

    lo = (fx - FACE_GAP - 0.5, fy - FACE_GAP - 0.5, 0.6)
    hi = (fx + FACE_GAP + 0.5, fy + FACE_GAP + 0.5, 1.2)
    return mesh_field('buttons', fn, lo, hi, 0.012)['buttons'], spots


def centre_controls_field():
    hx, hy = LAYOUT['home']

    def fn(x, y, z):
        out = {}
        pills = None
        for key in ('menu', 'view'):
            px0, py0 = LAYOUT[key]
            zc = float(z_front(abs(px0), py0)) + 0.03
            p = round_box3(x - px0, y - py0, z - zc, 0.34, 0.16, 0.08, 0.07)
            pills = p if pills is None else np.minimum(pills, p)
        floor = float(z_front(0, hy)) - 0.07
        home = rounded_cylinder(x - hx, y - hy, z - (floor + 0.07), 0.3, 0.08, 0.05)
        out['plastic'] = np.minimum(pills, home)
        sx, sy = LAYOUT['slit']
        out['slit'] = round_box3(x - sx, y - sy, z - (float(z_front(0, sy)) - 0.01), 0.04, 0.3, 0.05, 0.035)
        return out

    lo, hi = (-1.9, -1.9, 0.7), (1.9, 1.3, 1.35)
    return mesh_field('centre', fn, lo, hi, 0.01)


# ---------------------------------------------------------------- materials


def node_mat(name, color, rough, metal=0.0, coat=0.0, coat_rough=0.3, spec=0.5, emission=None, strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = metal
    bsdf.inputs['Coat Weight'].default_value = coat
    bsdf.inputs['Coat Roughness'].default_value = coat_rough
    bsdf.inputs['Specular IOR Level'].default_value = spec
    if emission:
        bsdf.inputs['Emission Color'].default_value = (*emission, 1)
        bsdf.inputs['Emission Strength'].default_value = strength
    return m


def srgb(h):
    h = h.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


def add_bump(mat, kind, scale, strength, distance):
    """Procedural micro detail in object space (no UVs needed)."""
    nt = mat.node_tree
    bsdf = nt.nodes['Principled BSDF']
    coord = nt.nodes.new('ShaderNodeTexCoord')
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = strength
    bump.inputs['Distance'].default_value = distance
    if kind == 'pebble':
        tex = nt.nodes.new('ShaderNodeTexVoronoi')
        tex.feature = 'SMOOTH_F1'
        tex.inputs['Scale'].default_value = scale
        tex.inputs['Randomness'].default_value = 0.9
        nt.links.new(coord.outputs['Object'], tex.inputs['Vector'])
        inv = nt.nodes.new('ShaderNodeMath')
        inv.operation = 'SUBTRACT'
        inv.inputs[0].default_value = 1.0
        nt.links.new(tex.outputs['Distance'], inv.inputs[1])
        nt.links.new(inv.outputs[0], bump.inputs['Height'])
    elif kind == 'fine':
        tex = nt.nodes.new('ShaderNodeTexNoise')
        tex.inputs['Scale'].default_value = scale
        tex.inputs['Detail'].default_value = 4
        nt.links.new(coord.outputs['Object'], tex.inputs['Vector'])
        nt.links.new(tex.outputs['Fac'], bump.inputs['Height'])
    elif kind == 'brushed':
        mapping = nt.nodes.new('ShaderNodeMapping')
        mapping.inputs['Scale'].default_value = (scale, 2.0, scale)  # streaks run along Z (vertical)
        tex = nt.nodes.new('ShaderNodeTexNoise')
        tex.inputs['Scale'].default_value = 1.0
        tex.inputs['Detail'].default_value = 6
        nt.links.new(coord.outputs['Object'], mapping.inputs['Vector'])
        nt.links.new(mapping.outputs['Vector'], tex.inputs['Vector'])
        nt.links.new(tex.outputs['Fac'], bump.inputs['Height'])
    elif kind == 'dimple':
        tex = nt.nodes.new('ShaderNodeTexVoronoi')
        tex.feature = 'F1'
        tex.inputs['Scale'].default_value = scale
        tex.inputs['Randomness'].default_value = 0.15
        nt.links.new(coord.outputs['Object'], tex.inputs['Vector'])
        ramp = nt.nodes.new('ShaderNodeMapRange')
        ramp.inputs['From Min'].default_value = 0.1
        ramp.inputs['From Max'].default_value = 0.42
        nt.links.new(tex.outputs['Distance'], ramp.inputs['Value'])
        nt.links.new(ramp.outputs['Result'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])


def well_liner(mat, liner_rgb):
    """Darkens the shell inside the control wells using the 'well' vertex attribute."""
    nt = mat.node_tree
    bsdf = nt.nodes['Principled BSDF']
    attr = nt.nodes.new('ShaderNodeAttribute')
    attr.attribute_name = 'well'
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    # The Mix node has float, vector and colour sockets that share the names A/B: pick the colour ones.
    col = [s for s in mix.inputs if s.type == 'RGBA']
    col[1].default_value = (*liner_rgb, 1)
    col[0].default_value = bsdf.inputs['Base Color'].default_value[:]
    fac = [s for s in mix.inputs if s.name == 'Factor' and s.type == 'VALUE'][0]
    nt.links.new(attr.outputs['Fac'], fac)
    out = [s for s in mix.outputs if s.type == 'RGBA'][0]
    nt.links.new(out, bsdf.inputs['Base Color'])
    mix.name = 'ShellColor'


def mark_wells(ob):
    """Vertex attribute 'well' = 1 on the shell surface inside each control well (walls and floor)."""
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3, np.float32)
    me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    val = np.zeros(n, np.float32)
    for wx, wy, r, depth, k, top in WELLS:
        inside = (np.hypot(co[:, 0] - wx, co[:, 1] - wy) < r + 0.02) & (co[:, 2] < top - 0.015)
        val[inside] = 1.0
    attr = me.attributes.new('well', 'FLOAT', 'POINT')
    attr.data.foreach_set('value', val)


# ---------------------------------------------------------------- text and small geometry


def text_obj(name, body, size, x, y, z, mat, depth=0.012, align='CENTER', rot_y=0.0):
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = body
    cu.size = size
    cu.align_x = align
    cu.align_y = 'CENTER'
    cu.extrude = depth
    cu.space_character = 1.25 if body.isalpha() and len(body) > 1 else 1.0
    ob = bpy.data.objects.new(name, cu)
    ob.location = (x, y, z)
    ob.rotation_euler = (0, rot_y, 0)
    ob.data.materials.append(mat)
    return ob


def rim_bezel(name, cx, cy, r, tube, mat):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = tube
    cu.bevel_resolution = 4
    sp = cu.splines.new('POLY')
    n = 180
    sp.points.add(n - 1)
    for i in range(n):
        t = i / n * math.tau
        px, py = cx + math.cos(t) * r, cy + math.sin(t) * r
        sp.points[i].co = (px, py, float(z_front(abs(px), py)) - tube * 0.9, 1)
    sp.use_cyclic_u = True
    ob = bpy.data.objects.new(name, cu)
    ob.data.materials.append(mat)
    return ob


def house_icon(name, x, y, z, mat):
    """Small outlined house: a closed poly curve with a round bevel."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = 0.012
    cu.bevel_resolution = 2
    sp = cu.splines.new('POLY')
    pts = [(-0.1, -0.1), (-0.1, 0.03), (0, 0.12), (0.1, 0.03), (0.1, -0.1)]
    sp.points.add(len(pts) - 1)
    for i, (px, py) in enumerate(pts):
        sp.points[i].co = (x + px, y + py, z, 1)
    sp.use_cyclic_u = True
    ob = bpy.data.objects.new(name, cu)
    ob.data.materials.append(mat)
    return ob


def bar(name, x, y, z, sx, sy, sz, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z))
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = (sx, sy, sz)
    ob.data.materials.append(mat)
    return ob


# ---------------------------------------------------------------- build


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    coll = bpy.data.collections.new('ARC')
    bpy.context.scene.collection.children.link(coll)
    root = bpy.data.objects.new('ARC_root', None)
    coll.objects.link(root)

    M = {
        'shell': node_mat('ARC_Shell', srgb('#1c1f24'), 0.5, coat=0.12, coat_rough=0.5),
        'grip': node_mat('ARC_Grip', srgb('#131518'), 0.72),
        'spine': node_mat('ARC_Spine', srgb('#7c7f84'), 0.36, metal=1.0),
        'plastic': node_mat('ARC_Plastic', srgb('#17191d'), 0.42, coat=0.3, coat_rough=0.35),
        'buttons': node_mat('ARC_Buttons', srgb('#1d1f23'), 0.42, coat=0.3, coat_rough=0.35, spec=0.4),
        'rubber': node_mat('ARC_Rubber', srgb('#1a1b1e'), 0.8, spec=0.3),
        'metal': node_mat('ARC_Metal', srgb('#8b8e93'), 0.42, metal=1.0),
        'liner': node_mat('ARC_Liner', srgb('#090a0c'), 0.65),
        'legend': node_mat('ARC_Legend', srgb('#e4e9f0'), 0.5, emission=srgb('#cfd6e0'), strength=0.15),
        'engrave': node_mat('ARC_Engrave', srgb('#34373c'), 0.4, metal=0.6),
        'accent': node_mat('ARC_Accent', srgb('#ff8a2a'), 0.3, emission=srgb('#ff7a1a'), strength=5.0),
        'port': node_mat('ARC_Port', srgb('#050506'), 0.6),
    }
    # Texture coordinates are the parts' own raw units (1 unit = 12 mm), so scale N gives features ~12/N mm.
    add_bump(M['shell'], 'fine', 70.0, 0.06, 0.004)
    add_bump(M['grip'], 'pebble', 15.0, 0.45, 0.02)
    add_bump(M['spine'], 'brushed', 260.0, 0.05, 0.004)
    add_bump(M['rubber'], 'dimple', 13.0, 0.6, 0.02)
    add_bump(M['metal'], 'fine', 120.0, 0.04, 0.002)
    well_liner(M['shell'], srgb('#0a0b0d'))
    well_liner(M['spine'], srgb('#0a0b0d'))

    parts = []
    shell = mesh_field('shell', shell_fields, (-7.7, -6.0, -3.4), (7.7, 4.7, 1.7), 0.03)
    for key, mat in (('front', 'shell'), ('back', 'shell'), ('spine', 'spine'), ('grip', 'grip'),
                     ('bumper', 'plastic'), ('trigger', 'plastic')):
        ob = shell[key]
        ob.data.materials.append(M[mat])
        if key in ('front', 'spine'):
            mark_wells(ob)
        parts.append(ob)

    for key in ('leftStick', 'rightStick'):
        st = stick_fields(*LAYOUT[key])
        st['base'].data.materials.append(M['plastic'])
        st['cap'].data.materials.append(M['rubber'])
        st['base'].name, st['cap'].name = f'{key}_base', f'{key}_cap'
        parts += [st['base'], st['cap']]
    dp = dpad_field(*LAYOUT['dpad'])
    dp.data.materials.append(M['metal'])
    parts.append(dp)
    fb, spots = face_buttons_field()
    fb.data.materials.append(M['buttons'])
    parts.append(fb)
    cc = centre_controls_field()
    cc['plastic'].data.materials.append(M['plastic'])
    cc['slit'].data.materials.append(M['accent'])
    parts += [cc['plastic'], cc['slit']]

    for key, r, tube in (('leftStick', STICK_R + 0.01, 0.035), ('rightStick', STICK_R + 0.01, 0.035), ('dpad', 1.07, 0.03)):
        parts.append(rim_bezel(f'{key}_bezel', *LAYOUT[key], r, tube, M['liner']))

    # Legends on the face buttons, icons on the centre keys, wordmarks.
    for (bx, by), letter in zip(spots, 'YBAX'):
        top = float(z_front(abs(bx), by)) - 0.1 + 0.19
        parts.append(text_obj(f'legend_{letter}', letter, 0.36, bx, by - 0.01, top - 0.004, M['legend'], depth=0.006))
    mx, my = LAYOUT['menu']
    mz = float(z_front(abs(mx), my)) + 0.03 + 0.08
    for i in (-1, 0, 1):
        parts.append(bar(f'menu_icon_{i}', mx, my + i * 0.055, mz, 0.2, 0.022, 0.012, M['legend']))
    vx, vy = LAYOUT['view']
    vz = float(z_front(abs(vx), vy)) + 0.03 + 0.08
    for ox, oy in ((-0.03, -0.02), (0.03, 0.02)):
        for sx, sy, w, h in ((0, 0.055, 0.12, 0.018), (0, -0.055, 0.12, 0.018), (0.06, 0, 0.018, 0.12), (-0.06, 0, 0.018, 0.12)):
            parts.append(bar('view_icon', vx + ox + sx, vy + oy + sy, vz, w, h, 0.012, M['legend']))
    hx, hy = LAYOUT['home']
    hz = float(z_front(0, hy)) - 0.07 + 0.15
    parts.append(house_icon('home_icon', hx, hy, hz, M['legend']))
    lx, ly = LAYOUT['logo']
    # Sits just proud of the curved spine so every letter shows fully.
    parts.append(text_obj('logo', 'ARC', 0.3, lx, ly, float(z_front(0, ly)) - 0.004, M['engrave'], depth=0.008))
    # Rear wordmark, read from behind.
    parts.append(text_obj('logo_rear', 'ARC', 0.34, 0.0, 1.6, float(z_back(0.0, 1.6)) - 0.004, M['engrave'], depth=0.008, rot_y=math.pi))
    parts.append(bar('usb_socket', 0, 3.0, -0.25, 0.72, 0.4, 0.18, M['port']))

    for ob in parts:
        if ob.name not in coll.objects:
            coll.objects.link(ob)
        ob.parent = root
    # Raw units -> metres, Z up, front facing -Y (toward a camera on -Y).
    root.scale = (SCALE, SCALE, SCALE)
    root.rotation_euler = (math.pi / 2, 0, 0)

    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'arc.blend'))
    print('saved', OUT / 'arc.blend')


build()
