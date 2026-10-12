# top = ray_unit::ray_unit

import os
import random
import sys

from cocotb import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge
from spade import SpadeExt

_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(_d, "swim.toml")):
    _d = os.path.dirname(_d)
sys.path.insert(0, os.path.join(_d, "model"))
import hw  # noqa: E402

LAT = 14


def arr(v):
    return "[" + ", ".join(str(x) for x in v) + "]"


def b(v):
    return "true" if v else "false"


def vectors():
    """Rays from the camera and from hit points, against every object."""
    random.seed(7)
    centres = hw.animate(0x1234)
    c = hw.camera(hw.DEFAULT_PARAMS)
    out = []
    for _ in range(600):
        kind = random.random()
        if kind < 0.15:
            d = [random.randrange(-131071, 131072) for _ in range(3)]
            out.append(dict(mode=0, idx=random.randrange(512), o=c["eye"], d=d, c=[0, 0, 0], r2=0,
                            floor=False, obj=0))
            continue
        o = list(c["eye"]) if random.random() < 0.6 else [random.randrange(-40000, 40000),
                                                            random.randrange(0, 20000),
                                                            random.randrange(-40000, 40000)]
        obj = random.randrange(7)
        if obj == hw.FLOOR:
            target = [random.randrange(-60000, 60000), 0, random.randrange(-60000, 60000)]
            cc, r2 = [0, 0, 0], 0
        else:
            cc, r2 = centres[obj], hw.sphere_static(obj)["r2"]
            jitter = hw.sphere_static(obj)["r"] * 2
            target = [cc[k] + random.randrange(-jitter, jitter + 1) for k in range(3)]
        v = [target[k] - o[k] for k in range(3)]
        n = max(1, (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5)
        d = [hw.sat18(round(x / n * 65536)) for x in v]
        mode = random.choice([1, 2])
        out.append(dict(mode=mode, idx=random.randrange(512), o=o, d=d, c=list(cc), r2=r2,
                        floor=obj == hw.FLOOR, obj=obj))
    return out


def in_str(q):
    return ("Some(RuIn$(mode: {mode}, idx: {idx}, o: {o}, d: {d}, c: {c}, r2: {r2}, floor: {fl}, obj: {obj}))"
            .format(mode=q["mode"], idx=q["idx"], o=arr(q["o"]), d=arr(q["d"]), c=arr(q["c"]),
                    r2=q["r2"], fl=b(q["floor"]), obj=q["obj"]))


def out_str(q):
    r = hw.ray_unit_ref(q["mode"], q["o"], q["d"], q["c"], q["r2"], q["floor"])
    return ("Some(RuOut$(mode: {}, idx: {}, obj: {}, t: {}, hit: {}, dn: {}))"
            .format(q["mode"], q["idx"], q["obj"], r["t"], b(r["hit"]), arr(r["dn"])))


@cocotb.test()
async def ray_unit_matches_model(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i
    await cocotb.start(Clock(clk, period=10, units="ns").start())
    vec = vectors()
    hits = sum(1 for q in vec if hw.ray_unit_ref(q["mode"], q["o"], q["d"], q["c"], q["r2"], q["floor"])["hit"])
    assert hits > 150, f"only {hits} hits in the vectors"
    s.i.inp = "None"
    for i in range(len(vec) + LAT):
        await FallingEdge(clk)
        s.i.inp = in_str(vec[i]) if i < len(vec) else "None"
        if i >= LAT:
            s.o.assert_eq(out_str(vec[i - LAT]))
