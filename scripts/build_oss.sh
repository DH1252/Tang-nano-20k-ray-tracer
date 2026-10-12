#!/bin/sh
# Build the bitstream with the open-source flow:
#   swim (Spade -> Verilog) -> Yosys synth_gowin -> nextpnr-himbaechel -> gowin_pack
# Tools: swim + spade (cargo), and the yowasp-yosys / yowasp-nextpnr-himbaechel-gowin
# / apycula Python packages, or native yosys / nextpnr-himbaechel / gowin_pack.
# Alternative to the Gowin EDA flow in scripts/build.sh.
# Usage: scripts/build_oss.sh        -> build/tn20k_raytracer.fs
#        CORE_MHZ=66 scripts/build_oss.sh   (core clock, default 75)
#        openFPGALoader -b tangnano20k build/tn20k_raytracer.fs   (SRAM)
#        openFPGALoader -b tangnano20k -f build/tn20k_raytracer.fs (flash)
set -eu
cd "$(dirname "$0")/.."

YOSYS=${YOSYS:-$(command -v yosys || echo yowasp-yosys)}
NEXTPNR=${NEXTPNR:-$(command -v nextpnr-himbaechel || echo yowasp-nextpnr-himbaechel-gowin)}
SEED=${SEED:-1}

python3 scripts/gen_tables.py
python3 scripts/clock_config.py
swim build

"$YOSYS" -q -l build/yosys.log -p "
    read_verilog -sv build/spade.sv;
    read_verilog rtl/dq_capture.v build/clocks.v rtl/gowin/dvi_phy.v rtl/gowin/sdram_clk.v;
    synth_gowin -family gw2a -top top -json build/hardware.json;
    tee -o build/utilization.txt stat;
"

"$NEXTPNR" --json build/hardware.json --write build/pnr.json \
    --device GW2AR-LV18QN88C8/I7 --vopt family=GW2A-18C \
    --vopt cst=constraints/tangnano20k.cst \
    --freq ${CORE_MHZ:-75} --seed "$SEED" \
    --report build/pnr_report.json -l build/nextpnr.log

gowin_pack -d GW2A-18C -o build/tn20k_raytracer.fs build/pnr.json
echo "bitstream: build/tn20k_raytracer.fs"
