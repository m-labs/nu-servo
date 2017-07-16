import logging
import string

from migen import *
from migen.genlib import io

import dds_ser


class TB(Module):
    def __init__(self, params, *args, **kwargs):
        self.params = p = params

        self.cs_b = Signal()
        self.sck = Signal()
        self.mosi = [Signal() for i in range(p.channels)]
        self.miso = Signal()
        self.io_update = Signal()

        self.dds = []

        stb_shift = Signal()
        stb_sample = Signal()
        sck_old = Signal()
        self.sync += sck_old.eq(self.sck)
        self.comb += [
                stb_shift.eq(Cat(sck_old, self.sck) == 0b01),
                stb_sample.eq(Cat(sck_old, self.sck) == 0b10)
        ]

        stb = Signal()
        cs_b_old = Signal()
        self.sync += cs_b_old.eq(self.cs_b)
        self.comb += [
                stb.eq(Cat(cs_b_old, self.cs_b) == 0b10)
        ]
        for i in range(p.channels):
            dds = Record([("cmd", 8), ("ftw", 32), ("pow", 16),
                ("asf", 14), ("pad", 2), ("stb", 1)])
            sr = Signal(len(dds) + 1)
            self.comb += [
                    dds.raw_bits().eq(sr),
                    dds.stb.eq(stb)
            ]
            self.sync += [
                    If(stb_sample,
                        sr[0].eq(self.mosi[i]),
                    ),
                    If(stb_shift,
                        sr[1:].eq(sr),
                    )
            ]

        self.submodules.dut = dut = dds_ser.DDS(self, params, *args, **kwargs)


def main():
    params = dds_ser.DDSParams(width=8, channels=4, div=0)
    tb = TB(params)

    def run(tb):
        dut = tb.dut
        #for i, ch in enumerate(dut.data):
        #    yield ch.eq(0)
        assert (yield dut.done)
        yield dut.start.eq(1)
        yield
        yield dut.start.eq(0)
        yield
        assert not (yield dut.done)
        while not (yield dut.done):
            yield
        x = (yield from [(yield d) for d in tb.dds])
        print(x)

    run_simulation(tb, [run(tb)], vcd_name="dds.vcd")


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
