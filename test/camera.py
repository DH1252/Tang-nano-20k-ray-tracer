# top = camera::camera_setup

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


def params_str(p):
    return ("CamParams$(yaw: {yaw}, pitch: {pitch}, dist: {dist}, tx: {tx}, ty: {ty}, tz: {tz}, "
            "fov: {fov}, light_az: {light_az}, light_el: {light_el})").format(**p)


def out_str(c):
    arr = lambda v: "[" + ", ".join(str(x) for x in v) + "]"
    return "CamOut$(eye: {}, d0: {}, du: {}, dv: {}, light: {}, fwd: {}, right: {}, up: {}, s: {})".format(
        arr(c["eye"]), arr(c["d0"]), arr(c["du"]), arr(c["dv"]), arr(c["light"]),
        arr(c["fwd"]), arr(c["right"]), arr(c["up"]), c["s"])


@cocotb.test()
async def camera_matches_model(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i
    await cocotb.start(Clock(clk, period=10, units="ns").start())
    s.i.rst = "true"
    s.i.start = "false"
    s.i.p = params_str(hw.DEFAULT_PARAMS)
    await FallingEdge(clk)
    s.i.rst = "false"
    random.seed(2)
    sets = [hw.DEFAULT_PARAMS]
    for _ in range(12):
        sets.append(dict(yaw=random.randrange(65536), pitch=random.randrange(-0x3000, 0x3000) & 0xFFFF,
                         dist=random.randrange(0x0800, 0xF000), tx=random.randrange(-0x6000, 0x6000),
                         ty=random.randrange(-0x2000, 0x6000), tz=random.randrange(-0x6000, 0x6000),
                         fov=random.randrange(0x1000, 0x9999), light_az=random.randrange(65536),
                         light_el=random.randrange(-0x4000, 0x4000) & 0xFFFF))
    for p in sets:
        s.i.p = params_str(p)
        s.i.start = "true"
        await FallingEdge(clk)
        s.i.start = "false"
        for _ in range(200):
            await FallingEdge(clk)
            if s.o.done.value() == "true":
                break
        else:
            raise AssertionError("done never asserted")
        await FallingEdge(clk)
        s.o.out.assert_eq(out_str(hw.camera(p)))
