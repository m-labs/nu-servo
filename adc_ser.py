import logging
import string
from collections import namedtuple

from migen import *
from migen.genlib import io


logger = logging.getLogger(__name__)


ADCParams = namedtuple("ADCParams", [
    "width",
    "channels",
    "t_cnvh",
    "t_conv",
    "t_rtt",    # maximum clock round trip time
])


class ADC(Module):
    def __init__(self, pads, params):
        self.params = p = params
        self.data = [Signal((p.width, True), reset_less=True)
                for i in range(p.channels)]
        self.start = Signal()    # start conversion and shifting
        self.reading = Signal()  # data is being shifted (invalid)
        self.done = Signal()     # data valid

        ###

        sdo = []
        for i in string.ascii_lowercase:
            try:
                sdo.append(self._diff(pads, "sdo" + i, "in"))
            except AttributeError:
                break
        lanes = len(sdo)
        t_read = p.width*p.channels//lanes//2  # DDR
        assert 2*lanes*t_read == p.width*p.channels
        count = Signal(max=max(p.t_cnvh, p.t_conv, t_read, p.t_rtt),
                reset_less=True)
        count_load = Signal.like(count)
        count_done = Signal()
        self.comb += [
                count_done.eq(count == 0),
        ]
        self.sync += [
                count.eq(count - 1),
                If(count_done,
                    count.eq(count_load),
                )
        ]

        sck = Signal()
        self.specials += io.DDROutput(0, sck, self._diff(pads, "sck", "out"))
        self.submodules.fsm = fsm = FSM("IDLE")
        pads.cnv_b.reset = 1
        fsm.act("IDLE",
                self.done.eq(1),
                count_load.eq(p.t_cnvh),
                If(self.start,
                    NextState("CNVH")
                )
        )
        fsm.act("CNVH",
                count_load.eq(p.t_conv),
                pads.cnv_b.eq(0),
                If(count_done,
                    NextState("CONV")
                )
        )
        fsm.act("CONV",
                count_load.eq(t_read),
                If(count_done,
                    NextState("READ")
                )
        )
        fsm.act("READ",
                self.reading.eq(1),
                sck.eq(1),
                count_load.eq(p.t_rtt),
                If(count_done,
                    NextState("RTT")
                )
        )
        # this avoids having synchronizers to signal end-of transfer (CLKOUT
        # and it ensures fixed latency early in the pipeline
        fsm.act("RTT",
                self.reading.eq(1),
                If(count_done,
                    NextState("RTT")
                )
        )

        self.clock_domains.cd_adc = ClockDomain("adc", reset_less=True)
        self.comb += [
                self.cd_adc.clk.eq(~self._diff(pads, "clkout", "in"))
        ]
        k = p.channels//lanes
        assert 2*t_read == k*p.width
        for i, sdo in enumerate(sdo):
            buf = Signal(2*t_read)
            self.comb += [
                    Cat([self.data[j*k] for j in range(k)]).eq(buf)
            ]
            dat = Signal(2)
            self.specials += io.DDRInput(sdo, dat[1], dat[0],
                    self.cd_adc.clk)
            self.sync.adc += [
                    buf.eq(Cat(dat, buf))
            ]

    def _diff(self, pads, name, dir):
        if hasattr(pads, name + "_p"):
            sig = Signal()
            p, n = (getattr(pads, name + "_" + s) for s in "pn")
            if dir == "in":
                self.specials += io.DifferentialInput(p, n, sig)
            else:
                self.specials += io.DifferentialOutput(sig, p, n)
            return sig
        return getattr(pads, name)
