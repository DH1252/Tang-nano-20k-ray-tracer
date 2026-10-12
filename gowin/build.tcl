# Gowin EDA (gw_sh) build for the Tang Nano 20K. Run through scripts/build.sh.
set_device -name GW2AR-18C GW2AR-LV18QN88C8/I7

add_file -type verilog build/spade_plain.v
add_file -type verilog rtl/dq_capture.v
add_file -type verilog rtl/gowin/clocks.v
add_file -type verilog rtl/gowin/dvi_phy.v
add_file -type verilog rtl/gowin/sdram_clk.v
add_file -type cst constraints/tangnano20k.cst
add_file -type sdc constraints/tangnano20k.sdc

set_option -top_module top
set_option -verilog_std sysv2017
set_option -output_base_name tn20k_raytracer
set_option -gen_text_timing_rpt 1
set_option -rpt_auto_place_io_info 1
set_option -place_option 1
set_option -route_option 1

run all
