// Copyright (c) 2014 Quanta Research Cambridge, Inc.

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

// bsv libraries
import Vector::*;
import GetPut::*;
import Connectable :: *;
import Clocks :: *;
import FIFO::*;
import DefaultValue::*;

// portz libraries
import Portal::*;
import Directory::*;
import CtrlMux::*;
import Portal::*;
import Leds::*;
import XADC::*;

// generated by tool
import ImageonSerdesRequestWrapper::*;
import ImageonSerdesIndicationProxy::*;
import ImageonSensorRequestWrapper::*;
import ImageonSensorIndicationProxy::*;
import HdmiInternalRequestWrapper::*;
import HdmiInternalIndicationProxy::*;

// defined by user
import IserdesDatadeser::*;
import Imageon::*;
import HDMI::*;
import YUV::*;
import XilinxCells::*;
import XbsvXilinxCells::*;

typedef enum { ImageonSerdesRequest, ImageonSensorRequest, HdmiInternalRequest,
    ImageonSerdesIndication, ImageonSensorIndication, HdmiInternalIndication} IfcNames deriving (Eq,Bits);

interface ImageCapturePins;
   interface ImageonSensorPins pins;
   interface ImageonSerdesPins serpins;
   (* prefix="" *)
   interface HDMI#(Bit#(HdmiBits)) hdmi;
   method Action fmc_video_clk1(Bit#(1) v);
endinterface
interface ImageCapture;
   interface Vector#(6,StdPortal) portals;
   interface ImageCapturePins pins;
   interface XADC             xadc;
endinterface

module mkImageCapture#(Clock fmc_imageon_clk1)(ImageCapture);
   Clock defaultClock <- exposeCurrentClock();
   Reset defaultReset <- exposeCurrentReset();
   ClockGenerator7AdvParams clockParams = defaultValue;
   clockParams.bandwidth          = "OPTIMIZED";
   clockParams.compensation       = "ZHOLD";
   clockParams.clkfbout_mult_f    = 8.000;
   clockParams.clkfbout_phase     = 0.0;
   clockParams.clkin1_period      = 6.734007; // 148.5 MHz
   clockParams.clkin2_period      = 6.734007;
   clockParams.clkout0_divide_f   = 8.000;    // 148.5 MHz
   clockParams.clkout0_duty_cycle = 0.5;
   clockParams.clkout0_phase      = 0.0000;
   clockParams.clkout1_divide     = 32;       // 37.125 MHz
   clockParams.clkout1_duty_cycle = 0.5;
   clockParams.clkout1_phase      = 0.0000;
   clockParams.divclk_divide      = 1;
   clockParams.ref_jitter1        = 0.010;
   clockParams.ref_jitter2        = 0.010;

   XClockGenerator7 clockGen <- mkClockGenerator7Adv(clockParams, clocked_by fmc_imageon_clk1);
   C2B c2b_fb <- mkC2B(clockGen.clkfbout, clocked_by clockGen.clkfbout);
   rule txoutrule5;
      clockGen.clkfbin(c2b_fb.o());
   endrule
   Clock hdmi_clock <- mkClockBUFG(clocked_by clockGen.clkout0);    // 148.5   MHz
   Clock imageon_clock <- mkClockBUFG(clocked_by clockGen.clkout1); //  37.125 MHz
   Reset hdmi_reset <- mkAsyncReset(2, defaultReset, hdmi_clock);
   Reset imageon_reset <- mkAsyncReset(2, defaultReset, imageon_clock);
   SyncPulseIfc vsyncPulse <- mkSyncHandshake(hdmi_clock, hdmi_reset, imageon_clock);

   // instantiate user portals
   // serdes: serial line protocol for wires from sensor (nothing sensor specific)
   ImageonSerdesIndicationProxy serdesIndicationProxy <- mkImageonSerdesIndicationProxy(ImageonSerdesIndication);
   ISerdes serdes <- mkISerdes(defaultClock, defaultReset, serdesIndicationProxy.ifc,
			clocked_by imageon_clock, reset_by imageon_reset);
   ImageonSerdesRequestWrapper serdesRequestWrapper <- mkImageonSerdesRequestWrapper(ImageonSerdesRequest,serdes.control);

   // fromSensor: sensor specific processing of serdes input, resulting in pixels
   ImageonSensorIndicationProxy sensorIndicationProxy <- mkImageonSensorIndicationProxy(ImageonSensorIndication);
   ImageonSensor fromSensor <- mkImageonSensor(defaultClock, defaultReset, serdes.data, vsyncPulse.pulse(),
       hdmi_clock, hdmi_reset, sensorIndicationProxy.ifc, clocked_by imageon_clock, reset_by imageon_reset);
   ImageonSensorRequestWrapper sensorRequestWrapper <- mkImageonSensorRequestWrapper(ImageonSensorRequest,fromSensor.control);

   // hdmi: output to display
   HdmiInternalIndicationProxy hdmiIndicationProxy <- mkHdmiInternalIndicationProxy(HdmiInternalIndication);
   HdmiGenerator#(Rgb888) hdmiGen <- mkHdmiGenerator(defaultClock, defaultReset,
       vsyncPulse, hdmiIndicationProxy.ifc, clocked_by hdmi_clock, reset_by hdmi_reset);
   Rgb888ToYyuv converter <- mkRgb888ToYyuv(clocked_by hdmi_clock, reset_by hdmi_reset);
   mkConnection(hdmiGen.rgb888, converter.rgb888);
   HDMI#(Bit#(HdmiBits)) hdmisignals <- mkHDMI(converter.yyuv, clocked_by hdmi_clock, reset_by hdmi_reset);
   HdmiInternalRequestWrapper hdmiRequestWrapper <- mkHdmiInternalRequestWrapper(HdmiInternalRequest,hdmiGen.control);

   Reg#(Bool) frameStart <- mkReg(False, clocked_by imageon_clock, reset_by imageon_reset);
   Reg#(Bit#(32)) frameCount <- mkReg(0, clocked_by imageon_clock, reset_by imageon_reset);
   SyncFIFOIfc#(Tuple2#(Bit#(2),Bit#(32))) frameStartSynchronizer <- mkSyncFIFO(2, imageon_clock, imageon_reset, defaultClock);

   rule frameStartRule;
       let monitor = fromSensor.monitor();
       Bool fs = unpack(monitor[0]);
       if (fs && !frameStart) begin
	  // start of frame?
	  // need to cross the clock domain
	  frameStartSynchronizer.enq(tuple2(monitor, frameCount));
	  frameCount <= frameCount + 1;
       end
      frameStart <= fs;
   endrule
   rule frameStartIndication;
      let tpl = frameStartSynchronizer.first();
      frameStartSynchronizer.deq();
      let monitor = tpl_1(tpl);
      let count = tpl_2(tpl);
      //captureIndicationProxy.ifc.frameStart(monitor, count);
   endrule

Reg#(Bit#(10)) xsvi <- mkReg(0, clocked_by hdmi_clock, reset_by hdmi_reset);
   rule xsviConnection;
       // copy data from sensor to hdmi output
       let xsvit <- fromSensor.get_data();
       xsvi <= xsvit;
   endrule
   rule xsviput;
       Bit#(32) pixel = {8'b0, xsvi[9:2], xsvi[9:2], xsvi[9:2]};
       hdmiGen.request.put(pixel);
   endrule
   Reg#(Bit#(1)) bozobit <- mkReg(0, clocked_by hdmi_clock, reset_by hdmi_reset);
    rule bozobit_rule;
        bozobit <= ~bozobit;
    endrule
   
   Vector#(6,StdPortal) portal_array;
   portal_array[0] = serdesRequestWrapper.portalIfc; 
   portal_array[1] = serdesIndicationProxy.portalIfc;
   portal_array[2] = sensorRequestWrapper.portalIfc; 
   portal_array[3] = sensorIndicationProxy.portalIfc; 
   portal_array[4] = hdmiRequestWrapper.portalIfc; 
   portal_array[5] = hdmiIndicationProxy.portalIfc; 
   interface Vector portals = portal_array;

   interface ImageCapturePins pins;
       interface ImageonSensorPins pins = fromSensor.pins;
       interface ImageonSerdesPins serpins = serdes.pins;
       interface HDMI hdmi = hdmisignals;
   endinterface
   interface XADC             xadc;
        method Bit#(4) gpio;
            return { bozobit, hdmisignals.hdmi_vsync,
                //hdmisignals.hdmi_data[8], hdmisignals.hdmi_data[0]};
                hdmisignals.hdmi_hsync, hdmisignals.hdmi_de};
        endmethod
   endinterface
endmodule

module mkPortalTop(PortalTop#(PhysAddrWidth,64,ImageCapturePins,0));
   //Clock defaultClock <- exposeCurrentClock();
   //Reset defaultReset <- exposeCurrentReset();
   B2C1 iclock <- mkB2C1();
   Clock iclock_buf <- mkClockBUFG(clocked_by iclock.c);
   ImageCapture ic <- mkImageCapture(iclock_buf);
   
   // instantiate system directory
   StdDirectory dir <- mkStdDirectory(ic.portals);
   let ctrl_mux <- mkSlaveMux(dir,ic.portals);
   
   interface interrupt = getInterruptVector(ic.portals);
   interface slave = ctrl_mux;
   interface masters = nil;
   //interface leds = captureRequestInternal.leds;
   interface xadc = ic.xadc;
   interface ImageCapturePins pins;
       method Action fmc_video_clk1(Bit#(1) v);
           iclock.inputclock(v);
       endmethod
       interface ImageonSensorPins pins = ic.pins.pins;
       interface ImageonSerdesPins serpins = ic.pins.serpins;
       interface HDMI hdmi = ic.pins.hdmi;
   endinterface
endmodule : mkPortalTop
