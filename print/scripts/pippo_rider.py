"""Pippo: move the little rider from the golem's head onto its shoulders.

    blender -b -P scripts/pippo_rider.py -- --preview

1. import pippo.stl (stone golem with a tiny helmeted character sprouting
   from the top of its head);
2. cut the rider off at the waist (local cut, only around the rider) and
   remove the leftover belt ring from the golem's head, capping the holes;
3. straighten the rider's torso and rebuild pelvis + legs in a riding pose:
   thighs open around the back of the golem's head, shins hanging along its
   sides, small boots;
4. fuse rider + legs into one watertight solid (voxel remesh), seat it in the
   hollow between head and upper back, and union it with the golem.

Outputs (output/pippo/): pippo_rider.stl (one piece, ready to print),
pippo_golem.stl and pippo_mini.stl (separate parts), previews, .blend.
Units: millimetres.
"""
import argparse
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

RIDER_AXIS = Vector((31.75, -5.05))   # rider's waist centre (XY) in the source
WAIST_Z = 29.35                       # cut height: just above the golem's skull
RING_Z = 28.6                         # belt ring leftovers above this are removed
RING_R = 1.55
SEAT = Vector((32.0, -0.7, 0.0))


def args_from_cli():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(ROOT, "pippo", "src", "pippo.stl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "output", "pippo"))
    ap.add_argument("--tilt", type=float, default=-25.0, help="lean the torso back (deg)")
    ap.add_argument("--voxel", type=float, default=0.025, help="rider remesh resolution (mm)")
    ap.add_argument("--preview", action="store_true")
    return ap.parse_args(argv)


# ------------------------------------------------------------------ helpers
def island(start):
    seen = {start}
    stack = [start]
    while stack:
        v = stack.pop()
        for e in v.link_edges:
            w = e.other_vert(v)
            if w not in seen:
                seen.add(w)
                stack.append(w)
    return seen


def local_cut(bm, z, axis, radius):
    """Bisect at height z but only split the mesh near `axis`."""
    res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                 plane_co=(0, 0, z), plane_no=(0, 0, 1))
    edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)
             and all((v.co.xy - axis).length < radius for v in e.verts)]
    bmesh.ops.split_edges(bm, edges=edges)
    return edges


def cap(bm):
    edges = [e for e in bm.edges if e.is_boundary]
    bmesh.ops.holes_fill(bm, edges=edges, sides=0)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])


def to_object(bm, name):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def activate(obj):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


# ------------------------------------------------------------------ steps
def split_rider(path):
    bpy.ops.wm.stl_import(filepath=path)
    src = bpy.context.object
    bm = bmesh.new()
    bm.from_mesh(src.data)
    bpy.data.objects.remove(src)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)

    local_cut(bm, WAIST_Z, RIDER_AXIS, 2.2)
    bm.verts.ensure_lookup_table()
    top = max(bm.verts, key=lambda v: v.co.z)
    rider_verts = island(top)
    rider = bmesh.new()
    vmap = {v: rider.verts.new(v.co) for v in rider_verts}
    for f in bm.faces:
        if all(v in vmap for v in f.verts):
            rider.faces.new([vmap[v] for v in f.verts])
    bmesh.ops.delete(bm, geom=list(rider_verts), context="VERTS")

    # remove the belt ring left on the skull and fair the hole with a smooth
    # membrane that follows the surrounding cranium
    ring = [v for v in bm.verts if v.co.z > RING_Z - 0.15
            and ((v.co.x - RIDER_AXIS.x) / 1.3) ** 2 + ((v.co.y - RIDER_AXIS.y) / 1.0) ** 2 < 1.0]
    bmesh.ops.delete(bm, geom=ring, context="VERTS")
    edges = [e for e in bm.edges if e.is_boundary and (e.verts[0].co.xy - RIDER_AXIS).length < 2.0]
    rim = {v for e in edges for v in e.verts}
    hole = bmesh.ops.holes_fill(bm, edges=edges, sides=0)["faces"]
    poked = bmesh.ops.poke(bm, faces=hole)
    patch = set(poked["faces"])
    for _ in range(4):
        inner_edges = [e for e in {e for f in patch for e in f.edges}
                       if not all(v in rim for v in e.verts)]   # keep the rim edges intact
        res = bmesh.ops.subdivide_edges(bm, edges=inner_edges, cuts=1, use_grid_fill=True)
        patch = {f for f in patch if f.is_valid}
        patch |= {f for f in res["geom"] + res["geom_inner"] if isinstance(f, bmesh.types.BMFace)}
        tri = bmesh.ops.triangulate(bm, faces=[f for f in patch if len(f.verts) > 3])
        patch = {f for f in patch if f.is_valid} | set(tri["faces"])
    inner = [v for v in {v for f in patch if f.is_valid for v in f.verts} - rim if v.is_valid]
    for _ in range(300):
        bmesh.ops.smooth_vert(bm, verts=inner, factor=0.8, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    # cobble texture like the rest of the skull (voronoi cells ~0.55 mm),
    # fading out towards the rim
    from mathutils import noise
    bm.normal_update()
    for v in inner:
        e = math.hypot((v.co.x - RIDER_AXIS.x) / 1.3, (v.co.y - RIDER_AXIS.y) / 1.0)
        fade = max(0.0, min(1.0, (1.0 - e) / 0.3))
        dist, _ = noise.voronoi(v.co / 0.55, distance_metric="DISTANCE", exponent=2.5)
        edge = min(1.0, (dist[1] - dist[0]) / 0.35)   # 0 on cell borders, 1 inside
        bump = 0.07 * (edge * edge * (3 - 2 * edge)) - 0.03
        v.co += v.normal * bump * fade
    print(f"[skull] removed belt ring ({len(ring)} verts), membrane {len(inner)} verts")
    cap(bm)
    cap(rider)
    print(f"[split] rider {len(rider.verts)} verts, golem {len(bm.verts)} verts")
    return to_object(bm, "Golem"), to_object(rider, "RiderTop")


def surface_z(bvh, x, y):
    hit = bvh.ray_cast(Vector((x, y, 60)), Vector((0, 0, -1)))
    return hit[0].z if hit[0] else None


def side_point(bvh, x0, y, z, direction):
    """First surface point hit when moving sideways from inside the head."""
    hit = bvh.ray_cast(Vector((x0 + direction * 8, y, z)), Vector((-direction, 0, 0)))
    return hit[0] if hit[0] else None


def build_rider(rider, golem, a):
    """Straighten the torso, add pelvis + legs, seat it, fuse to one solid."""
    me = rider.data
    base = [v.co.copy() for v in me.vertices if abs(v.co.z - WAIST_Z) < 1e-3]
    waist = sum(base, Vector()) / len(base)
    width = max(v.x for v in base) - min(v.x for v in base)

    bvh = BVHTree.FromObject(golem, bpy.context.evaluated_depsgraph_get())
    seat_z = surface_z(bvh, SEAT.x, SEAT.y)
    seat = Vector((SEAT.x, SEAT.y, seat_z))
    pelvis_h = 0.55
    hips = seat + Vector((0, 0, pelvis_h))  # where the waist cut will sit

    # torso: lean back, then move the waist onto the seat
    M = (Matrix.Translation(hips) @ Matrix.Rotation(math.radians(a.tilt), 4, "X")
         @ Matrix.Translation(-waist))
    me.transform(M)

    # legs follow the golem: thighs over the head's back corners, shins down its sides
    parts = []

    def ball(p, r, sx=1.0, sy=1.0, sz=1.0):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=r, location=p)
        o = bpy.context.object
        o.scale = (sx, sy, sz)
        parts.append(o)

    def limb(p0, p1, r0, r1, step=0.06):
        n = max(2, int((p1 - p0).length / step))
        for i in range(n + 1):
            t = i / n
            ball(p0.lerp(p1, t), r0 + (r1 - r0) * t)

    ball(hips + Vector((0, 0.05, -0.25)), width * 0.5, 1.0, 0.8, 0.75)   # pelvis
    # legs astride the back of the head: knees resting on the skull's back
    # corners, shins hanging down outside the head, small boots
    for s in (-1, 1):
        hip = hips + Vector((s * width * 0.3, -0.1, -0.4))
        kxy = Vector((SEAT.x + s * 1.9, SEAT.y - 1.0))
        knee = Vector((kxy.x, kxy.y, (surface_z(bvh, kxy.x, kxy.y) or seat_z) + 0.22))
        ax = knee.x
        az = knee.z - 1.05
        for _ in range(12):  # slide out (max 0.6 mm) until the shin hangs free of the head
            sz = surface_z(bvh, ax, kxy.y - 0.35)
            if sz is None or sz < az - 0.15:
                break
            ax += s * 0.05
        ankle = Vector((ax, kxy.y - 0.35, az))
        limb(hip, knee, 0.36, 0.30)
        limb(knee, ankle, 0.30, 0.25)
        ball(knee, 0.31)                                                      # knee cap
        ball(ankle + Vector((s * 0.02, -0.2, -0.12)), 0.27, 0.95, 1.5, 0.8)   # boot
        ball(ankle + Vector((0, 0, 0.05)), 0.29, 1.0, 1.0, 0.6)               # boot cuff
        print(f"[leg] side {s:+d}: knee {tuple(round(c, 2) for c in knee)}, ankle {tuple(round(c, 2) for c in ankle)}")

    activate(parts[0])
    for p in parts:
        p.select_set(True)
    bpy.ops.object.join()
    legs = bpy.context.object
    legs.name = "Legs"

    # fuse torso + legs into one watertight solid
    activate(rider)
    legs.select_set(True)
    bpy.ops.object.join()
    rider = bpy.context.object
    rider.name = "Rider"
    rm = rider.modifiers.new("Fuse", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = a.voxel
    bpy.ops.object.modifier_apply(modifier=rm.name)
    sm = rider.modifiers.new("Soften", "CORRECTIVE_SMOOTH")
    sm.iterations = 3
    bpy.ops.object.modifier_apply(modifier=sm.name)
    print(f"[rider] seat {tuple(round(c, 2) for c in seat)}, {len(rider.data.polygons)} faces")
    return rider


def repair_skull(golem):
    """Carve the leftover belt ring off the skull and fill the spot with the
    skull's own curvature (sphere fitted to the surrounding cranium)."""
    rad = RING_R + 0.15

    def cylinder(r, z0, z1):
        bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=r, depth=z1 - z0,
                                            location=(RIDER_AXIS.x, RIDER_AXIS.y, (z0 + z1) / 2))
        return bpy.context.object

    cutter = cylinder(rad, RING_Z - 0.05, 33.0)       # remove the belt ring stump
    mod = golem.modifiers.new("Carve", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.object = cutter
    activate(golem)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    # filler: a plug whose top follows the real skull height all around the
    # rim and blends to a soft crown in the middle (no lip, no pit)
    bvh = BVHTree.FromObject(golem, bpy.context.evaluated_depsgraph_get())
    segs, rings = 64, 14
    rim = []
    for k in range(segs):
        ang = 2 * math.pi * k / segs
        z = surface_z(bvh, RIDER_AXIS.x + math.cos(ang) * (rad + 0.1), RIDER_AXIS.y + math.sin(ang) * (rad + 0.1))
        rim.append(z if z is not None and z > RING_Z - 2.5 else RING_Z)
    for _ in range(3):  # smooth the rim profile a little
        rim = [(rim[k - 1] + 2 * rim[k] + rim[(k + 1) % segs]) / 4 for k in range(segs)]
    centre_z = sum(rim) / segs + 0.12
    bottom = min(rim) - 1.0
    verts, faces = [], []
    r_out = rad + 0.04
    for i in range(1, rings + 1):
        t = i / rings
        for k in range(segs):
            ang = 2 * math.pi * k / segs
            z = rim[k] * t * t + centre_z * (1 - t * t) - 0.02 * t
            verts.append((RIDER_AXIS.x + math.cos(ang) * r_out * t, RIDER_AXIS.y + math.sin(ang) * r_out * t, z))
    for k in range(segs):  # bottom ring
        ang = 2 * math.pi * k / segs
        verts.append((RIDER_AXIS.x + math.cos(ang) * r_out, RIDER_AXIS.y + math.sin(ang) * r_out, bottom))
    top_c = len(verts)
    verts.append((RIDER_AXIS.x, RIDER_AXIS.y, centre_z))
    bot_c = len(verts)
    verts.append((RIDER_AXIS.x, RIDER_AXIS.y, bottom))
    ring = lambda i, k: (i - 1) * segs + (k % segs)
    for k in range(segs):
        faces.append((top_c, ring(1, k), ring(1, k + 1)))
        for i in range(1, rings):
            faces.append((ring(i, k), ring(i + 1, k), ring(i + 1, k + 1), ring(i, k + 1)))
        faces.append((ring(rings, k), ring(rings + 1, k), ring(rings + 1, k + 1), ring(rings, k + 1)))
        faces.append((bot_c, ring(rings + 1, k + 1), ring(rings + 1, k)))
    me = bpy.data.meshes.new("SkullPlug")
    me.from_pydata(verts, [], faces)
    me.update()
    dome = bpy.data.objects.new("SkullPlug", me)
    bpy.context.scene.collection.objects.link(dome)
    activate(dome)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    clip = cylinder(0.01, 0, 0.01)  # placeholder, removed below
    print(f"[skull] rim z {min(rim):.2f}..{max(rim):.2f}, crown {centre_z:.2f}")
    for o in (cutter, clip):
        bpy.data.objects.remove(o)
    union_into(golem, dome)
    bpy.data.objects.remove(dome)


def union_into(target, other):
    mod = target.modifiers.new(other.name, "BOOLEAN")
    mod.operation = "UNION"
    mod.solver = "EXACT"
    mod.object = other
    activate(target)
    bpy.ops.object.modifier_apply(modifier=mod.name)


def union(golem, rider):
    combo = golem.copy()
    combo.data = golem.data.copy()
    combo.name = "Pippo"
    bpy.context.scene.collection.objects.link(combo)
    mod = combo.modifiers.new("Rider", "BOOLEAN")
    mod.operation = "UNION"
    mod.solver = "EXACT"
    mod.object = rider
    activate(combo)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return combo


def check(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bad = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    print(f"[check] {obj.name}: {len(obj.data.polygons)} faces, non-manifold edges {bad}")


def export(obj, path):
    activate(obj)
    bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True)
    print("[export]", path)


def preview(objs, out_dir):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 24
    sc.render.resolution_x = sc.render.resolution_y = 900
    mat = bpy.data.materials.new("Resin")
    mat.use_nodes = True
    p = mat.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (0.62, 0.62, 0.6, 1)
    p.inputs["Roughness"].default_value = 0.5
    for o in objs:
        o.data.materials.clear()
        o.data.materials.append(mat)
    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.2, 0.2, 0.22, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8
    sc.world = world
    for name, rot, e in (("Key", (0.9, 0.1, -0.7), 3.5), ("Rim", (1.1, 0.0, 2.6), 2.0)):
        l = bpy.data.lights.new(name, "SUN")
        l.energy = e
        lo = bpy.data.objects.new(name, l)
        lo.rotation_euler = rot
        sc.collection.objects.link(lo)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.type = "ORTHO"
    sc.collection.objects.link(cam)
    sc.camera = cam
    shots = (
        ("full_front", Vector((32, -1, 16)), Vector((0, -1, 0.15)), 38),
        ("full_3q", Vector((32, -1, 16)), Vector((-0.8, -1, 0.35)), 38),
        ("rider_front", Vector((32, -2, 28.5)), Vector((0, -1, 0.35)), 9),
        ("rider_3q", Vector((32, -2, 28.5)), Vector((0.9, -1, 0.45)), 9),
        ("rider_side", Vector((32, -2, 28.5)), Vector((1, 0, 0.15)), 9),
        ("rider_back", Vector((32, -1, 28.5)), Vector((-0.4, 1, 0.6)), 9),
    )
    for name, c, d, scale in shots:
        cam.data.ortho_scale = scale
        cam.location = c + d.normalized() * 120
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = os.path.join(out_dir, f"preview_{name}.png")
        bpy.ops.render.render(write_still=True)


def main():
    a = args_from_cli()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    os.makedirs(a.out, exist_ok=True)
    golem, rider = split_rider(a.src)
    rider = build_rider(rider, golem, a)
    check(golem)
    check(rider)
    combo = union(golem, rider)
    check(combo)
    export(combo, os.path.join(a.out, "pippo_rider.stl"))
    export(golem, os.path.join(a.out, "pippo_golem.stl"))
    export(rider, os.path.join(a.out, "pippo_mini.stl"))
    golem.hide_render = rider.hide_render = True
    golem.hide_set(True)
    rider.hide_set(True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(a.out, "pippo_rider.blend"))
    if a.preview:
        preview([combo], a.out)


if __name__ == "__main__":
    main()
