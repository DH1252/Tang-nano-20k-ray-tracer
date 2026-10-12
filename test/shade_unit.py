# top = shade_unit::shade_unit

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

LAT = 22


def arr(v):
    return "[" + ", ".join(str(x) for x in v) + "]"


def b(v):
    return "true" if v else "false"


def vectors():
    """SuIn fields from real rays: primary and reflected, both modes."""
    random.seed(11)
    p = dict(hw.DEFAULT_PARAMS, yaw=0x1800, light_el=0x1400, light_az=0x6800)
    scene = dict(hw.DEFAULT_SCENE, floor_kr=1, depth=2)
    c, d0, du, dv, centres = hw.frame_setup(p, scene)
    out = []
    while len(out) < 700:
        x, y = random.randrange(320), random.randrange(240)
        d = [hw.wrap(d0[i] + y * dv[i] + x * du[i], 28) for i in range(3)]
        O, D = list(c["eye"]), hw.gen_ray(d)
        for depth in range(2):
            t, hid = hw.closest_hit(O, D, centres, 6)
            sp = hw.su_input(False, O, D, t, hid, centres, scene, idx=random.randrange(512),
                             pix=random.randrange(512), tp=random.randrange(257))
            out.append(sp)
            r = hw.shade_unit_ref(sp, c["light"])
            P = r["p"] if r["hit"] else O
            sh = hw.su_input(True, P, D, t, hid, centres, scene, shadow=random.random() < 0.3,
                             acc=[random.randrange(256) for _ in range(3)], first=random.random() < 0.5,
                             may_refl=random.random() < 0.7, tp=random.randrange(257),
                             idx=random.randrange(512), pix=random.randrange(512))
            out.append(sh)
            rs = hw.shade_unit_ref(sh, c["light"])
            if not r["hit"]:
                break
            O, D = rs["p"], rs["r"]
    return c["light"], out


def in_str(q):
    return ("Some(SuIn$(shade: {}, idx: {}, pix: {}, tp: {}, o: {}, d: {}, t: {}, id: {}, shadow: {}, "
            "acc: {}, first: {}, may_refl: {}, c: {}, invr: {}, alb: {}, kr: {}, spec: {}))").format(
        b(q["shade"]), q["idx"], q["pix"], q["tp"], arr(q["o"]), arr(q["d"]), q["t"], q["id"],
        b(q["shadow"]), arr(q["acc"]), b(q["first"]), b(q["may_refl"]), arr(q["c"]), q["invr"],
        arr(q["alb"]), q["kr"], b(q["spec"]))


def out_str(q, light):
    r = hw.shade_unit_ref(q, light)
    return ("Some(SuOut$(shade: {}, idx: {}, pix: {}, p: {}, r: {}, hit: {}, spawn_shadow: {}, refl: {}, "
            "tp_next: {}, acc: {}))").format(
        b(r["shade"]), r["idx"], r["pix"], arr(r["p"]), arr(r["r"]), b(r["hit"]), b(r["spawn_shadow"]),
        b(r["refl"]), r["tp_next"], arr(r["acc"]))


@cocotb.test()
async def shade_unit_matches_model(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i
    await cocotb.start(Clock(clk, period=10, units="ns").start())
    light, vec = vectors()
    s.i.light = arr(light)
    s.i.inp = "None"
    for i in range(len(vec) + LAT):
        await FallingEdge(clk)
        s.i.inp = in_str(vec[i]) if i < len(vec) else "None"
        if i >= LAT:
            s.o.assert_eq(out_str(vec[i - LAT], light))
