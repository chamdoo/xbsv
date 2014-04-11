// Copyright (c) 2013 Quanta Research Cambridge, Inc.

// Permission is hereby granted, free of charge, to any person
// obtaining a copy of this software and associated documentation
// files (the "Software"), to deal in the Software without
// restriction, including without limitation the rights to use, copy,
// modify, merge, publish, distribute, sublicense, and/or sell copies
// of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:

// The above copyright notice and this permission notice shall be
// included in all copies or substantial portions of the Software.

// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
// EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
// MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
// NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
// BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
// ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
// CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

// BSV Libraries
import FIFO::*;
import GetPut::*;
import ClientServer::*;

// XBSV Libraries
import AxiMasterSlave::*;
import Dma::*;
import PortalMemory::*;


module mkAxiDmaSlave#(MemSlave#(addrWidth,dataWidth) slave) (Axi3Slave#(addrWidth,dataWidth,12));
   interface Put req_ar;
      method Action put((Axi3ReadRequest#(addrWidth, 12)) req);
	 slave.read_server.readReq.put(MemRequest{addr:req.address, burstLen:extend(req.len+1),  tag:truncate(req.id)});
      endmethod
   endinterface
   interface Get resp_read;
      method ActionValue#(Axi3ReadResponse#(dataWidth, 12)) get;
	 let resp <- slave.read_server.readData.get;
	 return Axi3ReadResponse{data:resp.data, resp:0, last:1, id:extend(resp.tag)};
      endmethod
   endinterface
   interface Put req_aw;
      method Action put(Axi3WriteRequest#(addrWidth, 12) req);
	 slave.write_server.writeReq.put(MemRequest{addr:req.address, burstLen:extend(req.len+1), tag:truncate(req.id)});
      endmethod
   endinterface
   interface Put resp_write;
      method Action put(Axi3WriteData#(dataWidth, 12) resp);
	 slave.write_server.writeData.put(MemData{data:resp.data, tag:truncate(resp.id)});
      endmethod
   endinterface
   interface Get resp_b;
      method ActionValue#(Axi3WriteResponse#(12)) get;
	 let rv <- slave.write_server.writeDone.get;
	 return Axi3WriteResponse{resp:0, id:extend(rv)};
      endmethod
   endinterface
endmodule

module mkAxiDmaMaster#(MemMaster#(addrWidth,dataWidth) master) (Axi3Master#(addrWidth,dataWidth,6))
   
   provisos(Div#(dataWidth,8,dataWidthBytes),
	    Mul#(dataWidthBytes,8,dataWidth),
	    Log#(dataWidthBytes,beatShift));

   Reg#(Bit#(8))  burstReg <- mkReg(0);
   FIFO#(Bit#(8)) reqs <- mkSizedFIFO(32);
   
   let beat_shift = fromInteger(valueOf(beatShift));

   interface Get req_aw;
      method ActionValue#(Axi3WriteRequest#(addrWidth,6)) get();
	 let req <- master.write_client.writeReq.get;
	 reqs.enq(req.burstLen);
	 return Axi3WriteRequest{address:req.addr, len:truncate((req.burstLen>>beat_shift)-1), id:req.tag, size: axiBusSize(valueOf(dataWidth)), burst: 1, prot: 0, cache: 3, lock:0, qos:0};
      endmethod
   endinterface
   interface Get resp_write;
      method ActionValue#(Axi3WriteData#(dataWidth,6)) get();
	 let tagdata <- master.write_client.writeData.get();
	 let burstLen = burstReg;
	 if (burstLen == 0) begin
	    burstLen = reqs.first >> beat_shift;
	    reqs.deq;
	 end
	 burstReg <= burstLen-1;
	 Bit#(1) last = burstLen == 1 ? 1'b1 : 1'b0;
	 return Axi3WriteData { data: tagdata.data, byteEnable: maxBound, last: last, id: tagdata.tag };
      endmethod
   endinterface
   interface Put resp_b;
      method Action put(Axi3WriteResponse#(6) resp);
	 master.write_client.writeDone.put(resp.id);
      endmethod
   endinterface
   interface Get req_ar;
      method ActionValue#(Axi3ReadRequest#(addrWidth,6)) get();
	 let req <- master.read_client.readReq.get;
	 //$display("req_ar %h", req.tag);
	 return Axi3ReadRequest{address:req.addr, len:truncate((req.burstLen>>beat_shift)-1), id:req.tag, size: axiBusSize(valueOf(dataWidth)), burst: 1, prot: 0, cache: 3, lock:0, qos:0};
      endmethod
   endinterface
   interface Put resp_read;
      method Action put(Axi3ReadResponse#(dataWidth,6) response);
	 //$display("resp_read %h %h", response.data, response.id);
	 master.read_client.readData.put(MemData { data: response.data, tag: response.id});
      endmethod
   endinterface

endmodule

