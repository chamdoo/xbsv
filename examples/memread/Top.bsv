// bsv libraries
import SpecialFIFOs::*;
import Vector::*;
import StmtFSM::*;
import FIFO::*;


// portz libraries
import AxiMasterSlave::*;
import Directory::*;
import CtrlMux::*;
import Portal::*;
import Leds::*;
import PortalMemory::*;
import AxiRDMA::*;
import BsimRDMA::*;
import PortalMemory::*;
import PortalRMemory::*;

// generated by tool
import MemreadRequestWrapper::*;
import DMARequestWrapper::*;
import MemreadIndicationProxy::*;
import DMAIndicationProxy::*;

// defined by user
import Memread::*;

module mkPortalDmaTop(PortalDmaTop);

   DMAIndicationProxy dmaIndicationProxy <- mkDMAIndicationProxy(9);

   MemreadIndicationProxy memreadIndicationProxy <- mkMemreadIndicationProxy(7);
   Memread memread <- mkMemread(memreadIndicationProxy.ifc);
   MemreadRequestWrapper memreadRequestWrapper <- mkMemreadRequestWrapper(1008,memread.request);

   Vector#(1, DMAReadClient#(64)) clients = cons(memread.dmaClient, nil);
`ifdef BSIM
   BsimDMAServer#(64)  dma <- mkBsimDMAServer(dmaIndicationProxy.ifc, clients, nil);
`else
   Integer             numRequests = 2;
   AxiDMAServer#(64,8) dma <- mkAxiDMAServer(dmaIndicationProxy.ifc, numRequests, clients, nil);
`endif

   DMARequestWrapper dmaRequestWrapper <- mkDMARequestWrapper(1005,dma.request);

   Vector#(4,StdPortal) portals;
   portals[0] = memreadRequestWrapper.portalIfc;
   portals[1] = memreadIndicationProxy.portalIfc; 
   portals[2] = dmaRequestWrapper.portalIfc;
   portals[3] = dmaIndicationProxy.portalIfc; 
   
   Directory dir <- mkDirectory(portals);
   Vector#(1,StdPortal) directories;
   directories[0] = dir.portalIfc;
   
   // when constructing ctrl and interrupt muxes, directories must be the first argument
   let ctrl_mux <- mkAxiSlaveMux(directories,portals);
   let interrupt_mux <- mkInterruptMux(portals);
   
   interface ReadOnly interrupt = interrupt_mux;
   interface StdAxi3Slave ctrl = ctrl_mux;
`ifndef BSIM
   interface StdAxi3Client m_axi = dma.m_axi;
`endif
endmodule : mkPortalDmaTop

module mkZynqTop(PortalDmaTop);
   let portalTop <- mkPortalDmaTop();
   return portalTop;
endmodule : mkZynqTop

import "BDPI" function Action      initPortal(Bit#(32) d);
import "BDPI" function Bool                    writeReq();
import "BDPI" function ActionValue#(Bit#(32)) writeAddr();
import "BDPI" function ActionValue#(Bit#(32)) writeData();
import "BDPI" function Bool                     readReq();
import "BDPI" function ActionValue#(Bit#(32))  readAddr();
import "BDPI" function Action        readData(Bit#(32) d);


module mkBsimTop();
   PortalDmaTop top <- mkPortalDmaTop;
   let wf <- mkPipelineFIFO;
   let init_seq = (action 
		      initPortal(0);
		      initPortal(1);
		      initPortal(2);
		      initPortal(3);
		      initPortal(4);
                   endaction);
   let init_fsm <- mkOnce(init_seq);
   rule init_rule;
      init_fsm.start;
   endrule
   rule wrReq (writeReq());
      let wa <- writeAddr;
      let wd <- writeData;
      top.ctrl.write.writeAddr(wa,0,0,0,0,0,0);
      wf.enq(wd);
   endrule
   rule wrData;
      wf.deq;
      top.ctrl.write.writeData(wf.first,0,0,0);
   endrule
   rule rdReq (readReq());
      let ra <- readAddr;
      top.ctrl.read.readAddr(ra,0,0,0,0,0,0);
   endrule
   rule rdResp;
      let rd <- top.ctrl.read.readData;
      readData(rd);
   endrule
endmodule