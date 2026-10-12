#!/bin/sh
# Simulates build/clocks.v (from rtl/gowin/clocks.v) and rtl/gowin/dvi_phy.v with Gowin's primitive
# models (iverilog).
# Usage: GOWIN_HOME=/path/to/Gowin sim/check_clocks.sh
set -eu
cd "$(dirname "$0")/.."
PRIM=${GOWIN_HOME:-/opt/gowin}/IDE/simlib/gw2a/prim_sim.v
mkdir -p build
python3 scripts/clock_config.py   # build/clocks.v for the core clock ($CORE_MHZ, default 75)
iverilog -g2012 -Ibuild -o build/tb_clocks.vvp -s tb_clocks "$PRIM" build/clocks.v sim/tb_clocks.v
vvp -n build/tb_clocks.vvp
iverilog -g2012 -o build/tb_dvi_phy.vvp -s tb_dvi_phy "$PRIM" rtl/gowin/dvi_phy.v sim/tb_dvi_phy.v
vvp -n build/tb_dvi_phy.vvp
