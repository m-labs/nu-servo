from migen import *
from migen.build.generic_platform import *
from migen.genlib import io

import adc_ser, iir, arty, impl

import adc_ser, arty, impl


class Top(impl.Impl):
    def __init__(self, plat):
        super().__init__(plat, clk=150e6)
        params = adc_ser.ADCParams(width=16, channels=8, lanes=2,
                t_cnvh=4, t_conv=57, t_rtt=4)
        self.submodules.adc = adc = adc_ser.ADC(
                plat.request("adc_ser"), params)

        w = iir.IIRWidths(state=25, coeff=18, adc=16,
                asf=14, word=16, accu=48, shift=11,
                channel=3, profile=5)
        self.submodules.proc = proc = iir.IIR(w)

        for i, j in zip(adc.data, proc.adc):
            self.comb += j.eq(i)

        self.comb += [
                proc.start.eq(adc.done),
        ]

        m_coeff = proc.m_coeff.get_port(write_capable=True)
        m_state = proc.m_state.get_port(write_capable=True)
        self.specials += m_coeff, m_state

        ins = [
                m_state.adr, m_state.we, m_state.dat_w,
                m_coeff.adr, m_coeff.we, m_coeff.dat_w,
                adc.start]
        for ctrl in proc.ctrl:
            ins += ctrl.flatten()
        self.dummy_inputs(ins, adc.start)

        outs = [proc.shifting, proc.loading, proc.processing, proc.done,
                m_state.dat_r, m_coeff.dat_r,
                adc.reading, adc.done] + proc.dds
        self.dummy_outputs(outs, proc.done)


if __name__ == "__main__":
    plat = arty.Platform()
    top = Top(plat)
    plat.build(top)
