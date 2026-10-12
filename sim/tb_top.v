// Full-system testbench: the real Spade `top` with simulation models for the
// clocks, the DVI receiver and the SDRAM. It drives a scripted UART session
// and the DVI model writes every displayed frame to sim_out/frame_NNN.ppm;
// sim/check.py finds the expected images (bit-exact Python model) among them.
//
//   1. the first frame: defaults plus one auto-motion step
//   2. after W commands (camera, sun, animation time, reflective floor) and
//      the keys `d` and `l`
//   3. the same view in the 640x480 quality mode (two checkerboard frames merged)
//   4. the quality-mode test pattern (key `t`)
`timescale 1ps/1ps
module tb;
    reg clk27 = 0;  // unused by the simulated clock block

    reg uart_rx = 1;
    wire uart_tx;
    wire [5:0] led;
    wire tmds_clk_p, tmds_clk_n;
    wire [2:0] tmds_d_p, tmds_d_n;
    wire sd_clk, sd_cke, sd_cs_n, sd_cas_n, sd_ras_n, sd_we_n;
    wire [3:0] sd_dqm;
    wire [10:0] sd_addr;
    wire [1:0] sd_ba;
    wire [31:0] sd_dq;

    top dut (
        .clk(clk27), .btn_s1(1'b0), .btn_s2(1'b0),
        .uart_rx(uart_rx), .uart_tx(uart_tx), .led(led),
        .tmds_clk_p(tmds_clk_p), .tmds_clk_n(tmds_clk_n), .tmds_d_p(tmds_d_p), .tmds_d_n(tmds_d_n),
        .O_sdram_clk(sd_clk), .O_sdram_cke(sd_cke), .O_sdram_cs_n(sd_cs_n),
        .O_sdram_cas_n(sd_cas_n), .O_sdram_ras_n(sd_ras_n), .O_sdram_wen_n(sd_we_n),
        .O_sdram_dqm(sd_dqm), .O_sdram_addr(sd_addr), .O_sdram_ba(sd_ba), .IO_sdram_dq(sd_dq)
    );

    sdram_model sdram (
        .clk(sd_clk), .cke(sd_cke), .cs_n(sd_cs_n), .ras_n(sd_ras_n), .cas_n(sd_cas_n),
        .we_n(sd_we_n), .ba(sd_ba), .addr(sd_addr), .dqm(sd_dqm), .dq(sd_dq)
    );

    // ---------------------------------------------------------------- UART
    // The DUT divides 54 MHz by 469: one bit = 469 core clocks.
    localparam BIT = 469 * 18518;

    task send_byte(input [7:0] b);
        integer i;
        begin
            uart_rx = 0; #BIT;
            for (i = 0; i < 8; i = i + 1) begin uart_rx = b[i]; #BIT; end
            uart_rx = 1; #BIT;
        end
    endtask

    task send(input [8*16-1:0] s);
        integer i;
        begin
            for (i = 15; i >= 0; i = i - 1)
                if (s[i*8 +: 8] != 0) send_byte(s[i*8 +: 8]);
        end
    endtask

    // Print what the DUT sends back.
    integer k;
    reg [7:0] rx_ch;
    reg [8*32-1:0] rx_line = 0;
    always @(negedge uart_tx) begin
        #(BIT / 2);
        if (!uart_tx) begin
            for (k = 0; k < 8; k = k + 1) begin #BIT; rx_ch[k] = uart_tx; end
            if (rx_ch == 8'h0a) begin
                $display("uart: %0s", rx_line);
                rx_line = 0;
            end else if (rx_ch != 8'h0d) begin
                rx_line = {rx_line[8*31-1:0], rx_ch};
            end
        end
    end

    // --------------------------------------------------------------- frames
    integer frames = 0;
    always @(posedge tmds_d_p[0] or negedge tmds_d_p[0]) if ($time > 0) frames = frames + 1;

    task wait_frames(input integer n);
        begin
            while (frames < n) #1000000;
        end
    endtask

    // Progress, flushed so it shows through pipes.
    integer ms = 0;
    always begin
        #1000000000;
        ms = ms + 1;
        $display("tb: %0d ms simulated, %0d frames", ms, frames);
        $fflush;
    end

    initial begin
        #2000000;
        send("W 01 0004\r");          // freeze after the first frame, no motion
        send("R 00\r");
        wait_frames(4);               // first frame (~23 ms to render) shown
        send("W 02 3000\r");          // yaw
        send("W 03 0400\r");          // pitch
        send("W 0A 7000\r");          // sun azimuth
        send("W 0B 1800\r");          // sun elevation
        send("W 10 2000\r");          // animation time
        send("W 12 0065\r");          // 1 bounce, floor kr 1/4, 6 spheres
        send("dl");                   // yaw + 0x200, sun azimuth + 0x400
        send("W 01 0000\r");          // run, no auto motion
        send("R 02\r");
        wait_frames(9);               // a frame with all of the above (~33 ms each)
        send("R 13\r");               // cycles per frame / 256
        send("W 12 0061\r");          // floor back to matt
        send("W 01 0020\r");          // 640x480 quality mode
        wait_frames(20);              // two checkerboard frames (~22 ms each) merged
        send("R 13\r");               // quality-mode cycles per frame / 256
        send("t");                    // test pattern
        wait_frames(24);
        $display("tb: sdram reads=%0d writes=%0d refreshes=%0d errors=%0d",
                 sdram.reads, sdram.writes, sdram.refreshes, sdram.errors);
        $display("tb: leds=%b", led);
        $display("tb: dvi errors=%0d", dut.dvi_phy_0.errors);
        $finish;
    end
endmodule
