// DVI physical layer: four 10:1 serialisers (OSER10, bit 0 first) driving
// true-LVDS output buffers on the HDMI connector (pins 33-40 are TLVDS pairs).
module dvi_phy (
    input  wire       clk_pix,
    input  wire       clk_ser,
    input  wire       rst,
    input  wire [9:0] ch0,
    input  wire [9:0] ch1,
    input  wire [9:0] ch2,
    output wire       tmds_clk_p,
    output wire       tmds_clk_n,
    output wire [2:0] tmds_d_p,
    output wire [2:0] tmds_d_n
);
    wire [9:0] sym [0:3];
    assign sym[0] = ch0;
    assign sym[1] = ch1;
    assign sym[2] = ch2;
    assign sym[3] = 10'b0000011111;  // TMDS clock: 5 high, 5 low per pixel

    // OSER10 RESET is checked against FCLK. Driven straight from the clk_pix
    // domain it failed removal timing (the divided clock's edges land just
    // after clk_ser's), so the lanes could leave reset on different serial
    // clock edges. Re-time it into clk_ser with plain (synchronous) flip-flops:
    // the clk_pix -> clk_ser hop is an ordinary path between related clocks,
    // and every RESET pin is released by the same clk_ser register.
    reg [1:0] rst_ser = 2'b11;
    always @(posedge clk_ser) rst_ser <= {rst_ser[0], rst};

    wire [3:0] ser;
    genvar i;
    generate
        for (i = 0; i < 4; i = i + 1) begin : lane
            OSER10 #(.GSREN("false"), .LSREN("true")) s (
                .Q(ser[i]),
                .D0(sym[i][0]), .D1(sym[i][1]), .D2(sym[i][2]), .D3(sym[i][3]), .D4(sym[i][4]),
                .D5(sym[i][5]), .D6(sym[i][6]), .D7(sym[i][7]), .D8(sym[i][8]), .D9(sym[i][9]),
                .PCLK(clk_pix), .FCLK(clk_ser), .RESET(rst_ser[1])
            );
        end
    endgenerate

    TLVDS_OBUF b0 (.I(ser[0]), .O(tmds_d_p[0]), .OB(tmds_d_n[0]));
    TLVDS_OBUF b1 (.I(ser[1]), .O(tmds_d_p[1]), .OB(tmds_d_n[1]));
    TLVDS_OBUF b2 (.I(ser[2]), .O(tmds_d_p[2]), .OB(tmds_d_n[2]));
    TLVDS_OBUF bc (.I(ser[3]), .O(tmds_clk_p), .OB(tmds_clk_n));
endmodule
