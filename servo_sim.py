import logging

from migen import *
from migen.genlib import io

import adc_sim, iir, dds_sim


class Servo(Module):
    def __init__(self):
        adc_p = adc_sim.ADCParams(width=16, channels=8, lanes=4,
                t_cnvh=4, t_conv=57, t_rtt=4)
        self.submodules.adc_tb = adc_sim.TB(adc_p)
        self.adc = self.adc_tb.adc

        proc_p = iir.IIRWidths(state=25, coeff=18, adc=16,
                asf=14, word=16, accu=48, shift=11,
                channel=3, profile=5)
        self.submodules.proc = proc = iir.IIR(proc_p)

        dds_p = dds_sim.DDSParams(width=8 + 32 + 16 + 16,
                channels=adc_p.channels, clk=1)
        self.submodules.dds_tb = dds_sim.TB(dds_p)
        self.dds = self.dds_tb.dds

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

    def test(self):
        assert (yield self.done)
        yield self.start.eq(1)
        yield
        # assert not (yield self.done)
        while not (yield self.done):
            yield
        while (yield self.done):
            yield
        while not (yield self.done):
            yield
        while (yield self.done):
            yield

if __name__ == "__main__":
    servo = Servo()
    run_simulation(servo, servo.test(), vcd_name="servo.vcd",
            clocks={
                "sys":   (8, 0),
                "adc":   (8, 0),
                "ret":   (8, 0),
                "async": (2, 0),
            },
            special_overrides={
                io.DDROutput: adc_sim.DDROutput,
                io.DDRInput: adc_sim.DDRInput
            })
