// Captures the SDRAM data bus on the falling edge of the controller clock,
// which is the rising edge of the (inverted) SDRAM clock: the edge on which
// CAS-latency-2 read data is centred. A rising-edge register then hands it to
// the controller half a cycle later. See src/sdram.spade for the latency.
module dq_capture (
    input  wire        clk,
    input  wire [31:0] d,
    output reg  [31:0] q
);
    reg [31:0] q_neg;
    always @(negedge clk) q_neg <= d;
    always @(posedge clk) q <= q_neg;
endmodule
