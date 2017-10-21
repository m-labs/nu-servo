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

        adc = 1
        x0 = 0x0141
        yield self.adc_tb.data[adc].eq(x0)
        channel = 3
        yield self.proc.adc[channel].eq(adc)
        yield self.proc.ctrl[channel].en_iir.eq(1)
        yield self.proc.ctrl[channel].en_out.eq(1)
        profile = 5
        yield self.proc.ctrl[channel].profile.eq(profile)
        x1 = 0x0743
        yield from self.proc.set_state(adc, x1, coeff="x1")
        y1 = 0x1145
        yield from self.proc.set_state(channel, y1,
                profile=profile, coeff="y1")
        coeff = dict(pow=0x1333, offset=0x1531, ftw0=0x1727, ftw1=0x1929,
                a1=0x0135, b0=0x0337, b1=0x0539, cfg=adc | (0 << 3))
        for ks in "pow offset ftw0 ftw1", "a1 b0 b1 cfg":
            for k in ks.split():
                yield from self.proc.set_coeff(channel, value=coeff[k],
                        profile=profile, coeff=k)
            yield

        yield self.start.eq(1)
        yield
        yield self.start.eq(0)
        while not (yield self.dds_tb.io_update):
            yield
        yield  # io_update

        w = self.proc.widths

        x0 = x0 << (w.state - w.adc - 1)
        _ = yield from self.proc.get_state(adc, coeff="x1")
        assert _ == x0, (hex(_), hex(x0))

        offset = coeff["offset"] << (w.state - w.coeff - 1)
        a1, b0, b1 = coeff["a1"], coeff["b0"], coeff["b1"]
        out = (
                0*(1 << w.shift - 1) +  # rounding
                a1*(0 - y1) + b0*(offset - x0) + b1*(offset - x1)
        ) >> w.shift
        y1 = min(max(0, out), (1 << w.state - 1) - 1)

        _ = yield from self.proc.get_state(channel, profile, coeff="y1")
        assert _ == y1, (hex(_), hex(y1))

        _ = yield self.dds_tb.ddss[channel].ftw
        ftw = (coeff["ftw1"] << 16) | coeff["ftw0"]
        assert _ == ftw, (hex(_), hex(ftw))

        _ = yield self.dds_tb.ddss[channel].pow
        assert _ == coeff["pow"], (hex(_), hex(coeff["pow"]))

        _ = yield self.dds_tb.ddss[channel].asf
        asf = y1 >> (w.state - w.asf - 1)
        assert _ == asf, (hex(_), hex(asf))


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
