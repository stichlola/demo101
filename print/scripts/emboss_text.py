"""Emboss a cursive text around the cylinder (base.stl) for vase-mode printing.

    blender -b -P scripts/emboss_text.py -- --text mymusicminis

Steps:
1. import base.stl (merging the duplicated STL vertices);
2. build the text with a connected script font (Pacifico), extruded and with
   a rounded bevel, so the relief has sloped sides (no flat overhangs);
3. slice the text densely along its length and wrap it around the outer wall:
   it sinks a bit into the wall and stands out by --relief millimetres;
4. boolean union (exact, self-intersection on: script letters overlap);
5. export STL + save a .blend and preview renders.

Vase mode notes: the relief is attached to the wall everywhere, so every
layer still has a single outer contour that the spiral wall can follow.
Units are millimetres (as in the STL files).
"""
import argparse
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def args_from_cli():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="mymusicminis")
    ap.add_argument("--font", default=os.path.join(ROOT, "fonts", "Pacifico-Regular.ttf"))
    ap.add_argument("--base", default=os.path.join(ROOT, "models", "base.stl"))
    ap.add_argument("--lid", default=os.path.join(ROOT, "models", "tappo.stl"))
    ap.add_argument("--voxel", type=float, default=0.08, help="remesh resolution of the lettering (mm)")
    ap.add_argument("--height", type=float, default=18.0, help="text height incl. ascenders/descenders (mm)")
    ap.add_argument("--max-width", type=float, default=118.0, help="max text length along the wall (mm)")
    ap.add_argument("--center-z", type=float, default=0.0, help="text centre height (cylinder spans -20..20)")
    ap.add_argument("--relief", type=float, default=1.0, help="how far the letters stand out (mm)")
    ap.add_argument("--embed", type=float, default=0.4, help="how deep the letters sink into the wall (mm)")
    ap.add_argument("--out", default=os.path.join(ROOT, "output"))
    ap.add_argument("--preview", action="store_true")
    return ap.parse_args(argv)


def import_stl(path, name):
    bpy.ops.wm.stl_import(filepath=path)
    o = bpy.context.object
    o.name = name
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)
    bm.to_mesh(o.data)
    bm.free()
    return o


def outer_radius(obj):
    return max(math.hypot(v.co.x, v.co.y) for v in obj.data.vertices)


def make_text(a):
    """Flat text mesh in the XY plane, depth along Z (z=0 is the middle)."""
    curve = bpy.data.curves.new("Lettering", "FONT")
    curve.body = a.text
    curve.font = bpy.data.fonts.load(a.font)
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.resolution_u = 6
    total = a.relief + a.embed
    # no curve bevel: on the sharp cusps of a script font it makes spikes;
    # the edges are softened after the remesh instead
    curve.extrude = total / 2
    curve.size = 10.0
    obj = bpy.data.objects.new("Lettering", curve)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    # scale to the requested height, limited by the available arc length
    deps = bpy.context.evaluated_depsgraph_get()
    me = obj.evaluated_get(deps).to_mesh()
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    obj.evaluated_get(deps).to_mesh_clear()
    s = min(a.height / h, a.max_width / w)
    curve.size *= s
    bpy.context.view_layer.update()
    # convert to a real mesh
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.object
    me = obj.data
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    k = min(a.height / (max(ys) - min(ys)), a.max_width / (max(xs) - min(xs)))
    for v in me.vertices:  # exact final size in X/Y, depth unchanged
        v.co.x = (v.co.x - cx) * k
        v.co.y = (v.co.y - cy) * k
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    # overlapping script glyphs -> one clean watertight solid
    rm = obj.modifiers.new("Fuse", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = a.voxel
    rm.use_smooth_shade = True
    bpy.ops.object.modifier_apply(modifier=rm.name)
    sm = obj.modifiers.new("Soften", "SMOOTH")  # rounded, printable edges
    sm.factor = 0.5
    sm.iterations = 4
    bpy.ops.object.modifier_apply(modifier=sm.name)
    print(f"[text] '{a.text}' {max(xs) - min(xs):.1f} x {max(ys) - min(ys):.1f} mm, depth {total:.2f} mm")
    return obj


def densify(obj, step=0.35):
    """Cut the text with planes across its length so it bends smoothly."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    xs = [v.co.x for v in bm.verts]
    x = min(xs) + step
    while x < max(xs):
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(x, 0, 0), plane_no=(1, 0, 0))
        x += step
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(obj.data)
    bm.free()


def wrap(obj, radius, a):
    """x -> angle around the wall, z (depth) -> radial, y -> height."""
    half = (a.relief + a.embed) / 2
    for v in obj.data.vertices:
        x, y, z = v.co
        theta = x / radius
        r = radius - a.embed + (z + half)
        v.co = Vector((r * math.sin(theta), -r * math.cos(theta), y + a.center_z))
    obj.data.update()


def union(base, text):
    mod = base.modifiers.new("Lettering", "BOOLEAN")
    mod.operation = "UNION"
    mod.solver = "EXACT"
    mod.object = text
    mod.use_self = False  # the lettering is already one watertight solid
    bpy.context.view_layer.objects.active = base
    bpy.ops.object.modifier_apply(modifier=mod.name)
    text.hide_set(True)
    text.hide_render = True


def check(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bad = sum(1 for e in bm.edges if not e.is_manifold)
    vol = bm.calc_volume()
    bm.free()
    print(f"[check] {obj.name}: {len(obj.data.polygons)} faces, non-manifold edges {bad}, volume {vol:.0f} mm3")
    return bad


def export_stl(obj, path):
    for o in bpy.context.scene.objects:
        o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, apply_modifiers=True)
    print("[export]", path)


def preview(base, lid, out_dir):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 24
    sc.cycles.device = "CPU"
    sc.render.resolution_x, sc.render.resolution_y = 900, 900
    mat = bpy.data.materials.new("PLA")
    mat.use_nodes = True
    p = mat.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (0.85, 0.2, 0.25, 1)
    p.inputs["Roughness"].default_value = 0.45
    for o in (base, lid):
        o.data.materials.clear()
        o.data.materials.append(mat)
    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.9, 0.9, 0.92, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    sc.world = world
    key = bpy.data.lights.new("Key", "AREA")
    key.energy = 400000
    key.size = 120
    ko = bpy.data.objects.new("Key", key)
    ko.location = (-120, -160, 140)
    ko.rotation_euler = (Vector((0, 0, 0)) - ko.location).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(ko)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.lens = 85
    sc.collection.objects.link(cam)
    sc.camera = cam
    for name, az, el, d in (("front", 0, 12, 190), ("three_quarter", -40, 22, 200), ("closeup", -15, 5, 120)):
        a, e = math.radians(az), math.radians(el)
        cam.location = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * d
        cam.rotation_euler = (Vector((0, 0, 0)) - cam.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = os.path.join(out_dir, f"preview_{name}.png")
        bpy.ops.render.render(write_still=True)


def main():
    a = args_from_cli()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 0.001
    bpy.context.scene.unit_settings.length_unit = "MILLIMETERS"
    base = import_stl(a.base, "Base")
    lid = import_stl(a.lid, "Tappo")
    radius = outer_radius(base)
    print(f"[base] outer radius {radius:.2f} mm")
    text = make_text(a)
    wrap(text, radius, a)
    union(base, text)
    check(base)
    os.makedirs(a.out, exist_ok=True)
    export_stl(base, os.path.join(a.out, f"base_{a.text}.stl"))
    # place the lid next to the cylinder for the preview / .blend
    lid.location.x = -(sum(v.co.x for v in lid.data.vertices) / len(lid.data.vertices)) + 70
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(a.out, f"base_{a.text}.blend"))
    if a.preview:
        lid.hide_render = True
        preview(base, lid, a.out)


if __name__ == "__main__":
    main()
