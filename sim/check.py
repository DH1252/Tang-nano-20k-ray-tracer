#!/usr/bin/env python3
"""Compare frames captured by the system simulation with the Python model.

usage: python3 sim/check.py sim_out [--png DIR]
Exits non-zero on any mismatch.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "model"))
import hw  # noqa: E402

D = hw.DEFAULT_PARAMS
CASES = [
    # (frame, description, params, test pattern)
    (1, "defaults + one auto-motion step",
     dict(D, yaw=0x0020, light_az=(D["light_az"] + 0x10) & 0xFFFF), False),
    (4, "after W commands and keys d, l",
     dict(D, yaw=0x3200, pitch=0x0400, light_az=0x7400, light_el=0x1800), False),
    (7, "test pattern", dict(D, yaw=0x3200, pitch=0x0400, light_az=0x7400, light_el=0x1800), True),
]


def read_ppm(path):
    with open(path, "rb") as f:
        data = f.read()
    parts = data.split(b"\n", 3)
    assert parts[0] == b"P6" and parts[1] == b"640 480" and parts[2] == b"255", path
    return parts[3]


def expected_rgb(img565):
    out = bytearray()
    for row in img565:
        line = b"".join(bytes(hw.rgb565_to_888(v)) * 2 for v in row)
        out += line * 2
    return bytes(out)


def main():
    out_dir = sys.argv[1]
    png_dir = sys.argv[sys.argv.index("--png") + 1] if "--png" in sys.argv else None
    ok = True
    log = open(os.path.join(out_dir, "sim.log")).read()
    for needle in ("uart: ok", "uart: 00=5254", "uart: 02=3200", "sdram reads=", "errors=0", "dvi errors=0"):
        if needle not in log:
            print(f"FAIL: '{needle}' not in sim.log")
            ok = False
    for frame, desc, params, tp in CASES:
        path = os.path.join(out_dir, f"frame_{frame:03d}.ppm")
        got = read_ppm(path)
        want = expected_rgb(hw.render_frame(params, tp))
        bad = sum(1 for i in range(0, len(want), 3) if got[i:i + 3] != want[i:i + 3])
        status = "ok" if bad == 0 else "FAIL"
        print(f"{status}: frame {frame} ({desc}): {bad} of {640 * 480} pixels differ")
        ok &= bad == 0
        if png_dir:
            from PIL import Image
            Image.frombytes("RGB", (640, 480), got).save(os.path.join(png_dir, f"sim_frame_{frame}.png"))
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
