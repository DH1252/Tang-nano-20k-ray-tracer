// Clock generation for the Tang Nano 20K (27 MHz crystal).
//   clk_ser  126.0 MHz  TMDS bit clock (OSER10 FCLK, DDR -> 252 Mbit/s)
//   clk_pix   25.2 MHz  640x480@60 pixel clock (clk_ser / 5)
//   clk_core  54.0 MHz  renderer, SDRAM, UART
//
// Pin 4 (the 27 MHz crystal) is LPLL1_T_IN, the dedicated input of one PLL
// only. So the video PLL takes the crystal, and the core PLL is cascaded from
// the video PLL's CLKOUTD3 (126 / 3 = 42 MHz) over the clock network, rather
// than reaching pin 4 through general routing (Gowin warning PR1014).
// PLL dividers from apicula's gowin_pll; the other parameters are the values
// Gowin's IP generator emits for a fixed-frequency rPLL on the GW2AR-18C.
module clocks (
    input  wire clk27,
    output wire clk_ser,
    output wire clk_pix,
    output wire clk_core,
    output wire locked
);
    wire lock_ser, lock_core;
    wire clk_42;   // pll_ser CLKOUTD3, reference for pll_core

    rPLL #(
        .FCLKIN("27"),
        .DEVICE("GW2AR-18C"),
        .DYN_IDIV_SEL("false"), .DYN_FBDIV_SEL("false"), .DYN_ODIV_SEL("false"),
        .PSDA_SEL("0000"), .DYN_DA_EN("true"), .DUTYDA_SEL("1000"),
        .CLKOUT_FT_DIR(1'b1), .CLKOUTP_FT_DIR(1'b1), .CLKOUT_DLY_STEP(0), .CLKOUTP_DLY_STEP(0),
        .CLKFB_SEL("internal"), .CLKOUT_BYPASS("false"), .CLKOUTP_BYPASS("false"),
        .CLKOUTD_BYPASS("false"), .DYN_SDIV_SEL(2), .CLKOUTD_SRC("CLKOUT"), .CLKOUTD3_SRC("CLKOUT"),
        .IDIV_SEL(2),     // PFD 9 MHz
        .FBDIV_SEL(13),   // 126 MHz
        .ODIV_SEL(4)      // VCO 504 MHz
    ) pll_ser (
        .CLKIN(clk27), .CLKOUT(clk_ser), .LOCK(lock_ser),
        .CLKOUTP(), .CLKOUTD(), .CLKOUTD3(clk_42),
        .RESET(1'b0), .RESET_P(1'b0), .CLKFB(1'b0),
        .FBDSEL(6'b0), .IDSEL(6'b0), .ODSEL(6'b0),
        .PSDA(4'b0), .DUTYDA(4'b0), .FDLY(4'b0)
    );

    CLKDIV #(.DIV_MODE("5"), .GSREN("false")) div5 (
        .HCLKIN(clk_ser), .RESETN(lock_ser), .CALIB(1'b0), .CLKOUT(clk_pix)
    );

    rPLL #(
        .FCLKIN("42"),
        .DEVICE("GW2AR-18C"),
        .DYN_IDIV_SEL("false"), .DYN_FBDIV_SEL("false"), .DYN_ODIV_SEL("false"),
        .PSDA_SEL("0000"), .DYN_DA_EN("true"), .DUTYDA_SEL("1000"),
        .CLKOUT_FT_DIR(1'b1), .CLKOUTP_FT_DIR(1'b1), .CLKOUT_DLY_STEP(0), .CLKOUTP_DLY_STEP(0),
        .CLKFB_SEL("internal"), .CLKOUT_BYPASS("false"), .CLKOUTP_BYPASS("false"),
        .CLKOUTD_BYPASS("false"), .DYN_SDIV_SEL(2), .CLKOUTD_SRC("CLKOUT"), .CLKOUTD3_SRC("CLKOUT"),
        .IDIV_SEL(6),     // PFD 6 MHz
        .FBDIV_SEL(8),    // 42 * 9 / 7 = 54 MHz
        .ODIV_SEL(16)     // VCO 864 MHz
    ) pll_core (
        .CLKIN(clk_42), .CLKOUT(clk_core), .LOCK(lock_core),
        .CLKOUTP(), .CLKOUTD(), .CLKOUTD3(),
        // held in reset until its reference (pll_ser) is locked
        .RESET(~lock_ser), .RESET_P(1'b0), .CLKFB(1'b0),
        .FBDSEL(6'b0), .IDSEL(6'b0), .ODSEL(6'b0),
        .PSDA(4'b0), .DUTYDA(4'b0), .FDLY(4'b0)
    );

    assign locked = lock_ser & lock_core;
endmodule
