#!/usr/bin/env python3
"""Generate src/tables.spade: the ROMs and scene constants used by the RTL.

The same table contents are used by model/skyfloor.py, so keep the formulas
here and import them from the model rather than duplicating them.

usage: python3 scripts/gen_tables.py   (rewrites src/tables.spade)
"""
import math
import os


def rsqrt_table():
    """1024 x u1.16. Index = top 10 bits of the u2.16 mantissa m in [1, 4);
    entries below 256 are unused. Value = 1/sqrt(midpoint of the bucket)."""
    t = []
    for i in range(1024):
        if i < 256:
            t.append(0)
        else:
            m = (i + 0.5) / 256.0
            t.append(min((1 << 17) - 1, round(65536 / math.sqrt(m))))
    return t


def sin_quarter_table():
    """2048 x u17 (entries 0..1024 used): 65536 * sin(2*pi*j/4096), a quarter
    wave. A full 4096-entry table would be a 73,728-bit constant, which Gowin's
    tools cannot handle (limit 2^16 bits)."""
    return [round(65536 * math.sin(2 * math.pi * j / 4096)) if j <= 1024 else 0
            for j in range(2048)]


def sin_table():
    """Full 4096 x s1.16 sine, rebuilt from the quarter table exactly as the
    camera unit does (mirror and negate)."""
    q = sin_quarter_table()
    out = []
    for i in range(4096):
        quad, j = i >> 10, i & 1023
        mag = q[1024 - j] if quad & 1 else q[j]
        out.append(-mag if quad >= 2 else mag)
    return out


# The specular and sun tables cover dot products in [0.75, 1): index =
# (v - 0.75) * 4096 for a s1.16 value v, so 1024 entries.
def _x(i):
    return 0.75 + (i + 0.5) / 4096.0


def pow_table():
    """1024 x u8: specular highlight 255 * x^48."""
    return [min(255, round(255 * _x(i) ** 48)) for i in range(1024)]


def sun_table():
    """1024 x u8: glow around the sun (the disc itself is drawn separately)."""
    return [min(255, round(170 * _x(i) ** 300 + 70 * _x(i) ** 24)) for i in range(1024)]


# Scene: six spheres plus the floor (object 6). Per sphere: orbit centre
# (cx, cz), orbit radius R, radius r, bounce height h, orbit and bounce speed
# multipliers kd, kb (angle = anim * k + phase; k in -2..4), phases od, ob,
# albedo, reflectivity kr in quarters (0..3), and a specular highlight flag.
#   (cx, cz, R, r, h, kd, kb, od, ob, (r, g, b), kr, spec)
SPHERES = [
    (0.0, 0.0, 0.0, 1.0, 0.0, 0, 0, 0x0000, 0x0000, (200, 200, 210), 3, 1),   # mirror
    (0.0, 0.0, 2.2, 0.6, 0.5, 1, 3, 0x0000, 0x0000, (220, 40, 40), 0, 1),     # red
    (0.0, 0.0, 2.2, 0.5, 0.9, 1, 4, 0x5555, 0x2000, (40, 80, 230), 1, 1),     # blue
    (0.0, 0.0, 2.2, 0.35, 1.2, 1, 2, 0xAAAA, 0x6000, (240, 180, 40), 2, 1),   # gold
    (0.0, 0.0, 3.8, 0.8, 0.3, -1, 1, 0x2000, 0x1000, (50, 200, 80), 0, 1),    # green
    (0.0, 0.0, 3.8, 0.9, 0.4, -1, 2, 0xA000, 0x7000, (150, 60, 200), 1, 1),   # purple
]


def q12(v):
    return round(v * 4096)


def sphere_static(i):
    """Fixed-point sphere constants: positions s5.12, r2 in .24, 1/r in .14."""
    cx, cz, R, r, h, kd, kb, od, ob, alb, kr, spec = SPHERES[i]
    rq = q12(r)
    return dict(cx=q12(cx), cz=q12(cz), R=q12(R), r=rq, h=q12(h), kd=kd, kb=kb, od=od, ob=ob,
                r2=rq * rq, invr=round((1 << 26) / rq), alb=alb, kr=kr, spec=spec)


def sphere_rom():
    arms = []
    for i in range(len(SPHERES)):
        s = sphere_static(i)
        arms.append(
            f"        {i} => SphStatic$(cx: {s['cx']}, cz: {s['cz']}, orbit: {s['R']}, r: {s['r']}, "
            f"h: {s['h']}, kd: {s['kd']}, kb: {s['kb']}, od: {s['od']}, ob: {s['ob']}, "
            f"r2: {s['r2']}, invr: {s['invr']}, alb: [{s['alb'][0]}, {s['alb'][1]}, {s['alb'][2]}], "
            f"kr: {s['kr']}, spec: {'true' if s['spec'] else 'false'}),")
    zero = ("SphStatic$(cx: 0, cz: 0, orbit: 0, r: 0, h: 0, kd: 0, kb: 0, od: 0, ob: 0, r2: 0, "
            "invr: 0, alb: [0, 0, 0], kr: 0, spec: false)")
    return f"""
// Scene constants (see SPHERES in scripts/gen_tables.py).
pub struct SphStatic {{
    cx: int<18>,
    cz: int<18>,
    orbit: int<18>,
    r: int<18>,
    h: int<18>,
    kd: int<4>,
    kb: int<4>,
    od: uint<16>,
    ob: uint<16>,
    r2: int<32>,
    invr: int<18>,
    alb: [uint<8>; 3],
    kr: uint<2>,
    spec: bool,
}}

pub fn sphere_static(i: uint<3>) -> SphStatic {{
    match i {{
{chr(10).join(arms)}
        _ => {zero},
    }}
}}
"""


def rom(name, width, signed, values, addr_bits):
    ty = f"int<{width}>" if signed else f"uint<{width}>"
    body = ",\n        ".join(
        ", ".join(str(v) for v in values[i:i + 16]) for i in range(0, len(values), 16))
    return f"""
// {len(values)} x {ty}. Combinational read: register the output at the use
// site (a pipeline `reg;` works) so it maps to block RAM.
pub entity {name}(clk: clock, idx: uint<{addr_bits}>) -> {ty} {{
    let mem = inst std::mem::clocked_memory_init(
        clk,
        [(false, 0u{addr_bits}, 0)],
        [
        {body}
        ],
    );
    inst std::mem::read_memory(mem, idx)
}}
"""


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = "// Generated by scripts/gen_tables.py. Do not edit.\n"
    src += rom("rsqrt_rom", 17, False, rsqrt_table(), 10)
    src += rom("sin_rom", 17, False, sin_quarter_table(), 11)
    src += rom("pow_rom", 8, False, pow_table(), 10)
    src += rom("sun_rom", 8, False, sun_table(), 10)
    src += sphere_rom()
    with open(os.path.join(root, "src", "tables.spade"), "w") as f:
        f.write(src)


if __name__ == "__main__":
    main()
