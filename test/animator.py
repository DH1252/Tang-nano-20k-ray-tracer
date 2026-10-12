# top = animator::animator

import os
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


@cocotb.test()
async def animator_matches_model(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i
    await cocotb.start(Clock(clk, period=10, units="ns").start())
    s.i.rst = "true"
    s.i.start = "false"
    s.i.anim = "0"
    await FallingEdge(clk)
    s.i.rst = "false"
    for anim in (0, 0x1234, 0x8000, 0xFFFF, 0x4321, 0xC0DE):
        s.i.anim = str(anim)
        s.i.start = "true"
        await FallingEdge(clk)
        s.i.start = "false"
        for _ in range(40):
            await FallingEdge(clk)
            if s.o.done.value() == "true":
                break
        else:
            raise AssertionError("done never asserted")
        c = hw.animate(anim)
        s.o.c.assert_eq("[" + ", ".join("[" + ", ".join(str(v) for v in p) + "]" for p in c) + "]")
