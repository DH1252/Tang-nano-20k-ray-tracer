`timescale 1ps/1ps
module sdram_clk (input wire clk, output wire sdram_clk);
    assign sdram_clk = ~clk;
endmodule
