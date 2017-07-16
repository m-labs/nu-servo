import logging
from collections import namedtuple

from migen import *

import spi


logger = logging.getLogger(__name__)


DDSParams = namedtuple("DDSParams", [
    "width",     # width of data chunks to be transferred
    "channels",  # number of channels (mosi lines)
    "div",       # clock divider t_sys*(div + 2) == t_sck
])


class DDS(Module):
    def __init__(self, pads, params):
        self.params = p = params
        assert p.div == 0

        self.data = Record([
            ("stb", 1),         # start transfer
            ("ack", 1),         # bits transferred
            ("eop", 1),         # end cycle after this transfer
            ("miso", p.width),  # bits read on miso
                                # data to be sent on mosi:
            ("mosi", [("mosi", p.width) for i in range(p.channels)])
        ])

        ###

        spis = [spi.Engine(data_width=p.width, div_width=1)
                for i in range(p.channels)]
        self.submodules += spis
