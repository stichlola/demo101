"""Encode rendered PNG frames into an H.264 MP4 with Blender's sequencer.

    blender -b -P scripts/encode_video.py -- --frames output/render/frames \
        --out output/render/rat_dance.mp4 --fps 30
"""
import argparse
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--frames", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--fps", type=int, default=30)
a = ap.parse_args(argv)

files = sorted(f for f in os.listdir(a.frames) if f.endswith(".png"))
sc = bpy.context.scene
img = bpy.data.images.load(os.path.join(a.frames, files[0]))
sc.render.resolution_x, sc.render.resolution_y = img.size
sc.render.resolution_percentage = 100
sc.render.fps = a.fps
se = sc.sequence_editor_create()
strip = se.sequences.new_image("frames", os.path.join(a.frames, files[0]), 1, 1)
for f in files[1:]:
    strip.elements.append(f)
sc.frame_start, sc.frame_end = 1, len(files)
sc.render.image_settings.file_format = "FFMPEG"
sc.render.ffmpeg.format = "MPEG4"
sc.render.ffmpeg.codec = "H264"
sc.render.ffmpeg.constant_rate_factor = "HIGH"
sc.render.ffmpeg.ffmpeg_preset = "GOOD"
sc.render.filepath = a.out
bpy.ops.render.render(animation=True)
print("encoded", a.out, len(files), "frames")
