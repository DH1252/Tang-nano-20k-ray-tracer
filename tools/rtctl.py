#!/usr/bin/env python3
"""Control the Tang Nano 20K ray tracer over its USB UART (115200 8N1).

usage: rtctl.py list                  serial ports on this computer
       rtctl.py PORT COMMAND [ARGS]   PORT is COM5 (Windows), /dev/ttyUSB1 (Linux),
                                      /dev/cu.usbserial-... (macOS)
Examples
  rtctl.py list                        # find the board's port
  rtctl.py COM5 dump                   # all registers, decoded
  rtctl.py COM5 set yaw 45             # degrees
  rtctl.py COM5 set dist 4.5 fov 70    # world units, horizontal fov in degrees
  rtctl.py COM5 set sun_el 30 sun_az 200 orbit off quality on
  rtctl.py COM5 set bounces 2 floor_kr 1 spheres 4   # fields of the scene register
  rtctl.py COM5 get yaw pitch cycles
  rtctl.py COM5 keys                   # interactive: keys go straight to the board
  rtctl.py COM5 raw "W 02 4000"        # raw protocol line
  rtctl.py COM5 debug                  # compare the hardware's camera and boxes
                                       # with model/hw.py (stops the motion)
  rtctl.py COM5 trig                   # sweep yaw and pitch, check the board's
                                       # sin/cos against the model

On Windows run it as `py tools\rtctl.py ...` from a Command Prompt or
PowerShell window. Requires pyserial (pip install pyserial). See
docs/uart-protocol.md.
"""
import math
import os
import sys
import time

try:
    import serial
    import serial.tools.list_ports
except ImportError:  # pragma: no cover
    serial = None


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


# Speeds are added once per rendered frame, and the frame rate depends on the
# scene (see `get cycles`), so they are given per frame.
def speed_enc(deg_per_frame):
    return round(deg_per_frame / 360.0 * 65536) & 0xFFFF


def speed_dec(v):
    return angle_dec(v)


def fov_enc(hfov_deg):
    return fixed_enc(math.tan(math.radians(hfov_deg) / 2), 15, False)


def fov_dec(v):
    return math.degrees(2 * math.atan(v / 32768))


def scene_dec(v):
    return f"0x{v:04x} (bounces={v & 3} floor_kr={(v >> 2) & 3}/4 spheres={min(6, (v >> 4) & 7)})"


# Core clock in MHz, read from the board (register 0x14) before decoding
# cycles; bitstreams without that register read 0 there, and get 75.
core_mhz = 75.0


def read_clock(b):
    global core_mhz
    v = b.read(0x14)
    if v:
        core_mhz = v / 100


def cycles_dec(v):
    ms = v * 256 / (core_mhz * 1e3)
    return f"{v * 256} cycles = {ms:.1f} ms = {1000 / ms:.1f} fps at {core_mhz:g} MHz" if v else "no frame yet"


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
    "orbit_speed": (0x09, lambda s: speed_enc(float(s)), speed_dec, "deg/frame"),
    "sun_az": (0x0A, lambda s: angle_enc(float(s)), angle_dec, "deg"),
    "sun_el": (0x0B, lambda s: angle_enc(float(s)), angle_dec, "deg"),
    "sun_speed": (0x0C, lambda s: speed_enc(float(s)), speed_dec, "deg/frame"),
    "sdram_rd_lat": (0x0D, lambda s: int(s, 0), int, "cycles"),
    "frames": (0x0E, None, int, ""),
    "status": (0x0F, None, lambda v: f"sdram_ready={v & 1} shown_640x480={(v >> 1) & 1} merged={(v >> 2) & 1}", ""),
    "anim": (0x10, lambda s: int(s, 0) & 0xFFFF, lambda v: f"0x{v:04x}", ""),
    "anim_speed": (0x11, lambda s: int(s, 0) & 0xFFFF, lambda v: f"0x{v:04x}", "per frame"),
    "scene": (0x12, lambda s: int(s, 0), scene_dec, ""),
    "cycles": (0x13, None, cycles_dec, ""),
    "core_clock": (0x14, None, lambda v: f"{v / 100:.2f}", "MHz"),
}
# Fields of the scene register (0x12): name -> (shift, mask, maximum)
SCENE = {"bounces": (0, 0x3, 3), "floor_kr": (2, 0x3, 3), "spheres": (4, 0x7, 6)}
FLAGS = {"orbit": 0x1, "sun_motion": 0x2, "freeze": 0x4, "test_pattern": 0x8, "sphere_motion": 0x10,
         "quality": 0x20}


def need_pyserial():
    if serial is None:
        sys.exit("pyserial is required: pip install pyserial  (Windows: py -m pip install pyserial)")


class Board:
    def __init__(self, port):
        need_pyserial()
        try:
            self.s = serial.Serial(port, 115200, bytesize=8, parity="N", stopbits=1, timeout=0.5,
                                   xonxoff=False, rtscts=False, dsrdtr=False)
        except serial.SerialException as e:
            sys.exit(f"cannot open {port}: {e}\n"
                     "Run `rtctl.py list` to see the ports, and close any other program using it "
                     "(a serial terminal, or the Gowin programmer).")
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
    read_clock(b)
    for name, (addr, _enc, dec, unit) in REGS.items():
        v = b.read(addr)
        print(f"{addr:02x} {name:13s} 0x{v:04x}  {dec(v)} {unit}".rstrip())
    ctrl = b.read(0x01)
    print("flags:", ", ".join(f"{k}={'on' if ctrl & m else 'off'}" for k, m in FLAGS.items()))


def cmd_get(b, args):
    read_clock(b)
    for name in args:
        if name in SCENE:
            sh, mask, _ = SCENE[name]
            print(f"{name} = {(b.read(0x12) >> sh) & mask}")
        elif name in FLAGS:
            print(f"{name} = {'on' if b.read(0x01) & FLAGS[name] else 'off'}")
        else:
            addr, _enc, dec, unit = check_name(name)
            print(f"{name} = {dec(b.read(addr))} {unit}".rstrip())


def check_name(name):
    if name not in REGS:
        sys.exit(f"unknown name {name!r}; registers: {', '.join(REGS)}; "
                 f"flags: {', '.join(FLAGS)}; scene: {', '.join(SCENE)}")
    return REGS[name]


def cmd_set(b, args):
    if len(args) % 2:
        sys.exit("set needs name/value pairs")
    for name, value in zip(args[::2], args[1::2]):
        if name in FLAGS:
            ctrl = b.read(0x01)
            on = value.lower() in ("1", "on", "true", "yes")
            b.write(0x01, (ctrl | FLAGS[name]) if on else (ctrl & ~FLAGS[name]))
        elif name in SCENE:
            sh, mask, top = SCENE[name]
            v = max(0, min(top, int(value, 0)))
            scene = b.read(0x12)
            b.write(0x12, (scene & ~(mask << sh) & 0xFFFF) | (v << sh))
        else:
            addr, enc, _dec, _unit = check_name(name)
            if enc is None:
                sys.exit(f"{name} is read-only")
            b.write(addr, enc(value))


def cmd_raw(b, args):
    print(b.line(" ".join(args)))


class KeyReader:
    """Single key presses without Enter: msvcrt on Windows, a cbreak
    terminal elsewhere. read() returns one character, or "" for a key that
    has no character (arrows, function keys)."""

    def __enter__(self):
        if os.name == "nt":
            import msvcrt
            self._msvcrt = msvcrt
        else:
            import termios
            import tty
            self._termios = termios
            self._fd = sys.stdin.fileno()
            self._old = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        return self

    def __exit__(self, *exc):
        if os.name != "nt":
            self._termios.tcsetattr(self._fd, self._termios.TCSADRAIN, self._old)

    def read(self):
        if os.name == "nt":
            ch = self._msvcrt.getwch()
            if ch in ("\x00", "\xe0"):   # arrow or function key: a second code follows
                self._msvcrt.getwch()
                return ""
            return ch
        return sys.stdin.read(1)


def key_to_send(ch):
    """The byte to send for a key press, None to quit, b"" to ignore it.
    Keys are sent in lower case: an upper-case W or R would start a line
    command on the board (Caps Lock, Shift) and swallow the keys after it."""
    if ch in ("q", "Q", "\x1b", "\x03", "\x04"):   # q, Esc, Ctrl+C, Ctrl+D
        return None
    if len(ch) == 1 and ch.isascii() and ch.isalpha():
        return ch.lower().encode()
    return b""


def cmd_keys(b, _args, reader=None):
    print(__doc_keys__)
    with (reader or KeyReader()) as keys:
        while True:
            out = key_to_send(keys.read())
            if out is None:
                break
            if out:
                b.s.write(out)


def cmd_list():
    need_pyserial()
    def natural(p):   # COM10 after COM9
        digits = "".join(c for c in p.device if c.isdigit())
        return (p.device.rstrip("0123456789"), int(digits) if digits else -1)
    ports = sorted(serial.tools.list_ports.comports(), key=natural)
    if not ports:
        print("no serial ports found: is the board plugged in (and, on Windows, its driver installed)?")
    for p in ports:
        print(f"{p.device:16s} {p.description}  [{p.hwid}]")
    print("The Tang Nano 20K shows two ports for its USB connector; the UART is usually the "
          "second (higher-numbered) one.")


__doc_keys__ = """keys: a/d yaw  w/s pitch  z/x distance  j/l sun azimuth  i/k sun elevation
      o orbit on/off  p sun motion on/off  m sphere motion on/off  v 640x480 quality mode
      b reflection bounces  r floor reflectivity  f freeze  t test pattern  c defaults
      q or Esc quits"""

def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def debug_words(b, idxs):
    out = {}
    for i in idxs:
        b.write(0x15, i)
        lo = b.read(0x16)
        out[i] = (b.read(0x17) << 16) | lo
    return out


def expected_debug(regs):
    """Model values of the debug words for the given register values."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "model"))
    import hw
    p = dict(yaw=regs[0x02], pitch=regs[0x03], dist=regs[0x04], tx=s16(regs[0x05]), ty=s16(regs[0x06]),
             tz=s16(regs[0x07]), fov=regs[0x08], light_az=regs[0x0A], light_el=regs[0x0B])
    sc = regs[0x12]
    scene = dict(anim=regs[0x10], nsph=min(6, (sc >> 4) & 7), depth=sc & 3, floor_kr=(sc >> 2) & 3)
    quality = bool(regs[0x01] & 0x20)
    cam = hw.camera(p)
    want = {}
    names = {}
    for base, key in ((0, "eye"), (3, "d0"), (6, "du"), (9, "dv"), (12, "light"), (15, "fwd"), (18, "right"),
                      (21, "up")):
        for j in range(3):
            want[base + j] = cam[key][j] & 0xFFFFFFFF
            names[base + j] = f"{key}[{'xyz'[j]}]"
    want[24], names[24] = cam["s"] & 0xFFFFFFFF, "s"
    sb, hb = hw.boxes(p, scene, quality)
    for base, bx, label in ((32, sb, "sphere box"), (48, hb, "shadow box")):
        for k, box in enumerate(bx):
            if box is None:
                want[base + 2 * k], want[base + 2 * k + 1] = 0, None   # off: x word 0, y word unused
            else:
                x0, x1, y0, y1 = box
                want[base + 2 * k] = 0x80000000 | (x0 << 16) | x1
                want[base + 2 * k + 1] = (y0 << 16) | y1
            names[base + 2 * k] = f"{label} {k} on/x0/x1"
            names[base + 2 * k + 1] = f"{label} {k} y0/y1"
    return want, names


def cmd_debug(b, _args):
    ctrl = b.read(0x01)
    if ctrl & 0x13:
        b.write(0x01, ctrl & ~0x13)   # orbit, sun and sphere motion off: the camera stays put
        print("motion stopped (orbit, sun, spheres) so the frame matches the registers")
        time.sleep(0.5)
    regs = {a: b.read(a) for a in (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x0A, 0x0B, 0x10, 0x12)}
    want, names = expected_debug(regs)
    got = debug_words(b, sorted(want))
    bad = 0
    for i in sorted(want):
        w = want[i]
        if w is None:
            continue
        g = got[i]
        ok = g == w
        bad += not ok
        print(f"{i:2d} {names[i]:24s} board 0x{g:08x}  model 0x{w:08x}  {'ok' if ok else 'MISMATCH'}")
    print("all match" if bad == 0 else f"{bad} mismatches")


def cmd_trig(b, args):
    """Sweep yaw and pitch together and compare the camera's sin/cos results:
    fwd.y = -sin(pitch), up.y = cos(pitch), right.x = cos(yaw), right.z = -sin(yaw)."""
    step = int(args[0], 0) if args else 0x0800
    ctrl = b.read(0x01)
    b.write(0x01, ctrl & ~0x17)            # no motion, not frozen: a frame renders and sets the camera
    saved = {a: b.read(a) for a in (0x02, 0x03)}
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "model"))
    import hw
    words = {"sin p": 16, "cos p": 22, "cos y": 18, "sin y": 20}
    print("angle   " + "  ".join(f"{n:>17s}" for n in words) + "   (board/model, x = wrong)")
    try:
        for a in list(range(0, 0x10000, step)) + [0x0700, 0x0900, 0x3F00, 0x4100, 0xAF80]:
            b.write(0x02, a)
            b.write(0x03, a)
            time.sleep(0.08)                 # a few frames: the camera runs at each frame start
            regs = {r: b.read(r) for r in (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x0A, 0x0B, 0x10, 0x12)}
            want, _ = expected_debug(regs)
            got = debug_words(b, words.values())
            cells = []
            for n, i in words.items():
                g, w = s32(got[i]), s32(want[i])
                cells.append(f"{g:7d}/{w:7d}{' ' if g == w else 'x'}")
            print(f"0x{a:04x}  " + "  ".join(cells))
    finally:
        for r, v in saved.items():
            b.write(r, v)


def s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


COMMANDS = {"dump": cmd_dump, "get": cmd_get, "set": cmd_set, "raw": cmd_raw, "keys": cmd_keys, "debug": cmd_debug,
            "trig": cmd_trig}


def main(argv):
    if len(argv) == 2 and argv[1] == "list":
        cmd_list()
        return 0
    if len(argv) < 3 or argv[2] not in COMMANDS:
        print(__doc__)
        print("registers:", ", ".join(REGS), "\nflags:", ", ".join(FLAGS), "\nscene:", ", ".join(SCENE))
        return 1
    COMMANDS[argv[2]](Board(argv[1]), argv[3:])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
