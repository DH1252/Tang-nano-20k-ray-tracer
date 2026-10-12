#!/bin/sh
# Full-system simulation with Verilator, then compare the frames with the model.
# Usage: sim/run.sh              simulate Spade's output as is
#        PLAIN=1 sim/run.sh      simulate the plain-identifier version fed to Gowin EDA
set -eu
cd "$(dirname "$0")/.."
python3 scripts/gen_tables.py
swim build
SRC=build/spade.sv
if [ "${PLAIN:-0}" = 1 ]; then
    python3 scripts/plain_identifiers.py build/spade.sv build/spade_plain.v
    SRC=build/spade_plain.v
fi
mkdir -p sim_out
rm -f sim_out/frame_*.ppm
verilator --binary --timing -j 0 -O3 -Wno-fatal -Wno-lint -Wno-style -Wno-MULTIDRIVEN -Wno-TIMESCALEMOD \
    --top-module tb -Mdir build/verilator -o tb \
    "$SRC" rtl/dq_capture.v \
    sim/clocks_sim.v sim/sdram_clk_sim.v sim/dvi_phy_sim.v sim/sdram_model.v sim/tb_top.v
build/verilator/tb | tee sim_out/sim.log
python3 sim/check.py sim_out
