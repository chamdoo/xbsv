##
## Copyright (C) 2012-2013 Nokia, Inc
##
import os
import math
import re

import syntax
import AST
import string
import util

preambleTemplate='''
import FIFO::*;
import FIFOF::*;
import GetPut::*;
import Connectable::*;
import Clocks::*;
import Adapter::*;
import AxiMasterSlave::*;
import AxiClientServer::*;
import HDMI::*;
import Zynq::*;
import Imageon::*;
import Vector::*;
import SpecialFIFOs::*;
import AxiDMA::*;
%(extraImports)s

'''

exposedInterfaces = ['HDMI', 'LEDS', 'ImageonVita', 'FmcImageonInterface']

bsimTopTemplate='''
import StmtFSM::*;
import AxiMasterSlave::*;
import FIFO::*;
import SpecialFIFOs::*;
import %(Base)sWrapper::*;


import "BDPI" function Action      initPortal(Bit#(32) d);

import "BDPI" function Bool                    writeReq();
import "BDPI" function ActionValue#(Bit#(32)) writeAddr();
import "BDPI" function ActionValue#(Bit#(32)) writeData();

import "BDPI" function Bool                     readReq();
import "BDPI" function ActionValue#(Bit#(32))  readAddr();
import "BDPI" function Action        readData(Bit#(32) d);


module mkBsimTop();
    %(Base)sWrapper dut <- mk%(Base)sWrapper;
    let wf <- mkPipelineFIFO;
    let init_seq = (action 
                        %(initBsimPortals)s
                    endaction);
    let init_fsm <- mkOnce(init_seq);
    rule init_rule;
        init_fsm.start;
    endrule
    rule wrReq (writeReq());
        let wa <- writeAddr;
        let wd <- writeData;
        dut.ctrl.write.writeAddr(wa,0,0,0,0,0,0);
        wf.enq(wd);
    endrule
    rule wrData;
        wf.deq;
        dut.ctrl.write.writeData(wf.first,0,0);
    endrule
    rule rdReq (readReq());
        let ra <- readAddr;
        dut.ctrl.read.readAddr(ra,0,0,0,0,0,0);
    endrule
    rule rdResp;
        let rd <- dut.ctrl.read.readData;
        readData(rd);
    endrule
endmodule
'''

topInterfaceTemplate='''
interface %(Base)sWrapper;
    interface Axi3Slave#(32,32,4,12) ctrl;
    interface Vector#(%(numPortals)s,ReadOnly#(Bit#(1))) interrupts;
%(axiSlaveDeclarations)s
%(axiMasterDeclarations)s
%(exposedInterfaceDeclarations)s
endinterface
'''

requestWrapperInterfaceTemplate='''
%(requestElements)s
interface %(Dut)sWrapper;
%(axiSlaveDeclarations)s
%(axiMasterDeclarations)s
endinterface
'''

requestStructTemplate='''
typedef struct {
%(paramStructDeclarations)s
} %(MethodName)s$Request deriving (Bits);
Bit#(6) %(methodName)s$Offset = %(channelNumber)s;
'''

indicationWrapperInterfaceTemplate='''
%(responseElements)s
interface RequestWrapperCommFIFOs;
    interface FIFO#(Bit#(15)) axiSlaveWriteAddrFifo;
    interface FIFO#(Bit#(15)) axiSlaveReadAddrFifo;
    interface FIFO#(Bit#(32)) axiSlaveWriteDataFifo;
    interface FIFO#(Bit#(32)) axiSlaveReadDataFifo;
endinterface

interface %(Dut)sWrapper;
    interface Axi3Slave#(32,32,4,12) ctrl;
    interface ReadOnly#(Bit#(1)) interrupt;
    interface %(Dut)s indication;
    interface RequestWrapperCommFIFOs rwCommFifos;%(indicationMethodDeclsAug)s
endinterface
'''

responseStructTemplate='''
typedef struct {
%(paramStructDeclarations)s
} %(MethodName)s$Response deriving (Bits);
Bit#(6) %(methodName)s$Offset = %(channelNumber)s;
'''

mkIndicationWrapperTemplate='''

module mk%(Dut)sWrapper(%(Dut)sWrapper);

    // indication-specific state
    Reg#(Bit#(32)) responseFiredCntReg <- mkReg(0);
    Vector#(%(indicationChannelCount)s, PulseWire) responseFiredWires <- replicateM(mkPulseWire);
    Reg#(Bit#(32)) outOfRangeReadCountReg <- mkReg(0);
    Vector#(%(indicationChannelCount)s, PulseWire) readOutstanding <- replicateM(mkPulseWire);
    
    function Bool my_or(Bool a, Bool b) = a || b;
    function Bool read_wire (PulseWire a) = a._read;    
    Reg#(Bool) interruptEnableReg <- mkReg(False);
    let       interruptStatus = fold(my_or, map(read_wire, readOutstanding));
    function Bit#(32) read_wire_cvt (PulseWire a) = a._read ? 32'b1 : 32'b0;
    function Bit#(32) my_add(Bit#(32) a, Bit#(32) b) = a+b;

    // state used to implement Axi Slave interface
    Reg#(Bit#(32)) getWordCount <- mkReg(0);
    Reg#(Bit#(32)) putWordCount <- mkReg(0);
    Reg#(Bit#(15)) axiSlaveReadAddrReg <- mkReg(0);
    Reg#(Bit#(15)) axiSlaveWriteAddrReg <- mkReg(0);
    Reg#(Bit#(12)) axiSlaveReadIdReg <- mkReg(0);
    Reg#(Bit#(12)) axiSlaveWriteIdReg <- mkReg(0);
    FIFO#(Bit#(1)) axiSlaveReadLastFifo <- mkPipelineFIFO;
    FIFO#(Bit#(12)) axiSlaveReadIdFifo <- mkPipelineFIFO;
    Reg#(Bit#(4)) axiSlaveReadBurstCountReg <- mkReg(0);
    Reg#(Bit#(4)) axiSlaveWriteBurstCountReg <- mkReg(0);
    FIFO#(Bit#(2)) axiSlaveBrespFifo <- mkFIFO();
    FIFO#(Bit#(12)) axiSlaveBidFifo <- mkFIFO();

    Vector#(2,FIFO#(Bit#(15))) axiSlaveWriteAddrFifos <- replicateM(mkPipelineFIFO);
    Vector#(2,FIFO#(Bit#(15))) axiSlaveReadAddrFifos <- replicateM(mkPipelineFIFO);
    Vector#(2,FIFO#(Bit#(32))) axiSlaveWriteDataFifos <- replicateM(mkPipelineFIFO);
    Vector#(2,FIFO#(Bit#(32))) axiSlaveReadDataFifos <- replicateM(mkPipelineFIFO);

    Reg#(Bit#(1)) axiSlaveRS <- mkReg(0);
    Reg#(Bit#(1)) axiSlaveWS <- mkReg(0);

    let axiSlaveWriteAddrFifo = axiSlaveWriteAddrFifos[1];
    let axiSlaveReadAddrFifo  = axiSlaveReadAddrFifos[1];
    let axiSlaveWriteDataFifo = axiSlaveWriteDataFifos[1];
    let axiSlaveReadDataFifo  = axiSlaveReadDataFifos[1];

    // count the number of times indication methods are invoked
    rule increment_responseFiredCntReg;
        responseFiredCntReg <= responseFiredCntReg + fold(my_add, map(read_wire_cvt, responseFiredWires));
    endrule
    
    rule writeCtrlReg if (axiSlaveWriteAddrFifo.first[14] == 1);
        axiSlaveWriteAddrFifo.deq;
        axiSlaveWriteDataFifo.deq;
	let addr = axiSlaveWriteAddrFifo.first[13:0];
	let v = axiSlaveWriteDataFifo.first;
	if (addr == 14'h000)
	    noAction; // interruptStatus is read-only
	if (addr == 14'h004)
	    interruptEnableReg <= v[0] == 1'd1;
    endrule

    rule readCtrlReg if (axiSlaveReadAddrFifo.first[14] == 1);

        axiSlaveReadAddrFifo.deq;
	let addr = axiSlaveReadAddrFifo.first[13:0];

	Bit#(32) v = 32'h05a05a0;
	if (addr == 14'h000)
	    v = interruptStatus ? 32'd1 : 32'd0;
	if (addr == 14'h004)
	    v = interruptEnableReg ? 32'd1 : 32'd0;
	if (addr == 14'h008)
	    v = responseFiredCntReg;
	if (addr == 14'h00C)
	    v = 0; // unused
	if (addr == 14'h010)
	    v = (32'h68470000 | extend(axiSlaveReadBurstCountReg));
	if (addr == 14'h014)
	    v = putWordCount;
	if (addr == 14'h018)
	    v = getWordCount;
        if (addr == 14'h01C)
	    v = outOfRangeReadCountReg;
        if (addr >= 14'h020 && addr <= (14'h024 + %(indicationChannelCount)s/4))
	begin
	    v = 0;
	    Bit#(7) baseQueueNumber = addr[9:3] << 5;
	    for (Bit#(7) i = 0; i <= baseQueueNumber+31 && i < %(indicationChannelCount)s; i = i + 1)
	    begin
		Bit#(5) bitPos = truncate(i - baseQueueNumber);
		// drive value based on which HW->SW FIFOs have pending messages
		v[bitPos] = readOutstanding[i] ? 1'd1 : 1'd0; 
	    end
	end
        axiSlaveReadDataFifo.enq(v);
    endrule

%(indicationMethodRules)s

    rule outOfRangeRead if (axiSlaveReadAddrFifo.first[14] == 0 && 
                            axiSlaveReadAddrFifo.first[13:8] >= %(indicationChannelCount)s);
        axiSlaveReadAddrFifo.deq;
        axiSlaveReadDataFifo.enq(0);
        outOfRangeReadCountReg <= outOfRangeReadCountReg+1;
    endrule


    rule axiSlaveReadAddressGenerator if (axiSlaveReadBurstCountReg != 0);
        axiSlaveReadAddrFifos[axiSlaveRS].enq(truncate(axiSlaveReadAddrReg));
        axiSlaveReadAddrReg <= axiSlaveReadAddrReg + 4;
        axiSlaveReadBurstCountReg <= axiSlaveReadBurstCountReg - 1;
        axiSlaveReadLastFifo.enq(axiSlaveReadBurstCountReg == 1 ? 1 : 0);
        axiSlaveReadIdFifo.enq(axiSlaveReadIdReg);
    endrule

    interface RequestWrapperCommFIFOs rwCommFifos;
        interface FIFO axiSlaveWriteAddrFifo = axiSlaveWriteAddrFifos[0];
        interface FIFO axiSlaveReadAddrFifo  = axiSlaveReadAddrFifos[0];
        interface FIFO axiSlaveWriteDataFifo = axiSlaveWriteDataFifos[0];
        interface FIFO axiSlaveReadDataFifo  = axiSlaveReadDataFifos[0];
    endinterface

    interface Axi3Slave ctrl;
        interface Axi3SlaveWrite write;
            method Action writeAddr(Bit#(32) addr, Bit#(4) burstLen, Bit#(3) burstWidth,
                                    Bit#(2) burstType, Bit#(3) burstProt, Bit#(4) burstCache,
				    Bit#(12) awid)
                          if (axiSlaveWriteBurstCountReg == 0);
                 axiSlaveWS <= addr[15];
                 axiSlaveWriteBurstCountReg <= burstLen + 1;
                 axiSlaveWriteAddrReg <= truncate(addr);
		 axiSlaveWriteIdReg <= awid;
            endmethod
            method Action writeData(Bit#(32) v, Bit#(4) byteEnable, Bit#(1) last)
                          if (axiSlaveWriteBurstCountReg > 0);
                let addr = axiSlaveWriteAddrReg;
                axiSlaveWriteAddrReg <= axiSlaveWriteAddrReg + 4;
                axiSlaveWriteBurstCountReg <= axiSlaveWriteBurstCountReg - 1;

                axiSlaveWriteAddrFifos[axiSlaveWS].enq(axiSlaveWriteAddrReg[14:0]);
                axiSlaveWriteDataFifos[axiSlaveWS].enq(v);

                putWordCount <= putWordCount + 1;
                if (last == 1'b1)
                begin
                    axiSlaveBrespFifo.enq(0);
                    axiSlaveBidFifo.enq(axiSlaveWriteIdReg);
                end
            endmethod
            method ActionValue#(Bit#(2)) writeResponse();
                axiSlaveBrespFifo.deq;
                return axiSlaveBrespFifo.first;
            endmethod
            method ActionValue#(Bit#(12)) bid();
                axiSlaveBidFifo.deq;
                return axiSlaveBidFifo.first;
            endmethod
        endinterface
        interface Axi3SlaveRead read;
            method Action readAddr(Bit#(32) addr, Bit#(4) burstLen, Bit#(3) burstWidth,
                                   Bit#(2) burstType, Bit#(3) burstProt, Bit#(4) burstCache, Bit#(12) arid)
                          if (axiSlaveReadBurstCountReg == 0);
                 axiSlaveRS <= addr[15];
                 axiSlaveReadBurstCountReg <= burstLen + 1;
                 axiSlaveReadAddrReg <= truncate(addr);
	    	 axiSlaveReadIdReg <= arid;
            endmethod
            method Bit#(1) last();
                return axiSlaveReadLastFifo.first;
            endmethod
            method Bit#(12) rid();
                return axiSlaveReadIdFifo.first;
            endmethod
            method ActionValue#(Bit#(32)) readData();

                let v = axiSlaveReadDataFifos[axiSlaveRS].first;
                axiSlaveReadDataFifo.deq;
                axiSlaveReadLastFifo.deq;
                axiSlaveReadIdFifo.deq;

                getWordCount <= getWordCount + 1;
                return v;
            endmethod
        endinterface
    endinterface

    interface ReadOnly interrupt;
        method Bit#(1) _read();
            if (interruptEnableReg && interruptStatus)
                return 1'd1;
            else
                return 1'd0;
        endmethod
    endinterface
    interface %(Dut)s indication;
%(indicationMethodsOrig)s
    endinterface
%(indicationMethodsAug)s

endmodule

'''

mkRequestWrapperTemplate='''


module mk%(Dut)sWrapper#(%(Dut)s %(dut)s, %(Indication)sWrapper iw)(%(Dut)sWrapper);

    // request-specific state
    Reg#(Bit#(32)) requestFiredCount <- mkReg(0);
    Reg#(Bit#(32)) overflowCount <- mkReg(0);
    Reg#(Bit#(32)) outOfRangeWriteCount <- mkReg(0);

    let axiSlaveWriteAddrFifo = iw.rwCommFifos.axiSlaveWriteAddrFifo;
    let axiSlaveReadAddrFifo  = iw.rwCommFifos.axiSlaveReadAddrFifo;
    let axiSlaveWriteDataFifo = iw.rwCommFifos.axiSlaveWriteDataFifo;
    let axiSlaveReadDataFifo  = iw.rwCommFifos.axiSlaveReadDataFifo; 


    rule writeCtrlReg if (axiSlaveWriteAddrFifo.first[14] == 1);
        axiSlaveWriteAddrFifo.deq;
        axiSlaveWriteDataFifo.deq;
	let addr = axiSlaveWriteAddrFifo.first[13:0];
	let v = axiSlaveWriteDataFifo.first;
	if (addr == 14'h000)
	    noAction;
	if (addr == 14'h004)
	    noAction;
    endrule

    rule readCtrlReg if (axiSlaveReadAddrFifo.first[14] == 1);
        axiSlaveReadAddrFifo.deq;
	let addr = axiSlaveReadAddrFifo.first[13:0];
	Bit#(32) v = 32'h05a05a0;
	if (addr == 14'h010)
	    v = requestFiredCount;
	if (addr == 14'h01C)
	    v = overflowCount;
	if (addr == 14'h034)
	    v = outOfRangeWriteCount;
        axiSlaveReadDataFifo.enq(v);
    endrule

%(methodRules)s

    rule outOfRangeWrite if (axiSlaveWriteAddrFifo.first[14] == 0 && 
                             axiSlaveWriteAddrFifo.first[13:8] >= %(channelCount)s);
        axiSlaveWriteAddrFifo.deq;
        axiSlaveWriteDataFifo.deq;
        outOfRangeWriteCount <= outOfRangeWriteCount+1;
    endrule
%(axiMasterModules)s
%(axiSlaveImplementations)s
%(axiMasterImplementations)s
endmodule
'''

mkTopTemplate='''
module mk%(Base)sWrapper%(dut_hdmi_clock_param)s(%(Base)sWrapper);
    Reg#(Bit#(TLog#(%(numPortals)s))) axiSlaveWS <- mkReg(0);
    Reg#(Bit#(TLog#(%(numPortals)s))) axiSlaveRS <- mkReg(0); 
%(indicationWrappers)s
%(indicationIfc)s
    %(Dut)s %(dut)s <- mk%(Dut)s(%(dut_hdmi_clock_arg)s indication);
%(axiMasterModules)s
%(requestWrappers)s
    Vector#(%(numPortals)s,Axi3Slave#(32,32,4,12)) ctrls_v;
    Vector#(%(numPortals)s,ReadOnly#(Bit#(1))) interrupts_v;
%(connectIndicationCtrls)s
%(connectIndicationInterrupts)s
    let ctrl_mux <- mkAxiSlaveMux(ctrls_v);
%(axiSlaveImplementations)s
%(axiMasterImplementations)s
%(exposedInterfaceImplementations)s
    interface ctrl = ctrl_mux;
    interface Vector interrupts = interrupts_v;
endmodule
'''

# this used to sit in the requestRuleTemplate, but
# support for impCondOf in bsc is questionable (mdk)
#
# // let success = impCondOf(%(dut)s.%(methodName)s(%(paramsForCall)s));
# // if (success)
# // %(dut)s.%(methodName)s(%(paramsForCall)s);
# // else
# // indication$Aug.putFailed(%(ord)s);


requestRuleTemplate='''
    FromBit32#(%(MethodName)s$Request) %(methodName)s$requestFifo <- mkFromBit32();
    rule axiSlaveWrite$%(methodName)s if (axiSlaveWriteAddrFifo.first[14] == 0 && axiSlaveWriteAddrFifo.first[13:8] == %(methodName)s$Offset);
        axiSlaveWriteAddrFifo.deq;
        axiSlaveWriteDataFifo.deq;
        %(methodName)s$requestFifo.enq(axiSlaveWriteDataFifo.first);
    endrule
    (* descending_urgency = "handle$%(methodName)s$request, handle$%(methodName)s$requestFailure" *)
    rule handle$%(methodName)s$request;
        let request = %(methodName)s$requestFifo.first;
        %(methodName)s$requestFifo.deq;
        %(dut)s.%(methodName)s(%(paramsForCall)s);
        requestFiredCount <= requestFiredCount+1;
    endrule
    rule handle$%(methodName)s$requestFailure;
        iw.putFailed(%(ord)s);
        %(methodName)s$requestFifo.deq;
        $display("%(methodName)s$requestFailure");
    endrule
'''

indicationRuleTemplate='''
    ToBit32#(%(MethodName)s$Response) %(methodName)s$responseFifo <- mkToBit32();
    rule %(methodName)s$axiSlaveRead if (axiSlaveReadAddrFifo.first[14] == 0 && 
                                         axiSlaveReadAddrFifo.first[13:8] == %(methodName)s$Offset);
        axiSlaveReadAddrFifo.deq;
        %(methodName)s$responseFifo.deq;
        axiSlaveReadDataFifo.enq(%(methodName)s$responseFifo.first);
    endrule
    rule %(methodName)s$axiSlaveReadOutstanding if (%(methodName)s$responseFifo.notEmpty);
        readOutstanding[%(channelNumber)s].send();
    endrule
'''

indicationMethodDeclTemplate='''
    method Action %(methodName)s(%(formals)s);'''

indicationMethodTemplate='''
    method Action %(methodName)s(%(formals)s);
        %(methodName)s$responseFifo.enq(%(MethodName)s$Response {%(structElements)s});
        responseFiredWires[%(channelNumber)s].send();
    endmethod'''


def emitPreamble(f, files):
    extraImports = ['import %s::*;\n' % os.path.splitext(os.path.basename(fn))[0] for fn in files]
    #axiMasterDecarations = ['interface AxiMaster#(64,8) %s;' % axiMaster for axiMaster in axiMasterNames]
    #axiSlaveDecarations = ['interface AxiSlave#(32,4) %s;' % axiSlave for axiSlave in axiSlaveNames]
    f.write(preambleTemplate % {'extraImports' : ''.join(extraImports)})

class ParamMixin:
    def numBitsBSV(self):
        return self.type.numBitsBSV();

class NullMixin:
    def emitBsvImplementation(self, f):
        pass

class TypeMixin:
    def toBsvType(self):
        if len(self.params):
            return '%s#(%s)' % (self.name, self.params[0].numeric())
        else:
            return self.name
    def numBitsBSV(self):
        if (self.name == 'Bit'):
		return self.params[0].numeric()
	sdef = syntax.globalvars[self.name]
	return sum([e.type.numBitsBSV() for e in sdef.elements])


class MethodMixin:
    def emitBsvImplementation(self, f):
        pass
    def substs(self, outerTypeName):
        if self.return_type.name == 'ActionValue':
            rt = self.return_type.params[0].toBsvType()
        else:
            rt = self.return_type.name
        d = { 'dut': util.decapitalize(outerTypeName),
              'Dut': util.capitalize(outerTypeName),
              'methodName': self.name,
              'MethodName': util.capitalize(self.name),
              'channelNumber': self.channelNumber,
              'ord': self.channelNumber,
              'methodReturnType': rt}
        return d

    def collectRequestElement(self, outerTypeName):
        substs = self.substs(outerTypeName)
        paramStructDeclarations = ['    %s %s;' % (p.type.toBsvType(), p.name)
                                   for p in self.params]
        if not self.params:
            paramStructDeclarations = ['    %s %s;' % ('Bit#(32)', 'padding')]

        substs['paramStructDeclarations'] = '\n'.join(paramStructDeclarations)
        return requestStructTemplate % substs

    def collectResponseElement(self, outerTypeName):
        substs = self.substs(outerTypeName)
        paramStructDeclarations = ['    %s %s;' % (p.type.toBsvType(), p.name)
                                   for p in self.params]
        if not self.params:
            paramStructDeclarations = ['    %s %s;' % ('Bit#(32)', 'padding')]
        substs['paramStructDeclarations'] = '\n'.join(paramStructDeclarations)
        return responseStructTemplate % substs

    def collectMethodRule(self, outerTypeName):
        substs = self.substs(outerTypeName)
        if self.return_type.name == 'Action':
            paramsForCall = ['request.%s' % p.name for p in self.params]
            substs['paramsForCall'] = ', '.join(paramsForCall)

            return requestRuleTemplate % substs
        else:
            return None

    def collectIndicationMethodRule(self, outerTypeName):
        substs = self.substs(outerTypeName)
        if self.return_type.name == 'Action':
            paramType = ['%s' % p.type.toBsvType() for p in self.params]
            substs['paramType'] = ', '.join(paramType)
            return indicationRuleTemplate % substs
        else:
            return None

    def collectIndicationMethod(self, outerTypeName):
        substs = self.substs(outerTypeName)
        if self.return_type.name == 'Action':
            formal = ['%s %s' % (p.type.toBsvType(), p.name) for p in self.params]
            substs['formals'] = ', '.join(formal)
            structElements = ['%s: %s' % (p.name, p.name) for p in self.params]
            substs['structElements'] = ', '.join(structElements)
            return indicationMethodTemplate % substs
        else:
            return None

    def collectIndicationMethodDecl(self, outerTypeName):
        substs = self.substs(outerTypeName)
        if self.return_type.name == 'Action':
            formal = ['%s %s' % (p.type.toBsvType(), p.name) for p in self.params]
            substs['formals'] = ', '.join(formal)
            structElements = ['%s: %s' % (p.name, p.name) for p in self.params]
            substs['structElements'] = ', '.join(structElements)
            return indicationMethodDeclTemplate % substs
        else:
            return None

class InterfaceMixin:

    def emitBsimTop(self,f):
        substs = {
		'Base' : self.base ,
		'initBsimPortals' : ''.join(util.intersperse((' '*23,'\n'), ['initPortal(%d);' % j for j in range(len(self.ind.decls))]))
		}
        f.write(bsimTopTemplate % substs);

    def emitBsvImplementationRequestTop(self,f):
        axiMasters = self.collectInterfaceNames('Axi3?Client')
        axiSlaves = self.collectInterfaceNames('AxiSlave')
        hdmiInterfaces = self.collectInterfaceNames('HDMI')
        ledInterfaces = self.collectInterfaceNames('LEDS')
        indicationWrappers = self.collectIndicationWrappers()
        connectIndicationCtrls = self.collectIndicationCtrls()
        connectIndicationInterrupts = self.collectIndicationInterrupts()
        requestWrappers = self.collectRequestWrappers()
        indicationIfc = self.generateIndicationIfc()
        dutName = util.decapitalize(self.name)
        methods = [d for d in self.decls if d.type == 'Method' and d.return_type.name == 'Action']
        buses = {}
        clknames = []
        for busType in exposedInterfaces:
            collected = self.collectInterfaceNames(busType)
            if collected:
                if busType == 'HDMI':
                    clknames.append('hdmi_clk')
            buses[busType] = collected
        # print 'clknames', clknames

        substs = {
            'dut': dutName,
            'Dut': util.capitalize(self.name),
            'base': util.decapitalize(self.base),
            'Base': self.base,
            'axiMasterDeclarations': '\n'.join(['    interface Axi3Master#(%s,%s,%s,%s) %s;' % (params[0].numeric(), params[1].numeric(), params[2].numeric(), params[3].numeric(), axiMaster)
                                                for (axiMaster,t,params) in axiMasters]),
            'axiSlaveDeclarations': '\n'.join(['    interface AxiSlave#(32,4) %s;' % axiSlave
                                               for (axiSlave,t,params) in axiSlaves]),
            'exposedInterfaceDeclarations':
                '\n'.join(['\n'.join(['    interface %s %s;' % (t, util.decapitalize(busname))
                                      for (busname,t,params) in buses[busType]])
                           for busType in exposedInterfaces]),
            'axiMasterModules': '\n'.join(['    Axi3Master#(%s,%s,%s,%s) %sMaster <- mkAxi3Master(%s.%s);'
                                           % (params[0].numeric(), params[1].numeric(), params[2].numeric(), params[3].numeric(), axiMaster,dutName,axiMaster)
                                                   for (axiMaster,t,params) in axiMasters]),
            'axiMasterImplementations': '\n'.join(['    interface Axi3Master %s = %sMaster;' % (axiMaster,axiMaster)
                                                   for (axiMaster,t,params) in axiMasters]),
            'dut_hdmi_clock_param': '#(%s)' % ', '.join(['Clock %s' % name for name in clknames]) if len(clknames) else '',
            'dut_hdmi_clock_arg': ' '.join(['%s,' % name for name in clknames]) if len(clknames) else '',
            'axiSlaveImplementations': '\n'.join(['    interface AxiSlave %s = %s.%s;' % (axiSlave,dutName,axiSlave)
                                                  for (axiSlave,t,params) in axiSlaves]),
            'exposedInterfaceImplementations': '\n'.join(['\n'.join(['    interface %s %s = %s.%s;' % (t, busname, dutName, busname)
                                                                     for (busname,t,params) in buses[busType]])
                                                          for busType in exposedInterfaces]),
            'Indication' : self.ind.name,
            'numPortals' : self.numPortals,
            'indicationWrappers' : ''.join(indicationWrappers),
            'requestWrappers' : ''.join(requestWrappers),
            'indicationIfc' : indicationIfc,
            'connectIndicationCtrls' : connectIndicationCtrls,
            'connectIndicationInterrupts' : connectIndicationInterrupts
            }
        f.write(topInterfaceTemplate % substs)
        f.write(mkTopTemplate % substs)

    def writeTopBsv(self,f):
        assert(self.top and (not self.isIndication))
        self.emitBsvImplementationRequestTop(f)

    def writeBsimTop(self,fname):
        assert(self.top and (not self.isIndication))
	f = util.createDirAndOpen(fname, 'w')
        print 'Writing bsv file ', fname
	self.emitBsimTop(f);
	f.close()

    def collectIndicationInterrupts(self):
        rv = []
        portalNum = 0
        for d in self.ind.decls:
            if d.type == 'Interface':
                rv.append('    interrupts_v[%s] = %sWrapper.interrupt;\n' % (portalNum, d.subinterfacename))
                portalNum = portalNum+1
        return ''.join(rv)

    def collectIndicationCtrls(self):
        rv = []
        portalNum = 0
        for d in self.ind.decls:
            if d.type == 'Interface':
                rv.append('    ctrls_v[%s] = %sWrapper.ctrl;\n' % (portalNum, d.subinterfacename))
                portalNum = portalNum+1
        return ''.join(rv)


    def generateIndicationIfc(self):
        rv = []
        ind_bsv_type = self.ind.interfaceType().toBsvType()
        ind_bsv_name = 'indication'
        rv.append('    %s %s = (interface %s;' % (ind_bsv_type, ind_bsv_name, ind_bsv_type))
        for d in self.ind.decls:
            if d.type == 'Interface':
                bsv_type = d.interfaceType().toBsvType()
                rv.append('\n        interface %s %s = %sWrapper.indication;' % (bsv_type, d.subinterfacename, d.subinterfacename))
        rv.append('\n    endinterface);\n')
        return ''.join(rv)

    def collectRequestWrappers(self):
        rv = []
        for d in self.decls:
            if d.type == 'Interface' and  syntax.globalvars.has_key(d.name):
                bsv_type = d.interfaceType().toBsvType()
                request = '%s.%s' % (util.decapitalize(self.name), util.decapitalize(d.subinterfacename))
                # this is a horrible hack (mdk)
                indication = '%sWrapper' % re.sub('Request', 'Indication', (util.decapitalize(d.subinterfacename)))
                rv.append('    %sWrapper %sWrapper <- mk%sWrapper(%s,%s);\n' % (bsv_type, d.subinterfacename, bsv_type, request, indication))
        return rv
            

    def collectIndicationWrappers(self):
        rv = []
        for d in self.ind.decls:
            if d.type == 'Interface':
                bsv_type = d.interfaceType().toBsvType()
                rv.append('    %sWrapper %sWrapper <- mk%sWrapper();\n' % (bsv_type, d.subinterfacename, bsv_type))
        return rv

    def emitBsvImplementationRequest(self,f):
        # print self.name
        requestElements = self.collectRequestElements(self.name)
        methodRules = self.collectMethodRules(self.name)
        axiMasters = self.collectInterfaceNames('Axi3?Client')
        axiSlaves = self.collectInterfaceNames('AxiSlave')
        hdmiInterfaces = self.collectInterfaceNames('HDMI')
        ledInterfaces = self.collectInterfaceNames('LEDS')
        dutName = util.decapitalize(self.name)
        methods = [d for d in self.decls if d.type == 'Method' and d.return_type.name == 'Action']
        substs = {
            'dut': dutName,
            'Dut': util.capitalize(self.name),
            'requestElements': ''.join(requestElements),
            'methodRules': ''.join(methodRules),
            'channelCount': self.channelCount,
            'writeChannelCount': self.channelCount,
            'axiMasterDeclarations': '\n'.join(['    interface Axi3Master#(%s,%s,%s,%s) %s;' % (params[0].numeric(), params[1].numeric(), params[2].numeric(), params[3].numeric(), axiMaster)
                                                for (axiMaster,t,params) in axiMasters]),
            'axiSlaveDeclarations': '\n'.join(['    interface AxiSlave#(32,4) %s;' % axiSlave
                                               for (axiSlave,t,params) in axiSlaves]),
            'axiMasterModules': '\n'.join(['    Axi3Master#(%s,%s,%s,%s) %sMaster <- mkAxi3Master(%s.%s);'
                                           % (params[0].numeric(), params[1].numeric(), params[2].numeric(), params[3].numeric(), axiMaster,dutName,axiMaster)
                                                   for (axiMaster,t,params) in axiMasters]),
            'axiMasterImplementations': '\n'.join(['    interface Axi3Master %s = %sMaster;' % (axiMaster,axiMaster)
                                                   for (axiMaster,t,params) in axiMasters]),
            'axiSlaveImplementations': '\n'.join(['    interface AxiSlave %s = %s.%s;' % (axiSlave,dutName,axiSlave)
                                                  for (axiSlave,t,params) in axiSlaves]),
            'Indication' : self.ind.name
            }
        f.write(requestWrapperInterfaceTemplate % substs)
        f.write(mkRequestWrapperTemplate % substs)

    def emitBsvImplementationIndication(self,f):

        responseElements = self.collectResponseElements(self.name)
        indicationMethodRules = self.collectIndicationMethodRules(self.name)
        indicationMethodsOrig = self.collectIndicationMethodsOrig(self.name)
        indicationMethodsAug = self.collectIndicationMethodsAug(self.name)
        indicationMethodDeclsOrig = self.collectIndicationMethodDeclsOrig(self.name)
        indicationMethodDeclsAug  = self.collectIndicationMethodDeclsAug(self.name)
        dutName = util.decapitalize(self.name)
        methods = [d for d in self.decls if d.type == 'Method' and d.return_type.name == 'Action']
        substs = {
            'dut': dutName,
            'Dut': util.capitalize(self.name),
            'responseElements': ''.join(responseElements),
            'indicationMethodRules': ''.join(indicationMethodRules),
            'indicationMethodsOrig': ''.join(indicationMethodsOrig),
            'indicationMethodsAug' : ''.join(indicationMethodsAug),
            'indicationMethodDeclsOrig' :''.join(indicationMethodDeclsOrig),
            'indicationMethodDeclsAug' :''.join(indicationMethodDeclsAug),
            'indicationChannelCount': self.channelCount,
            'channelCount': self.channelCount
            }
        f.write(indicationWrapperInterfaceTemplate % substs)
        f.write(mkIndicationWrapperTemplate % substs)
    def emitBsvImplementation(self, f):
        if self.isIndication:
            self.emitBsvImplementationIndication(f)
        else:
            self.emitBsvImplementationRequest(f)

    def collectRequestElements(self, outerTypeName):
        requestElements = []
        for m in self.decls:
            if m.type == 'Method':
                e = m.collectRequestElement(outerTypeName)
                if e:
                    requestElements.append(e)
        return requestElements
    def collectResponseElements(self, outerTypeName):
        responseElements = []
        for m in self.decls:
            if m.type == 'Method':
                e = m.collectResponseElement(outerTypeName)
                if e:
                    responseElements.append(e)
        return responseElements
    def collectMethodRules(self,outerTypeName):
        methodRules = []
        for m in self.decls:
            if m.type == 'Method':
                methodRule = m.collectMethodRule(outerTypeName)
                if methodRule:
                    methodRules.append(methodRule)
        return methodRules
    def collectIndicationMethodRules(self,outerTypeName):
        methodRules = []
        for m in self.decls:
            if m.type == 'Method':
                methodRule = m.collectIndicationMethodRule(outerTypeName)
                if methodRule:
                    methodRules.append(methodRule)
        return methodRules
    def collectIndicationMethodsOrig(self,outerTypeName):
        methods = []
        for m in self.decls:
            if m.type == 'Method' and not m.aug:
                methodRule = m.collectIndicationMethod(outerTypeName)
                if methodRule:
                    methods.append(methodRule)
        return methods
    def collectIndicationMethodsAug(self,outerTypeName):
        methods = []
        for m in self.decls:
            if m.type == 'Method' and m.aug:
                methodRule = m.collectIndicationMethod(outerTypeName)
                if methodRule:
                    methods.append(methodRule)
        return methods
    def collectIndicationMethodDeclsOrig(self,outerTypeName):
        methods = []
        for m in self.decls:
            if m.type == 'Method' and not m.aug:
                methodRule = m.collectIndicationMethodDecl(outerTypeName)
                if methodRule:
                    methods.append(methodRule)
        return methods
    def collectIndicationMethodDeclsAug(self,outerTypeName):
        methods = []
        for m in self.decls:
            if m.type == 'Method' and m.aug:
                methodRule = m.collectIndicationMethodDecl(outerTypeName)
                if methodRule:
                    methods.append(methodRule)
        return methods
    def collectInterfaceNames(self, name):
        interfaceNames = []
        for m in self.decls:
            if m.type == 'Interface':
                #print ("interface name: {%s}" % (m.name)), m
                #print 'name', name, m.name
                pass
            if m.type == 'Interface' and re.match(name, m.name):
                interfaceNames.append((m.subinterfacename, m.name, m.params))
        return interfaceNames
