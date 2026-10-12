// Timing constraints for Gowin EDA.
// 27 MHz crystal; PLL and divider outputs are constrained directly. The pixel
// and core domains only meet in the dual-clock line RAM and in synchronised
// handshakes, so they are asynchronous to each other.
create_clock -name clk27    -period 37.037 [get_ports {clk}]
create_clock -name clk_ser  -period 7.937  [get_pins {clocks_0/pll_ser/CLKOUT}]
create_clock -name clk_pix  -period 39.683 [get_pins {clocks_0/div5/CLKOUT}]
create_clock -name clk_core -period 18.519 [get_pins {clocks_0/pll_core/CLKOUT}]
set_clock_groups -asynchronous -group [get_clocks {clk_core}] -group [get_clocks {clk_pix clk_ser}] -group [get_clocks {clk27}]
