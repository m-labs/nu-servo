import logging

from migen import *

import spi

logger = logging.getLogger(__name__)

SPIParams = spi.SPIParams

class SPIDDS(spi.SPISimple):
    def __init__(self, pads, params):
        super().__init__(pads, params)
        io_update = self._diff(pads, "io_update", output=True)

        done, self.done = self.done, Signal()
        self.sync += [
                If(~done,
                    self.done.eq(0),
                ),
                If(done,
                    io_update.eq(1),
                ),
                If(io_update,
                    io_update.eq(0),
                    self.done.eq(1)
                )
        ]
