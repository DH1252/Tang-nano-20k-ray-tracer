# Stores the timing settings of timing_options.tcl in the project file, so the
# IDE uses them too, and writes every option the project now uses to
# build/gowin_options.tcl. Run from the repository root through
# scripts/build.sh options.
set here [file dirname [file normalize [info script]]]
open_project $here/tn20k_raytracer/tn20k_raytracer.gprj
source $here/timing_options.tcl
saveto -all_options [file normalize $here/../build/gowin_options.tcl]
puts "all project options: build/gowin_options.tcl"
