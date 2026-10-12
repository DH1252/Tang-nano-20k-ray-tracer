// Behavioural model of the GW2AR-18's embedded SDR SDRAM (2M x 32, 4 banks,
// 2048 rows, 256 columns) for system simulation.
//
// It models CAS latency 2 (data for a READ on edge n is on the bus from edge
// n+1 until edge n+2, where the controller samples it), so a read-capture
// latency that is off by an edge shows up as wrong pixels. It is zero-delay
// for simulation speed; the real tAC/tOH window is discussed in
// src/sdram.spade. It also checks the command protocol and timing.
`timescale 1ps/1ps
module sdram_model (
    input  wire        clk,
    input  wire        cke,
    input  wire        cs_n,
    input  wire        ras_n,
    input  wire        cas_n,
    input  wire        we_n,
    input  wire [1:0]  ba,
    input  wire [10:0] addr,
    input  wire [3:0]  dqm,
    inout  wire [31:0] dq
);
    localparam T_RCD = 15000, T_RP = 15000, T_RFC = 60000, T_RAS = 42000, T_REFI = 15625000;

    reg [31:0] mem [0:(1 << 21) - 1];   // bank(2) x row(11) x col(8)
    reg [31:0] dq_val = 0;
    reg        dq_en = 0;
    assign dq = dq_en ? dq_val : 32'bz;

    reg        row_open = 0;
    reg [10:0] open_row;
    reg [1:0]  open_bank;
    reg        mode_set = 0;
    realtime   t_act = 0, t_pre = -1.0e9, t_ref = -1.0e9, t_last_ref = 0;
    integer    errors = 0, refreshes = 0, reads = 0, writes = 0;

    // CL = 2: a READ at edge n drives data from n+1 + tAC to n+2 + tOH, so the
    // controller can sample it on edge n+2.
    reg        rv0 = 0;
    reg [31:0] rd0;

    integer i;
    initial for (i = 0; i < (1 << 21); i = i + 1) mem[i] = 32'h0;

    task fail(input [8*80-1:0] msg);
        begin
            if (errors < 20) $display("sdram: %0t ps: %0s", $time, msg);
            errors = errors + 1;
        end
    endtask

    always @(posedge clk) begin
        // Output side: drive the data for the READ issued on the previous edge.
        dq_en  <= rv0;
        dq_val <= rd0;
        rv0 <= 0;

        if (cke && !cs_n) begin
            case ({ras_n, cas_n, we_n})
                3'b011: begin // ACTIVATE
                    if (!mode_set) fail("ACTIVATE before mode register set");
                    if (row_open) fail("ACTIVATE with a row already open");
                    if ($realtime - t_pre < T_RP) fail("tRP violated");
                    if ($realtime - t_ref < T_RFC) fail("tRFC violated");
                    row_open = 1; open_row = addr; open_bank = ba; t_act = $realtime;
                end
                3'b101: begin // READ
                    if (!row_open) fail("READ with no open row");
                    if ($realtime - t_act < T_RCD) fail("tRCD violated (read)");
                    if (addr[10]) fail("unexpected auto-precharge");
                    if (ba != open_bank) fail("READ to a bank without the open row");
                    rv0 <= 1; rd0 <= mem[{open_bank, open_row, addr[7:0]}];
                    reads = reads + 1;
                end
                3'b100: begin // WRITE
                    if (!row_open) fail("WRITE with no open row");
                    if ($realtime - t_act < T_RCD) fail("tRCD violated (write)");
                    if (dqm != 0) fail("unexpected DQM");
                    if (^dq === 1'bx || dq_en) fail("WRITE data undefined or bus conflict");
                    if (ba != open_bank) fail("WRITE to a bank without the open row");
                    mem[{open_bank, open_row, addr[7:0]}] = dq;
                    writes = writes + 1;
                end
                3'b010: begin // PRECHARGE
                    if (row_open && $realtime - t_act < T_RAS) fail("tRAS violated");
                    if (row_open && !addr[10] && ba != open_bank) fail("PRECHARGE of the wrong bank");
                    row_open = 0; t_pre = $realtime;
                end
                3'b001: begin // AUTO REFRESH
                    if (row_open) fail("REFRESH with a row open");
                    if ($realtime - t_pre < T_RP) fail("tRP violated before refresh");
                    if (mode_set && $realtime - t_last_ref > T_REFI) fail("refresh interval exceeded");
                    t_ref = $realtime; t_last_ref = $realtime;
                    refreshes = refreshes + 1;
                end
                3'b000: begin // LOAD MODE REGISTER
                    if (row_open) fail("MRS with a row open");
                    if (addr != 11'h020) fail("unexpected mode register value");
                    if (refreshes < 2) fail("MRS before two refreshes");
                    mode_set = 1;
                end
                default: ;
            endcase
        end
    end
endmodule
