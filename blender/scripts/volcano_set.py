"""Volcano set: a round basalt islet in a lake of lava inside an active crater.

Everything is procedural:
* islet: flat dance floor (radius ISLET_FLAT) breaking into jagged rock that
  sinks into the lava, with glowing cracks near the lava line;
* lava lake: animated crust/molten shader (4D noise + voronoi cracks) on a
  slowly undulating surface;
* crater walls: displaced basalt with strata, lit from below by the lava;
* lighting: lava bounce ring, wall under-glow, warm key + cool rim for the
  dancers, flickering lava light;
* FX: smoke/haze volumes, rising embers with turbulence, falling ash, lava
  bursts with their own light pulses;
* compositor: fog glow, chromatic dispersion, vignette, warm/teal grade;
  camera gets a subtle drone shake.
"""
import math
import random

import bpy
import bmesh
from mathutils import Vector, noise

LAVA_Z = 0.0
ISLET_TOP = 1.2
ISLET_FLAT = 9.0      # flat dancing area radius
ISLET_RADIUS = 13.0   # where the rock disappears under the lava
CRATER_RADIUS = 48.0
CRATER_HEIGHT = 90.0

LAVA_HOT = (1.0, 0.32, 0.04)
LAVA_GLOW = (1.0, 0.45, 0.12)


# ------------------------------------------------------------------ helpers
def _link(obj, col):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    col.objects.link(obj)
    return obj


def _frame_driver(socket, expr):
    fc = socket.driver_add("default_value")
    fc.driver.type = "SCRIPTED"
    fc.driver.expression = expr
    return fc


def _smooth(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def _mesh_from(name, verts, faces, col):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    for p in me.polygons:
        p.use_smooth = True
    o = bpy.data.objects.new(name, me)
    col.objects.link(o)
    return o


def _emission_flicker(light, base, amount=0.25, speed=0.35, phase=0.0):
    fc = light.driver_add("energy")
    fc.driver.type = "SCRIPTED"
    fc.driver.expression = (f"{base:.1f}*(1+{amount:.2f}*sin(frame*{speed:.3f}+{phase:.2f})"
                            f"*sin(frame*{speed * 2.7:.3f}+{phase * 1.7:.2f}))")


# ------------------------------------------------------------------ materials
def lava_material():
    m = bpy.data.materials.new("M_Lava")
    m.use_nodes = True
    nt = m.node_tree
    n, l = nt.nodes, nt.links
    p = n["Principled BSDF"]
    out = n["Material Output"]
    tc = n.new("ShaderNodeTexCoord")
    mp = n.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.03, 0.03, 0.03)
    # big slow convection cells
    cells = n.new("ShaderNodeTexNoise")
    cells.noise_dimensions = "4D"
    cells.inputs["Scale"].default_value = 2.0
    cells.inputs["Detail"].default_value = 6.0
    cells.inputs["Roughness"].default_value = 0.6
    _frame_driver(cells.inputs["W"], "frame*0.0025")
    # crust plates separated by molten cracks
    vor = n.new("ShaderNodeTexVoronoi")
    vor.feature = "DISTANCE_TO_EDGE"
    vor.voronoi_dimensions = "4D"
    vor.inputs["Scale"].default_value = 9.0
    vor.inputs["Randomness"].default_value = 0.9
    _frame_driver(vor.inputs["W"], "frame*0.0015")
    warp = n.new("ShaderNodeVectorMath")
    warp.operation = "ADD"
    l.new(tc.outputs["Object"], mp.inputs["Vector"])
    l.new(mp.outputs["Vector"], cells.inputs["Vector"])
    l.new(mp.outputs["Vector"], warp.inputs[0])
    l.new(cells.outputs["Color"], warp.inputs[1])
    l.new(warp.outputs["Vector"], vor.inputs["Vector"])
    crack = n.new("ShaderNodeMapRange")  # distance-to-edge -> molten mask
    crack.inputs["From Min"].default_value = 0.0
    crack.inputs["From Max"].default_value = 0.045
    crack.inputs["To Min"].default_value = 1.0
    crack.inputs["To Max"].default_value = 0.0
    l.new(vor.outputs["Distance"], crack.inputs["Value"])
    heat = n.new("ShaderNodeMath")  # molten = cracks + hot cells
    heat.operation = "MAXIMUM"
    hot_cells = n.new("ShaderNodeMapRange")
    hot_cells.inputs["From Min"].default_value = 0.6
    hot_cells.inputs["From Max"].default_value = 0.85
    l.new(cells.outputs["Fac"], hot_cells.inputs["Value"])
    l.new(crack.outputs["Result"], heat.inputs[0])
    l.new(hot_cells.outputs["Result"], heat.inputs[1])
    ramp = n.new("ShaderNodeValToRGB")  # blackbody-like colour
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (0.0, 0.0, 0.0, 1)
    els[1].position, els[1].color = 1.0, (1.0, 0.85, 0.35, 1)
    e = els.new(0.35)
    e.color = (0.6, 0.05, 0.0, 1)
    e = els.new(0.7)
    e.color = (1.0, 0.35, 0.03, 1)
    l.new(heat.outputs[0], ramp.inputs["Fac"])
    strength = n.new("ShaderNodeMath")
    strength.operation = "MULTIPLY"
    strength.inputs[1].default_value = 7.0
    l.new(heat.outputs[0], strength.inputs[0])
    l.new(ramp.outputs["Color"], p.inputs["Emission Color"])
    l.new(strength.outputs[0], p.inputs["Emission Strength"])
    crust_col = n.new("ShaderNodeMixRGB")
    crust_col.inputs["Color1"].default_value = (0.03, 0.025, 0.022, 1)
    crust_col.inputs["Color2"].default_value = (0.25, 0.04, 0.01, 1)
    l.new(heat.outputs[0], crust_col.inputs["Fac"])
    l.new(crust_col.outputs["Color"], p.inputs["Base Color"])
    rough = n.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.85
    rough.inputs["To Max"].default_value = 0.35
    l.new(heat.outputs[0], rough.inputs["Value"])
    l.new(rough.outputs["Result"], p.inputs["Roughness"])
    bump = n.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.6
    l.new(vor.outputs["Distance"], bump.inputs["Height"])
    l.new(bump.outputs["Normal"], p.inputs["Normal"])
    l.new(p.outputs[0], out.inputs["Surface"])
    return m


def basalt_material(name, glow_height=0.8, glow_strength=10.0, strata=False, crack_scale=6.0):
    """Dark basalt; cracks glow where the rock is close to the lava."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    n, l = nt.nodes, nt.links
    p = n["Principled BSDF"]
    p.inputs["Roughness"].default_value = 0.85
    tc = n.new("ShaderNodeTexCoord")
    rock = n.new("ShaderNodeTexNoise")
    rock.inputs["Scale"].default_value = 1.5
    rock.inputs["Detail"].default_value = 12.0
    rock.inputs["Roughness"].default_value = 0.65
    l.new(tc.outputs["Object"], rock.inputs["Vector"])
    col = n.new("ShaderNodeValToRGB")
    col.color_ramp.elements[0].color = (0.018, 0.016, 0.015, 1)
    col.color_ramp.elements[1].color = (0.11, 0.09, 0.08, 1)
    if strata:
        wave = n.new("ShaderNodeTexWave")
        wave.wave_type = "BANDS"
        wave.bands_direction = "Z"
        wave.inputs["Scale"].default_value = 0.08
        wave.inputs["Distortion"].default_value = 8.0
        wave.inputs["Detail"].default_value = 6.0
        mix = n.new("ShaderNodeMath")
        mix.operation = "MULTIPLY_ADD"
        mix.inputs[1].default_value = 0.6
        l.new(tc.outputs["Object"], wave.inputs["Vector"])
        l.new(wave.outputs["Fac"], mix.inputs[0])
        l.new(rock.outputs["Fac"], mix.inputs[2])
        l.new(mix.outputs[0], col.inputs["Fac"])
    else:
        l.new(rock.outputs["Fac"], col.inputs["Fac"])
    l.new(col.outputs["Color"], p.inputs["Base Color"])
    bump = n.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.8
    bump.inputs["Distance"].default_value = 0.2
    l.new(rock.outputs["Fac"], bump.inputs["Height"])
    # glowing cracks, fading out with height above the lava
    vor = n.new("ShaderNodeTexVoronoi")
    vor.feature = "DISTANCE_TO_EDGE"
    vor.inputs["Scale"].default_value = crack_scale
    l.new(tc.outputs["Object"], vor.inputs["Vector"])
    crack = n.new("ShaderNodeMapRange")
    crack.inputs["From Max"].default_value = 0.03
    crack.inputs["To Min"].default_value = 1.0
    crack.inputs["To Max"].default_value = 0.0
    l.new(vor.outputs["Distance"], crack.inputs["Value"])
    geo = n.new("ShaderNodeNewGeometry")
    sep = n.new("ShaderNodeSeparateXYZ")
    l.new(geo.outputs["Position"], sep.inputs["Vector"])
    near = n.new("ShaderNodeMapRange")
    near.inputs["From Min"].default_value = LAVA_Z
    near.inputs["From Max"].default_value = LAVA_Z + glow_height
    near.inputs["To Min"].default_value = 1.0
    near.inputs["To Max"].default_value = 0.0
    l.new(sep.outputs["Z"], near.inputs["Value"])
    glow = n.new("ShaderNodeMath")
    glow.operation = "MULTIPLY"
    l.new(crack.outputs["Result"], glow.inputs[0])
    l.new(near.outputs["Result"], glow.inputs[1])
    edge = n.new("ShaderNodeMath")  # plus a hot skin right at the lava line
    edge.operation = "POWER"
    edge.inputs[1].default_value = 6.0
    l.new(near.outputs["Result"], edge.inputs[0])
    tot = n.new("ShaderNodeMath")
    tot.operation = "MAXIMUM"
    l.new(glow.outputs[0], tot.inputs[0])
    l.new(edge.outputs[0], tot.inputs[1])
    s = n.new("ShaderNodeMath")
    s.operation = "MULTIPLY"
    s.inputs[1].default_value = glow_strength
    l.new(tot.outputs[0], s.inputs[0])
    p.inputs["Emission Color"].default_value = (*LAVA_HOT, 1)
    l.new(s.outputs[0], p.inputs["Emission Strength"])
    # crack grooves
    gb = n.new("ShaderNodeBump")
    gb.invert = True
    gb.inputs["Strength"].default_value = 0.5
    l.new(crack.outputs["Result"], gb.inputs["Height"])
    l.new(bump.outputs["Normal"], gb.inputs["Normal"])
    l.new(gb.outputs["Normal"], p.inputs["Normal"])
    return m


def emission_material(name, color, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    n = m.node_tree.nodes
    p = n["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Emission Color"].default_value = (*color, 1)
    p.inputs["Emission Strength"].default_value = strength
    return m


def volume_material(name, color, density, emission=None, emit_strength=0.0, scale=0.04, contrast=(0.45, 0.75),
                    anisotropy=0.3, w_speed=0.002):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    n, l = nt.nodes, nt.links
    n.remove(n["Principled BSDF"])
    vol = n.new("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = (*color, 1)
    vol.inputs["Anisotropy"].default_value = anisotropy
    if emission:
        vol.inputs["Emission Color"].default_value = (*emission, 1)
    tc = n.new("ShaderNodeTexCoord")
    mp = n.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (scale, scale, scale * 1.6)
    nz = n.new("ShaderNodeTexNoise")
    nz.noise_dimensions = "4D"
    nz.inputs["Scale"].default_value = 1.0
    nz.inputs["Detail"].default_value = 4.0
    _frame_driver(nz.inputs["W"], f"frame*{w_speed}")
    l.new(tc.outputs["Object"], mp.inputs["Vector"])
    l.new(mp.outputs["Vector"], nz.inputs["Vector"])
    mr = n.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = contrast[0]
    mr.inputs["From Max"].default_value = contrast[1]
    mr.inputs["To Max"].default_value = density
    l.new(nz.outputs["Fac"], mr.inputs["Value"])
    l.new(mr.outputs["Result"], vol.inputs["Density"])
    if emission:
        es = n.new("ShaderNodeMath")
        es.operation = "MULTIPLY"
        es.inputs[1].default_value = emit_strength / max(density, 1e-6)
        l.new(mr.outputs["Result"], es.inputs[0])
        l.new(es.outputs[0], vol.inputs["Emission Strength"])
    l.new(vol.outputs[0], n["Material Output"].inputs["Volume"])
    return m


# ------------------------------------------------------------------ geometry
def build_islet(col, seed=11):
    """Round islet: flat top, broken jagged shore sinking into the lava."""
    rings, segs = 70, 192
    verts = [(0.0, 0.0, ISLET_TOP)]
    off = Vector((seed * 3.1, seed * 1.7, 0))
    for i in range(1, rings + 1):
        r = ISLET_RADIUS * 1.08 * i / rings
        for j in range(segs):
            a = 2 * math.pi * j / segs
            dirv = Vector((math.cos(a), math.sin(a), 0))
            # wobbly coastline so the islet is round but natural
            rr = r * (1 + 0.06 * noise.noise(dirv * 2.0 + off))
            t = _smooth(ISLET_FLAT, ISLET_RADIUS, rr)
            p = dirv * rr
            jag = noise.noise(p * 0.45 + off) * 0.9 + noise.noise(p * 1.6 + off) * 0.35
            z = ISLET_TOP + (-(ISLET_TOP + 1.8) * t) + jag * t * (1 - t) * 3.0
            z += noise.noise(p * 0.15 + off) * 0.04 * (1 - t)  # nearly flat floor
            if t >= 1:
                z = LAVA_Z - 1.8
            verts.append((p.x, p.y, z))
    faces = []
    for j in range(segs):
        faces.append((0, 1 + j, 1 + (j + 1) % segs))
    for i in range(rings - 1):
        b0, b1 = 1 + i * segs, 1 + (i + 1) * segs
        for j in range(segs):
            j1 = (j + 1) % segs
            faces.append((b0 + j, b1 + j, b1 + j1, b0 + j1))
    o = _mesh_from("Islet", verts, faces, col)
    # boulders on the shore
    rnd = random.Random(seed)
    for k in range(26):
        a = rnd.uniform(0, 2 * math.pi)
        r = rnd.uniform(ISLET_FLAT + 0.6, ISLET_RADIUS + 0.5)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=1)
        b = bpy.context.object
        b.name = f"Boulder{k:02d}"
        s = rnd.uniform(0.4, 1.4)
        b.scale = (s * rnd.uniform(0.8, 1.6), s * rnd.uniform(0.8, 1.4), s * rnd.uniform(0.5, 1.1))
        b.location = (math.cos(a) * r, math.sin(a) * r, rnd.uniform(-0.3, 0.6))
        b.rotation_euler = (rnd.uniform(0, 3), rnd.uniform(0, 3), rnd.uniform(0, 3))
        d = b.modifiers.new("Rock", "DISPLACE")
        tex = bpy.data.textures.get("T_RockDisp") or bpy.data.textures.new("T_RockDisp", "VORONOI")
        tex.noise_scale = 0.6
        d.texture = tex
        d.strength = 0.35
        bpy.ops.object.shade_smooth()
        _link(b, col)
    return o


def build_crater(col, seed=5):
    """Inward-facing crater wall, wider at the top, with ledges and strata."""
    rings, segs = 60, 256
    verts = []
    off = Vector((seed, seed * 2.3, 0))
    for i in range(rings + 1):
        z = -3 + (CRATER_HEIGHT + 3) * i / rings
        for j in range(segs):
            a = 2 * math.pi * j / segs
            d = Vector((math.cos(a), math.sin(a), 0))
            base = CRATER_RADIUS + 0.004 * z * z + 4.0 * math.sin(z * 0.12)  # bowl with ledges
            pz = Vector((d.x * 3, d.y * 3, z * 0.05)) + off
            r = base + noise.noise(pz) * 7 + noise.noise(pz * 3.5) * 2.2 + noise.noise(pz * 9) * 0.6
            verts.append((d.x * r, d.y * r, z))
    faces = []
    for i in range(rings):
        b0, b1 = i * segs, (i + 1) * segs
        for j in range(segs):
            j1 = (j + 1) % segs
            faces.append((b0 + j, b0 + j1, b1 + j1, b1 + j))  # normals point inward
    return _mesh_from("CraterWall", verts, faces, col)


def build_lava(col, start, end):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=220, y_subdivisions=220, size=2 * (CRATER_RADIUS + 25))
    lava = bpy.context.object
    lava.name = "LavaLake"
    lava.location.z = LAVA_Z
    _link(lava, col)
    # slow heaving surface: displace with a texture whose space drifts
    drift = bpy.data.objects.new("LavaDrift", None)
    col.objects.link(drift)
    drift.location = (0, 0, 0)
    drift.keyframe_insert("location", frame=start)
    drift.location = (6.0, 3.5, 2.0)
    drift.keyframe_insert("location", frame=end)
    for fc in drift.animation_data.action.fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
    tex = bpy.data.textures.new("T_LavaHeave", "CLOUDS")
    tex.noise_scale = 6.0
    tex.noise_depth = 2
    d = lava.modifiers.new("Heave", "DISPLACE")
    d.texture = tex
    d.texture_coords = "OBJECT"
    d.texture_coords_object = drift
    d.strength = 0.35
    d.mid_level = 0.5
    bpy.ops.object.shade_smooth()
    lava.data.materials.append(lava_material())
    return lava


def build_spires(col, seed=3):
    rnd = random.Random(seed)
    for k in range(9):
        a = rnd.uniform(0, 2 * math.pi)
        r = rnd.uniform(20, CRATER_RADIUS - 8)
        h = rnd.uniform(4, 14)
        bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=rnd.uniform(1.5, 3.5), radius2=rnd.uniform(0.2, 0.8),
                                        depth=h, location=(math.cos(a) * r, math.sin(a) * r, h / 2 - 1))
        s = bpy.context.object
        s.name = f"Spire{k}"
        sub = s.modifiers.new("Sub", "SUBSURF")
        sub.levels = sub.render_levels = 2
        d = s.modifiers.new("Rock", "DISPLACE")
        tex = bpy.data.textures.get("T_SpireDisp") or bpy.data.textures.new("T_SpireDisp", "CLOUDS")
        tex.noise_scale = 1.2
        d.texture = tex
        d.strength = 1.2
        s.rotation_euler = (rnd.uniform(-0.15, 0.15), rnd.uniform(-0.15, 0.15), rnd.uniform(0, 6))
        _link(s, col)
        yield s


# ------------------------------------------------------------------ FX
def _particle_instance(name, radius, mat, col):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=radius, location=(0, 0, -50))
    o = bpy.context.object
    o.name = name
    o.data.materials.append(mat)
    o.hide_render = True  # only rendered through the particles
    o.hide_viewport = True
    return _link(o, col)


def _annulus(name, r0, r1, z, col, segs=64):
    verts, faces = [], []
    for j in range(segs):
        a = 2 * math.pi * j / segs
        verts.append((math.cos(a) * r0, math.sin(a) * r0, z))
        verts.append((math.cos(a) * r1, math.sin(a) * r1, z))
    for j in range(segs):
        j1 = (j + 1) % segs
        faces.append((2 * j, 2 * j + 1, 2 * j1 + 1, 2 * j1))
    return _mesh_from(name, verts, faces, col)


def _particles(emitter, name, inst, count, start, end, life, vel, rand, gravity, size, size_rand, seed):
    mod = emitter.modifiers.new(name, "PARTICLE_SYSTEM")
    ps = emitter.particle_systems[mod.name]
    ps.seed = seed
    s = ps.settings
    s.name = name
    s.count = count
    s.frame_start, s.frame_end = start, end
    s.lifetime = life
    s.lifetime_random = 0.5
    s.emit_from = "FACE"
    s.normal_factor = vel
    s.factor_random = rand
    s.physics_type = "NEWTON"
    s.effector_weights.gravity = gravity
    s.render_type = "OBJECT"
    s.instance_object = inst
    s.particle_size = size
    s.size_random = size_rand
    emitter.show_instancer_for_render = False  # render the particles, not the emitter
    s.display_method = "DOT"
    return s


def build_fx(col, start, end):
    ember_mat = emission_material("M_Ember", (1.0, 0.42, 0.08), 60.0)
    ash_mat = bpy.data.materials.new("M_Ash")
    ash_mat.diffuse_color = (0.05, 0.05, 0.05, 1)
    blob_mat = emission_material("M_LavaBlob", (1.0, 0.38, 0.05), 35.0)

    # rising embers from the lava around the islet
    ember = _particle_instance("FX_EmberInstance", 0.04, ember_mat, col)
    em = _annulus("FX_EmberEmitter", ISLET_RADIUS, ISLET_RADIUS + 22, LAVA_Z + 0.2, col)
    _particles(em, "Embers", ember, 5000, start - 120, end, 140, 2.5, 1.5, -0.12, 1.0, 0.7, 3)
    # fine sparks close to the dancers (slower, many)
    em2 = _annulus("FX_SparkEmitter", ISLET_RADIUS - 1, ISLET_RADIUS + 6, LAVA_Z + 0.1, col)
    _particles(em2, "Sparks", ember, 2500, start - 60, end, 90, 4.0, 2.0, -0.05, 0.5, 0.6, 9)
    # falling ash from the crater mouth
    ash = _particle_instance("FX_AshInstance", 0.02, ash_mat, col)
    ae = _annulus("FX_AshEmitter", 0.0, CRATER_RADIUS - 5, 0.0, col)
    ae.rotation_euler.x = math.pi  # normals down
    ae.location.z = 45.0
    ash_ps = _particles(ae, "Ash", ash, 3000, start - 400, end, 400, 0.6, 0.6, 0.04, 1.0, 0.8, 5)
    ash_ps.effector_weights.wind = 0.0  # the heat updraft only lifts embers
    # turbulence keeps embers and ash swirling
    bpy.ops.object.effector_add(type="TURBULENCE", location=(0, 0, 8))
    t = bpy.context.object
    t.name = "FX_Turbulence"
    t.field.strength = 4.0
    t.field.size = 3.0
    t.field.flow = 0.5
    _link(t, col)
    bpy.ops.object.effector_add(type="WIND", location=(0, 0, -5), rotation=(0, 0, 0))
    w = bpy.context.object
    w.name = "FX_HeatUpdraft"
    w.field.strength = 1.5
    w.field.noise = 1.0
    _link(w, col)

    # lava bursts: short fountains with a matching light pulse
    rnd = random.Random(21)
    blob = _particle_instance("FX_LavaBlobInstance", 0.09, blob_mat, col)
    for k, frame in enumerate((140, 330, 520, 700, 860, 1040)):
        a = rnd.uniform(0, 2 * math.pi)
        r = rnd.uniform(ISLET_RADIUS + 3, ISLET_RADIUS + 10)
        pos = Vector((math.cos(a) * r, math.sin(a) * r, LAVA_Z + 0.1))
        bpy.ops.mesh.primitive_circle_add(vertices=12, radius=0.8, fill_type="NGON", location=pos)
        e = bpy.context.object
        e.name = f"FX_Burst{k}"
        _link(e, col)
        _particles(e, f"Burst{k}", blob, 260, frame, frame + 25, 60, 9.0, 3.5, 1.0, 1.0, 0.8, 30 + k)
        ld = bpy.data.lights.new(f"BurstLight{k}", "POINT")
        ld.color = LAVA_GLOW
        ld.shadow_soft_size = 1.5
        lo = bpy.data.objects.new(f"BurstLight{k}", ld)
        lo.location = pos + Vector((0, 0, 2.0))
        col.objects.link(lo)
        for f, en in ((frame - 5, 0), (frame + 4, 60000), (frame + 30, 20000), (frame + 70, 0)):
            ld.energy = en
            ld.keyframe_insert("energy", frame=f)

    # volumes: low lava haze (glowing from below) + drifting smoke higher up
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 3.5))
    haze = bpy.context.object
    haze.name = "FX_LavaHaze"
    haze.scale = (2 * CRATER_RADIUS + 20, 2 * CRATER_RADIUS + 20, 7)
    haze.data.materials.append(volume_material("M_LavaHaze", (0.9, 0.55, 0.4), 0.012, emission=LAVA_GLOW,
                                               emit_strength=0.004, scale=0.05, contrast=(0.35, 0.8)))
    _link(haze, col)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 32))
    smoke = bpy.context.object
    smoke.name = "FX_Smoke"
    smoke.scale = (2 * CRATER_RADIUS + 30, 2 * CRATER_RADIUS + 30, 50)
    smoke.data.materials.append(volume_material("M_Smoke", (0.3, 0.28, 0.27), 0.005, scale=0.02,
                                                contrast=(0.5, 0.8), anisotropy=0.5, w_speed=0.003))
    _link(smoke, col)


# ------------------------------------------------------------------ lights
def build_lights(col):
    sc = bpy.context.scene
    # lava bounce ring around the islet, aimed up/inward at the dancers
    for k in range(12):
        a = 2 * math.pi * k / 12
        pos = Vector((math.cos(a) * (ISLET_RADIUS + 3), math.sin(a) * (ISLET_RADIUS + 3), LAVA_Z + 0.4))
        ld = bpy.data.lights.new(f"LavaBounce{k}", "AREA")
        ld.shape = "DISK"
        ld.size = 7
        ld.color = LAVA_GLOW
        ld.spread = math.radians(160)
        lo = bpy.data.objects.new(f"LavaBounce{k}", ld)
        lo.location = pos
        tgt = Vector((0, 0, ISLET_TOP + 2.0))
        lo.rotation_euler = (tgt - pos).to_track_quat("-Z", "Y").to_euler()
        col.objects.link(lo)
        _emission_flicker(ld, 1500, 0.2, 0.2 + 0.03 * k, k * 0.9)
    # under-glow on the crater walls
    for k in range(10):
        a = 2 * math.pi * (k + 0.5) / 10
        pos = Vector((math.cos(a) * (CRATER_RADIUS - 10), math.sin(a) * (CRATER_RADIUS - 10), LAVA_Z + 1.0))
        ld = bpy.data.lights.new(f"WallGlow{k}", "AREA")
        ld.shape = "DISK"
        ld.size = 18
        ld.color = LAVA_HOT
        lo = bpy.data.objects.new(f"WallGlow{k}", ld)
        lo.location = pos
        tgt = Vector((math.cos(a) * CRATER_RADIUS * 1.3, math.sin(a) * CRATER_RADIUS * 1.3, 25))
        lo.rotation_euler = (tgt - pos).to_track_quat("-Z", "Y").to_euler()
        col.objects.link(lo)
        _emission_flicker(ld, 12000, 0.15, 0.12 + 0.02 * k, k * 1.3)
    # warm key on the dancers (from the brightest lava side, raised)
    key = bpy.data.lights.new("DancerKey", "SPOT")
    key.energy = 16000
    key.color = (1.0, 0.62, 0.38)
    key.spot_size = math.radians(55)
    key.spot_blend = 0.8
    key.shadow_soft_size = 2.0
    ko = bpy.data.objects.new("DancerKey", key)
    ko.location = (-9, -14, 12)
    ko.rotation_euler = (Vector((0, 0, ISLET_TOP)) - ko.location).to_track_quat("-Z", "Y").to_euler()
    col.objects.link(ko)
    # lava glow bounced back down by the smoke layer: soft warm top fill
    top = bpy.data.lights.new("SmokeBounce", "AREA")
    top.shape = "DISK"
    top.size = 22
    top.energy = 9000
    top.color = (1.0, 0.5, 0.25)
    to = bpy.data.objects.new("SmokeBounce", top)
    to.location = (0, 0, ISLET_TOP + 24)
    col.objects.link(to)
    # cool rim from the crater mouth for separation
    rim = bpy.data.lights.new("SkyRim", "SUN")
    rim.energy = 1.2
    rim.color = (0.45, 0.6, 1.0)
    rim.angle = math.radians(4)
    ro = bpy.data.objects.new("SkyRim", rim)
    ro.rotation_euler = (math.radians(30), 0, math.radians(160))
    col.objects.link(ro)
    # smoky dark-red sky through the crater opening
    world = bpy.data.worlds.new("VolcanoSky")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.08, 0.03, 0.025, 1)
    bg.inputs["Strength"].default_value = 0.25
    sc.world = world


def build_compositor():
    sc = bpy.context.scene
    sc.use_nodes = True
    nt = sc.node_tree
    n, l = nt.nodes, nt.links
    for x in list(n):
        n.remove(x)
    rl = n.new("CompositorNodeRLayers")
    glare = n.new("CompositorNodeGlare")
    glare.glare_type = "FOG_GLOW"
    glare.quality = "HIGH"
    glare.threshold = 1.5
    glare.size = 8
    glare.mix = -0.55
    lens = n.new("CompositorNodeLensdist")
    lens.inputs["Distortion"].default_value = -0.005
    lens.inputs["Dispersion"].default_value = 0.012
    lens.use_fit = True
    grade = n.new("CompositorNodeColorBalance")
    grade.correction_method = "LIFT_GAMMA_GAIN"
    grade.lift = (0.97, 0.99, 1.04)   # cool shadows
    grade.gain = (1.06, 1.0, 0.94)    # warm highlights
    mask = n.new("CompositorNodeEllipseMask")
    mask.width, mask.height = 0.95, 0.85
    blur = n.new("CompositorNodeBlur")
    blur.filter_type = "FAST_GAUSS"
    blur.use_relative = True
    blur.factor_x = blur.factor_y = 30
    vig = n.new("CompositorNodeMixRGB")
    vig.blend_type = "MULTIPLY"
    vig.inputs["Fac"].default_value = 0.45
    comp = n.new("CompositorNodeComposite")
    view = n.new("CompositorNodeViewer")
    l.new(rl.outputs["Image"], glare.inputs["Image"])
    l.new(glare.outputs["Image"], lens.inputs["Image"])
    l.new(lens.outputs["Image"], grade.inputs["Image"])
    l.new(mask.outputs["Mask"], blur.inputs["Image"])
    l.new(grade.outputs["Image"], vig.inputs[1])
    l.new(blur.outputs["Image"], vig.inputs[2])
    l.new(vig.outputs["Image"], comp.inputs["Image"])
    l.new(vig.outputs["Image"], view.inputs["Image"])


def camera_shake(cam, strength=0.04, scale=25.0):
    """Subtle drone shake on top of the baked camera path."""
    for fc in cam.animation_data.action.fcurves:
        if fc.data_path == "location":
            mod = fc.modifiers.new("NOISE")
            mod.strength = strength
            mod.scale = scale
            mod.phase = fc.array_index * 13.0


def render_settings():
    sc = bpy.context.scene
    ee = sc.eevee
    for attr, val in (("use_shadows", True), ("use_raytracing", True), ("use_volumetric_shadows", True),
                      ("volumetric_tile_size", "4"), ("volumetric_samples", 64), ("volumetric_end", 250.0),
                      ("volumetric_start", 0.5), ("use_volumetric_lights", True), ("taa_render_samples", 64),
                      ("shadow_ray_count", 2), ("shadow_step_count", 8), ("use_fast_gi", True),
                      ("fast_gi_method", "GLOBAL_ILLUMINATION"), ("use_gtao", True)):
        if hasattr(ee, attr):
            try:
                setattr(ee, attr, val)
            except (TypeError, ValueError):
                pass
    if hasattr(ee, "ray_tracing_options"):
        ee.ray_tracing_options.resolution_scale = "2"
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 0.5
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Punchy"
    sc.view_settings.exposure = -0.25


def build(col_set, col_lights, col_fx, start, end):
    build_islet(col_set)
    build_crater(col_set)
    build_lava(col_set, start, end)
    spires = list(build_spires(col_set))
    islet_mat = basalt_material("M_IsletBasalt", glow_height=0.9, glow_strength=8.0, crack_scale=2.5)
    wall_mat = basalt_material("M_CraterBasalt", glow_height=4.0, glow_strength=5.0, strata=True, crack_scale=0.6)
    spire_mat = basalt_material("M_SpireBasalt", glow_height=2.5, glow_strength=10.0, crack_scale=1.5)
    for o in col_set.objects:
        if o.type != "MESH" or o.data.materials:
            continue
        if o.name == "CraterWall":
            o.data.materials.append(wall_mat)
        elif o in spires:
            o.data.materials.append(spire_mat)
        else:
            o.data.materials.append(islet_mat)
    build_lights(col_lights)
    build_fx(col_fx, start, end)
    build_compositor()
    render_settings()
