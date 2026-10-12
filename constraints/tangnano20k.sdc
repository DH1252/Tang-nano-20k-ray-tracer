// Timing constraints for Gowin EDA.
//
// clk27 is the crystal on pin 4. The PLL and divider outputs are generated
// clocks so the timing analyser knows how they relate:
//   clk_ser  = clk27 * 14 / 3   126 MHz  (pll_ser)
//   clk_pix  = clk_ser / 5      25.2 MHz (CLKDIV); clk_pix and clk_ser meet in
//                               the OSER10 serialisers (PCLK / FCLK)
//   clk_core = clk_ser * 3 / 7  54 MHz   (CLKOUTD3 = /3, then pll_core * 9 / 7)
// The core domain meets the video domain only through the dual-clock line RAM
// and synchronised handshakes, so it is asynchronous to it.
create_clock -name clk27 -period 37.037 [get_ports {clk}]
create_generated_clock -name clk_ser -source [get_ports {clk}] -master_clock clk27 -multiply_by 14 -divide_by 3 [get_pins {clocks_0/pll_ser/CLKOUT}]
create_generated_clock -name clk_pix -source [get_pins {clocks_0/pll_ser/CLKOUT}] -master_clock clk_ser -divide_by 5 [get_pins {clocks_0/div5/CLKOUT}]
create_generated_clock -name clk_core -source [get_pins {clocks_0/pll_ser/CLKOUT}] -master_clock clk_ser -multiply_by 3 -divide_by 7 [get_pins {clocks_0/pll_core/CLKOUT}]
set_clock_groups -asynchronous -group [get_clocks {clk_core}] -group [get_clocks {clk_ser clk_pix}]

// Worst core-clock setup paths, listed in the timing report.
report_timing -setup -from_clock [get_clocks {clk_core}] -to_clock [get_clocks {clk_core}] -max_paths 5 -max_common_paths 1
