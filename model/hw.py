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
    y1, e, _ = rsqrt_m(x, fin)
    return y1, e


def rsqrt_m(x, fin):
    """rsqrt plus the normalised mantissa m (u2.16, in [1, 4)) it was taken
    of: x * 2^-fin = m * 2^-16 * 2^e."""
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
    return y1 & ((1 << 17) - 1), e, m


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




# ------------------------------------------------------------- common helpers
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
    """Table index for a s1.16 dot product in [0.75, 1)."""
    return clamp((v - 49152) >> 4, 0, 1023)


def shift_signed(v, s):
    """Unsigned v shifted left by s (s >= 0) or right by -s."""
    return v << s if s >= 0 else v >> -s


# ------------------------------------------------------------ animator.spade
SPHERES = gen_tables.SPHERES
NSPH = len(SPHERES)
FLOOR, NONE = 6, 7
TMAX, EPS = 131071, 16


sphere_static = gen_tables.sphere_static


def sin16(ang):
    return SIN[(ang & 0xFFFF) >> 4]


def animate(anim):
    """Sphere centres (s5.12) for animation time `anim`, exactly as
    animator.spade computes them."""
    out = []
    for i in range(NSPH):
        s = sphere_static(i)
        td = (anim * s["kd"] + s["od"]) & 0xFFFF
        tb = (anim * s["kb"] + s["ob"]) & 0xFFFF
        x = s["cx"] + ((s["R"] * sin16(td + 0x4000)) >> 16)
        y = s["r"] + ((s["h"] * abs(sin16(tb))) >> 16)
        z = s["cz"] + ((s["R"] * sin16(td)) >> 16)
        out.append([sat18(x), sat18(y), sat18(z)])
    return out


# ------------------------------------------------------------ ray_unit.spade
def ray_unit_ref(mode, o, d, c=(0, 0, 0), r2=0, floor=False):
    """Bit-exact ray_unit output fields (t, hit, dn) for one input.
    mode 0 = GEN (d is the quantised direction), 1 = closest, 2 = any hit."""
    gen = mode == 0
    lw = [c[k] - o[k] for k in range(3)]
    ovf = any(abs(v) > 131071 for v in lw)
    l = [sat18(v) for v in lw]
    s = list(d) if gen else l
    b = sat18((l[0] * d[0] + l[1] * d[1] + l[2] * d[2]) >> 16)
    ll = s[0] * s[0] + s[1] * s[1] + s[2] * s[2]
    disc = b * b - (ll - r2)
    if gen:
        x, fin = ll, 32
    elif floor:
        x, fin = (-d[1] if d[1] < 0 else 1), 16
    else:
        x, fin = (disc if disc > 0 else 1), 24
    y1, e, m = rsqrt_m(x, fin)
    rsn = shift_signed(y1, (-e) >> 1) & ((1 << 20) - 1)
    rsn = min(rsn, 131071)
    dn = [sat18((v * rsn) >> 16) for v in d]
    prod = (y1 if floor else m) * y1
    sq = (prod >> 16) & ((1 << 19) - 1)
    sqrtd = shift_signed(sq, (e >> 1) - 4) & ((1 << 24) - 1)
    t_sph = b - sqrtd
    r16 = (prod >> 16) & ((1 << 17) - 1)
    w0 = (o[1] * r16) >> 16
    ws = wrap(-e, 8)
    w_big = wrap(w0 << ws, 40) if 0 <= ws < 20 else 0x1FFFF
    t_floor = clamp(w_big, 0, 0x1FFFF)
    t = t_floor if floor else t_sph
    geom = (d[1] < 0 and o[1] > 0) if floor else (not ovf and disc > 0)
    hit = geom and 16 < t < 131071 and not gen
    return dict(t=wrap(t, 18), hit=hit, dn=dn)


def gen_ray(d):
    """Primary ray direction: d (s3.24 accumulators) -> unit D (s1.16)."""
    return ray_unit_ref(0, (0, 0, 0), [sat18(v >> 8) for v in d])["dn"]


def closest_hit(O, D, centres, nsph):
    best_t, best_id = TMAX, NONE
    objs = list(range(nsph)) + [FLOOR]
    for i in objs:
        if i == FLOOR:
            r = ray_unit_ref(1, O, D, (0, 0, 0), 0, True)
        else:
            r = ray_unit_ref(1, O, D, centres[i], sphere_static(i)["r2"], False)
        if r["hit"] and r["t"] < best_t:
            best_t, best_id = r["t"], i
    return best_t, best_id


def any_hit(O, L, centres, nsph):
    return any(ray_unit_ref(2, O, L, centres[i], sphere_static(i)["r2"], False)["hit"]
               for i in range(nsph))


# ---------------------------------------------------------- shade_unit.spade
def _sum3(a, b):
    return sat18((a[0] * b[0] + a[1] * b[1] + a[2] * b[2]) >> 16)


def shade_unit_ref(q, light):
    """Bit-exact shade_unit output for input fields q (see SuIn)."""
    hit = q["id"] != NONE
    floor = q["id"] == FLOOR
    teff = 0 if q["shade"] else q["t"]
    p = [sat18(q["o"][k] + ((teff * q["d"][k]) >> 16)) for k in range(3)]
    pc = [sat18(p[k] - q["c"][k]) for k in range(3)]
    if floor:
        n = [0, 65536, 0]
    elif not hit:
        n = [0, 0, 0]
    else:
        n = [sat18((pc[k] * q["invr"]) >> 10) for k in range(3)]
    nl = _sum3(n, light)
    dn = _sum3(q["d"], n)
    r = [sat18(q["d"][k] - ((dn * n[k]) >> 15)) for k in range(3)]
    rl = _sum3(r, light)
    shadowed = hit and (nl <= 0 or q["shadow"])
    tidx = dot_index(rl)
    ly8 = clamp(light[1] >> 8, 0, 256)
    k8 = clamp8(q["d"][1] >> 8)
    d8 = 0 if shadowed else clamp(nl >> 8, 0, 256)
    sun_v = 0 if hit else (255 if rl >= 65500 else SUN[tidx])
    skyscale = 150 + ((ly8 * 106) >> 8)
    lightf = 96 + ((d8 * 160) >> 8)
    spec = POW[tidx] if (q["spec"] and not shadowed) else 0
    if floor:
        checker = ((p[0] >> 12) ^ (p[2] >> 12)) & 1
        alb = (230, 230, 230) if checker else (40, 40, 40)
    else:
        alb = q["alb"]
    fade = 256 - (((q["t"] & 0x3FFFF) >> 9) & 0xFF)
    col = []
    for k, (base, slope, sc) in enumerate(((200, 160, 255), (215, 125, 230), (235, 45, 180))):
        g = base + ((-(slope * k8)) >> 8)
        sky = clamp8(((g * skyscale) >> 8) + ((sun_v * sc) >> 8))
        lit = min(255, ((alb[k] * lightf) >> 8) + spec)
        col.append(sky + (((lit - sky) * fade) >> 8) if hit else sky)
    kr, tp = q["kr"], q["tp"]
    refl = hit and kr != 0 and q["may_refl"]
    wk = {1: tp * 3, 2: tp * 2, 3: tp}.get(kr, tp * 4)
    w = (wk >> 2) if refl else tp
    tp_next = ({1: tp, 2: tp * 2, 3: tp * 3}.get(kr, 0) >> 2) & 0x1FF
    acc = [min(255, (0 if q["first"] else q["acc"][k]) + ((col[k] * w) >> 8)) for k in range(3)]
    return dict(shade=q["shade"], idx=q["idx"], pix=q["pix"], p=p, r=r, hit=hit,
                spawn_shadow=(not q["shade"]) and hit and nl > 0, refl=q["shade"] and refl,
                tp_next=tp_next, acc=acc)


def su_input(shade, O, D, t, hid, centres, scene, shadow=False, acc=(0, 0, 0), first=True,
             may_refl=False, tp=256, idx=0, pix=0):
    """The SuIn fields the tracer builds for a ray (object constants by id)."""
    s = sphere_static(hid if hid < NSPH else 0)
    is_floor = hid == FLOOR
    return dict(shade=shade, idx=idx, pix=pix, tp=tp, o=list(O), d=list(D), t=t, id=hid,
                shadow=shadow, acc=list(acc), first=first, may_refl=may_refl,
                c=list(centres[hid if hid < NSPH else 0]), invr=s["invr"], alb=s["alb"],
                kr=scene["floor_kr"] if is_floor else s["kr"], spec=is_floor or bool(s["spec"]))


def trace_pixel(d, eye, light, centres, scene):
    """Accumulated RGB of one pixel through the same passes as the tracer:
    GEN, then per bounce ISECT, SPAWN, SHADOW, SHADE."""
    nsph, maxd = scene["nsph"], scene["depth"]
    O, D = list(eye), gen_ray(d)
    tp, acc = 256, [0, 0, 0]
    for depth in range(maxd + 1):
        t, hid = closest_hit(O, D, centres, nsph)
        sp = shade_unit_ref(su_input(False, O, D, t, hid, centres, scene), light)
        P = sp["p"] if sp["hit"] else O
        shadow = sp["spawn_shadow"] and nsph > 0 and any_hit(P, light, centres, nsph)
        sh = shade_unit_ref(su_input(True, P, D, t, hid, centres, scene, shadow, acc, depth == 0,
                                     depth < maxd, tp), light)
        acc = sh["acc"]
        if not sh["refl"]:
            break
        O, D, tp = sh["p"], sh["r"], sh["tp_next"]
    return acc


DEFAULT_SCENE = dict(anim=0, nsph=6, depth=1, floor_kr=0)


def dither565(acc, x, y):
    dth = BAYER4[y & 3][x & 3]
    r, g, b = acc
    return pack565(min(255, r + (dth >> 1)), min(255, g + (dth >> 2)), min(255, b + (dth >> 1)))


def frame_setup(p, scene, quality=False):
    c = camera(p)
    d0, du, dv = c["d0"], c["du"], c["dv"]
    if quality:
        d0 = [d0[i] - (du[i] >> 2) - (dv[i] >> 2) for i in range(3)]
        du = [v >> 1 for v in du]
        dv = [v >> 1 for v in dv]
    return c, d0, du, dv, animate(scene["anim"])


def render_line(p, scene, y, quality=False, tp=False, setup=None):
    c, d0, du, dv, centres = setup or frame_setup(p, scene, quality)
    w = 640 if quality else 320
    row = []
    for x in range(w):
        if tp:
            row.append(test_pattern(x >> 1, y >> 1) if quality else test_pattern(x, y))
            continue
        d = [wrap(d0[i] + y * dv[i] + x * du[i], 28) for i in range(3)]
        acc = trace_pixel(d, c["eye"], c["light"], centres, scene)
        row.append(dither565(acc, x, y))
    return row


def render_frame(p, scene=DEFAULT_SCENE, quality=False, tp=False):
    """List of rows of RGB565: 240 x 320, or 480 x 640 in quality mode."""
    setup = frame_setup(p, scene, quality)
    return [render_line(p, scene, y, quality, tp, setup) for y in range(480 if quality else 240)]


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
