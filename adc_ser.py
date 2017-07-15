import logging
import string
from collections import namedtuple

from migen import *
from migen.genlib import io


logger = logging.getLogger(__name__)


# all times in cycles
ADCParams = namedtuple("ADCParams", [
    "channels", # number of channels
                # number of lanes will be inferred from pads
    "width",    # bits to transfer per channel
    "t_cnvh",   # CNVH duration (minimum)
    "t_conv",   # CONV duration (minimum)
    "t_rtt",    # upper estimate for clock round trip time from
                # sck at the FPGA to clkout at the FPGA
])


class ADC(Module):
    def __init__(self, pads, params):
        self.params = p = params
        self.data = [Signal((p.width, True), reset_less=True)
                for i in range(p.channels)]
        self.start = Signal()    # start conversion and reading
        self.reading = Signal()  # data is being read (outputs are invalid)
        self.done = Signal()     # data is valid

        ###

        # collect sdo lines
        sdo = []
        for i in string.ascii_lowercase:
            try:
                sdo.append(self._diff(pads, "sdo" + i))
            except AttributeError:
                break
        lanes = len(sdo)

        # set up counters for the four states CNVH, CONV, READ, RTT
        t_read = p.width*p.channels//lanes//2  # DDR
        assert 2*lanes*t_read == p.width*p.channels
        assert all(_ > 0 for _ in (p.t_cnvh, p.t_conv, p.t_rtt))
        count = Signal(max=max(p.t_cnvh, p.t_conv, t_read, p.t_rtt) - 1,
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

        sck_en = Signal()
        self._sck_en = Signal(reset_less=True)  # expose for testbench
        self.sync += self._sck_en.eq(sck_en)
        # technically it could be "0, sck_en" because we
        # don't care about phase here and only about delay
        # but let's prefer not having to mess with the duration values
        # return clkout will always be used in the correct phase
        self.specials += io.DDROutput(0, sck_en,
                self._diff(pads, "sck", output=True))
        self.submodules.fsm = fsm = FSM("IDLE")
        fsm.act("IDLE",
                self.done.eq(1),
                If(self.start,
                    count_load.eq(p.t_cnvh - 1),
                    NextState("CNVH")
                )
        )
        fsm.act("CNVH",
                count_load.eq(p.t_conv - 1),
                pads.cnv_b.eq(1),
                If(count_done,
                    NextState("CONV")
                )
        )
        fsm.act("CONV",
                count_load.eq(t_read - 1),
                If(count_done,
                    sck_en.eq(1),  # ODDR pipeline delay
                    NextState("READ")
                )
        )
        fsm.act("READ",
                self.reading.eq(1),
                count_load.eq(p.t_rtt - 1),
                If(count_done,
                    NextState("RTT")
                ).Else(
                    sck_en.eq(1)
                )
        )
        # this avoids having synchronizers to signal end-of transfer (CLKOUT
        # and it ensures fixed latency early in the pipeline
        fsm.act("RTT",
                self.reading.eq(1),
                If(count_done,
                    NextState("IDLE")
                )
        )

        self.clock_domains.cd_ret = ClockDomain("ret", reset_less=True)
        self.comb += [
                # falling clkout makes two bits available
                self.cd_ret.clk.eq(~self._diff(pads, "clkout")),
        ]
        self._clkout_en = Signal(reset=1)  # expose for testbench
        k = p.channels//lanes
        assert 2*t_read == k*p.width
        for i, sdo in enumerate(sdo):
            buf = Signal(2*t_read - 2)
            dat = Signal(2)
            self.specials += io.DDRInput(sdo, dat[1], dat[0],
                    self.cd_ret.clk)
            self.sync.ret += [
                    If(self.reading & self._clkout_en,
                        buf.eq(Cat(dat, buf))
                    )
            ]
            self.comb += [
                    Cat(reversed([self.data[i*k + j] for j in range(k)])).eq(
                        Cat(dat, buf))
            ]


    def _diff(self, pads, name, output=False):
        if hasattr(pads, name + "_p"):
            sig = Signal()
            p, n = (getattr(pads, name + "_" + s) for s in "pn")
            if output:
                self.specials += io.DifferentialOutput(sig, p, n)
            else:
                self.specials += io.DifferentialInput(p, n, sig)
            return sig
        else:
            return getattr(pads, name)
