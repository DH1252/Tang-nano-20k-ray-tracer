# Timing/speed-optimised implementation settings for Gowin EDA, from
# SUG1220-2.1E (Gowin Software Tcl Commands). Sourced by build.tcl and
# create_project.tcl; in the IDE, open the project and run in the Tcl console:
#   source <repo>/gowin/timing_options.tcl
# then save the project so the settings are stored in it.
#
# Options a given Gowin release does not know are skipped with a message, so
# the same file works on older installs (V1.9.11.03 lacks the synthesis ones).

proc tn20k_option {name value} {
    if {[catch {set_option -$name $value} err]} {
        puts "timing_options: -$name not supported by this Gowin release, skipped"
    }
}

# --- GowinSynthesis -----------------------------------------------------------
tn20k_option opt_goal timing          ;# timing-prioritised optimisation (default auto)
tn20k_option map_option 3             ;# LUT5 mapping, some extra LUTs for timing
                                      ;# (4 = LUT5/LUT6, costs the most LUTs)
tn20k_option netlist_hierarchy 0      ;# flatten: Spade emits many tiny modules, let
                                      ;# synthesis optimise across their boundaries
# -max_fanout is left at its default: synthesis-level replication costs LUTs,
# and place and route replicates the nets that matter (replicate_resources).

# --- Place & Route ------------------------------------------------------------
tn20k_option timing_driven 1          ;# timing-driven place and route
tn20k_option place_option 2           ;# timing-prioritised placement
tn20k_option route_option 1           ;# better routing result, slower compile
tn20k_option replicate_resources 1    ;# duplicate high-fanout drivers
tn20k_option retiming_resource all    ;# retime logic around DSP and BSRAM
tn20k_option clock_route_order 1      ;# route clocks fastest first
tn20k_option correct_hold_violation 1 ;# fix hold violations while routing
tn20k_option ireg_in_iob 1            ;# keep SDRAM/DVI I/O registers in the IOBs
tn20k_option oreg_in_iob 1
tn20k_option ioreg_in_iob 1
