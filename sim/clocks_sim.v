// Simulation stand-in for rtl/gowin/clocks.v (no PLL model needed).
`timescale 1ps/1ps
//
// A template like rtl/gowin/clocks.v: scripts/clock_config.py writes
// build/clocks_sim.v with these localparams set for the chosen core clock.
module clocks (
    input  wire clk27,
    output reg  clk_ser,
    output reg  clk_pix,
    output reg  clk_core,
    output reg  locked,
    output wire [15:0] uart_div,
    output wire [9:0]  ref_interval,
    output wire [15:0] core_cmhz
);
    localparam CORE_HALF_PS = 6667;   // 75.0 MHz (13.33 ns)
    localparam [15:0] UART_DIV = 651;
    localparam [9:0] REF_INTERVAL = 600;
    localparam [15:0] CORE_CMHZ = 7500;
    assign uart_div = UART_DIV;
    assign ref_interval = REF_INTERVAL;
    assign core_cmhz = CORE_CMHZ;

    initial begin
        clk_ser = 0; clk_pix = 0; clk_core = 0; locked = 0;
        #1000000 locked = 1;
    end
    // The serial clock only feeds the serialisers, which the simulated DVI
    // receiver bypasses, so it stays low; the pixel clock is generated directly.
    always #19841 clk_pix = ~clk_pix;     // 25.2 MHz (39.68 ns)
    always #CORE_HALF_PS clk_core = ~clk_core;
endmodule
