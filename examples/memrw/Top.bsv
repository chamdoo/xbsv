// bsv libraries
import SpecialFIFOs::*;
import Vector::*;
import StmtFSM::*;
import FIFO::*;

// portz libraries
import Directory::*;
import CtrlMux::*;
import Portal::*;
import Leds::*;
import PortalMemory::*;
import MemTypes::*;
import MemServer::*;

// generated by tool
import MemrwRequestWrapper::*;
import DmaConfigWrapper::*;
import MemrwIndicationProxy::*;
import DmaIndicationProxy::*;

// defined by user
import Memrw::*;

typedef enum {MemrwIndication, MemrwRequest, DmaIndication, DmaConfig} IfcNames deriving (Eq,Bits);

module mkPortalTop(StdPortalDmaTop#(PhysAddrWidth));

   MemrwIndicationProxy memrwIndicationProxy <- mkMemrwIndicationProxy(MemrwIndication);
   Memrw memrw <- mkMemrw(memrwIndicationProxy.ifc);
   MemrwRequestWrapper memrwRequestWrapper <- mkMemrwRequestWrapper(MemrwRequest,memrw.request);
   
   DmaIndicationProxy dmaIndicationProxy <- mkDmaIndicationProxy(DmaIndication);
   Vector#(1,  ObjectReadClient#(64))   readClients = cons(memrw.dmaReadClient, nil);
   Vector#(1, ObjectWriteClient#(64)) writeClients = cons(memrw.dmaWriteClient, nil);
   MemServer#(PhysAddrWidth, 64, 1)   dma <- mkMemServer(dmaIndicationProxy.ifc, readClients, writeClients);
   DmaConfigWrapper dmaRequestWrapper <- mkDmaConfigWrapper(DmaConfig,dma.request);
   
   Vector#(4,StdPortal) portals;
   portals[0] = memrwRequestWrapper.portalIfc;
   portals[1] = memrwIndicationProxy.portalIfc; 
   portals[2] = dmaRequestWrapper.portalIfc;
   portals[3] = dmaIndicationProxy.portalIfc; 
   
   StdDirectory dir <- mkStdDirectory(portals);
   let ctrl_mux <- mkSlaveMux(dir,portals);
   
   interface interrupt = getInterruptVector(portals);
   interface slave = ctrl_mux;
   interface masters = dma.masters;
   interface leds = default_leds;
endmodule


