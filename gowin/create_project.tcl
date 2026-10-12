# Regenerates the Gowin EDA project gowin/tn20k_raytracer/tn20k_raytracer.gprj
# (only needed when the file list or options change; the project is committed).
# Run from the repository root:
#   gw_sh gowin/create_project.tcl
#   sed -i 's|path="[^"]*/Tang-nano-20k-ray-tracer/|path="../../|' gowin/tn20k_raytracer/tn20k_raytracer.gprj
# gw_sh stores absolute paths; the sed makes them relative so the project opens
# from any checkout (adjust the pattern to your checkout directory name).
set here [file dirname [file normalize [info script]]]
create_project -name tn20k_raytracer -dir gowin -pn GW2AR-LV18QN88C8/I7 -device_version C -force

# create_project switches into gowin/tn20k_raytracer: paths are relative to it.
add_file -type verilog ../../build/spade_plain.v
add_file -type verilog ../../rtl/dq_capture.v
add_file -type verilog ../../rtl/gowin/clocks.v
add_file -type verilog ../../rtl/gowin/dvi_phy.v
add_file -type verilog ../../rtl/gowin/sdram_clk.v
add_file -type cst ../../constraints/tangnano20k.cst
add_file -type sdc ../../constraints/tangnano20k.sdc

set_option -top_module top
set_option -verilog_std sysv2017
set_option -output_base_name tn20k_raytracer
source $here/timing_options.tcl
# Reports (-gen_text_timing_rpt was dropped in SUG1220-2.0E, hence the guard).
tn20k_option gen_text_timing_rpt 1
tn20k_option rpt_auto_place_io_info 1
