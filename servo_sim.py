import logging

from migen import *
from migen.genlib import io

import adc_sim, iir, dds_sim


class Servo(Module):
    def __init__(self):
        params = adc_sim.ADCParams(width=16, channels=8, lanes=4,
                t_cnvh=4, t_conv=57, t_rtt=4)
        self.submodules.adc_tb = adc_tb = adc_sim.TB(params)

        w = iir.IIRWidths(state=25, coeff=18, adc=16,
                asf=14, word=16, accu=48, shift=11,
                channel=3, profile=5)
        self.submodules.proc = proc = iir.IIR(w)

        for i, j in zip(adc_tb.adc.data, proc.adc):
            self.comb += j.eq(i)

        self.comb += [
                proc.start.eq(adc_tb.adc.done),
        ]

        params = dds_sim.DDSParams(width=8 + 32 + 16 + 16, channels=8, clk=1)
        self.submodules.dds_tb = dds_tb = dds_sim.TB(params)

        for i, j in zip(proc.dds, dds_tb.dds.profile):
            self.comb += j.eq(i)

        self.comb += [
                dds_tb.dds.start.eq(proc.done),
                adc_tb.adc.start.eq(dds_tb.dds.done)
        ]

        m_coeff = proc.m_coeff.get_port(write_capable=True)
        m_state = proc.m_state.get_port(write_capable=True)
        self.specials += m_coeff, m_state

    def test(self):
        for i in range(3):
            yield
        while not (yield self.dds_tb.dds.done):
            yield
        yield
        while not (yield self.dds_tb.dds.done):
            yield
        yield
        while not (yield self.dds_tb.dds.done):
            yield
        yield
        while not (yield self.dds_tb.dds.done):
            yield
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
