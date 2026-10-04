"""Auto-rig static character meshes (GLB) onto the mocap skeleton layout.

Pipeline for each character:
1. import the GLB (Z up, facing -Y, A-pose) and scale it to the mocap
   skeleton's leg length;
2. build an armature in the mesh's A-pose from joint landmarks, with the same
   bone names as the BVH skeleton (Hips, Spine, LeftUpLeg, ...);
3. skin the mesh (Blender bone heat, falling back to nearest-bone weights);
4. pose every bone onto the direction of the mocap rest pose, bake that into
   the mesh and apply it as the new rest pose, then copy the bone rolls.

After step 4 the rig has the same rest orientations as the BVH armature, so
the BVH actions play on it unchanged.

Landmarks are in the model's own units (the GLBs are 1 m tall), "L" side only
(+X); the right side is mirrored.
"""
import bpy
from mathutils import Matrix, Vector

LANDMARKS = {
    # goblin_3d_model.glb: chibi proportions, hunched, big head
    "goblin": {
        "pelvis": (0, 0.12, 0.32), "hip": (0.08, 0.12, 0.29), "knee": (0.13, 0.10, 0.17),
        "ankle": (0.15, 0.13, 0.06), "toe": (0.18, 0.00, 0.025), "toe_end": (0.20, -0.05, 0.02),
        "spine1": (0, 0.13, 0.42), "spine2": (0, 0.13, 0.50), "neck0": (0, 0.12, 0.57),
        "neck1": (0, 0.09, 0.61), "head0": (0, 0.06, 0.65), "head1": (0, 0.02, 0.97),
        "shoulder": (0.16, 0.15, 0.55), "elbow": (0.24, 0.17, 0.42), "wrist": (0.29, 0.10, 0.31),
        "hand": (0.31, 0.07, 0.26), "finger": (0.32, 0.05, 0.20), "thumb": (0.30, 0.00, 0.27),
    },
    # skeleton_3d_model.glb: slim human proportions
    "skeleton": {
        "pelvis": (0, 0.0, 0.50), "hip": (0.06, 0.0, 0.47), "knee": (0.11, -0.01, 0.28),
        "ankle": (0.13, 0.04, 0.07), "toe": (0.14, -0.04, 0.02), "toe_end": (0.15, -0.09, 0.01),
        "spine1": (0, 0.01, 0.58), "spine2": (0, 0.0, 0.67), "neck0": (0, 0.0, 0.77),
        "neck1": (0, 0.0, 0.81), "head0": (0, 0.0, 0.84), "head1": (0, 0.0, 0.99),
        "shoulder": (0.12, 0.0, 0.77), "elbow": (0.17, 0.03, 0.63), "wrist": (0.19, 0.0, 0.50),
        "hand": (0.195, -0.01, 0.45), "finger": (0.20, -0.02, 0.38), "thumb": (0.19, -0.04, 0.45),
    },
}


def _bone_layout(lm):
    """(bone, head, tail) for the BVH skeleton, from landmarks (A-pose)."""
    v = {k: Vector(p) for k, p in lm.items()}
    out = [
        ("Hips", v["pelvis"], v["pelvis"] + Vector((0, 0, 0.04))),
        ("Spine", v["pelvis"], v["spine1"]),
        ("Spine1", v["spine1"], v["spine2"]),
        ("Spine2", v["spine2"], v["neck0"]),
        ("Neck", v["neck0"], v["neck1"]),
        ("Neck1", v["neck1"], v["head0"]),
        ("Head", v["head0"], v["head1"]),
    ]
    for side, sx in (("Left", 1), ("Right", -1)):
        m = lambda k: Vector((v[k].x * sx, v[k].y, v[k].z))
        mid = m("hand").lerp(m("finger"), 0.4)
        out += [
            (f"{side}HipJoint", v["pelvis"], m("hip")),
            (f"{side}UpLeg", m("hip"), m("knee")),
            (f"{side}Leg", m("knee"), m("ankle")),
            (f"{side}Foot", m("ankle"), m("toe")),
            (f"{side}ToeBase", m("toe"), m("toe_end")),
            (f"{side}Shoulder", v["neck0"], m("shoulder")),
            (f"{side}Arm", m("shoulder"), m("elbow")),
            (f"{side}ForeArm", m("elbow"), m("wrist")),
            (f"{side}Hand", m("wrist"), m("hand")),
            (f"{side}HandMid", m("hand"), mid),
            (f"{side}HandIndex1", mid, m("finger")),
            (f"{side}HandThumb1", m("hand"), m("thumb")),
        ]
    return out


def _activate(obj, mode="OBJECT"):
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if mode != "OBJECT":
        bpy.ops.object.mode_set(mode=mode)


def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    for o in new:
        if o.type != "MESH":
            for m in meshes:
                if m.parent == o:
                    w = m.matrix_world.copy()
                    m.parent = None
                    m.matrix_world = w
    for o in new:
        if o.type != "MESH":
            bpy.data.objects.remove(o)
    if len(meshes) > 1:
        _activate(meshes[0])
        for m in meshes[1:]:
            m.select_set(True)
        bpy.ops.object.join()
    mesh = meshes[0]
    _activate(mesh)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    # generated meshes are split along UV seams: weld them so skinning can't tear
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=0.0005)
    bpy.ops.object.mode_set(mode="OBJECT")
    return mesh


def _nearest_bone_weights(mesh, arm, power=6.0, only=None):
    """Fallback skinning: inverse-distance weights to the closest bone segments."""
    segs = []
    for b in arm.data.bones:
        if not b.use_deform:
            continue
        segs.append((b.name, b.head_local.copy(), b.tail_local.copy()))
    for name, _, _ in segs:
        if name not in mesh.vertex_groups:
            mesh.vertex_groups.new(name=name)
    groups = {g.name: g for g in mesh.vertex_groups}
    for v in mesh.data.vertices:
        if only is not None and v.index not in only:
            continue
        for g in v.groups:
            mesh.vertex_groups[g.group].remove([v.index])
        p = v.co
        ds = []
        for name, h, t in segs:
            ab = t - h
            k = max(0.0, min(1.0, (p - h).dot(ab) / max(ab.length_squared, 1e-9)))
            ds.append(((p - (h + ab * k)).length + 1e-4, name))
        ds.sort()
        ds = ds[:3]
        ws = [(1.0 / d ** power, n) for d, n in ds]
        tot = sum(w for w, _ in ws)
        for w, n in ws:
            groups[n].add([v.index], w / tot, "REPLACE")


def rig_character(glb_path, kind, source_arm, name):
    """Return (armature, mesh) rigged to match `source_arm`'s rest pose."""
    lm = LANDMARKS[kind]
    mesh = import_glb(glb_path)
    mesh.name = f"{name}_mesh"

    # scale so the leg length matches the mocap skeleton (feet stay planted)
    src = source_arm.data.bones
    src_leg = (src["LeftUpLeg"].head_local - src["LeftFoot"].head_local).length
    dst_leg = (Vector(lm["hip"]) - Vector(lm["ankle"])).length
    s = src_leg / dst_leg
    pelvis = Vector(lm["pelvis"]) * s
    height = max((mesh.matrix_world @ Vector(c)).z for c in mesh.bound_box) * s
    # model space -> rig space: scaled, pelvis at the origin like the BVH root
    to_rig = Matrix.Translation(-pelvis) @ Matrix.Scale(s, 4)
    mesh.data.transform(to_rig)
    mesh.matrix_world = Matrix.Identity(4)

    # 1. armature in the mesh's A-pose
    arm_data = bpy.data.armatures.new(name)
    arm = bpy.data.objects.new(name, arm_data)
    bpy.context.scene.collection.objects.link(arm)
    _activate(arm, "EDIT")
    eb = arm_data.edit_bones
    for bname, h, t in _bone_layout(lm):
        b = eb.new(bname)
        b.head = to_rig @ h
        b.tail = to_rig @ t
    for b in eb:
        sb = src[b.name]
        if sb.parent:
            b.parent = eb[sb.parent.name]
        b.align_roll(Vector((0, -1, 0)) if abs(b.vector.normalized().y) < 0.9 else Vector((0, 0, 1)))
    for small in ("Hips", "LeftHipJoint", "RightHipJoint", "LeftHandThumb1", "RightHandThumb1",
                  "LeftHandIndex1", "RightHandIndex1", "LeftToeBase", "RightToeBase"):
        eb[small].use_deform = small in ("Hips", "LeftHandThumb1", "RightHandThumb1",
                                          "LeftHandIndex1", "RightHandIndex1", "LeftToeBase", "RightToeBase")
    bpy.ops.object.mode_set(mode="OBJECT")

    # 2. skin: bone heat, then fill in anything it missed
    _activate(mesh)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    try:
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    except RuntimeError:
        pass
    if not any(m.type == "ARMATURE" for m in mesh.modifiers):
        mesh.parent = arm
        mod = mesh.modifiers.new("Armature", "ARMATURE")
        mod.object = arm
    missing = [v.index for v in mesh.data.vertices if not any(g.weight > 0.01 for g in v.groups)]
    print(f"[rig] {name}: bone heat left {len(missing)}/{len(mesh.data.vertices)} vertices unweighted")
    if missing:
        _nearest_bone_weights(mesh, arm, only=set(missing))

    # 3. pose onto the mocap rest directions (parents first)
    _activate(arm, "POSE")
    order = [b.name for b in src]  # BVH bones are stored parent-first
    for bname in order:
        pb = arm.pose.bones[bname]
        sb = src[bname]
        target_dir = (sb.tail_local - sb.head_local).normalized()
        M = pb.matrix.copy()
        q = M.col[1].xyz.normalized().rotation_difference(target_dir)
        pb.matrix = Matrix.Translation(M.translation) @ q.to_matrix().to_4x4() @ M.to_3x3().to_4x4()
        bpy.context.view_layer.update()
    bpy.ops.object.mode_set(mode="OBJECT")

    # bake the pose into the mesh and make it the rest pose
    _activate(mesh)
    mod = next(m for m in mesh.modifiers if m.type == "ARMATURE")
    bpy.ops.object.modifier_apply(modifier=mod.name)
    _activate(arm, "POSE")
    bpy.ops.pose.armature_apply(selected=False)
    bpy.ops.object.mode_set(mode="EDIT")
    for b in arm_data.edit_bones:
        b.align_roll(src[b.name].matrix_local.col[2].xyz)
    bpy.ops.object.mode_set(mode="OBJECT")
    mod = mesh.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    mesh.parent = arm
    mesh.matrix_parent_inverse = Matrix.Identity(4)

    # same rotation modes as the BVH pose so its actions play unchanged
    for pb in arm.pose.bones:
        pb.rotation_mode = source_arm.pose.bones[pb.name].rotation_mode
    arm["rest_height"] = height
    arm["foot_offset"] = -pelvis.z  # rest-pose ground height in rig space
    arm_data.display_type = "STICK"
    return arm, mesh
