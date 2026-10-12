#!/usr/bin/env python3
"""Control the Tang Nano 20K ray tracer over its USB UART (115200 8N1).

Examples
  rtctl.py /dev/ttyUSB1 dump                   # all registers, decoded
  rtctl.py /dev/ttyUSB1 set yaw 45             # degrees
  rtctl.py /dev/ttyUSB1 set dist 4.5 fov 70    # world units, horizontal fov in degrees
  rtctl.py /dev/ttyUSB1 set sun_el 30 sun_az 200 orbit off
  rtctl.py /dev/ttyUSB1 get yaw pitch
  rtctl.py /dev/ttyUSB1 keys                   # interactive: keys go straight to the board
  rtctl.py /dev/ttyUSB1 raw "W 02 4000"        # raw protocol line

Requires pyserial (pip install pyserial). See docs/uart-protocol.md.
"""
import math
import sys
import time

try:
    import serial
except ImportError:  # pragma: no cover
    serial = None

FPS = 60.0


def angle_enc(deg):
    return round(deg / 360.0 * 65536) & 0xFFFF


def angle_dec(v):
    if v >= 0x8000:
        v -= 0x10000
    return v * 360.0 / 65536


def fixed_enc(x, frac, signed):
    v = round(x * (1 << frac))
    lo, hi = (-0x8000, 0x7FFF) if signed else (0, 0xFFFF)
    return max(lo, min(hi, v)) & 0xFFFF


def fixed_dec(v, frac, signed):
    if signed and v >= 0x8000:
        v -= 0x10000
    return v / (1 << frac)


def speed_enc(deg_per_s):
    return round(deg_per_s / FPS / 360.0 * 65536) & 0xFFFF


def speed_dec(v):
    return angle_dec(v) * FPS


def fov_enc(hfov_deg):
    return fixed_enc(math.tan(math.radians(hfov_deg) / 2), 15, False)


def fov_dec(v):
    return math.degrees(2 * math.atan(v / 32768))


# name: (address, encode, decode, unit)
REGS = {
    "id": (0x00, None, lambda v: f"0x{v:04x}", ""),
    "ctrl": (0x01, lambda s: int(s, 0), lambda v: f"0x{v:04x}", ""),
    "yaw": (0x02, lambda s: angle_enc(float(s)), angle_dec, "deg"),
    "pitch": (0x03, lambda s: angle_enc(float(s)), angle_dec, "deg"),
    "dist": (0x04, lambda s: fixed_enc(float(s), 12, False), lambda v: fixed_dec(v, 12, False), "units"),
    "target_x": (0x05, lambda s: fixed_enc(float(s), 12, True), lambda v: fixed_dec(v, 12, True), "units"),
    "target_y": (0x06, lambda s: fixed_enc(float(s), 12, True), lambda v: fixed_dec(v, 12, True), "units"),
    "target_z": (0x07, lambda s: fixed_enc(float(s), 12, True), lambda v: fixed_dec(v, 12, True), "units"),
    "fov": (0x08, lambda s: fov_enc(float(s)), fov_dec, "deg (horizontal)"),
    "orbit_speed": (0x09, lambda s: speed_enc(float(s)), speed_dec, "deg/s"),
    "sun_az": (0x0A, lambda s: angle_enc(float(s)), angle_dec, "deg"),
    "sun_el": (0x0B, lambda s: angle_enc(float(s)), angle_dec, "deg"),
    "sun_speed": (0x0C, lambda s: speed_enc(float(s)), speed_dec, "deg/s"),
    "sdram_rd_lat": (0x0D, lambda s: int(s, 0), int, "cycles"),
    "frames": (0x0E, None, int, ""),
    "status": (0x0F, None, lambda v: f"sdram_ready={v & 1} front_buffer={(v >> 1) & 1}", ""),
}
FLAGS = {"orbit": 0x1, "sun_motion": 0x2, "freeze": 0x4, "test_pattern": 0x8}


class Board:
    def __init__(self, port):
        if serial is None:
            sys.exit("pyserial is required: pip install pyserial")
        self.s = serial.Serial(port, 115200, timeout=0.5)
        time.sleep(0.05)
        self.s.reset_input_buffer()

    def line(self, text):
        self.s.write((text + "\r").encode())
        reply = self.s.readline().decode(errors="replace").strip()
        if not reply:
            raise RuntimeError(f"no reply to {text!r}")
        return reply

    def read(self, addr):
        reply = self.line(f"R {addr:02x}")
        if "=" not in reply:
            raise RuntimeError(f"bad reply {reply!r}")
        return int(reply.split("=")[1], 16)

    def write(self, addr, value):
        reply = self.line(f"W {addr:02x} {value:04x}")
        if reply != "ok":
            raise RuntimeError(f"write rejected: {reply!r}")


def cmd_dump(b, _args):
    for name, (addr, _enc, dec, unit) in REGS.items():
        v = b.read(addr)
        print(f"{addr:02x} {name:13s} 0x{v:04x}  {dec(v)} {unit}".rstrip())
    ctrl = b.read(0x01)
    print("flags:", ", ".join(f"{k}={'on' if ctrl & m else 'off'}" for k, m in FLAGS.items()))


def cmd_get(b, args):
    for name in args:
        addr, _enc, dec, unit = REGS[name]
        print(f"{name} = {dec(b.read(addr))} {unit}".rstrip())


def cmd_set(b, args):
    if len(args) % 2:
        sys.exit("set needs name/value pairs")
    for name, value in zip(args[::2], args[1::2]):
        if name in FLAGS:
            ctrl = b.read(0x01)
            on = value.lower() in ("1", "on", "true", "yes")
            b.write(0x01, (ctrl | FLAGS[name]) if on else (ctrl & ~FLAGS[name]))
        else:
            addr, enc, _dec, _unit = REGS[name]
            if enc is None:
                sys.exit(f"{name} is read-only")
            b.write(addr, enc(value))


def cmd_raw(b, args):
    print(b.line(" ".join(args)))


def cmd_keys(b, _args):
    import termios
    import tty
    print(__doc_keys__)
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch in ("q", "\x1b"):
                break
            b.s.write(ch.encode())
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


__doc_keys__ = """keys: a/d yaw  w/s pitch  z/x distance  j/l sun azimuth  i/k sun elevation
      o orbit on/off  p sun motion on/off  f freeze  t test pattern  c defaults
      q or Esc quits"""

COMMANDS = {"dump": cmd_dump, "get": cmd_get, "set": cmd_set, "raw": cmd_raw, "keys": cmd_keys}


def main(argv):
    if len(argv) < 3 or argv[2] not in COMMANDS:
        print(__doc__)
        print("registers:", ", ".join(REGS), "\nflags:", ", ".join(FLAGS))
        return 1
    COMMANDS[argv[2]](Board(argv[1]), argv[3:])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
