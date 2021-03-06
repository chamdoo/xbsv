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
import MemlatencyRequestWrapper::*;
import DmaConfigWrapper::*;
import MemlatencyIndicationProxy::*;
import DmaIndicationProxy::*;

// defined by user
import Memlatency::*;

typedef enum {MemlatencyIndication, MemlatencyRequest, DmaIndication, DmaConfig} IfcNames deriving (Eq,Bits);

module mkPortalTop(StdPortalDmaTop#(PhysAddrWidth));

   MemlatencyIndicationProxy memlatencyIndicationProxy <- mkMemlatencyIndicationProxy(MemlatencyIndication);
   Memlatency memlatency <- mkMemlatency(memlatencyIndicationProxy.ifc);
   MemlatencyRequestWrapper memlatencyRequestWrapper <- mkMemlatencyRequestWrapper(MemlatencyRequest,memlatency.request);
   
   DmaIndicationProxy dmaIndicationProxy <- mkDmaIndicationProxy(DmaIndication);
   Vector#(1,  ObjectReadClient#(64))   readClients = cons(memlatency.dmaReadClient, nil);
   Vector#(1, ObjectWriteClient#(64)) writeClients = cons(memlatency.dmaWriteClient, nil);
   MemServer#(PhysAddrWidth, 64, 1)   dma <- mkMemServer(dmaIndicationProxy.ifc, readClients, writeClients);
   DmaConfigWrapper dmaRequestWrapper <- mkDmaConfigWrapper(DmaConfig,dma.request);
   
   Vector#(4,StdPortal) portals;
   portals[0] = memlatencyRequestWrapper.portalIfc;
   portals[1] = memlatencyIndicationProxy.portalIfc; 
   portals[2] = dmaRequestWrapper.portalIfc;
   portals[3] = dmaIndicationProxy.portalIfc; 
   
   StdDirectory dir <- mkStdDirectory(portals);
   let ctrl_mux <- mkSlaveMux(dir,portals);
   
   interface Empty pins; endinterface
   interface interrupt = getInterruptVector(portals);
   interface slave = ctrl_mux;
   interface masters = dma.masters;
   interface leds = default_leds;
endmodule


