// Clock generation for the Tang Nano 20K (27 MHz crystal).
//   clk_ser  126.0 MHz  TMDS bit clock (OSER10 FCLK, DDR -> 252 Mbit/s)
//   clk_pix   25.2 MHz  640x480@60 pixel clock (clk_ser / 5)
//   clk_core  54.0 MHz  renderer, SDRAM, UART
// PLL settings from apicula's gowin_pll for GW2AR-18 C8/I7.
module clocks (
    input  wire clk27,
    output wire clk_ser,
    output wire clk_pix,
    output wire clk_core,
    output wire locked
);
    wire lock_ser, lock_core;

    rPLL #(
        .FCLKIN("27"),
        .IDIV_SEL(2),     // PFD 9 MHz
        .FBDIV_SEL(13),   // 126 MHz
        .ODIV_SEL(4)      // VCO 504 MHz
    ) pll_ser (
        .CLKIN(clk27), .CLKOUT(clk_ser), .LOCK(lock_ser),
        .CLKOUTP(), .CLKOUTD(), .CLKOUTD3(),
        .RESET(1'b0), .RESET_P(1'b0), .CLKFB(1'b0),
        .FBDSEL(6'b0), .IDSEL(6'b0), .ODSEL(6'b0),
        .PSDA(4'b0), .DUTYDA(4'b0), .FDLY(4'b0)
    );

    CLKDIV #(.DIV_MODE("5"), .GSREN("false")) div5 (
        .HCLKIN(clk_ser), .RESETN(lock_ser), .CALIB(1'b0), .CLKOUT(clk_pix)
    );

    rPLL #(
        .FCLKIN("27"),
        .IDIV_SEL(0),     // PFD 27 MHz
        .FBDIV_SEL(1),    // 54 MHz
        .ODIV_SEL(16)     // VCO 864 MHz
    ) pll_core (
        .CLKIN(clk27), .CLKOUT(clk_core), .LOCK(lock_core),
        .CLKOUTP(), .CLKOUTD(), .CLKOUTD3(),
        .RESET(1'b0), .RESET_P(1'b0), .CLKFB(1'b0),
        .FBDSEL(6'b0), .IDSEL(6'b0), .ODSEL(6'b0),
        .PSDA(4'b0), .DUTYDA(4'b0), .FDLY(4'b0)
    );

    assign locked = lock_ser & lock_core;
endmodule
