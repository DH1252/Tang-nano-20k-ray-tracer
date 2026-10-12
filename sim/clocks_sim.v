// Simulation stand-in for rtl/gowin/clocks.v (no PLL model needed).
`timescale 1ps/1ps
module clocks (
    input  wire clk27,
    output reg  clk_ser,
    output reg  clk_pix,
    output reg  clk_core,
    output reg  locked
);
    initial begin
        clk_ser = 0; clk_pix = 0; clk_core = 0; locked = 0;
        #1000000 locked = 1;
    end
    // The serial clock only feeds the serialisers, which the simulated DVI
    // receiver bypasses, so it stays low; the pixel clock is generated directly.
    always #19841 clk_pix = ~clk_pix;     // 25.2 MHz (39.68 ns)
    always #6667 clk_core = ~clk_core;    // 75.0 MHz (13.33 ns)
endmodule
