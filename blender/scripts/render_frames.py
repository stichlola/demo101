"""Render a share of the animation as PNG frames (run several in parallel).

    blender -b output/rat_dance.blend -P scripts/render_frames.py -- \
        --out output/render/frames --workers 3 --index 0 --scale 50 --samples 8
"""
import argparse
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--workers", type=int, default=1)
ap.add_argument("--index", type=int, default=0)
ap.add_argument("--scale", type=int, default=50, help="resolution percentage")
ap.add_argument("--samples", type=int, default=16)
a = ap.parse_args(argv)

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE_NEXT"
sc.eevee.taa_render_samples = a.samples
sc.render.resolution_percentage = a.scale
sc.render.image_settings.file_format = "PNG"
os.makedirs(a.out, exist_ok=True)
for f in range(sc.frame_start + a.index, sc.frame_end + 1, a.workers):
    path = os.path.join(a.out, f"{f:04d}.png")
    if os.path.exists(path):
        continue  # resumable
    sc.frame_set(f)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print(f"FRAME {f} done", flush=True)
