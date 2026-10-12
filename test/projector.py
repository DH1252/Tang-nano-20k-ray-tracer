# top = projector::projector

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


def arr(v):
    return "[" + ", ".join(str(x) for x in v) + "]"


def box(b):
    if b is None:
        return "Box$(on: false, x0: 0, x1: 0, y0: 0, y1: 0)"
    return f"Box$(on: true, x0: {b[0]}, x1: {b[1]}, y0: {b[2]}, y1: {b[3]})"


@cocotb.test()
async def projector_matches_model(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i
    await cocotb.start(Clock(clk, period=10, units="ns").start())
    s.i.rst = "true"
    s.i.start = "false"
    await FallingEdge(clk)
    s.i.rst = "false"
    random.seed(4)
    cases = [(hw.DEFAULT_PARAMS, hw.DEFAULT_SCENE, False), (hw.DEFAULT_PARAMS, hw.DEFAULT_SCENE, True)]
    for _ in range(14):
        p = dict(hw.DEFAULT_PARAMS, yaw=random.randrange(65536), pitch=random.randrange(-0x2000, 0x3000) & 0xFFFF,
                 dist=random.randrange(0x1800, 0xF000), fov=random.randrange(0x1000, 0x9999),
                 ty=random.randrange(0, 0x4000), light_az=random.randrange(65536),
                 light_el=random.choice([random.randrange(0, 0x4000), 0x0100, 0x0200]))
        cases.append((p, dict(hw.DEFAULT_SCENE, anim=random.randrange(65536)), random.random() < 0.5))
    # Views with divisions that saturate (quotient >= 2^17): the divider
    # answers those at once, which must not lose the result.
    cases.append((dict(hw.DEFAULT_PARAMS, yaw=36763, pitch=62984, dist=9630, ty=12616, fov=4423,
                       light_az=51077, light_el=8273), dict(hw.DEFAULT_SCENE, anim=17203), True))
    cases.append((dict(hw.DEFAULT_PARAMS, yaw=48401, pitch=4295, dist=41241, ty=7158, fov=25798,
                       light_az=20049, light_el=1612), dict(hw.DEFAULT_SCENE, anim=46050), True))
    for p, sc, q in cases:
        cam = hw.camera(p)
        cen = hw.animate(sc["anim"])
        s.i.quality = "true" if q else "false"
        s.i.eye = arr(cam["eye"])
        s.i.fwd = arr(cam["fwd"])
        s.i.right = arr(cam["right"])
        s.i.up = arr(cam["up"])
        s.i.s = str(cam["s"])
        s.i.fov = str(p["fov"])
        s.i.light = arr(cam["light"])
        s.i.centres = "[" + ", ".join(arr(c) for c in cen) + "]"
        s.i.start = "true"
        await FallingEdge(clk)
        s.i.start = "false"
        for n in range(3000):
            await FallingEdge(clk)
            if s.o.done.value() == "true":
                break
        else:
            raise AssertionError("done never asserted")
        await FallingEdge(clk)
        sb, hb = hw.boxes(p, sc, q)
        s.o.sph.assert_eq("[" + ", ".join(box(b) for b in sb) + "]")
        s.o.shd.assert_eq("[" + ", ".join(box(b) for b in hb) + "]")
        dut._log.info(f"case ok after {n} cycles: quality={q} sun_el={p['light_el']:#06x}")
