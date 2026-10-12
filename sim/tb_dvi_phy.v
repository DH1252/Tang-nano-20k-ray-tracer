// Checks rtl/gowin/dvi_phy.v with Gowin's OSER10/TLVDS_OBUF models: after
// reset every lane must repeat its symbol LSB first, all four lanes aligned to
// the same serial clock edge, and each _n output the inverse of its _p output.
`timescale 1ps/1ps
module tb_dvi_phy;
    GSR GSR (.GSRI(1'b1));

    reg clk_ser = 0;
    always #3968 clk_ser = ~clk_ser;          // 126 MHz
    // clk_pix = clk_ser / 5, edges a little after clk_ser's like CLKDIV's
    reg [2:0] div = 0;
    reg clk_pix_r = 0;
    always @(posedge clk_ser or negedge clk_ser) begin
        div <= (div == 4) ? 0 : div + 1;
        if (div == 4) clk_pix_r <= ~clk_pix_r;
    end
    wire #500 clk_pix = clk_pix_r;

    reg rst = 1;
    reg [9:0] ch0 = 10'b1101010100, ch1 = 10'b0010101011, ch2 = 10'b0101010100;
    wire tmds_clk_p, tmds_clk_n;
    wire [2:0] tmds_d_p, tmds_d_n;

    dvi_phy dut (.clk_pix(clk_pix), .clk_ser(clk_ser), .rst(rst),
                 .ch0(ch0), .ch1(ch1), .ch2(ch2),
                 .tmds_clk_p(tmds_clk_p), .tmds_clk_n(tmds_clk_n),
                 .tmds_d_p(tmds_d_p), .tmds_d_n(tmds_d_n));

    // Shift in the serial bits (one per clk_ser edge, DDR) and look for the
    // clock lane's 0000011111 pattern ending at the newest bit.
    reg [9:0] sh [0:3];
    integer n = 0, frames = 0, errors = 0, k;
    integer settle = 0;   // serialiser latency: skip symbols right after a change
    always @(posedge clk_ser or negedge clk_ser) begin
        #1000;
        sh[0] = {tmds_d_p[0], sh[0][9:1]};
        sh[1] = {tmds_d_p[1], sh[1][9:1]};
        sh[2] = {tmds_d_p[2], sh[2][9:1]};
        sh[3] = {tmds_clk_p, sh[3][9:1]};
        if (tmds_clk_n !== ~tmds_clk_p || tmds_d_n !== ~tmds_d_p) errors = errors + 1;
        n = n + 1;
        if (!rst && n > 400 && sh[3] == 10'b0000011111) begin
            frames = frames + 1;
            if (settle > 0) settle = settle - 1;
            else if (sh[0] !== ch0 || sh[1] !== ch1 || sh[2] !== ch2) begin
                errors = errors + 1;
                $display("misaligned: %b %b %b", sh[0], sh[1], sh[2]);
            end
        end
    end

    initial begin
        for (k = 0; k < 4; k = k + 1) sh[k] = 0;
        repeat (20) @(posedge clk_pix);
        rst <= 0;
        repeat (100) @(posedge clk_pix);
        // change the symbols on a pixel edge; they must follow
        ch0 <= 10'b0010101011; ch1 <= 10'b1011001100; ch2 <= 10'b1111100000;
        settle = 3;
        repeat (100) @(posedge clk_pix);
        if (frames < 150 || errors != 0) begin
            $display("FAIL dvi_phy: %0d symbols, %0d errors", frames, errors);
            $fatal(1);
        end
        $display("PASS dvi_phy: %0d symbols, lanes aligned", frames);
        $finish;
    end
endmodule
