source "board.tcl"
source "$xbsvdir/scripts/xbsv-synth-ip.tcl"

if $needspcie {
    set pcieversion {3.0}
    set maxlinkwidth {X8}
    if {$boardname == {zc706}} {
	set maxlinkwidth {X4}
    }
    if {$boardname == {ac701}} {
	set maxlinkwidth {X4}
    }
    if {[version -short] == "2013.2"} {
	set pcieversion {2.1}
    }
    xbsv_synth_ip pcie_7x $pcieversion pcie_7x_0 [list 				CONFIG.mode_selection {Advanced} 				CONFIG.ASPM_Optionality {true} 				CONFIG.Buf_Opt_BMA {true} 				CONFIG.Bar0_64bit {true} 				CONFIG.Bar0_Size {16} 				CONFIG.Bar0_Scale {Kilobytes} 				CONFIG.Bar2_64bit {true} 				CONFIG.Bar2_Enabled {true} 				CONFIG.Bar2_Scale {Megabytes} 				CONFIG.Bar2_Size {1} 				CONFIG.Base_Class_Menu {Memory_controller} 				CONFIG.Device_ID {c100} 				CONFIG.IntX_Generation {false} 				CONFIG.MSI_Enabled {false} 				CONFIG.MSIx_Enabled {true} 				CONFIG.MSIx_PBA_Offset {1f0} 				CONFIG.MSIx_Table_Offset {200} 				CONFIG.MSIx_Table_Size {10} 				CONFIG.Maximum_Link_Width $maxlinkwidth 				CONFIG.Subsystem_ID {a705} 				CONFIG.Subsystem_Vendor_ID {1be7} 				CONFIG.Use_Class_Code_Lookup_Assistant {false} 				CONFIG.Vendor_ID {1be7} 			       ]
# Description of MSIx_Table_Offset is in:
# Xilinx/Vivado/2013.2/data/ip/xilinx/pcie_7x_v2_1/xgui/pcie_7x_v2_1.tcl
# (it is byteoffset/8, expressed in hex)
}
