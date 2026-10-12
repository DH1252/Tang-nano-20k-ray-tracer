// Simulation stand-in for rtl/gowin/dvi_phy.v: a DVI receiver. It decodes
// the three TMDS channels every pixel clock, checks the symbols, and writes
// each complete 640x480 frame to sim_out/frame_NNN.ppm.
`timescale 1ps/1ps
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
    assign tmds_clk_p = clk_pix;
    assign tmds_clk_n = ~clk_pix;
    // tmds_d_p[0] toggles after every frame written, so the testbench can
    // count frames without hierarchical references.
    reg frame_toggle = 0;
    assign tmds_d_p = {2'b0, frame_toggle};
    assign tmds_d_n = 3'b0;

    // 0..3 for control symbols (c1 c0), -1 for data
    function integer ctrl_of(input [9:0] s);
        case (s)
            10'b1101010100: ctrl_of = 0;
            10'b0010101011: ctrl_of = 1;
            10'b0101010100: ctrl_of = 2;
            10'b1010101011: ctrl_of = 3;
            default:        ctrl_of = -1;
        endcase
    endfunction

    // Running disparity (ones minus zeros) per channel: TMDS keeps it bounded.
    integer disp [0:2];
    initial begin disp[0] = 0; disp[1] = 0; disp[2] = 0; end
    function integer ones_minus_zeros(input [9:0] s);
        integer j;
        begin
            ones_minus_zeros = 0;
            for (j = 0; j < 10; j = j + 1) ones_minus_zeros = ones_minus_zeros + (s[j] ? 1 : -1);
        end
    endfunction

    task check_balance(input integer ch, input [9:0] s, input integer is_data);
        begin
            if (!is_data) disp[ch] = 0;   // the encoder resets its count in blanking
            else begin
                disp[ch] = disp[ch] + ones_minus_zeros(s);
                if (synced && (disp[ch] > 20 || disp[ch] < -20)) begin
                    if (errors < 10) $display("dvi: channel %0d disparity %0d", ch, disp[ch]);
                    errors = errors + 1;
                end
            end
        end
    endtask

    function [7:0] decode(input [9:0] s);
        reg [7:0] d;
        integer i;
        begin
            d = s[9] ? ~s[7:0] : s[7:0];
            decode[0] = d[0];
            for (i = 1; i < 8; i = i + 1)
                decode[i] = s[8] ? (d[i] ^ d[i-1]) : ~(d[i] ^ d[i-1]);
        end
    endfunction

    reg [23:0] fb [0:640*480-1];
    integer x = 0, y = 0, frames = 0, errors = 0;
    integer prev_de = 0, prev_vs = 1, synced = 0;
    integer c0, c1, c2, de, vs, f, i;
    reg [8*64-1:0] name;

    always @(posedge clk_pix) if (!rst) begin
        c0 = ctrl_of(ch0); c1 = ctrl_of(ch1); c2 = ctrl_of(ch2);
        de = (c0 < 0);
        check_balance(0, ch0, c0 < 0);
        check_balance(1, ch1, c1 < 0);
        check_balance(2, ch2, c2 < 0);
        if (synced && ((c1 < 0) != de || (c2 < 0) != de)) begin
            if (errors < 10) $display("dvi: channels disagree on DE at x=%0d y=%0d", x, y);
            errors = errors + 1;
        end
        if (de) begin
            if (x < 640 && y < 480)
                fb[y * 640 + x] = {decode(ch2), decode(ch1), decode(ch0)};
            x = x + 1;
        end else begin
            if (prev_de) begin
                if (synced && x != 640) begin
                    $display("dvi: line %0d had %0d pixels", y, x);
                    errors = errors + 1;
                end
                x = 0;
                y = y + 1;
            end
            vs = c0[1];  // vsync level, active low
            if (!vs && prev_vs) begin
                if (!synced) begin
                    synced = 1;   // ignore everything before the first vsync
                    x = 0;
                end else if (y == 480) begin
                    $sformat(name, "sim_out/frame_%03d.ppm", frames);
                    f = $fopen(name, "wb");
                    $fwrite(f, "P6\n640 480\n255\n");
                    for (i = 0; i < 640 * 480; i = i + 1)
                        $fwrite(f, "%c%c%c", fb[i][23:16], fb[i][15:8], fb[i][7:0]);
                    $fclose(f);
                    $display("dvi: frame %0d written at %0t ps", frames, $time);
                    frames = frames + 1;
                    frame_toggle = ~frame_toggle;
                end else begin
                    $display("dvi: partial frame with %0d lines", y);
                    errors = errors + 1;
                end
                y = 0;
            end
            prev_vs = vs;
        end
        prev_de = de;
    end
endmodule
