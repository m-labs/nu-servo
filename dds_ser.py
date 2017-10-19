import logging

from migen import *

import spi

logger = logging.getLogger(__name__)

SPIParams = spi.SPIParams

class SPIDDS(spi.SPISimple):
    def __init__(self, pads, params):
        super().__init__(pads, params)

        self.profile = [Signal(32 + 16 + 16, reset_less=True)
                for i in range(params.channels)]
        cmd = Signal(8, reset=0x0e)  # write to single tone profile 0
        self.sync += [
                If(self.start,
                    [d.eq(Cat(p, cmd))
                        for d, p in zip(self.data, self.profile)]
                )
        ]

        io_update = self._diff(pads, "io_update", output=True)
        # this assumes that the cycle time (1/125 MHz = 8 ns) is >1 SYNC_CLK
        # cycle (1/250 MHz = 4ns)
        done, self.done = self.done, Signal()
        self.sync += [
                self.done.eq(done),
                io_update.eq(done & ~self.done)
        ]
