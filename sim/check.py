#!/usr/bin/env python3
"""Find the frames the system simulation should have shown, bit for bit.

usage: python3 sim/check.py sim_out [--png DIR]

Rendering a frame takes longer than displaying one, so instead of fixed frame
numbers each expected image must appear among the captured frames, in order.
Exits non-zero on any mismatch.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "model"))
import hw  # noqa: E402

D = hw.DEFAULT_PARAMS
S = hw.DEFAULT_SCENE
AFTER = dict(D, yaw=0x3200, pitch=0x0400, light_az=0x7400, light_el=0x1800)
CASES = [
    # (description, params, scene, quality, test pattern)
    ("first frame: defaults + one auto-motion step",
     dict(D, yaw=0x0020, light_az=(D["light_az"] + 0x10) & 0xFFFF), dict(S, anim=0x0040), False, False),
    ("after W commands and keys d, l (reflective floor)", AFTER, dict(S, anim=0x2000, floor_kr=1), False, False),
    ("640x480 quality mode", AFTER, dict(S, anim=0x2000), True, False),
    ("640x480 test pattern", AFTER, dict(S, anim=0x2000), True, True),
]


def read_ppm(path):
    with open(path, "rb") as f:
        data = f.read()
    parts = data.split(b"\n", 3)
    assert parts[0] == b"P6" and parts[1] == b"640 480" and parts[2] == b"255", path
    return parts[3]


def expected_rgb(img565):
    out = bytearray()
    scale = 640 // len(img565[0])
    for row in img565:
        line = b"".join(bytes(hw.rgb565_to_888(v)) * scale for v in row)
        out += line * scale
    return bytes(out)


def main():
    out_dir = sys.argv[1]
    png_dir = sys.argv[sys.argv.index("--png") + 1] if "--png" in sys.argv else None
    ok = True
    log = open(os.path.join(out_dir, "sim.log")).read()
    for needle in ("uart: ok", "uart: 00=5254", "uart: 02=3200", "uart: 13=", "sdram reads=", "errors=0",
                   "dvi errors=0"):
        if needle not in log:
            print(f"FAIL: '{needle}' not in sim.log")
            ok = False
    frames = sorted(glob.glob(os.path.join(out_dir, "frame_*.ppm")))
    pos = 0
    for n, (desc, params, scene, quality, tp) in enumerate(CASES, 1):
        want = expected_rgb(hw.render_frame(params, scene, quality, tp))
        found = None
        best = None
        for i in range(pos, len(frames)):
            got = read_ppm(frames[i])
            if got == want:
                found = i
                break
            bad = sum(1 for k in range(0, len(want), 3) if got[k:k + 3] != want[k:k + 3])
            if best is None or bad < best[0]:
                best = (bad, i)
        if found is None:
            print(f"FAIL: case {n} ({desc}): not shown; closest {os.path.basename(frames[best[1]])} "
                  f"with {best[0]} of {640 * 480} pixels different" if best else f"FAIL: case {n}: no frames")
            ok = False
        else:
            print(f"ok: case {n} ({desc}): {os.path.basename(frames[found])}, all {640 * 480} pixels match")
            pos = found + 1
            if png_dir:
                from PIL import Image
                Image.frombytes("RGB", (640, 480), read_ppm(frames[found])).save(
                    os.path.join(png_dir, f"sim_frame_{n}.png"))
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
