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
        puts "timing_options: SKIPPED -$name (not supported by this Gowin release)"
    } else {
        puts "timing_options: set -$name $value"
    }
}

# The design fills about 70 % of the logic, so these favour routability: with
# the timing-first algorithms (place_option 2, route_option 1, map_option 3,
# resource replication, retiming everywhere) place and route left thousands
# of nets unrouted (PR0004). The core still has margin at 75 MHz without them.

# --- GowinSynthesis -----------------------------------------------------------
tn20k_option opt_goal timing          ;# timing-prioritised optimisation (default auto)
tn20k_option map_option 0             ;# default LUT mapping (3 and 4 spend extra LUTs)
tn20k_option netlist_hierarchy 0      ;# flatten: Spade emits many tiny modules, let
                                      ;# synthesis optimise across their boundaries

# --- Place & Route ------------------------------------------------------------
tn20k_option timing_driven 1          ;# timing-driven place and route
tn20k_option place_option 1           ;# placement algorithm 1: routability priority
                                      ;# (2 is timing priority)
tn20k_option route_option 0           ;# default router: routes around congestion
                                      ;# (1 routes by timing alone)
tn20k_option replicate_resources 0    ;# no duplicated drivers (more cells to route)
# -retiming_resource is no longer set (it was `all`: register moves around DSP
# and BSRAM); a project that stored it keeps it until it is cleared in the IDE.
tn20k_option clock_route_order 1      ;# route clocks fastest first
tn20k_option correct_hold_violation 1 ;# fix hold violations while routing
tn20k_option ireg_in_iob 1            ;# keep SDRAM/DVI I/O registers in the IOBs
tn20k_option oreg_in_iob 1
tn20k_option ioreg_in_iob 1
