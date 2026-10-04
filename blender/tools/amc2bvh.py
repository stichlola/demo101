#!/usr/bin/env python3
"""Convert CMU ASF/AMC motion capture into BVH with Mixamo-style joint names.

Pure Python (no numpy), so it runs with system Python or Blender's Python.

    python3 amc2bvh.py 85.asf 85_12.amc out.bvh --fps 30

The output is Y-up, in metres, with joint names such as Hips, Spine,
LeftUpLeg ... so every character in the scene shares one skeleton layout.
CMU data: http://mocap.cs.cmu.edu/ (free for all uses).
"""
import argparse
import math

# CMU bone name -> standard joint name
NAME_MAP = {
    "root": "Hips",
    "lhipjoint": "LeftHipJoint", "lfemur": "LeftUpLeg", "ltibia": "LeftLeg",
    "lfoot": "LeftFoot", "ltoes": "LeftToeBase",
    "rhipjoint": "RightHipJoint", "rfemur": "RightUpLeg", "rtibia": "RightLeg",
    "rfoot": "RightFoot", "rtoes": "RightToeBase",
    "lowerback": "Spine", "upperback": "Spine1", "thorax": "Spine2",
    "lowerneck": "Neck", "upperneck": "Neck1", "head": "Head",
    "lclavicle": "LeftShoulder", "lhumerus": "LeftArm", "lradius": "LeftForeArm",
    "lwrist": "LeftHand", "lhand": "LeftHandMid", "lfingers": "LeftHandIndex1",
    "lthumb": "LeftHandThumb1",
    "rclavicle": "RightShoulder", "rhumerus": "RightArm", "rradius": "RightForeArm",
    "rwrist": "RightHand", "rhand": "RightHandMid", "rfingers": "RightHandIndex1",
    "rthumb": "RightHandThumb1",
}

INCH = 0.0254


# ---------------------------------------------------------------- matrices
def rx(a):
    c, s = math.cos(a), math.sin(a)
    return [[1, 0, 0], [0, c, -s], [0, s, c]]


def ry(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def rz(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def transpose(a):
    return [[a[j][i] for j in range(3)] for i in range(3)]


def euler_xyz(x, y, z):
    """ASF/AMC convention: rotate about X, then Y, then Z (fixed axes)."""
    return mul(rz(z), mul(ry(y), rx(x)))


def to_zxy(m):
    """Decompose m = Rz * Rx * Ry, returned as (z, x, y) in degrees."""
    x = math.asin(max(-1.0, min(1.0, m[2][1])))
    y = math.atan2(-m[2][0], m[2][2])
    z = math.atan2(-m[0][1], m[1][1])
    return [math.degrees(z), math.degrees(x), math.degrees(y)]


# ---------------------------------------------------------------- parsing
class Bone:
    def __init__(self, name):
        self.name = name
        self.direction = [0.0, 0.0, 0.0]
        self.length = 0.0
        self.axis = [0.0, 0.0, 0.0]
        self.dof = []
        self.children = []
        self.parent = None


def parse_asf(path):
    lines = [l.strip() for l in open(path, encoding="latin-1").read().splitlines()]
    bones = {"root": Bone("root")}
    length_unit = 1.0
    section = None
    cur = None
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line or line.startswith("#"):
            continue
        if line.startswith(":"):
            section = line.split()[0][1:]
            continue
        tok = line.split()
        if section == "units" and tok[0] == "length":
            length_unit = float(tok[1])
        elif section == "root":
            if tok[0] == "orientation":
                bones["root"].axis = [float(v) for v in tok[1:4]]
        elif section == "bonedata":
            if tok[0] == "begin":
                cur = Bone("?")
            elif tok[0] == "end":
                bones[cur.name] = cur
                cur = None
            elif tok[0] == "name":
                cur.name = tok[1]
            elif tok[0] == "direction":
                cur.direction = [float(v) for v in tok[1:4]]
            elif tok[0] == "length":
                cur.length = float(tok[1])
            elif tok[0] == "axis":
                cur.axis = [float(v) for v in tok[1:4]]
            elif tok[0] == "dof":
                cur.dof = tok[1:]
        elif section == "hierarchy":
            if tok[0] in ("begin", "end"):
                continue
            parent = bones[tok[0]]
            for c in tok[1:]:
                parent.children.append(bones[c])
                bones[c].parent = parent
    scale = (1.0 / length_unit) * INCH
    for b in bones.values():
        b.length *= scale
        ax = [math.radians(v) for v in b.axis]
        b.C = euler_xyz(*ax)
        b.Cinv = transpose(b.C)
    return bones, scale


def parse_amc(path):
    frames = []
    cur = None
    for line in open(path, encoding="latin-1").read().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(":"):
            continue
        tok = line.split()
        if len(tok) == 1 and tok[0].isdigit():
            cur = {}
            frames.append(cur)
        elif cur is not None:
            cur[tok[0]] = [float(v) for v in tok[1:]]
    return frames


# ---------------------------------------------------------------- writing
def joint_order(bones):
    order = []

    def walk(b):
        order.append(b)
        for c in b.children:
            walk(c)

    walk(bones["root"])
    return order


def write_bvh(bones, scale, frames, out, fps, src_fps=120):
    lines = ["HIERARCHY"]

    def emit(b, depth, offset):
        ind = "  " * depth
        name = NAME_MAP.get(b.name, b.name)
        if b.name == "root":
            lines.append(f"ROOT {name}")
        else:
            lines.append(f"{ind}JOINT {name}")
        lines.append(ind + "{")
        lines.append(f"{ind}  OFFSET {offset[0]:.6f} {offset[1]:.6f} {offset[2]:.6f}")
        if b.name == "root":
            lines.append(f"{ind}  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation")
        else:
            lines.append(f"{ind}  CHANNELS 3 Zrotation Xrotation Yrotation")
        end = [d * b.length for d in b.direction]
        if b.children:
            for c in b.children:
                emit(c, depth + 1, end)
        else:
            lines.append(f"{ind}  End Site")
            lines.append(ind + "  {")
            lines.append(f"{ind}    OFFSET {end[0]:.6f} {end[1]:.6f} {end[2]:.6f}")
            lines.append(ind + "  }")
        lines.append(ind + "}")

    emit(bones["root"], 0, [0.0, 0.0, 0.0])

    step = max(1, round(src_fps / fps))
    picked = frames[::step]
    order = joint_order(bones)
    lines.append("MOTION")
    lines.append(f"Frames: {len(picked)}")
    lines.append(f"Frame Time: {step / src_fps:.6f}")

    prev = None
    for fr in picked:
        row = []
        for b in order:
            vals = fr.get(b.name, [])
            if b.name == "root":
                pos = [v * scale for v in vals[0:3]]
                rot = [math.radians(v) for v in vals[3:6]]
                L = euler_xyz(*rot)
                row.extend(pos)
            else:
                r = {"rx": 0.0, "ry": 0.0, "rz": 0.0}
                for d, v in zip(b.dof, vals):
                    r[d] = math.radians(v)
                L = euler_xyz(r["rx"], r["ry"], r["rz"])
            local = mul(b.C, mul(L, b.Cinv))
            row.extend(to_zxy(local))
        # keep euler channels continuous (avoid 180/-180 pops between frames)
        if prev is not None:
            for k in range(len(row)):
                if k < 3:
                    continue
                while row[k] - prev[k] > 180.0:
                    row[k] -= 360.0
                while row[k] - prev[k] < -180.0:
                    row[k] += 360.0
        prev = row
        lines.append(" ".join(f"{v:.5f}" for v in row))

    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    return len(picked)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("asf")
    ap.add_argument("amc")
    ap.add_argument("out")
    ap.add_argument("--fps", type=float, default=30.0)
    a = ap.parse_args()
    bones, scale = parse_asf(a.asf)
    frames = parse_amc(a.amc)
    n = write_bvh(bones, scale, frames, a.out, a.fps)
    print(f"{a.out}: {n} frames @ {a.fps:g} fps")


if __name__ == "__main__":
    main()
