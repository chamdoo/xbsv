source board.tcl
source $xbsvdir/scripts/xbsv-synth-ip.tcl

xbsv_synth_ip aurora_64b66b 9.2 aurora_64b66b_0 [list CONFIG.interface_mode {Framing} CONFIG.C_GT_LOC_5 {1} CONFIG.C_GT_LOC_1 {X}]
