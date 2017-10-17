import logging
from collections import namedtuple

from migen import *
from migen.genlib.fsm import FSM, NextState


logger = logging.getLogger(__name__)


# all times in cycles
SPIParams = namedtuple("SPIParams", [
    "channels", # number of MOSI? data lanes
    "width",    # transfer width
    "clk",      # CLK half cycle width (in cycles)
])



class SPISimple(Module):
    def __init__(self, pads, params):
        self.params = p = params
        self.data = [Signal(p.width, reset_less=True)
                for i in range(p.channels)]
        self.start = Signal()  # start transfer
        self.done = Signal()   # data is valid

        ###

        assert p.clk >= 1

        cs_n = self._diff(pads, "cs_n", output=True)

        clk = self._diff(pads, "clk", output=True)
        cnt = Signal(max=p.clk, reset_less=True)
        cnt_done = Signal()
        cnt_next = Signal()
        self.comb += cnt_done.eq(cnt == 0)
        self.sync += [
                If(cnt_done,
                    If(cnt_next,
                        cnt.eq(p.clk - 1)
                    )
                ).Else(
                    cnt.eq(cnt - 1)
                )
        ]

        for i, d in enumerate(self.data):
            self.comb += [
                    self._diff(pads, "mosi{}".format(i), output=True).eq(d[-1])
            ]

        bits = Signal(max=p.width, reset_less=True)

        self.submodules.fsm = fsm = FSM("IDLE")

        fsm.act("IDLE",
                self.done.eq(1),
                cs_n.eq(1),
                If(self.start,
                    cnt_next.eq(1),
                    NextState("SETUP")
                )
        )
        fsm.act("SETUP",
                cnt_next.eq(1),
                If(cnt_done,
                    If(bits == 0,
                        NextState("IDLE")
                    ).Else(
                        NextState("HOLD")
                    )
                )
        )
        fsm.act("HOLD",
                cnt_next.eq(1),
                clk.eq(1),
                If(cnt_done,
                    NextState("SETUP")
                )
        )

        self.sync += [
            If(fsm.ongoing("HOLD") & cnt_done,
                bits.eq(bits - 1),
                [d[1:].eq(d) for d in self.data]
            ),
            If(fsm.ongoing("IDLE"),
                bits.eq(p.width - 1)
            )
        ]

    def _diff(self, pads, name, output=True):
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
