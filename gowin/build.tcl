# Command-line build of the Gowin EDA project (the same one the IDE opens).
# Run from the repository root through scripts/build.sh.
set here [file dirname [file normalize [info script]]]
open_project $here/tn20k_raytracer/tn20k_raytracer.gprj
source $here/timing_options.tcl
run all
