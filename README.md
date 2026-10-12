# Tang Nano 20K Ray Tracer

A real-time ray tracer in FPGA logic for the Sipeed Tang Nano 20K (Gowin
GW2AR-18), written in [Spade](https://spade-lang.org). The plan and its
LUT/DSP/BRAM budget are in [docs/PLAN.md](docs/PLAN.md).

**Status:** the display, memory and control path is built and verified in
simulation. It has not been tested on a board yet.

- 640×480@60 DVI out of the HDMI connector.
- A double-buffered 320×240 RGB565 framebuffer in the chip's embedded SDRAM.
  Buffers swap during vertical blanking, so there is no tearing.
- An orbit camera and a sun that move on their own or under control from the
  USB UART ([protocol](docs/uart-protocol.md)) and the two buttons.
- A first per-pixel ray renderer: sky, sun and a checkerboard floor with a sun
  glint. Spheres, shadows and reflections (plan milestones M2–M4) are next.

Frames from the full-system simulation, captured at the HDMI encoder and
identical to the Python model. Left: the first frame. Right: after
`W 02 3000`, `W 03 0400`, `W 0A 7000`, `W 0B 1800` and the keys `d` `l` over
the UART:

<img src="docs/img/sim_frame_1.png" width="49%"> <img src="docs/img/sim_frame_4.png" width="49%">

## Build and program

The default flow is **Gowin EDA** (GowinSynthesis plus Gowin place and route)
driven headless through `gw_sh`. You need:
- [swim](https://codeberg.org/spade-lang/swim) (`cargo install --git https://codeberg.org/spade-lang/swim`)
- Gowin EDA; the free Education edition (V1.9.11.03 for Linux) supports the GW2AR-18C.

```
GOWIN_HOME=/opt/gowin scripts/build.sh     # -> build/gowin/impl/pnr/tn20k_raytracer.fs
openFPGALoader -b tangnano20k build/gowin/impl/pnr/tn20k_raytracer.fs   # load to SRAM
```

`scripts/build.sh` sets `QT_QPA_PLATFORM=offscreen`, so no display is needed.
It also preloads the system libfreetype, because the one Gowin bundles breaks
on current distributions. Two things in the Spade output have to be adapted
for Gowin's tools:
- **Escaped identifiers:** Spade uses names like `\_` for anonymous
  registers, which Gowin's place and route cannot read back from the
  synthesised netlist. `scripts/plain_identifiers.py` rewrites them;
  `PLAIN=1 sim/run.sh` simulates that rewritten file.
- **Large ROM constants:** constants over 2^16 bits are not accepted, so the
  sine table is stored as a quarter wave.

Pin and timing constraints: `constraints/tangnano20k.cst` and
`constraints/tangnano20k.sdc`. The Gowin project script is `gowin/build.tcl`.

`scripts/build_oss.sh` is the open-source alternative (Yosys, nextpnr-himbaechel,
apicula). It produced the only full build so far:

| LUT4 | Flip-flops | Block RAM | 18×18 multipliers | PLLs | fmax core / pixel (needed) |
|------|-----------|-----------|-------------------|------|----------------------------|
| 6,100 / 20,736 (29 %) | 3,725 / 15,552 | 10 / 46 | 29 / 48 (+7 9×9) | 2 / 2 | 146.6 / 85.8 MHz (54 / 25.2) |

## Control it

Open the board's serial port at 115200 baud and press keys:

- `a` / `d`: orbit the camera
- `w` / `s`: raise or lower the camera
- `z` / `x`: zoom in or out
- `j` / `l`: move the sun's azimuth
- `i` / `k`: raise or lower the sun
- `o`: camera auto-orbit on/off
- `p`: sun motion on/off
- `t`: test pattern
- `c`: reset to defaults

The host tool takes values in real units:

```
pip install pyserial
tools/rtctl.py /dev/ttyUSB1 dump
tools/rtctl.py /dev/ttyUSB1 set yaw 45 dist 4.5 fov 70 sun_el 20 orbit off
tools/rtctl.py /dev/ttyUSB1 keys
```

LEDs, from `led[0]`:
- `led[0]` frame heartbeat
- `led[1]` SDRAM ready
- `led[2]` orbit on
- `led[3]` sun motion on
- `led[4]` UART activity
- `led[5]` freeze

## Test

```
swim test        # cocotb unit tests: rsqrt unit, camera setup, UART + command parser
sim/run.sh       # full system in Verilator: SDRAM and DVI models, scripted UART session,
                 # 3 frames compared bit for bit with model/hw.py (needs Verilator 5)
PLAIN=1 sim/run.sh   # the same on the identifier-rewritten Verilog that Gowin EDA builds
```

`model/hw.py` is a bit-exact Python model of the RTL arithmetic. The tests
compare against it, and the system simulation also checks the SDRAM protocol,
SDRAM timing and TMDS symbols.

## Layout

```
src/            Spade RTL (main.spade is the top level)
rtl/            Verilog: Gowin primitive wrappers, SDRAM read capture
constraints/    pin (.cst) and timing (.sdc) constraints
gowin/          Gowin EDA project script (gw_sh)
test/           cocotb tests          sim/      system testbench and models
model/          Python models         scripts/  build and table generation
tools/          host tools            docs/     plan, UART protocol
```
