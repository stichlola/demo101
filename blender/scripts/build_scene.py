"""Rat Dance - procedural Blender scene.

A rat breakdances on a big wooden table in a huge kitchen while an army of
cockroaches dances a choreography behind it. The camera flies aerial,
choreographed moves around the rat.

Run (Blender 4.2+):

    blender -b -P scripts/build_scene.py -- --out output/rat_dance.blend

Optional:
    --rat-bvh / --roach-bvh   mocap clips to use (BVH, Mixamo-style names)
    --rows / --cols           cockroach formation size
    --preview DIR             also render a low-res preview PNG sequence

Everything is a placeholder built from primitives and bone-parented to base
skeletons (RAT_rig, ROACH_rig_*), so custom models can later be skinned to
the same armatures (same bone names) and the dances keep working.

Reference point: the rat. All positions are expressed relative to RAT_MARK,
the spot on the table where the rat dances.
"""
import argparse
import math
import os
import random
import sys

import bpy
from mathutils import Euler, Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rig_models  # noqa: E402
import volcano_set  # noqa: E402
ROOT = os.path.dirname(HERE)

# ------------------------------------------------------------------ config
FPS = 30
RES = (1080, 1920)            # vertical, like a reel

TABLE_SIZE = (3.6, 1.9)       # x, y in metres
TABLE_TOP = 0.95              # table surface height
RAT_MARK = Vector((0.0, -0.25, TABLE_TOP))   # where the rat dances

RAT_HEIGHT = 0.14             # standing height of the rat (metres)
ROACH_HEIGHT = 0.30           # cockroaches are giant backup dancers
ROACH_SPACING = (0.36, 0.30)  # x, y between dancers
ROACH_FRONT_GAP = 0.40        # distance from rat mark to first roach row
ROACH_WAVE = 4                # frames of delay per row (canon effect)

ROOM = (16.0, 14.0, 4.8)      # big kitchen: width, depth, height

# Camera choreography: keys in spherical coordinates around the rat.
# (frame, radius m, azimuth deg, elevation deg, lens mm)
# azimuth 0 = in front of the rat (-Y), 90 = to its right (+X), 180 = behind.
CAMERA_KEYS = [
    (1,    5.0,  -35, 38, 24),   # aerial establishing shot of the kitchen
    (90,   3.0,  -15, 42, 28),   # dive toward the table
    (180,  1.10,   0, 22, 35),   # land in front of the rat (like the reel)
    (300,  0.80,  80, 14, 35),   # arc to the side, low
    (390,  1.40, 170, 18, 28),   # swing behind, through the roach army
    (480,  0.90, 270, 25, 35),   # complete the orbit
    (570,  1.30, 380, 82, 24),   # crane up: top-down spinning shot
    (690,  1.10, 470, 80, 24),
    (780,  0.75, 520, 8, 35),    # floor-level close-up
    (900,  0.85, 600, 14, 40),
    (1000, 2.20, 690, 35, 28),   # rise again
    (1125, 6.00, 740, 30, 22),   # final aerial pull-back reveal
]


# Volcano set: real human scale. Skeletons are 1.8 m, the goblin is about
# half their height. Same choreography idea, wider aerial moves.
VOLCANO = dict(
    TABLE_TOP=volcano_set.ISLET_TOP,
    RAT_MARK=Vector((0.0, -2.0, volcano_set.ISLET_TOP)),
    RAT_HEIGHT=0.84,
    ROACH_HEIGHT=1.8,
    ROACH_SPACING=(2.1, 1.8),
    ROACH_FRONT_GAP=2.6,
    STAGE_RADIUS=volcano_set.ISLET_FLAT - 0.8,
    CAMERA_KEYS=[
        (1,    46.0, -30, 34, 20),   # wide: the islet alone in the lava lake
        (100,  20.0, -15, 22, 24),   # swoop down over the lava
        (190,  4.2,    0, 10, 35),   # land in front of the goblin
        (300,  3.2,   80,  6, 35),   # low arc to the side, lava behind
        (390,  8.0,  170, 14, 28),   # behind, through the skeleton army
        (480,  3.8,  270, 16, 35),   # complete the orbit
        (570,  7.0,  380, 80, 24),   # crane up: top-down spinning shot
        (690,  5.5,  470, 78, 24),
        (780,  2.6,  520,  5, 35),   # ground-level close-up, embers in front
        (900,  3.2,  600, 10, 40),
        (1000, 14.0, 690, 24, 24),   # rise again
        (1125, 40.0, 740, 28, 20),   # final reveal of the crater
    ],
)
STAGE_RADIUS = None  # kitchen: table bounds

# ------------------------------------------------------------------ helpers
def args_from_cli():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "output", "rat_dance.blend"))
    ap.add_argument("--rat-bvh", default=os.path.join(ROOT, "mocap", "breakdance_long_85_12.bvh"))
    ap.add_argument("--roach-bvh", default=os.path.join(ROOT, "mocap", "salsa_60_08.bvh"))
    ap.add_argument("--rat-model", default=os.path.join(ROOT, "models", "goblin.glb"),
                    help="GLB to rig as the lead dancer ('' = primitive placeholder rat)")
    ap.add_argument("--rat-kind", default="goblin", help="landmark set in rig_models.LANDMARKS")
    ap.add_argument("--roach-model", default=os.path.join(ROOT, "models", "skeleton.glb"),
                    help="GLB to rig as the backup dancers ('' = primitive placeholder roaches)")
    ap.add_argument("--roach-kind", default="skeleton")
    ap.add_argument("--set", choices=("volcano", "kitchen"), default="volcano")
    ap.add_argument("--rows", type=int, default=3)
    ap.add_argument("--cols", type=int, default=7)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--preview", default="")
    ap.add_argument("--preview-step", type=int, default=3)
    return ap.parse_args(argv)


def collection(name, parent=None):
    col = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(col)
    return col


def link(obj, col):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    col.objects.link(obj)
    return obj


def material(name, color, rough=0.5, metal=0.0, emit=None, emit_strength=0.0):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    if emit:
        p.inputs["Emission Color"].default_value = (*emit, 1)
        p.inputs["Emission Strength"].default_value = emit_strength
    return m


def wood_material(name, light, dark, scale=3.0, stretch=8.0):
    """Procedural wood: stretched noise driving a two-tone ramp."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Roughness"].default_value = 0.45
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, stretch, 1.0)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 8.0
    noise.inputs["Distortion"].default_value = 2.0
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.inputs["Scale"].default_value = scale * 0.6
    wave.inputs["Distortion"].default_value = 6.0
    mix = nt.nodes.new("ShaderNodeMath")
    mix.operation = "MULTIPLY_ADD"
    mix.inputs[1].default_value = 0.5
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*dark, 1)
    ramp.color_ramp.elements[1].color = (*light, 1)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], noise.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], mix.inputs[0])
    nt.links.new(wave.outputs["Fac"], mix.inputs[2])
    nt.links.new(mix.outputs[0], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    return m


def tiles_material(name, a, b, scale=6.0):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Roughness"].default_value = 0.25
    tc = nt.nodes.new("ShaderNodeTexCoord")
    chk = nt.nodes.new("ShaderNodeTexChecker")
    chk.inputs["Color1"].default_value = (*a, 1)
    chk.inputs["Color2"].default_value = (*b, 1)
    chk.inputs["Scale"].default_value = scale
    nt.links.new(tc.outputs["Object"], chk.inputs["Vector"])
    nt.links.new(chk.outputs["Color"], p.inputs["Base Color"])
    return m


def box(name, size, loc, mat, col, bevel=0.0, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        mod = o.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 3
    o.data.materials.append(mat)
    return link(o, col)


def cylinder(name, r, depth, loc, mat, col, rot=(0, 0, 0), verts=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return link(o, col)


def sphere(name, r, loc, mat, col, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=r, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return link(o, col)


# ------------------------------------------------------------------ kitchen
def build_kitchen(col):
    W, D, H = ROOM
    floor_mat = tiles_material("M_FloorTiles", (0.75, 0.72, 0.66), (0.42, 0.36, 0.3), scale=W / 0.6)
    wall_mat = material("M_WallGreen", (0.42, 0.47, 0.22), rough=0.9)
    wains_mat = material("M_Wainscot", (0.82, 0.78, 0.66), rough=0.6)
    ceil_mat = material("M_Ceiling", (0.9, 0.88, 0.84), rough=0.9)
    cab_mat = wood_material("M_CabinetWood", (0.62, 0.42, 0.24), (0.38, 0.22, 0.1), scale=2.0)
    top_mat = material("M_Countertop", (0.18, 0.18, 0.2), rough=0.2)
    steel = material("M_Steel", (0.8, 0.8, 0.82), rough=0.25, metal=1.0)
    white = material("M_Appliance", (0.92, 0.92, 0.9), rough=0.3)
    glass_sky = material("M_WindowSky", (0.6, 0.8, 1.0), emit=(0.7, 0.85, 1.0), emit_strength=6.0)

    # room shell (table stands at the room centre-ish, back wall behind roaches)
    oy = 0.5  # room centre is shifted back so there is space for the camera
    box("Floor", (W, D, 0.1), (0, oy, -0.05), floor_mat, col)
    box("Ceiling", (W, D, 0.1), (0, oy, H + 0.05), ceil_mat, col)
    back_y = oy + D / 2
    box("Wall_Back", (W, 0.2, H), (0, back_y + 0.1, H / 2), wall_mat, col)
    box("Wall_Front", (W, 0.2, H), (0, oy - D / 2 - 0.1, H / 2), wall_mat, col)
    box("Wall_Left", (0.2, D, H), (-W / 2 - 0.1, oy, H / 2), wall_mat, col)
    box("Wall_Right", (0.2, D, H), (W / 2 + 0.1, oy, H / 2), wall_mat, col)
    for name, size, loc in (
        ("Wainscot_Back", (W, 0.04, 1.1), (0, back_y - 0.02, 0.55)),
        ("Wainscot_Left", (0.04, D, 1.1), (-W / 2 + 0.02, oy, 0.55)),
        ("Wainscot_Right", (0.04, D, 1.1), (W / 2 - 0.02, oy, 0.55)),
    ):
        box(name, size, loc, wains_mat, col)

    # window on the back wall (emissive sky)
    box("Window_Sky", (3.2, 0.05, 1.8), (-3.0, back_y - 0.01, 2.4), glass_sky, col)
    for i in range(3):
        box(f"Window_Mullion_V{i}", (0.06, 0.08, 1.9), (-4.6 + i * 1.6, back_y - 0.05, 2.4), cab_mat, col)
    for z in (1.5, 2.4, 3.3):
        box(f"Window_Mullion_H{z}", (3.3, 0.08, 0.06), (-3.0, back_y - 0.05, z), cab_mat, col)

    # counters along the back and left wall: base cabinets + top + uppers
    def run(prefix, start, axis, count, facing):
        for i in range(count):
            off = Vector(axis) * (i * 0.8)
            p = Vector(start) + off
            depth_vec = Vector(facing) * 0.3
            size = (0.78, 0.6, 0.88) if axis[0] else (0.6, 0.78, 0.88)
            box(f"{prefix}_Base{i}", size, p + Vector((0, 0, 0.44)), cab_mat, col, bevel=0.01)
            box(f"{prefix}_Handle{i}", (0.25, 0.02, 0.02) if axis[0] else (0.02, 0.25, 0.02),
                p + depth_vec + Vector((0, 0, 0.78)), steel, col)
            tsize = (0.8, 0.66, 0.04) if axis[0] else (0.66, 0.8, 0.04)
            box(f"{prefix}_Top{i}", tsize, p + Vector((0, 0, 0.9)), top_mat, col)
            usize = (0.78, 0.36, 0.8) if axis[0] else (0.36, 0.78, 0.8)
            box(f"{prefix}_Upper{i}", usize, p - Vector(facing) * 0.12 + Vector((0, 0, 2.0)), cab_mat, col, bevel=0.01)

    run("CounterBack", (0.4, back_y - 0.32, 0), (1, 0, 0), 9, (0, -1, 0))
    run("CounterLeft", (-ROOM[0] / 2 + 0.32, oy - 3.5, 0), (0, 1, 0), 9, (1, 0, 0))

    # fridge, stove + hood, sink
    box("Fridge", (0.95, 0.75, 2.1), (ROOM[0] / 2 - 0.9, back_y - 0.42, 1.05), white, col, bevel=0.03)
    box("Fridge_Handle", (0.03, 0.04, 0.9), (ROOM[0] / 2 - 1.3, back_y - 0.82, 1.2), steel, col)
    box("Stove", (0.8, 0.02, 0.5), (2.8, back_y - 0.63, 0.5), material("M_Oven", (0.05, 0.05, 0.05), rough=0.1), col)
    for i, (dx, dy) in enumerate(((-0.18, -0.15), (0.18, -0.15), (-0.18, 0.12), (0.18, 0.12))):
        cylinder(f"Burner{i}", 0.09, 0.02, (2.8 + dx, back_y - 0.32 + dy, 0.93), steel, col)
    box("Hood", (1.0, 0.55, 0.4), (2.8, back_y - 0.3, 2.0), steel, col, bevel=0.02)
    box("Sink", (0.6, 0.45, 0.05), (5.2, back_y - 0.32, 0.92), steel, col)
    cylinder("Faucet", 0.02, 0.35, (5.2, back_y - 0.08, 1.08), steel, col)

    # some clutter on the counters
    rnd = random.Random(3)
    jar_mats = [material(f"M_Jar{i}", c, rough=0.4) for i, c in enumerate(
        ((0.8, 0.3, 0.2), (0.9, 0.75, 0.3), (0.3, 0.5, 0.7), (0.9, 0.9, 0.85)))]
    for i in range(10):
        x = 0.6 + i * 0.7 + rnd.uniform(-0.2, 0.2)
        if 2.3 < x < 3.3:
            continue
        cylinder(f"Jar{i}", rnd.uniform(0.05, 0.1), rnd.uniform(0.15, 0.35),
                 (x, back_y - 0.35, 1.0 + 0.1), rnd.choice(jar_mats), col)

    # chairs around the table
    chair_mat = wood_material("M_ChairWood", (0.55, 0.36, 0.2), (0.3, 0.17, 0.08))
    tw, td = TABLE_SIZE
    for i, (x, y, rz) in enumerate(((-0.9, -td / 2 - 0.45, 0), (0.9, -td / 2 - 0.45, 0),
                                     (-0.9, td / 2 + 0.45, math.pi), (0.9, td / 2 + 0.45, math.pi),
                                     (-tw / 2 - 0.5, 0, -math.pi / 2), (tw / 2 + 0.5, 0, math.pi / 2))):
        base = Vector((x, y, 0))
        rot = Matrix.Rotation(rz, 3, "Z")
        box(f"Chair{i}_Seat", (0.48, 0.48, 0.05), base + Vector((0, 0, 0.48)), chair_mat, col, rot=(0, 0, rz))
        for j, (lx, ly) in enumerate(((-0.2, -0.2), (0.2, -0.2), (-0.2, 0.2), (0.2, 0.2))):
            box(f"Chair{i}_Leg{j}", (0.04, 0.04, 0.48), base + rot @ Vector((lx, ly, 0.24)), chair_mat, col)
        box(f"Chair{i}_Back", (0.48, 0.04, 0.5), base + rot @ Vector((0, -0.22, 0.76)), chair_mat, col, rot=(0, 0, rz))


def build_table(col):
    """Big wooden table with a drawer (as in the reference) and a mouse trap."""
    tw, td = TABLE_SIZE
    top = wood_material("M_TableWood", (0.86, 0.55, 0.28), (0.6, 0.33, 0.14), scale=1.5, stretch=10.0)
    leg = wood_material("M_TableLegs", (0.7, 0.45, 0.22), (0.45, 0.25, 0.1))
    dark = material("M_DrawerKnob", (0.05, 0.05, 0.05), rough=0.3)
    brass = material("M_Brass", (0.85, 0.6, 0.25), rough=0.2, metal=1.0)

    box("Table_Top", (tw, td, 0.06), (0, 0, TABLE_TOP - 0.03), top, col, bevel=0.01)
    box("Table_Apron", (tw - 0.2, td - 0.2, 0.14), (0, 0, TABLE_TOP - 0.13), leg, col)
    for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        box(f"Table_Leg{i}", (0.09, 0.09, TABLE_TOP - 0.06),
            (sx * (tw / 2 - 0.12), sy * (td / 2 - 0.12), (TABLE_TOP - 0.06) / 2), leg, col)
    # drawer front facing the camera side
    box("Table_Drawer", (0.9, 0.02, 0.11), (0, -td / 2 + 0.09, TABLE_TOP - 0.13), top, col, bevel=0.005)
    box("Table_DrawerHandle", (0.4, 0.03, 0.02), (0, -td / 2 + 0.07, TABLE_TOP - 0.13), dark, col, bevel=0.008)
    sphere("Table_DrawerKnob", 0.018, (0, -td / 2 + 0.055, TABLE_TOP - 0.13), brass, col)

    # mouse trap (cheeky detail from the reference)
    trap_wood = wood_material("M_TrapWood", (0.9, 0.75, 0.5), (0.7, 0.55, 0.3))
    base = Vector((1.15, -0.35, TABLE_TOP))
    box("MouseTrap_Base", (0.12, 0.28, 0.012), base + Vector((0, 0, 0.006)), trap_wood, col)
    box("MouseTrap_Bar", (0.11, 0.006, 0.006), base + Vector((0, 0.05, 0.016)), material("M_Steel", (0.8, 0.8, 0.82), 0.25, 1.0), col)
    box("MouseTrap_Cheese", (0.03, 0.03, 0.02), base + Vector((0, -0.07, 0.022)),
        material("M_Cheese", (0.95, 0.75, 0.2), rough=0.6), col, rot=(0, 0, 0.6))


def build_lights(col):
    sc = bpy.context.scene
    # sun through the window
    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = 3.0
    sun.color = (1.0, 0.92, 0.8)
    sun.angle = math.radians(3)
    o = bpy.data.objects.new("Sun", sun)
    o.rotation_euler = Euler((math.radians(55), 0, math.radians(200)))
    col.objects.link(o)
    # pendant lamps above the table (warm pools of light like the reference)
    lamp_mat = material("M_LampShade", (0.05, 0.05, 0.05), rough=0.4)
    bulb_mat = material("M_Bulb", (1, 0.9, 0.7), emit=(1, 0.85, 0.6), emit_strength=20)
    for i, x in enumerate((-1.0, 0.0, 1.0)):
        z = TABLE_TOP + 1.25
        cylinder(f"Pendant{i}_Cord", 0.006, ROOM[2] - z, (x, 0.1, (ROOM[2] + z) / 2), lamp_mat, col)
        bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=0.24, radius2=0.05, depth=0.2, location=(x, 0.1, z))
        shade = bpy.context.object
        shade.name = f"Pendant{i}_Shade"
        shade.data.materials.append(lamp_mat)
        link(shade, col)
        sphere(f"Pendant{i}_Bulb", 0.05, (x, 0.1, z - 0.08), bulb_mat, col)
        l = bpy.data.lights.new(f"Pendant{i}", "SPOT")
        l.energy = 120
        l.color = (1.0, 0.82, 0.6)
        l.spot_size = math.radians(80)
        l.spot_blend = 0.6
        l.shadow_soft_size = 0.08
        lo = bpy.data.objects.new(f"Pendant{i}_Light", l)
        lo.location = (x, 0.1, z - 0.12)
        col.objects.link(lo)
    # soft fill from the ceiling
    fill = bpy.data.lights.new("CeilingFill", "AREA")
    fill.energy = 600
    fill.size = 6
    fill.color = (1.0, 0.95, 0.9)
    fo = bpy.data.objects.new("CeilingFill", fill)
    fo.location = (0, 1.5, ROOM[2] - 0.1)
    col.objects.link(fo)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.35, 0.4, 0.45, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.3
    sc.world = world


# ------------------------------------------------------------------ skeletons
def import_bvh(path, name):
    bpy.ops.import_anim.bvh(filepath=path, rotate_mode="NATIVE", axis_forward="-Z", axis_up="Y",
                            update_scene_fps=False, update_scene_duration=False)
    arm = bpy.context.object
    arm.name = name
    arm.data.name = name
    action = arm.animation_data.action
    action.name = os.path.splitext(os.path.basename(path))[0]
    action.use_fake_user = True
    return arm, action


def add_bones(arm, specs):
    """specs: list of (name, parent, head, tail) in armature space (rest)."""
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    for name, parent, head, tail in specs:
        b = eb.new(name)
        b.head = head
        b.tail = tail
        b.parent = eb[parent]
        b.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")


def rest(arm, name):
    b = arm.data.bones[name]
    return b.head_local.copy(), b.tail_local.copy()


def rat_extra_bones(arm):
    h0, h1 = rest(arm, "Head")
    hip, _ = rest(arm, "Hips")
    up = (h1 - h0).normalized()
    specs = [
        ("Snout", "Head", h0 + up * 0.03, h0 + up * 0.03 + Vector((0, -0.14, -0.02))),
        ("Ear.L", "Head", h1 + Vector((0.05, 0, -0.02)), h1 + Vector((0.12, 0.02, 0.07))),
        ("Ear.R", "Head", h1 + Vector((-0.05, 0, -0.02)), h1 + Vector((-0.12, 0.02, 0.07))),
    ]
    prev, p = "Hips", hip + Vector((0, 0.08, -0.05))
    for i in range(6):
        q = p + Vector((0, 0.13, -0.04 + i * 0.01))
        specs.append((f"Tail{i + 1}", prev, p, q))
        prev, p = f"Tail{i + 1}", q
    add_bones(arm, specs)


def roach_extra_bones(arm):
    h0, h1 = rest(arm, "Head")
    s0, s1 = rest(arm, "Spine1")
    hip, _ = rest(arm, "Hips")
    specs = []
    for side, sx in (("L", 1), ("R", -1)):
        a = h1 + Vector((sx * 0.03, -0.04, -0.02))
        b = a + Vector((sx * 0.12, -0.1, 0.35))
        c = b + Vector((sx * 0.25, 0.05, 0.3))
        specs.append((f"Antenna1.{side}", "Head", a, b))
        specs.append((f"Antenna2.{side}", f"Antenna1.{side}", b, c))
        m0 = (s0 + s1) / 2 + Vector((sx * 0.15, -0.02, 0))
        m1 = m0 + Vector((sx * 0.3, -0.05, -0.05))
        m2 = m1 + Vector((sx * 0.1, -0.05, -0.35))
        specs.append((f"MidLeg1.{side}", "Spine1", m0, m1))
        specs.append((f"MidLeg2.{side}", f"MidLeg1.{side}", m1, m2))
        specs.append((f"Wing.{side}", "Spine2", s1 + Vector((sx * 0.06, 0.12, 0.05)),
                      s1 + Vector((sx * 0.09, 0.3, -0.75))))
    specs.append(("Abdomen", "Hips", hip + Vector((0, 0.08, 0.05)), hip + Vector((0, 0.3, -0.35))))
    add_bones(arm, specs)


def wiggle(arm, bone, axis, amp, speed, phase):
    """Procedural secondary motion on extra bones (tail, antennae, wings)."""
    pb = arm.pose.bones[bone]
    pb.rotation_mode = "XYZ"
    fc = pb.driver_add("rotation_euler", axis)
    fc.driver.type = "SCRIPTED"
    fc.driver.expression = f"{amp:.3f}*sin(frame*{speed:.3f}+{phase:.3f})"


# ------------------------------------------------------------------ placeholders
def part(arm, bone, name, mat, col, shape="capsule", radius=0.05, scale=(1, 1, 1), along=0.5,
         offset=(0, 0, 0), length=None):
    """Mesh rigidly parented to a bone, built at the rest pose (armature space)."""
    b = arm.data.bones[bone]
    h, t = b.head_local, b.tail_local
    blen = (t - h).length
    L = length if length is not None else blen
    if shape == "capsule":
        bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=10, radius=1)
        o = bpy.context.object
        o.scale = (radius * scale[0], L / 2 * scale[1], radius * scale[2])
    elif shape == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=10, radius=radius)
        o = bpy.context.object
        o.scale = scale
    elif shape == "cone":
        bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=radius, radius2=radius * 0.15, depth=L)
        o = bpy.context.object
        o.rotation_euler = (-math.pi / 2, 0, 0)  # point along bone +Y
        o.scale = scale
    elif shape == "box":
        bpy.ops.mesh.primitive_cube_add(size=1)
        o = bpy.context.object
        o.scale = (radius * 2 * scale[0], L * scale[1], radius * 2 * scale[2])
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bpy.ops.object.shade_smooth()
    o.name = name
    o.data.materials.append(mat)
    link(o, col)
    # rest placement: along the bone, `offset` is in armature space (front = -Y)
    rot = b.matrix_local.to_3x3().to_4x4()
    pos = h + (t - h) * along + Vector(offset)
    world = Matrix.Translation(pos) @ rot
    # bone parenting attaches to the bone tail; express `world` in that space
    o.parent = arm
    o.parent_type = "BONE"
    o.parent_bone = bone
    o.matrix_parent_inverse = Matrix.Identity(4)
    o.matrix_basis = (b.matrix_local @ Matrix.Translation((0, blen, 0))).inverted() @ world
    return o


def dress_rat(arm, col):
    fur = material("M_RatFur", (0.88, 0.86, 0.84), rough=0.8)
    pink = material("M_RatPink", (0.95, 0.6, 0.62), rough=0.6)
    eye = material("M_Eye", (0.01, 0.01, 0.01), rough=0.1)
    shoe = material("M_RedShoes", (0.75, 0.05, 0.05), rough=0.4)
    sole = material("M_ShoeSole", (0.95, 0.95, 0.95), rough=0.5)
    r = 0.11  # radii are in skeleton units (before object scaling)
    part(arm, "Hips", "Rat_Pelvis", fur, col, "sphere", r * 1.5, (1.1, 1.0, 1.2), along=-0.6)
    part(arm, "Spine", "Rat_Belly", fur, col, radius=r * 1.5, scale=(1.0, 1.6, 0.95))
    part(arm, "Spine1", "Rat_Chest", fur, col, radius=r * 1.35, scale=(1.0, 1.6, 0.9))
    part(arm, "Spine2", "Rat_Shoulders", fur, col, radius=r * 1.2, scale=(1.1, 1.5, 0.8))
    part(arm, "Neck", "Rat_Neck", fur, col, radius=r * 0.7, scale=(1, 1.5, 1))
    part(arm, "Neck1", "Rat_Neck1", fur, col, radius=r * 0.7, scale=(1, 1.5, 1))
    part(arm, "Head", "Rat_Head", fur, col, "sphere", r * 1.1, (1.0, 1.0, 1.05), along=0.4)
    part(arm, "Snout", "Rat_Snout", fur, col, "cone", r * 0.85, along=0.5)
    part(arm, "Snout", "Rat_Nose", pink, col, "sphere", r * 0.18, along=1.0)
    for s in ("L", "R"):
        part(arm, f"Ear.{s}", f"Rat_Ear.{s}", pink, col, "sphere", r * 0.55, (1.0, 0.25, 1.0), along=0.6)
        sx = 1 if s == "L" else -1
        part(arm, "Head", f"Rat_Eye.{s}", eye, col, "sphere", r * 0.16, along=0.6, offset=(sx * r * 0.45, -r * 0.95, r * 0.15))
        side = "Left" if s == "L" else "Right"
        part(arm, f"{side}Shoulder", f"Rat_Clavicle.{s}", fur, col, radius=r * 0.45)
        part(arm, f"{side}HipJoint", f"Rat_HipJoint.{s}", fur, col, radius=r * 0.6)
        # joint balls hide gaps between the rigid parts in extreme poses
        for jb, jr in ((f"{side}Arm", 0.38), (f"{side}ForeArm", 0.32), (f"{side}Leg", 0.42),
                       (f"{side}Foot", 0.36), (f"{side}UpLeg", 0.58)):
            part(arm, jb, f"Rat_Joint_{jb}", fur, col, "sphere", r * jr, along=0.0)
        part(arm, f"{side}Arm", f"Rat_UpperArm.{s}", fur, col, radius=r * 0.35)
        part(arm, f"{side}ForeArm", f"Rat_ForeArm.{s}", fur, col, radius=r * 0.3)
        part(arm, f"{side}Hand", f"Rat_Hand.{s}", pink, col, "sphere", r * 0.3, along=0.5)
        part(arm, f"{side}UpLeg", f"Rat_Thigh.{s}", fur, col, radius=r * 0.55)
        part(arm, f"{side}Leg", f"Rat_Shin.{s}", fur, col, radius=r * 0.38)
        part(arm, f"{side}Foot", f"Rat_Shoe.{s}", shoe, col, radius=r * 0.4, scale=(1.0, 1.8, 0.8), along=0.6)
        part(arm, f"{side}Foot", f"Rat_Sole.{s}", sole, col, "box", r * 0.38, (1.0, 1.6, 0.25), along=0.6,
             offset=(0, 0, -r * 0.25))
    for i in range(6):
        part(arm, f"Tail{i + 1}", f"Rat_Tail{i + 1}", pink, col, radius=r * (0.22 - i * 0.03), scale=(1, 1.15, 1))


def dress_roach(arm, col):
    shell = material("M_RoachShell", (0.12, 0.04, 0.015), rough=0.25)
    leg = material("M_RoachLeg", (0.08, 0.03, 0.01), rough=0.4)
    wing = material("M_RoachWing", (0.2, 0.07, 0.02), rough=0.15)
    eye = material("M_Eye", (0.01, 0.01, 0.01), rough=0.1)
    r = 0.1
    part(arm, "Spine1", "Roach_Thorax", shell, col, radius=r * 1.5, scale=(1.1, 1.4, 0.9))
    part(arm, "Spine2", "Roach_Pronotum", shell, col, "sphere", r * 1.7, (1.15, 0.6, 0.9), along=0.8)
    part(arm, "Abdomen", "Roach_Abdomen", shell, col, radius=r * 1.6, scale=(1.0, 1.0, 0.7))
    part(arm, "Head", "Roach_Head", shell, col, "sphere", r * 0.85, along=0.4)
    for s in ("L", "R"):
        sx = 1 if s == "L" else -1
        part(arm, "Head", f"Roach_Eye.{s}", eye, col, "sphere", r * 0.25, along=0.5, offset=(sx * r * 0.45, -r * 0.7, r * 0.1))
        part(arm, f"Wing.{s}", f"Roach_Wing.{s}", wing, col, radius=r * 1.0, scale=(1.0, 1.0, 0.18))
        for i in (1, 2):
            part(arm, f"Antenna{i}.{s}", f"Roach_Antenna{i}.{s}", leg, col, radius=r * 0.04)
            part(arm, f"MidLeg{i}.{s}", f"Roach_MidLeg{i}.{s}", leg, col, radius=r * 0.12)
        side = "Left" if s == "L" else "Right"
        for bone, rad in ((f"{side}Arm", 0.14), (f"{side}ForeArm", 0.11), (f"{side}UpLeg", 0.2),
                          (f"{side}Leg", 0.13), (f"{side}Foot", 0.1)):
            part(arm, bone, f"Roach_{bone}", leg, col, radius=r * rad)
        part(arm, f"{side}Hand", f"Roach_Claw.{s}", leg, col, "cone", r * 0.12, length=0.15)


# ------------------------------------------------------------------ placement
def skeleton_height(arm):
    if "rest_height" in arm:
        return arm["rest_height"]
    zs = [b.head_local.z for b in arm.data.bones] + [b.tail_local.z for b in arm.data.bones]
    return max(zs) - min(zs)


def sample_motion(arm, frames, bones=None):
    """World-space bone points of the animation (armature at identity)."""
    sc = bpy.context.scene
    pts = []
    for f in frames:
        sc.frame_set(f)
        for pb in arm.pose.bones:
            if bones and pb.name not in bones:
                continue
            pts.append((f, pb.name, arm.matrix_world @ pb.head, arm.matrix_world @ pb.tail))
    return pts


def facing_angle(arm, frame):
    """Rotation about Z that turns the character to face -Y at `frame`."""
    bpy.context.scene.frame_set(frame)
    l = arm.pose.bones["LeftUpLeg"].head
    r = arm.pose.bones["RightUpLeg"].head
    side = (l - r)
    fwd = Vector((side.x, side.y, 0)).cross(Vector((0, 0, 1)))
    return math.atan2(-1, 0) - math.atan2(fwd.y, fwd.x)


def mesh_min_z(mesh, frames):
    """Lowest evaluated vertex of a skinned mesh for each of `frames` (world z)."""
    sc = bpy.context.scene
    out = []
    for f in frames:
        sc.frame_set(f)
        ev = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mw = ev.matrix_world
        out.append(min((mw @ v.co).z for v in ev.data.vertices))
    return out


def ground_contact(arm, mesh, action_range, col, floor_z, step=2):
    """Per-frame vertical correction so a character with a different body volume
    than the mocap actor neither sinks into nor floats above the table during
    floor work, while real jumps stay airborne. Keys a parent empty's Z."""
    frames = list(range(int(action_range[0]), int(action_range[1]) + 1, step))
    lows = mesh_min_z(mesh, frames)
    ref = sorted(lows)[len(lows) // 2]  # sole height while standing
    want = [floor_z - min(m, ref) for m in lows]
    root = bpy.data.objects.new(f"{arm.name}_root", None)
    root.empty_display_size = 0.1
    col.objects.link(root)
    arm.parent = root
    for i, (f, m) in enumerate(zip(frames, lows)):
        win = want[max(0, i - 3):i + 4]
        root.location.z = max(sum(win) / len(win), floor_z - m)
        root.keyframe_insert("location", index=2, frame=f)
    return root


def place_on_table(arm, action_range, height, mark, face_frame, mesh=None):
    """Scale to `height`, ground the lowest point of the dance on the table and
    centre the average dance position on `mark`."""
    s = height / skeleton_height(arm)
    ang = facing_angle(arm, face_frame)
    frames = range(int(action_range[0]), int(action_range[1]) + 1, 3)
    pts = sample_motion(arm, frames)
    rot = Matrix.Rotation(ang, 3, "Z")
    if mesh is not None:
        min_z = min(mesh_min_z(mesh, range(int(action_range[0]), int(action_range[1]) + 1, 5)))
    else:
        min_z = min(min(h.z, t.z) for _, _, h, t in pts)
    hips = [rot @ h for _, n, h, _ in pts if n == "Hips"]
    cx = sum(p.x for p in hips) / len(hips)
    cy = sum(p.y for p in hips) / len(hips)
    arm.scale = (s, s, s)
    arm.rotation_euler = (0, 0, ang)
    arm.location = (mark.x - cx * s, mark.y - cy * s, mark.z - min_z * s)
    return s


def nla_play(arm, action, start, end, offset=0, speed=1.0):
    """Put `action` on an NLA strip repeating to cover [start, end]."""
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = None
    tr = ad.nla_tracks.new()
    tr.name = "Dance"
    a0, a1 = action.frame_range
    strip = tr.strips.new(action.name, int(start + offset), action)
    strip.scale = 1.0 / speed
    clip_len = (a1 - a0) / speed
    strip.repeat = max(1.0, (end - start - offset) / clip_len + 1)
    strip.blend_in = 0
    strip.extrapolation = "HOLD"
    return strip


# ------------------------------------------------------------------ camera
def catmull(p0, p1, p2, p3, t):
    t2, t3 = t * t, t * t * t
    return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)


def camera_params(frame):
    keys = CAMERA_KEYS
    if frame <= keys[0][0]:
        return keys[0][1:]
    if frame >= keys[-1][0]:
        return keys[-1][1:]
    for i in range(len(keys) - 1):
        if keys[i][0] <= frame <= keys[i + 1][0]:
            break
    k0 = keys[max(i - 1, 0)]
    k1, k2 = keys[i], keys[i + 1]
    k3 = keys[min(i + 2, len(keys) - 1)]
    t = (frame - k1[0]) / (k2[0] - k1[0])
    t = t * t * (3 - 2 * t)  # ease in/out between keys
    return tuple(catmull(k0[j], k1[j], k2[j], k3[j], t) for j in range(1, 5))


def smooth(values, radius):
    out = []
    for i in range(len(values)):
        lo, hi = max(0, i - radius), min(len(values), i + radius + 1)
        acc = Vector()
        for v in values[lo:hi]:
            acc += v
        out.append(acc / (hi - lo))
    return out


def build_camera(col, rat, start, end):
    sc = bpy.context.scene
    target = bpy.data.objects.new("CAM_Target", None)
    target.empty_display_type = "SPHERE"
    target.empty_display_size = 0.05
    col.objects.link(target)

    cam_data = bpy.data.cameras.new("DanceCam")
    cam_data.sensor_width = 36
    cam_data.dof.use_dof = True
    cam_data.dof.focus_object = target
    cam_data.dof.aperture_fstop = 2.8
    cam_data.clip_start = 0.01
    cam = bpy.data.objects.new("DanceCam", cam_data)
    col.objects.link(cam)
    sc.camera = cam
    tt = cam.constraints.new("TRACK_TO")
    tt.target = target
    tt.track_axis = "TRACK_NEGATIVE_Z"
    tt.up_axis = "UP_Y"

    # bake a smoothed follow target from the rat's hips (spins would make it jitter)
    frames = list(range(start, end + 1))
    hips = []
    for f in frames:
        sc.frame_set(f)
        hips.append(rat.matrix_world @ rat.pose.bones["Spine1"].head)
    hips = smooth(hips, 12)
    # keep the frame centred near the mark, follow the rat only partially
    for f, p in zip(frames, hips):
        p = RAT_MARK.lerp(p, 0.7)
        p.z = max(p.z, TABLE_TOP + RAT_HEIGHT * 0.35)
        target.location = p
        target.keyframe_insert("location", frame=f)
        radius, az, el, lens = camera_params(f)
        az, el = math.radians(az), math.radians(el)
        cam.location = p + Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))) * radius
        cam.keyframe_insert("location", frame=f)
        cam_data.lens = lens
        cam_data.keyframe_insert("lens", frame=f)
    return cam


# ------------------------------------------------------------------ main
def main():
    args = args_from_cli()
    random.seed(args.seed)
    if args.set == "volcano":
        globals().update(VOLCANO)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.name = "RatDance"
    sc.render.fps = FPS
    sc.render.resolution_x, sc.render.resolution_y = RES
    sc.unit_settings.system = "METRIC"

    c_set = collection("SET_Kitchen")
    c_table = collection("SET_Table")
    c_lights = collection("LIGHTS")
    c_rat = collection("CHAR_Rat")
    c_roach = collection("CHAR_Roaches")
    c_cam = collection("CAMERA")

    if args.set == "kitchen":
        build_kitchen(c_set)
        build_table(c_table)
        build_lights(c_lights)

    # ---- rat: breakdance mocap on the base skeleton (or the custom model)
    rat_src, rat_action = import_bvh(args.rat_bvh, "RAT_rig")
    start, end = 1, int(rat_action.frame_range[1])
    sc.frame_start, sc.frame_end = start, end
    if args.rat_model:
        rat, rat_mesh = rig_models.rig_character(args.rat_model, args.rat_kind, rat_src, "RAT_rig_model")
        link(rat, c_rat)
        link(rat_mesh, c_rat)
        bpy.data.objects.remove(rat_src)
        rat.name = rat.data.name = "RAT_rig"
        rat_mesh.name = "RAT_mesh"
        rat.animation_data_create().action = rat_action
        place_on_table(rat, rat_action.frame_range, RAT_HEIGHT, RAT_MARK, face_frame=start, mesh=rat_mesh)
        ground_contact(rat, rat_mesh, rat_action.frame_range, c_rat, TABLE_TOP)
    else:
        rat = rat_src
        link(rat, c_rat)
        rat_extra_bones(rat)
        dress_rat(rat, c_rat)
        place_on_table(rat, rat_action.frame_range, RAT_HEIGHT, RAT_MARK, face_frame=start)
        for i in range(6):
            wiggle(rat, f"Tail{i + 1}", 0, 0.25, 0.25, i * 0.6)
            wiggle(rat, f"Tail{i + 1}", 2, 0.2, 0.17, i * 0.5)
        for s, ph in (("L", 0.0), ("R", 1.3)):
            wiggle(rat, f"Ear.{s}", 0, 0.15, 0.5, ph)
        rat.data.display_type = "STICK"

    # ---- backup dancers template (cockroach placeholder or custom model)
    tmpl_src, roach_action = import_bvh(args.roach_bvh, "ROACH_rig_template")
    tmpl_parts = collection("ROACH_template_parts", c_roach)
    if args.roach_model:
        tmpl, tmpl_mesh = rig_models.rig_character(args.roach_model, args.roach_kind, tmpl_src, "ROACH_rig_tmp")
        bpy.data.objects.remove(tmpl_src)
        tmpl.name = tmpl.data.name = "ROACH_rig_template"
        tmpl_mesh.name = "ROACH_mesh_template"
        link(tmpl, c_roach)
        link(tmpl_mesh, tmpl_parts)
        tmpl.animation_data_create().action = roach_action
        place_on_table(tmpl, roach_action.frame_range, ROACH_HEIGHT, Vector((0, 0, TABLE_TOP)),
                       face_frame=1, mesh=tmpl_mesh)
    else:
        tmpl = tmpl_src
        link(tmpl, c_roach)
        roach_extra_bones(tmpl)
        dress_roach(tmpl, tmpl_parts)
        place_on_table(tmpl, roach_action.frame_range, ROACH_HEIGHT, Vector((0, 0, TABLE_TOP)), face_frame=1)
    base_loc = tmpl.location.copy()
    base_rot = tmpl.rotation_euler.copy()
    tmpl.animation_data.action = None
    tmpl.data.display_type = "STICK"

    # ---- formation: staggered rows behind the rat, like the reference
    dancers = []
    for row in range(args.rows):
        for colm in range(args.cols):
            stagger = (row % 2) * ROACH_SPACING[0] / 2
            x = (colm - (args.cols - 1) / 2) * ROACH_SPACING[0] + stagger
            y = RAT_MARK.y + ROACH_FRONT_GAP + row * ROACH_SPACING[1]
            if abs(x) < ROACH_SPACING[0] * 0.6 and row == 0:
                continue  # leave room behind the rat
            if STAGE_RADIUS is None and abs(x) > TABLE_SIZE[0] / 2 - 0.2:
                continue
            if STAGE_RADIUS is not None and Vector((x, y)).length > STAGE_RADIUS:
                continue
            dancers.append((row, colm, x, y))

    for idx, (row, colm, x, y) in enumerate(dancers):
        arm = tmpl.copy()
        arm.data = tmpl.data  # shared skeleton data
        arm.name = f"ROACH_rig_{idx:02d}"
        c_roach.objects.link(arm)
        arm.location = base_loc + Vector((x, y, 0))
        arm.rotation_euler = base_rot
        arm.rotation_euler.z += random.uniform(-0.1, 0.1)
        if arm.animation_data:
            for d in list(arm.animation_data.drivers):
                arm.animation_data.drivers.remove(d)
        nla_play(arm, roach_action, start, end, offset=row * ROACH_WAVE)
        if not args.roach_model:
            ph = random.uniform(0, 6.28)
            for s in ("L", "R"):
                wiggle(arm, f"Antenna1.{s}", 0, 0.25, 0.3, ph)
                wiggle(arm, f"Antenna2.{s}", 2, 0.35, 0.22, ph + 1.0)
                wiggle(arm, f"Wing.{s}", 1, 0.08, 0.6, ph)
        pc = collection(f"ROACH_{idx:02d}_parts", c_roach)
        for p in tmpl_parts.objects:
            o = p.copy()  # linked duplicate: mesh data stays shared
            o.parent = arm
            for m in o.modifiers:
                if m.type == "ARMATURE":
                    m.object = arm
            pc.objects.link(o)
    # hide the template (kept as the source for custom models)
    tmpl_parts.hide_render = True
    tmpl_parts.hide_viewport = True
    tmpl.hide_render = True
    tmpl.hide_viewport = True

    # rat plays its breakdance through NLA as well
    rat.animation_data.action = None
    nla_play(rat, rat_action, start, end)

    cam = build_camera(c_cam, rat, start, end)
    if args.set == "volcano":
        volcano_set.build(c_set, c_lights, collection("FX"), start, end)
        volcano_set.camera_shake(cam)
        cam.data.clip_end = 600
        cam.data.dof.aperture_fstop = 2.0
        c_table.hide_render = c_table.hide_viewport = True

    # ---- render settings
    sc.render.engine = "BLENDER_EEVEE_NEXT"
    if args.set == "kitchen":
        sc.eevee.taa_render_samples = 32
    if hasattr(sc.eevee, "use_shadows"):
        sc.eevee.use_shadows = True
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Punchy"
    sc.render.image_settings.file_format = "FFMPEG"
    sc.render.ffmpeg.format = "MPEG4"
    sc.render.ffmpeg.codec = "H264"
    sc.render.filepath = os.path.join(ROOT, "output", "render", "rat_dance_")
    sc.frame_set(start)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=args.out, compress=True)
    print(f"saved {args.out}: frames {start}-{end}, {len(dancers)} cockroaches")

    if args.preview:
        render_preview(args.preview, args.preview_step)


def render_preview(out_dir, step):
    """Quick low-res Cycles preview (works headless without a GPU)."""
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 12
    sc.cycles.use_denoising = True
    sc.render.resolution_percentage = 25
    sc.render.image_settings.file_format = "PNG"
    os.makedirs(out_dir, exist_ok=True)
    for f in range(sc.frame_start, sc.frame_end + 1, step):
        sc.frame_set(f)
        sc.render.filepath = os.path.join(out_dir, f"f{f:04d}.png")
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
