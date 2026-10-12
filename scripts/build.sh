#!/bin/sh
# Build the bitstream with Gowin EDA (GowinSynthesis + Gowin place and route):
#   swim (Spade -> Verilog) -> gw_sh gowin/build.tcl
# Needs swim and Gowin EDA (the free Education edition covers the GW2AR-18C).
# Point GOWIN_HOME at the install (the directory containing IDE/bin/gw_sh).
# Usage: GOWIN_HOME=/opt/gowin scripts/build.sh  -> build/gowin/impl/pnr/tn20k_raytracer.fs
#        openFPGALoader -b tangnano20k build/gowin/impl/pnr/tn20k_raytracer.fs   (SRAM)
# scripts/build_oss.sh is the open-source alternative (Yosys / nextpnr / apicula).
set -eu
cd "$(dirname "$0")/.."
ROOT=$(pwd)

GW_SH=${GW_SH:-${GOWIN_HOME:-/opt/gowin}/IDE/bin/gw_sh}
[ -x "$GW_SH" ] || { echo "gw_sh not found at $GW_SH (set GOWIN_HOME or GW_SH)"; exit 1; }

python3 scripts/gen_tables.py
swim build
# Gowin place and route cannot parse Spade's escaped identifiers.
python3 scripts/plain_identifiers.py build/spade.sv build/spade_plain.v

# Headless: no X display needed. Gowin bundles an old libfreetype that clashes
# with recent system fontconfig, so prefer the system one when it exists.
export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-offscreen}
for f in /lib/x86_64-linux-gnu/libfreetype.so.6 /usr/lib/x86_64-linux-gnu/libfreetype.so.6 /usr/lib64/libfreetype.so.6; do
    if [ -f "$f" ]; then export LD_PRELOAD="$f${LD_PRELOAD:+:$LD_PRELOAD}"; break; fi
done

# gw_sh writes its project tree (impl/...) into the current directory.
rm -rf build/gowin
mkdir -p build/gowin
cd build/gowin
for d in build rtl constraints; do ln -s "$ROOT/$d" "$d"; done
"$GW_SH" "$ROOT/gowin/build.tcl" | tee gw_sh.log

FS=impl/pnr/tn20k_raytracer.fs
[ -f "$FS" ] || { echo "no bitstream produced, see build/gowin/gw_sh.log"; exit 1; }
grep -h -A30 "Resource Usage Summary" impl/pnr/tn20k_raytracer.rpt.txt 2>/dev/null | head -30 || true
echo "bitstream: build/gowin/$FS"
