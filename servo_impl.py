from migen import *
from migen.build.generic_platform import *
from migen.genlib import io

import adc_ser, iir, dds_ser, impl


class Top(impl.Impl):
    def __init__(self, plat):
        super().__init__(plat, clk=150e6)
        adc_p = adc_ser.ADCParams(width=16, channels=8, lanes=4,
                t_cnvh=4, t_conv=57, t_rtt=4)
        adc_pads = plat.request("adc_ser")
        self.submodules.adc = adc_ser.ADC(adc_pads, adc_p)

        plat.add_period_constraint(adc_pads.clkout_p,
                plat.default_clk_period)
        plat.add_false_path_constraints(
                plat.lookup_request(plat.default_clk_name),
                adc_pads.clkout_p)

        proc_p = iir.IIRWidths(state=25, coeff=18, adc=16,
                asf=14, word=16, accu=48, shift=11,
                channel=3, profile=5)
        self.submodules.proc = iir.IIR(proc_p)

        dds_p = dds_ser.DDSParams(width=8 + 32 + 16 + 16,
                channels=adc_p.channels, clk=1)
        dds_pads = plat.request("dds_ser")
        self.submodules.dds = dds_ser.DDS(dds_pads, dds_p)

        t_adc = (adc_p.t_cnvh + adc_p.t_conv + adc_p.t_rtt +
            adc_p.channels*adc_p.width//2//adc_p.lanes)
        t_iir = ((1 + 4 + 1) << proc_p.channel) + 1
        t_dds = (dds_p.width*2 + 1)*dds_p.clk + 1
        t_cycle = max(t_adc, t_iir, t_dds)

        for i, j, k, l in zip(self.adc.data, self.proc.adc,
                self.proc.dds, self.dds.profile):
            self.comb += j.eq(i), l.eq(k)

        self.start = Signal()
        cnt = Signal(max=t_cycle)
        cnt_done = Signal()
        token = Signal(2)
        self.done = Signal()
        self.comb += [
                cnt_done.eq(cnt == 0),
                self.adc.start.eq(self.start & cnt_done),
                self.proc.start.eq(token[0] & self.adc.done),
                self.dds.start.eq(token[1] & self.proc.shifting),
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
                If(self.proc.shifting,
                    token[1].eq(0),
                ),
                If(self.proc.start,
                    token[1].eq(token[0]),
                )
        ]

        m_coeff = self.proc.m_coeff.get_port(write_capable=True)
        m_state = self.proc.m_state.get_port(write_capable=True)
        self.specials += m_coeff, m_state

        ins = [
                m_state.adr, m_state.we, m_state.dat_w,
                m_coeff.adr, m_coeff.we, m_coeff.dat_w,
                self.start]
        for ctrl in self.proc.ctrl:
            ins += ctrl.flatten()
        self.dummy_inputs(ins, self.start)

        outs = [m_state.dat_r, m_coeff.dat_r]
        self.dummy_outputs(outs, self.dds.done)


if __name__ == "__main__":
    plat = impl.Platform()
    top = Top(plat)
    plat.build(top)
