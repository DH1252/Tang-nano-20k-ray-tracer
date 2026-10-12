// Drives the SDRAM clock pin with the inverted controller clock through an
// output DDR register, so the SDRAM samples commands mid-cycle.
module sdram_clk (
    input  wire clk,
    output wire sdram_clk
);
    ODDR #(.INIT(1'b0), .TXCLK_POL(1'b0)) oddr (
        .D0(1'b0), .D1(1'b1), .TX(1'b0), .CLK(clk), .Q0(sdram_clk), .Q1()
    );
endmodule
