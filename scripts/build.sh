#!/bin/sh
# Gowin EDA build of gowin/tn20k_raytracer/tn20k_raytracer.gprj.
#
#   scripts/build.sh prepare   generate the Verilog the project uses
#                              (build/spade_plain.v); then open the .gprj in
#                              the Gowin IDE and press Run All
#   scripts/build.sh           prepare, then build headless with gw_sh
#                              -> gowin/tn20k_raytracer/impl/pnr/tn20k_raytracer.fs
#   scripts/build.sh options   store the timing settings (gowin/timing_options.tcl)
#                              in the project so the IDE uses them; lists every
#                              option in build/gowin_options.tcl. Close the
#                              project in the IDE first.
#
# Needs swim and Gowin EDA. Set GOWIN_HOME to the install directory (the one
# containing IDE/bin/gw_sh) or GW_SH to the gw_sh binary. Licensing is whatever
# your Gowin install is configured with.
# scripts/build_oss.sh is the open-source alternative (Yosys / nextpnr / apicula).
set -eu
cd "$(dirname "$0")/.."

gw_sh_setup() {
    GW_SH=${GW_SH:-${GOWIN_HOME:-/opt/gowin}/IDE/bin/gw_sh}
    [ -x "$GW_SH" ] || { echo "gw_sh not found at $GW_SH (set GOWIN_HOME or GW_SH)"; exit 1; }
    # Headless Linux: no X display needed. Some Gowin releases bundle a
    # libfreetype that clashes with recent system fontconfig, so prefer the
    # system one.
    export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-offscreen}
    for f in /lib/x86_64-linux-gnu/libfreetype.so.6 /usr/lib/x86_64-linux-gnu/libfreetype.so.6 /usr/lib64/libfreetype.so.6; do
        if [ -f "$f" ]; then export LD_PRELOAD="$f${LD_PRELOAD:+:$LD_PRELOAD}"; break; fi
    done
    mkdir -p build
}

if [ "${1:-}" = options ]; then
    gw_sh_setup
    "$GW_SH" gowin/apply_options.tcl
    exit 0
fi

python3 scripts/gen_tables.py
swim build
# Gowin place and route cannot read back some of Spade's escaped identifiers.
python3 scripts/plain_identifiers.py build/spade.sv build/spade_plain.v
# Stamp the source revision, so a Gowin project building stale Verilog shows.
REV=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)
git diff --quiet HEAD -- src 2>/dev/null || REV="$REV+local-changes"
sed -i "1i // Generated from revision $REV on $(date -u +%Y-%m-%dT%H:%MZ) by scripts/build.sh" build/spade_plain.v
echo "generated build/spade_plain.v (revision $REV)"
[ "${1:-}" = prepare ] && exit 0

gw_sh_setup
"$GW_SH" gowin/build.tcl | tee build/gw_sh.log

FS=gowin/tn20k_raytracer/impl/pnr/tn20k_raytracer.fs
[ -f "$FS" ] || { echo "no bitstream produced, see build/gw_sh.log"; exit 1; }
echo "bitstream: $FS"
