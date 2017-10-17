import logging
import string

from migen import *
from migen.genlib import io

import dds_ser


class TB(Module):
    def __init__(self, *args, **kwargs):
        p = dds_ser.SPIParams(channels=4, width=8 + 32 + 16 + 16, clk=2)

        self.cs_n = Signal()
        self.clk = Signal()
        self.mosi = [Signal() for i in range(p.channels)]
        for i, m in enumerate(self.mosi):
            setattr(self, "mosi{}".format(i), m)
        self.miso = Signal()
        self.io_update = Signal()

        self.submodules.dut = dut = dds_ser.SPIDDS(self, p, *args, **kwargs)

        clk0 = Signal()
        self.sync += clk0.eq(self.clk)
        sample = Signal()
        self.comb += sample.eq(Cat(self.clk, clk0) == 0b10)

        self.dds = []
        for i in range(p.channels):
            dds = Record([("asf", 16), ("pow", 16), ("ftw", 32), ("cmd", 8)])
            sr = Signal(len(dds) + 1)
            self.comb += [
                    dds.raw_bits().eq(sr),
            ]
            self.sync += [
                    If(~self.cs_n & sample,
                        sr.eq(Cat(self.mosi[i], sr))
                    )
            ]
            self.dds.append(dds)

    @passive
    def watch(self):
        while True:
            if (yield self.io_update):
                for dds in self.dds:
                    v = yield from [(yield getattr(dds, k))
                            for k in "cmd ftw pow asf".split()]
                    print([hex(_) for _ in v])
            yield



def main():
    tb = TB()

    def run(tb):
        dut = tb.dut
        for i, ch in enumerate(dut.data):
            yield ch.eq(((((0
                << 8 | i | 0x10)
                << 32 | i | 0x20)
                << 16 | i | 0x30)
                << 16 | i | 0x40))
        # assert (yield dut.done)
        yield dut.start.eq(1)
        yield
        yield dut.start.eq(0)
        yield
        yield
        assert not (yield dut.done)
        while not (yield dut.done):
            yield

    run_simulation(tb, [tb.watch(), run(tb)], vcd_name="dds.vcd")


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
