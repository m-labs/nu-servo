from migen import *
from migen.build.generic_platform import *
from migen.genlib import io

import adc_ser, iir, dds_ser, impl


class Top(impl.Impl):
    def __init__(self, plat):
        super().__init__(plat, clk=150e6)
        params = adc_ser.ADCParams(width=16, channels=8, lanes=4,
                t_cnvh=4, t_conv=57, t_rtt=4)
        adc_pads = plat.request("adc_ser")
        self.submodules.adc = adc = adc_ser.ADC(adc_pads, params)

        plat.add_period_constraint(adc_pads.clkout_p,
                plat.default_clk_period)
        plat.add_false_path_constraints(
                plat.lookup_request(plat.default_clk_name),
                adc_pads.clkout_p)

        w = iir.IIRWidths(state=25, coeff=18, adc=16,
                asf=14, word=16, accu=48, shift=11,
                channel=3, profile=5)
        self.submodules.proc = proc = iir.IIR(w)

        for i, j in zip(adc.data, proc.adc):
            self.comb += j.eq(i)

        self.comb += [
                proc.start.eq(adc.done),
        ]

        dds_pads = plat.request("dds_ser")
        params = dds_ser.SPIParams(width=8 + 32 + 16 + 16, channels=8, clk=1)
        self.submodules.dds = dds = dds_ser.SPIDDS(dds_pads, params)

        for i, j in zip(proc.dds, dds.profile):
            self.comb += j.eq(i)

        self.comb += [
                dds.start.eq(proc.done)
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
                adc.reading, adc.done, dds.done]
        self.dummy_outputs(outs, proc.done)


if __name__ == "__main__":
    plat = impl.Platform()
    top = Top(plat)
    plat.build(top)
