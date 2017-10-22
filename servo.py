from migen import *

from adc_ser import ADC, ADCParams
from iir import IIR, IIRWidths
from dds_ser import DDS, DDSParams


class Servo(Module):
    def __init__(self, adc_pads, dds_pads, adc_p, iir_p, dds_p):
        self.submodules.adc = ADC(adc_pads, adc_p)
        self.submodules.iir = IIR(iir_p)
        self.submodules.dds = DDS(dds_pads, dds_p)

        t_adc = (adc_p.t_cnvh + adc_p.t_conv + adc_p.t_rtt +
            adc_p.channels*adc_p.width//2//adc_p.lanes)
        t_iir = ((1 + 4 + 1) << iir_p.channel) + 1
        t_dds = (dds_p.width*2 + 1)*dds_p.clk + 1
        t_cycle = max(t_adc, t_iir, t_dds)

        for i, j, k, l in zip(self.adc.data, self.iir.adc,
                self.iir.dds, self.dds.profile):
            self.comb += j.eq(i), l.eq(k)

        self.start = Signal()
        cnt = Signal(max=t_cycle)
        cnt_done = Signal()
        token = Signal(2)
        self.done = Signal()
        self.comb += [
                cnt_done.eq(cnt == 0),
                self.adc.start.eq(self.start & cnt_done),
                self.iir.start.eq(token[0] & self.adc.done),
                self.dds.start.eq(token[1] & self.iir.shifting),
                self.done.eq(self.dds.done),
        ]
        self.sync += [
                If(~cnt_done,
                    cnt.eq(cnt - 1),
                ),
                If(self.adc.done,
                    token[0].eq(0),
                ),
                If(self.adc.start,
                    cnt.eq(t_cycle - 1),
                    token[0].eq(1)
                ),
                If(self.iir.shifting,
                    token[1].eq(0),
                ),
                If(self.iir.start,
                    token[1].eq(token[0]),
                )
        ]
