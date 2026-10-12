# top = sfu::rsqrt

import math
import os
import random
import sys

from cocotb import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge
from spade import SpadeExt

# Tests run from build/<test>/; find the repo root to import the model.
_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(_d, "swim.toml")):
    _d = os.path.dirname(_d)
sys.path.insert(0, os.path.join(_d, "model"))
import hw  # noqa: E402


@cocotb.test()
async def rsqrt_matches_model(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i
    await cocotb.start(Clock(clk, period=10, units="ns").start())
    random.seed(1)
    cases = [(1, 16), (65536, 16), (3 << 30, 32), ((1 << 40) - 1, 32), (12345, 16), (7, 0), (0, 16)]
    cases += [(random.randrange(1, 1 << 40), random.choice([0, 12, 16, 24, 32])) for _ in range(400)]
    worst = 0.0
    for x, fin in cases:
        await FallingEdge(clk)
        s.i.x = str(x)
        s.i.fin = str(fin)
        for _ in range(5):
            await FallingEdge(clk)
        y1 = int(s.o.y1.value())
        e = int(s.o.e.value())
        assert (y1, e) == hw.rsqrt(x, fin), f"x={x} fin={fin}: rtl {(y1, e)} model {hw.rsqrt(x, fin)}"
        exact = 1.0 / math.sqrt(max(x, 1) / 2.0 ** fin)
        rel = abs(y1 / 65536.0 * 2.0 ** (-e / 2) / exact - 1)
        worst = max(worst, rel)
        assert rel < 4e-5, f"x={x} fin={fin} rel={rel}"
    dut._log.info(f"{len(cases)} cases bit-exact with model; worst relative error {worst:.2e}")
