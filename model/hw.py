"""Bit-exact Python model of the arithmetic in the Spade RTL.

Used by the cocotb tests (test/*.py) and by model/skyfloor.py to produce the
reference image the full-system simulation must match exactly. Every function
mirrors one Spade function or pipeline; widths and shifts follow the RTL.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import gen_tables  # noqa: E402

RSQRT = gen_tables.rsqrt_table()
SIN = gen_tables.sin_table()
POW = gen_tables.pow_table()
SUN = gen_tables.sun_table()


def wrap(v, bits):
    """Two's complement wrap to a signed `bits`-wide value."""
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


# ----------------------------------------------------------------- sfu.spade
def rsqrt(x, fin):
    """Returns (y1, e): rsqrt(x * 2^-fin) ~= y1 * 2^-16 * 2^(-e/2)."""
    x = x & ((1 << 40) - 1)
    if x == 0:
        x = 1
    msb = x.bit_length() - 1
    eraw = msb - fin
    e = eraw & ~1
    v = x << (47 - msb)            # MSB on bit 47
    m = (v >> 30) if (eraw & 1) else (v >> 31)
    m &= (1 << 18) - 1
    y0 = RSQRT[m >> 8]
    y0sq = (y0 * y0) >> 16
    t = (m * y0sq) >> 16
    t &= (1 << 18) - 1
    f = 196608 - t
    y1 = (y0 * f) >> 17
    return y1 & ((1 << 17) - 1), e


# -------------------------------------------------------------- camera.spade
# (op, dst, a, b, sh, neg); op 1 = trig (neg selects cos), 2 = mul, 3 = add
CAM_PROGRAM = [
    (1, 0, 32, 0, 0, False), (1, 1, 32, 0, 0, True), (1, 2, 33, 0, 0, False), (1, 3, 33, 0, 0, True),
    (1, 4, 34, 0, 0, False), (1, 5, 34, 0, 0, True), (1, 6, 35, 0, 0, False), (1, 7, 35, 0, 0, True),
    (2, 8, 0, 3, 16, False), (2, 9, 1, 3, 16, False), (2, 10, 0, 2, 16, False), (2, 11, 1, 2, 16, False),
    (2, 12, 36, 8, 16, False), (2, 13, 36, 2, 16, False), (2, 14, 36, 9, 16, False),
    (3, 12, 12, 38, 0, False), (3, 13, 13, 39, 0, False), (3, 14, 14, 40, 0, False),
    (2, 15, 37, 44, 12, False),
    (2, 16, 15, 1, 16, False), (2, 17, 15, 0, 16, True),
    (2, 18, 15, 10, 16, False), (2, 19, 15, 3, 16, True), (2, 20, 15, 11, 16, False),
    (2, 21, 16, 42, 1, False), (2, 22, 18, 43, 1, False), (3, 21, 21, 22, 0, False),
    (2, 22, 8, 41, 0, True), (3, 21, 22, 21, 0, True),
    (2, 22, 19, 43, 1, False), (2, 23, 2, 41, 0, True), (3, 23, 23, 22, 0, True),
    (2, 24, 17, 42, 1, False), (2, 25, 20, 43, 1, False), (3, 24, 24, 25, 0, False),
    (2, 25, 9, 41, 0, True), (3, 25, 25, 24, 0, True),
    (2, 26, 7, 4, 16, False), (2, 27, 7, 5, 16, False),
]

DEFAULT_PARAMS = dict(yaw=0x0000, pitch=0x0700, dist=0x6000, tx=0, ty=0x0CCD, tz=0,
                      fov=0x49E7, light_az=0x9000, light_el=0x0900)


def camera(p):
    """Returns dict(eye, d0, du, dv, light) exactly as camera_setup outputs them."""
    r = [0] * 32

    def src(sel):
        if sel < 32:
            return r[sel]
        return {36: p["dist"], 37: p["fov"], 38: p["tx"], 39: p["ty"], 40: p["tz"],
                41: 256, 42: 319, 43: 239, 44: 13107}.get(sel, 0)

    angles = {32: p["yaw"], 33: p["pitch"], 34: p["light_az"], 35: p["light_el"]}
    for op, dst, a, b, sh, neg in CAM_PROGRAM:
        if op == 1:
            ang = (angles[a] + (0x4000 if neg else 0)) & 0xFFFF
            res = SIN[ang >> 4]
        elif op == 2:
            prod = src(a) * wrap(src(b), 18)
            res = wrap(prod >> sh, 28)
            if neg:
                res = wrap(-res, 28)
        else:
            res = wrap(src(a) - src(b) if neg else src(a) + src(b), 28)
        r[dst] = res
    n18 = lambda v: wrap(v, 18)
    return dict(eye=[n18(r[12]), n18(r[13]), n18(r[14])],
                d0=[r[21], r[23], r[25]],
                du=[r[16], 0, r[17]],
                dv=[r[18], r[19], r[20]],
                light=[n18(r[26]), n18(r[6]), n18(r[27])])


# -------------------------------------------------------------- render.spade
def sat18(v):
    return clamp(v, -131071, 131071)


def clamp8(v):
    return clamp(v, 0, 255)


def pack565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def test_pattern(x, y):
    if x == 0 or x == 319 or y == 0 or y == 239:
        return 0xFFFF
    if y < 160:
        bar = (x * 205) >> 13
        return [0xFFFF, 0xFFE0, 0x07FF, 0x07E0, 0xF81F, 0xF800, 0x001F, 0x0000][bar]
    level = ((x * 205) >> 8) & 0xFF
    return pack565(level, level, level)


BAYER4 = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def dot_index(v):
    return clamp((v - 49152) >> 4, 0, 1023)


def shade_pixel(d, eye, light, tp, x, y):
    """RGB565 of one pixel, exactly as render.spade `shade` computes it."""
    dx, dy, dz = (sat18(v >> 8) for v in d)
    dd = dx * dx + dy * dy + dz * dz
    dl = sat18((dx * light[0] + dy * light[1] + dz * light[2]) >> 16)
    ny = -dy if dy < 0 else 1
    rs_y1, rs_e = rsqrt(dd, 32)
    rc_y1, rc_e = rsqrt(ny, 16)
    # F
    half_e = (-rs_e) >> 1
    rsn = (rs_y1 << half_e) if half_e >= 0 else (rs_y1 >> -half_e)
    rsn &= (1 << 20) - 1
    rsn = min(rsn, 131071)   # saturated to 18 bits in the RTL
    dy_n = sat18(wrap((dy * rsn) >> 16, 40))
    dl_n = sat18(wrap((dl * rsn) >> 16, 40))
    r16s = ((rc_y1 * rc_y1) >> 16) & ((1 << 17) - 1)
    ey = eye[1]
    w0 = wrap((ey * r16s) >> 16, 40)
    wshift = wrap(-rc_e, 8)
    # G
    if 0 <= wshift < 20:
        w_big = wrap(w0 << wshift, 40)
    else:
        w_big = 0x1FFFF
    w = 0x1FFFF if w_big > 0x1FFFF else 0 if w_big < 0 else w_big
    hit = dy < 0 and ey > 0 and w < 0x1E000
    rl = sat18(dl_n - wrap((dy_n * light[1]) >> 15, 40))
    # H
    px = wrap(eye[0] + wrap((w * dx) >> 16, 24), 24)
    pz = wrap(eye[2] + wrap((w * dz) >> 16, 24), 24)
    k8 = clamp8(dy_n >> 8)
    sun8 = SUN[dot_index(dl_n)]
    spec8 = POW[dot_index(rl)]
    disc = dl_n >= 65500
    ly8 = clamp(light[1] >> 8, 0, 256)
    # I
    checker = ((px >> 12) ^ (pz >> 12)) & 1
    wf = (w >> 8) & 0x3FF
    fade = 0 if wf >= 256 else 256 - wf
    light_f = 96 + ((ly8 * 160) >> 8)
    skyscale = 150 + ((ly8 * 106) >> 8)
    albedo = 230 if checker else 40
    spec_on = spec8 if ly8 > 0 else 0
    lit = ((albedo * light_f) >> 8) + spec_on
    floor_lit = min(lit, 255)
    sky = []
    for base, slope, sc in ((200, -160, 255), (215, -125, 230), (235, -45, 180)):
        sun_v = 255 if disc else sun8
        v = ((base + ((slope * k8) >> 8)) * skyscale >> 8) + ((sun_v * sc) >> 8)
        sky.append(clamp8(v))
    # J
    inv_fade = 256 - fade
    fog = [((floor_lit * fade + c * inv_fade) >> 8) & 0xFF for c in sky]
    if tp:
        return test_pattern(x, y)
    r, g, b = fog if hit else sky
    dth = BAYER4[y & 3][x & 3]
    return pack565(min(255, r + (dth >> 1)), min(255, g + (dth >> 2)), min(255, b + (dth >> 1)))


def render_frame(p, tp=False):
    """320x240 list of rows of RGB565, as the renderer writes them."""
    c = camera(p)
    img = []
    for y in range(240):
        row = []
        for x in range(320):
            d = [wrap(c["d0"][i] + y * c["dv"][i] + x * c["du"][i], 28) for i in range(3)]
            row.append(shade_pixel(d, c["eye"], c["light"], tp, x, y))
        img.append(row)
    return img


def rgb565_to_888(v):
    r5, g6, b5 = v >> 11, (v >> 5) & 0x3F, v & 0x1F
    return (r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2)


def write_ppm(path, img565, scale=1):
    h, w = len(img565), len(img565[0])
    with open(path, "wb") as f:
        f.write(b"P6\n%d %d\n255\n" % (w * scale, h * scale))
        for row in img565:
            line = b"".join(bytes(rgb565_to_888(v)) * scale for v in row)
            f.write(line * scale)
