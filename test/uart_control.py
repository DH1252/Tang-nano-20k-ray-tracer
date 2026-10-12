# top = harness::uart_control

from cocotb import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge
from spade import SpadeExt

CPB = 16  # clocks per bit in this test


class Serial:
    def __init__(self, dut, s):
        self.dut = dut
        self.s = s
        self.clk = dut.clk_i

    async def cycles(self, n):
        for _ in range(n):
            await FallingEdge(self.clk)

    async def send(self, text):
        for ch in text.encode():
            bits = [0] + [(ch >> i) & 1 for i in range(8)] + [1]
            for b in bits:
                self.s.i.rx = "true" if b else "false"
                await self.cycles(CPB)
            await self.cycles(CPB)  # idle gap

    async def query(self, text):
        """Send `text` and return the reply line (listening starts first)."""
        task = cocotb.start_soon(self.recv_line())
        await self.send(text)
        return await task

    async def recv_line(self, timeout_bits=400):
        out = b""
        for _ in range(timeout_bits * CPB):
            await FallingEdge(self.clk)
            if self.s.o.tx.value() == "false":
                # start bit: sample in the middle of each data bit
                await self.cycles(CPB // 2)
                ch = 0
                for i in range(8):
                    await self.cycles(CPB)
                    if self.s.o.tx.value() == "true":
                        ch |= 1 << i
                await self.cycles(CPB)
                out += bytes([ch])
                if out.endswith(b"\n"):
                    return out.decode()
        raise AssertionError(f"timeout, got {out!r}")


async def setup(dut):
    s = SpadeExt(dut)
    await cocotb.start(Clock(dut.clk_i, period=10, units="ns").start())
    s.i.rst = "true"
    s.i.rx = "true"
    s.i.clocks_per_bit = str(CPB)
    s.i.frame_tick = "false"
    await FallingEdge(dut.clk_i)
    await FallingEdge(dut.clk_i)
    s.i.rst = "false"
    return s, Serial(dut, s)


@cocotb.test()
async def read_write_registers(dut):
    s, ser = await setup(dut)
    assert await ser.query("R 00\r") == "00=5254\r\n"
    assert await ser.query("R 04\n") == "04=6000\r\n"
    assert await ser.query("W 02 1a2B\r") == "ok\r\n"
    s.o.params.cam.yaw.assert_eq("0x1a2b")
    assert await ser.query("R 2\r") == "02=1a2b\r\n"
    assert await ser.query("R 0E\r") == "0e=1234\r\n"
    assert await ser.query("R 14\r") == "14=1d4c\r\n"  # core clock 75.00 MHz
    # fov is clamped to 1.2
    assert await ser.query("W 08 FFFF\r") == "ok\r\n"
    s.o.params.cam.fov.assert_eq("0x9999")
    # malformed
    assert await ser.query("W 02\r") == "?\r\n"
    assert await ser.query("Rxyz\r") == "?\r\n"
    s.o.params.cam.yaw.assert_eq("0x1a2b")


@cocotb.test()
async def keys_and_auto_motion(dut):
    s, ser = await setup(dut)
    await ser.send("d")
    s.o.params.cam.yaw.assert_eq("0x0200")
    await ser.send("aa")
    s.o.params.cam.yaw.assert_eq("0xfe00")
    await ser.send("w")
    s.o.params.cam.pitch.assert_eq("0x0800")
    await ser.send("z")
    s.o.params.cam.dist.assert_eq("0x5c00")
    await ser.send("li")
    s.o.params.cam.light_az.assert_eq("0x9400")
    s.o.params.cam.light_el.assert_eq("0x0b00")
    await ser.send("t")
    s.o.params.test_pattern.assert_eq("true")
    # auto motion: yaw += 0x20 and az += 0x10 per frame while enabled
    for _ in range(3):
        s.i.frame_tick = "true"
        await FallingEdge(dut.clk_i)
        s.i.frame_tick = "false"
        await FallingEdge(dut.clk_i)
    s.o.params.cam.yaw.assert_eq("0xfe60")
    s.o.params.cam.light_az.assert_eq("0x9430")
    await ser.send("op")
    s.o.params.orbit.assert_eq("false")
    s.o.params.light_auto.assert_eq("false")
    s.i.frame_tick = "true"
    await FallingEdge(dut.clk_i)
    s.i.frame_tick = "false"
    await FallingEdge(dut.clk_i)
    s.o.params.cam.yaw.assert_eq("0xfe60")
    await ser.send("c")
    s.o.params.cam.yaw.assert_eq("0x0000")
    s.o.params.cam.dist.assert_eq("0x6000")
    s.o.params.orbit.assert_eq("true")
    s.o.params.test_pattern.assert_eq("false")
