// Checks rtl/gowin/clocks.v against Gowin's primitive simulation models:
// measures each output frequency once the PLLs report lock.
// Run: sim/check_clocks.sh  (needs a Gowin install for prim_sim.v)
`timescale 1ps/1ps
module tb_clocks;
    reg clk27 = 0;
    always #18519 clk27 = ~clk27;   // 27 MHz
    wire clk_ser, clk_pix, clk_core, locked;
    GSR GSR (.GSRI(1'b1));          // Gowin models reference a global GSR instance
    clocks dut (.clk27(clk27), .clk_ser(clk_ser), .clk_pix(clk_pix), .clk_core(clk_core), .locked(locked));

    task measure(input integer which, input [8*8-1:0] name, input real want_mhz);
        realtime t0, t1;
        integer n;
        real mhz;
        begin
            n = 0;
            case (which)
                0: begin @(posedge clk_ser);  t0 = $realtime; repeat (1000) @(posedge clk_ser);  end
                1: begin @(posedge clk_pix);  t0 = $realtime; repeat (1000) @(posedge clk_pix);  end
                2: begin @(posedge clk_core); t0 = $realtime; repeat (1000) @(posedge clk_core); end
                3: begin @(posedge dut.clk_42); t0 = $realtime; repeat (1000) @(posedge dut.clk_42); end
            endcase
            t1 = $realtime;
            mhz = 1.0e6 * 1000.0 / (t1 - t0);
            if (mhz > want_mhz * 0.999 && mhz < want_mhz * 1.001)
                $display("ok   %0s %0.3f MHz", name, mhz);
            else
                $display("FAIL %0s %0.3f MHz (want %0.3f)", name, mhz, want_mhz);
        end
    endtask

    initial begin
        wait (locked === 1'b1);
        $display("locked at %0t ps", $time);
        #1000000;
        measure(0, "clk_ser", 126.0);
        measure(1, "clk_pix", 25.2);
        measure(3, "clk_42", 42.0);
        measure(2, "clk_core", 75.0);
        $finish;
    end
    initial begin #2000000000; $display("FAIL timeout, locked=%b", locked); $finish; end
endmodule
