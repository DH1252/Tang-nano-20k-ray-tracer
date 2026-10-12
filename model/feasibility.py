#!/usr/bin/env python3
"""Feasibility model for the Tang Nano 20K ray tracer (see docs/PLAN.md).

Renders the planned demo scene twice:
  * fixed-point, emulating the planned hardware formats (18-bit DSP operands,
    shared rsqrt-table SFU with one Newton step, integer shading, RGB333 dither)
  * float64 reference with exact math
and reports the error, the largest operand seen at every multiplier site
(does it fit a MULT18X18?) and a cycle estimate for the scanline-batched
pass architecture.

This is the starting point for M0. It is not yet bit-exact with any RTL.

usage: python3 model/feasibility.py [max_depth=2] [out_dir=.]
"""
import sys
import numpy as np
from PIL import Image

W, H = 320, 240
FW, FD = 12, 16                 # world s5.12, direction s1.16
S18, U18 = (1 << 17) - 1, (1 << 18) - 1
TMAX = S18                      # 31.99 world units in .12
EPS_T = 16                      # 1/256 world unit
MAX_DEPTH = int(sys.argv[1]) if len(sys.argv) > 1 else 2   # 1 = no reflections
I64 = np.int64

# ---------------------------------------------------------------- scene
# (center, radius, albedo, kr/256, ks)
SPHERES = [
    ((0.0, 1.0, 0.0), 1.0, (200, 200, 210), 192, 1),   # mirror
    ((-2.0, 0.6, 1.0), 0.6, (220, 40, 40), 0, 1),       # red
    ((1.9, 0.5, 0.9), 0.5, (40, 80, 230), 64, 1),       # blue
    ((0.9, 0.35, 1.9), 0.35, (240, 180, 40), 128, 1),   # gold
    ((-1.2, 0.8, -2.2), 0.8, (50, 200, 80), 0, 1),      # green
    ((2.2, 1.2, -1.8), 1.2, (150, 60, 200), 64, 1),     # purple
]
NS = len(SPHERES)
PLANE = NS                      # object id of the ground plane y = 0
EYE = np.array([1.5, 2.0, 7.0])
TARGET = np.array([0.0, 0.8, 0.0])
LIGHT = np.array([-0.5, 0.8, 0.6]); LIGHT /= np.linalg.norm(LIGHT)
HFOV = np.radians(60)
AMB = 40
CHK_MID, CHK_DELTA = 140, 100

fwd = TARGET - EYE; fwd /= np.linalg.norm(fwd)
right = np.cross(fwd, [0, 1, 0]); right /= np.linalg.norm(right)
up = np.cross(right, fwd)
pix = 2 * np.tan(HFOV / 2) / W
dU, dV = right * pix, -up * pix

# shared tables (would live in BSRAM)
POW_TBL = np.round(255 * (np.arange(256) / 256.0) ** 32).astype(I64)
SUN_TBL = np.round(255 * (np.arange(256) / 256.0) ** 256).astype(I64)
_sy = (np.arange(256) + 0.5) / 128.0 - 1.0


def sky_f(dy):
    k = np.clip(dy, 0, 1)[..., None] ** 0.6
    return (1 - k) * np.array([200, 215, 235]) + k * np.array([40, 90, 190])


SKY_TBL = np.round(sky_f(_sy)).astype(I64)

stats = {}


def chk(name, a, lim=S18):
    a = np.asarray(a)
    m = int(np.max(np.abs(a))) if a.size else 0
    s = stats.setdefault(name, [0, 0, lim])
    s[0] = max(s[0], m)
    s[1] += int(np.count_nonzero(np.abs(a) > lim))
    return a


def dsp(tag, a, b, la=S18, lb=S18):
    """One MULT18X18: both operands must fit (signed 18 unless lim says U18)."""
    chk(tag + ".a", a, la); chk(tag + ".b", b, lb)
    return a.astype(I64) * b.astype(I64)


def shl(v, s):
    s = np.clip(s, -62, 40)
    return np.where(s >= 0, v << np.maximum(s, 0), v >> np.maximum(-s, 0))


# ---------------------------------------------------------------- SFU
_mmid = (np.arange(768) + 256 + 0.5) / 256.0
RSQ_TBL = np.round(_mmid ** -0.5 * 65536).astype(I64)      # 768 x 17 bit


def sfu(x, fin):
    """rsqrt core. X = x*2^-fin = (m*2^-16) * 2^e, m in [1,4), e even.
    Returns y1 ~ rsqrt(m) in .16, m in .16, e."""
    x = np.maximum(x.astype(I64), 1)
    _, ex = np.frexp(x.astype(np.float64))
    eraw = (ex - 1) - fin
    e = eraw - np.mod(eraw, 2)
    m = shl(x, 16 - fin - e)
    y0 = RSQ_TBL[(m >> 8) - 256]
    y0sq = dsp("sfu.y0sq", y0, y0, U18, U18) >> 16
    t = dsp("sfu.my0sq", m, y0sq, U18, U18) >> 16
    y1 = dsp("sfu.newton", y0, 3 * 65536 - t, U18, U18) >> 17
    return y1, m, e


def f_sqrt(x, fin, fout):
    y1, m, e = sfu(x, fin)
    s = dsp("sfu.sqrt", m, y1, U18, U18) >> 16
    return shl(s, e // 2 + fout - 16)


def f_rsqrt(x, fin, fout):
    y1, m, e = sfu(x, fin)
    return shl(y1, fout - 16 - e // 2)


def f_recip_mul(a, x, fin):
    """a * (1/X), result keeps a's scale, saturated to TMAX."""
    y1, m, e = sfu(x, fin)
    r = dsp("sfu.recip", y1, y1, U18, U18) >> 16          # (0.25,1] in .16
    p = dsp("plane.t", a, r) >> 16
    return np.minimum(shl(p, np.minimum(-e, 30)), TMAX)


# ---------------------------------------------------------------- backends
class Fixed:
    fixed, tmax = True, TMAX

    def __init__(self):
        q = lambda v, f: np.round(np.asarray(v) * (1 << f)).astype(I64)
        self.q = q
        self.C = [q(s[0], FW) for s in SPHERES]
        self.r2 = [q(s[1] ** 2, 2 * FW) for s in SPHERES]
        self.invr = [q(1 / s[1], 14) for s in SPHERES]
        self.L = q(LIGHT, FD)

    def primary(self):
        q = self.q
        ys, xs = np.mgrid[0:H, 0:W]
        px = (xs - W // 2).reshape(-1, 1)          # integer pixel offsets
        py = (ys - H // 2).reshape(-1, 1)
        acc = q(fwd + 0.5 * dU + 0.5 * dV, 24) + px * q(dU, 24) + py * q(dV, 24)
        d = acc >> 8                                # .16, incremental adders
        chk("gen.d", d)
        dd = sum(dsp("gen.dd", d[:, k], d[:, k]) for k in range(3))
        rs = f_rsqrt(dd, 32, 16)
        D = np.stack([dsp("gen.scale", d[:, k], rs) >> 16 for k in range(3)], 1)
        O = np.tile(q(EYE, FW), (W * H, 1))
        return O, D

    def intersect(self, O, D, spheres_only=False):
        n = len(O)
        bt = np.full(n, TMAX, I64); bid = np.full(n, -1)
        for i in range(NS):
            Lw = self.C[i] - O                    # saturate: |L| > 32 => miss
            far = (np.abs(Lw) > S18).any(1)
            L = chk("iu.L", np.clip(Lw, -S18, S18))
            b = sum(dsp("iu.b", L[:, k], D[:, k]) for k in range(3)) >> 16
            LL = sum(dsp("iu.LL", L[:, k], L[:, k]) for k in range(3))
            disc = dsp("iu.bb", b, b) - (LL - self.r2[i])
            ok = (disc > 0) & ~far
            t = b - f_sqrt(np.where(ok, disc, 1), 2 * FW, FW)
            ok &= (t > EPS_T) & (t < bt)
            bt = np.where(ok, t, bt); bid = np.where(ok, i, bid)
        if not spheres_only:
            ok = (D[:, 1] < 0) & (O[:, 1] > 0)
            t = f_recip_mul(O[:, 1], np.where(ok, -D[:, 1], 1), FD)
            ok &= (t > EPS_T) & (t < bt)
            bt = np.where(ok, t, bt); bid = np.where(ok, PLANE, bid)
        return bt, bid

    def hitpoint(self, O, D, t):
        return O + np.stack([dsp("su.tD", t, D[:, k]) >> 16 for k in range(3)], 1)

    def normal(self, P, ids):
        N = np.zeros_like(P); N[:, 1] = 1 << FD
        for i in range(NS):
            m = ids == i
            if m.any():
                PC = chk("su.PC", P[m] - self.C[i])
                N[m] = np.stack([dsp("su.N", PC[:, k], self.invr[i]) >> 10
                                 for k in range(3)], 1)
        return N

    def dot(self, tag, A, B):
        return sum(dsp(tag, A[:, k], B[:, k]) for k in range(3)) >> 16

    def reflect(self, D, N):
        dn = self.dot("su.DN", D, N)
        return D - np.stack([dsp("su.R", dn, N[:, k]) >> 15 for k in range(3)], 1)

    def offset(self, P, N):
        return P + (N >> (FD - FW + 7))          # P + N/128

    def to8(self, x16):                          # [0,1] .16 -> table index
        return np.clip(x16 >> 8, 0, 255)

    pow_ = lambda self, x: POW_TBL[self.to8(x)]
    sun = lambda self, x: SUN_TBL[self.to8(x)]
    sky = lambda self, dy: SKY_TBL[np.clip((dy + 65536) >> 9, 0, 255)]

    def checker(self, P, t):
        c = ((P[:, 0] >> FW) ^ (P[:, 2] >> FW)) & 1
        fade = np.maximum(0, 256 - (t >> 8))
        dl = (CHK_DELTA * fade) >> 8
        return np.where(c == 1, CHK_MID + dl, CHK_MID - dl)


class Float:
    fixed, tmax = False, TMAX / 4096.0

    def __init__(self):
        self.C = [np.array(s[0]) for s in SPHERES]
        self.L = LIGHT

    def primary(self):
        ys, xs = np.mgrid[0:H, 0:W]
        px = (xs - W // 2 + 0.5).reshape(-1, 1)
        py = (ys - H // 2 + 0.5).reshape(-1, 1)
        d = fwd + px * dU + py * dV
        D = d / np.linalg.norm(d, axis=1, keepdims=True)
        return np.tile(EYE, (W * H, 1)), D

    def intersect(self, O, D, spheres_only=False):
        n = len(O)
        bt = np.full(n, TMAX / 4096.0); bid = np.full(n, -1)
        for i, s in enumerate(SPHERES):
            L = self.C[i] - O
            b = (L * D).sum(1)
            disc = b * b - ((L * L).sum(1) - s[1] ** 2)
            ok = disc > 0
            t = b - np.sqrt(np.where(ok, disc, 0))
            ok &= (t > EPS_T / 4096) & (t < bt)
            bt = np.where(ok, t, bt); bid = np.where(ok, i, bid)
        if not spheres_only:
            ok = (D[:, 1] < 0) & (O[:, 1] > 0)
            t = np.where(ok, O[:, 1] / np.where(ok, -D[:, 1], 1), 1e9)
            ok &= (t > EPS_T / 4096) & (t < bt)
            bt = np.where(ok, t, bt); bid = np.where(ok, PLANE, bid)
        return bt, bid

    def hitpoint(self, O, D, t):
        return O + t[:, None] * D

    def normal(self, P, ids):
        N = np.zeros_like(P); N[:, 1] = 1
        for i, s in enumerate(SPHERES):
            m = ids == i
            N[m] = (P[m] - self.C[i]) / s[1]
        return N

    def dot(self, tag, A, B):
        return (A * B).sum(1)

    def reflect(self, D, N):
        return D - 2 * self.dot("", D, N)[:, None] * N

    def offset(self, P, N):
        return P + N / 128

    pow_ = lambda self, x: 255 * np.clip(x, 0, 1) ** 32
    sun = lambda self, x: 255 * np.clip(x, 0, 1) ** 256
    sky = lambda self, dy: sky_f(dy)

    def checker(self, P, t):
        c = (np.floor(P[:, 0]).astype(I64) ^ np.floor(P[:, 2]).astype(I64)) & 1
        fade = np.maximum(0, 1 - t / 16)
        return np.where(c == 1, CHK_MID + CHK_DELTA * fade, CHK_MID - CHK_DELTA * fade)


# ---------------------------------------------------------------- tracer
ALB = np.array([s[2] for s in SPHERES], I64)
KR = np.array([s[3] for s in SPHERES] + [0])
KS = np.array([s[4] for s in SPHERES] + [0])


def shade(B, O, D, depth, counts):
    """One SHADE pass + the passes it spawns. Returns colour (n,3) in 0..255."""
    n = len(O)
    t, ids = B.intersect(O, D)
    counts.append(("isect", n, NS + 1))
    hit = ids >= 0
    col = np.zeros((n, 3))
    # misses: sky + sun
    m = ~hit
    if m.any():
        sky = B.sky(D[m, 1]).astype(float)
        col[m] = np.minimum(255, sky + B.sun(B.dot("su.DL", D[m], np.tile(B.L, (m.sum(), 1))))[:, None])
    if not hit.any():
        return col
    Oh, Dh, th, ih = O[hit], D[hit], t[hit], ids[hit]
    P = B.hitpoint(Oh, Dh, th)
    N = B.normal(P, ih)
    Lt = np.tile(B.L, (len(P), 1))
    ndl = B.dot("su.NL", N, Lt)
    lit = ndl > 0
    # shadow pass: only lit-facing hits spawn shadow rays (spheres only)
    vis = np.zeros(len(P), bool)
    if lit.any():
        st, _ = B.intersect(B.offset(P[lit], N[lit]), Lt[lit], spheres_only=True)
        counts.append(("shadow", int(lit.sum()), NS))
        vis[lit] = st >= B.tmax
    R = B.reflect(Dh, N)
    if B.fixed:
        d8 = np.clip(ndl >> 8, 0, 256)
        light = AMB + (((d8 * (256 - AMB)) >> 8) * vis)
    else:
        light = AMB + np.clip(ndl, 0, 1) * 256 * (256 - AMB) / 256 * vis
    spec = B.pow_(B.dot("su.RL", R, Lt)) * vis * KS[ih]
    alb = np.zeros((len(P), 3))
    sp = ih < NS
    alb[sp] = ALB[ih[sp]]
    alb[~sp] = B.checker(P[~sp], th[~sp])[:, None]
    if B.fixed:
        local = np.minimum(255, ((alb.astype(I64) * light[:, None]) >> 8) + spec[:, None])
    else:
        local = np.minimum(255, alb * light[:, None] / 256 + spec[:, None])
    kr = KR[ih]
    rf = (kr > 0) & (depth < MAX_DEPTH)
    if rf.any():
        rc = shade(B, B.offset(P[rf], N[rf]), R[rf], depth + 1, counts)
        k = kr[rf][:, None]
        if B.fixed:
            local[rf] = (local[rf].astype(I64) * (256 - k) + rc.astype(I64) * k) >> 8
        else:
            local[rf] = (local[rf] * (256 - k) + rc * k) / 256
    col[hit] = local
    return col


def bayer4():
    b = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]])
    return (b * 16 + 8)


def rgb333(img8):
    th = np.tile(bayer4(), (H // 4, W // 4))[..., None]
    v = np.clip(((img8.astype(I64) * 7) + th) >> 8, 0, 7)
    return (v * 255 // 7).astype(np.uint8)


def render(B):
    O, D = B.primary()
    counts = []
    col = shade(B, O, D, 1, counts)
    return col.reshape(H, W, 3), counts


if __name__ == "__main__":
    # usage: feasibility.py [max_depth] [out_dir]
    out = sys.argv[2] if len(sys.argv) > 2 else "."
    fx, cnt = render(Fixed())
    fl, _ = render(Float())
    fx8 = np.clip(fx, 0, 255).astype(np.uint8)
    fl8 = np.clip(np.round(fl), 0, 255).astype(np.uint8)
    diff = np.abs(fx8.astype(int) - fl8.astype(int))
    mse = np.mean(diff.astype(float) ** 2)
    print(f"MAX_DEPTH={MAX_DEPTH}")
    print(f"PSNR fixed vs float: {10*np.log10(255**2/mse):.1f} dB, "
          f"pixels with any channel off by >16: {np.mean(diff.max(2) > 16)*100:.2f}%, "
          f">4: {np.mean(diff.max(2) > 4)*100:.2f}%")
    print("operand ranges (max |x| / limit, overflows):")
    for k, (mx, ov, lim) in sorted(stats.items()):
        print(f"  {k:14s} {mx:8d} / {lim:7d}  {'OK ' if ov == 0 else 'OVF'} {ov}")
    # cycle model: scanline batches, compaction, 1 (ray,object) test / clk
    LAT, NPIX = 32, W * H
    tests = sum(nr * no for _, nr, no in cnt)
    shade_cyc = sum(nr for k, nr, _ in cnt if k == "isect")  # one SHADE slot per ray
    passes_per_line = len(cnt) + 1 + len([c for c in cnt if c[0] == "isect"])
    cyc = NPIX + tests + shade_cyc + passes_per_line * LAT * H
    print(f"ray-object tests/frame {tests/1e6:.2f} M, total cycles/frame {cyc/1e6:.2f} M "
          f"({cyc/NPIX:.1f} cyc/pixel)")
    for f in (54, 75):
        print(f"  @{f} MHz: {f*1e6/cyc:.1f} fps")
    big = lambda a: np.kron(a, np.ones((2, 2, 1), np.uint8))
    Image.fromarray(big(rgb333(fx8))).save(f"{out}/preview_rgb333.png")
    Image.fromarray(big(fl8)).save(f"{out}/reference_float.png")
    Image.fromarray(np.clip(diff * 8, 0, 255).astype(np.uint8)).save(f"{out}/diff_x8.png")
