from migen import *
from migen.genlib.fsm import FSM, NextState
from misoc.interconnect.csr import *


class _SPI:
    def __init__(self):
        self.cs_b = TSTriple()  # needs pull-up
        self.clk = TSTriple()
        self.mosi = TSTriple()
        self.miso = TSTriple()


class _Par(Record):
    def __init__(self, width):
        n = log2_int(width + 1, need_pow2=False)
        Record.__init__(self, [
            ("tx", width),  # data to be sent
            ("bits", n),    # length of next xfer
            ("oe", 1),      # drive data line (half_duplex and/or slave)
            ("eop", 1),     # end after this xfer
            ("stb", 1),     # xfer trigger (master only)
            ("ack", 1),     # xfer started, data loaded

            ("rx", width),  # previous data received
            ("done", 1),    # previous xfer completed, rx valid

            ("en", 1),      # enable (cs asserted, independent of stb/ack)
        ])


class ShiftRegister(Module):
    def __init__(self, width, spi, par):
        self.master = Signal()
        self.enable = Signal()
        self.half_duplex = Signal()
        self.lsb = Signal()  # LSB first

        self.shift = Signal()
        self.sample = Signal()

        self.done = Signal()
        self.eop = Signal()

        data = Signal(width + 1)
        n = Signal(log2_int(len(data), need_pow2=False))
        ser_rx = Signal()
        oe = Signal()

        self.comb += [
                par.rx.eq(Mux(self.lsb, data[1:], data[:-1])),
                par.en.eq(self.enable),
                spi.mosi.o.eq(Mux(self.lsb, data[0],  data[-1])),
                spi.miso.o.eq(spi.mosi.o),
                spi.mosi.oe.eq(self.enable &
                    Mux(self.half_duplex, oe, self.master)),
                spi.miso.oe.eq(self.enable &
                    ~self.half_duplex & oe & ~self.master),
                ser_rx.eq(Mux(
                    self.half_duplex | ~self.master, spi.mosi.i, spi.miso.i)),
                self.done.eq(n == 0),
        ]
        self.sync += [
                If(self.shift,
                    If(self.lsb,
                        data[:-1].eq(data[1:])
                    ).Else(
                        data[1:].eq(data[:-1])
                    )
                ),
                If(self.sample,
                    If(self.lsb,
                        data[-1].eq(ser_rx)
                    ).Else(
                        data[0].eq(ser_rx)
                    ),
                    If(~self.done,
                        n.eq(n - 1)
                    )
                ),
                If(par.ack,
                    If(self.lsb,
                        data[:-1].eq(par.tx)
                    ).Else(
                        data[1:].eq(par.tx)
                    ),
                    n.eq(par.bits),
                    oe.eq(par.oe),
                    self.eop.eq(par.eop)
                ),
        ]


class Clocking(Module):
    def __init__(self, div_width, spi):
        self.div = Signal(div_width)  # divide sys_clk by `2 + div`
        self.master = Signal()
        self.run = Signal()
        self.cont = Signal()
        self.phase = Signal()

        self.cpol = Signal()
        self.cpha = Signal()

        self.enable = Signal()
        self.grant = Signal()
        self.adv = Signal()

        cnt = Signal.like(self.div)
        cnt_load = Signal.like(self.div)

        clk_in = Signal()
        clk = Signal(reset=1)

        block = Signal()
        done = Signal()

        self.comb += [
                spi.cs_b.oe.eq(self.master & (self.enable | block)),
                spi.cs_b.o.eq(~self.enable),

                spi.clk.o.eq((clk & self.enable) ^ self.cpol),
                spi.clk.oe.eq(self.master & self.enable),

                clk_in.eq((spi.clk.i ^ self.cpol) | spi.cs_b.i),

                cnt_load.eq(self.div[1:] + (self.phase & self.div[0])),
                done.eq(cnt == 0),

                self.adv.eq(done & (self.master | (clk_in ^ clk))),
                self.grant.eq(spi.cs_b.i ^ ~self.master),
        ]

        self.sync += [
                If(~done,
                    cnt.eq(cnt - 1)
                ),
                If(self.adv,
                    block.eq(0),
                    If(self.cont,
                        cnt.eq(cnt_load),
                        clk.eq(Mux(self.master, ~clk, clk_in) | ~self.run),
                        If(self.enable & ~self.run,
                            block.eq(1)
                        )
                    )
                )
        ]


#       cpha=0           cpha=1
#       0123456789012345 0123456789012345
# cs_b  ---__________--- ---__________---
# clki  ---__--__--__--- ---__--__--__---
# clk   _____--__--_____ _____--__--_____
# adv   ---_-_-_-_-_-_-- ---_-_-_-_-_-_--
# run   __---------_____ __---------_____
# phase ---__--__--__--- ___--__--__--___
# samp  ________-___-___ ______-___-_____
# shift ______-___-_____ ____-___-_______
# mosi     aaaabbbbxx       xxaaaabbbb
# miso     aaaabbbbxx       xxaaaabbbb
# n     0002211110000000 0000022111100000
# busy  ___-------_---__ ___---------_-__
# ack   __-_______x_____ ____-_______x___
# stb   __-_____________ __---___________
# done  __________-_____ ____________-___


class Engine(Module):
    def __init__(self, data_width=32, div_width=8):
        self.par = _Par(data_width)
        self.spi = _SPI()

        self.submodules.gen = Clocking(div_width, self.spi)
        self.submodules.reg = ShiftRegister(data_width, self.spi, self.par)
        self.submodules.fsm = ResetInserter()(CEInserter()(FSM("IDLE")))

        self.active = Signal()
        self.busy = Signal()
        self.offline = Signal(reset=1)

        self.fsm.act("IDLE",
                If(self.gen.grant & (~self.gen.master | self.par.stb),
                    self.gen.cont.eq(1),
                    self.par.ack.eq(self.fsm.ce),
                    If(self.gen.cpha,
                        NextState("WAIT")
                    ).Else(
                        NextState("SETUP")
                    )
                )
        )
        self.fsm.act("WAIT",
                self.gen.cont.eq(1),
                If(self.gen.cpha,
                    NextState("SETUP")
                ).Else(
                    NextState("IDLE")
                )
        )
        self.fsm.act("SETUP",
                self.gen.cont.eq(1),
                NextState("HOLD")
        )
        self.fsm.act("HOLD",
                If(self.reg.done,
                    self.par.done.eq(self.fsm.ce),
                    If(self.par.stb | ~self.gen.master,
                        self.gen.cont.eq(1),
                        self.par.ack.eq(self.fsm.ce),
                        NextState("SETUP")
                    ).Elif(self.reg.eop,
                        self.gen.cont.eq(1),
                        If(self.gen.cpha,
                            NextState("IDLE")
                        ).Else(
                            NextState("WAIT")
                        )
                    )
                ).Else(
                    self.gen.cont.eq(1),
                    NextState("SETUP")
                )
        )

        self.comb += [
                self.reg.master.eq(self.gen.master),
                self.reg.enable.eq(self.gen.enable),
                self.reg.shift.eq(self.fsm.before_leaving("HOLD") &
                    self.fsm.ce),
                self.reg.sample.eq(self.fsm.before_leaving("SETUP") &
                    self.fsm.ce),
                self.gen.run.eq(~self.fsm.before_entering("IDLE")),
                # self.gen.cont.eq(self.fsm.transitioning),
                self.gen.phase.eq(self.fsm.before_entering("SETUP")),
                self.gen.enable.eq(self.active),

                self.fsm.reset.eq(self.offline |
                    ~(self.gen.master | self.gen.grant)),
                self.fsm.ce.eq(self.gen.adv),

                self.active.eq(~self.fsm.ongoing("IDLE")),
                self.busy.eq(~self.fsm.ce | ~self.reg.done |
                    self.fsm.ongoing("SETUP") | self.fsm.ongoing("WAIT")),
        ]

    def cfg(self, div=3, cpol=0, cpha=0, lsb=0, offline=0, master=1,
            half_duplex=0):
        yield self.offline.eq(offline)
        yield self.gen.master.eq(master)
        yield self.gen.div.eq(div)
        yield self.gen.cpol.eq(cpol)
        yield self.gen.cpha.eq(cpha)
        yield self.reg.lsb.eq(lsb)
        yield self.reg.half_duplex.eq(half_duplex)

    def xfer(self, d, n=None, oe=1, eop=1):
        m = len(self.par.tx)
        if n is None:
            n = m
        if not (yield self.reg.lsb):
            d <<= m - n
        yield self.par.tx.eq(d)
        yield self.par.bits.eq(n)
        yield self.par.oe.eq(oe)
        yield self.par.eop.eq(eop)
        yield self.par.stb.eq(1)
        while not (yield self.par.ack):
            yield
        yield self.par.stb.eq(0)
        while not (yield self.par.done):
            yield
        d = (yield self.par.rx)
        if (yield self.reg.lsb):
            d >>= m - n
        if (yield self.par.done):
            return d


class CSBank(Module):
    def __init__(self, master, width):
        # not TSTriple(width) since oe is not wide
        self.cs_b = [TSTriple() for i in range(width)]  # needs pull-ups
        self.mask = Signal(width)

        for i, cs_b in enumerate(self.cs_b):
            self.comb += [
                cs_b.oe.eq(self.mask[i] & master.oe),
                cs_b.o.eq(master.o)
            ]
        self.comb += [
            master.i.eq(Mux(
                master.oe,
                master.o,
                Cat([cs_b.i for cs_b in self.cs_b]) & self.mask != 0),
            )
        ]


class CSREngine(Engine):
    def __init__(self, data_width=32, div_width=8, cs_width=1):
        Engine.__init__(self, data_width, div_width)

        self._data_read = CSRStatus(data_width)
        self._data_write = CSRStorage(data_width, atomic_write=True)
        self._bits = CSRStorage(len(self.par.bits))
        self._oe = CSRStorage()
        self._eop = CSRStorage()

        self._offline = CSRStorage(reset=1)
        self._busy = CSRStatus()
        self._active = CSRStatus()

        self._lsb_first = CSRStorage()
        self._half_duplex = CSRStorage()
        self._master = CSRStorage()

        self._clk_div = CSRStorage(div_width)
        self._clk_polarity = CSRStorage()
        self._clk_phase = CSRStorage()

        self.data_width = CSRConstant(data_width)
        self.div_width = CSRConstant(div_width)
        self.bits_width = CSRConstant(len(self.par.bits))
        self.cs_width = CSRConstant(cs_width)

        if cs_width:
            self.submodules.cs = CSBank(self.spi.cs_b, cs_width)
            self._cs = CSRStorage(cs_width)
            self.comb += self.cs.mask.eq(self._cs.storage)

        ###

        self.comb += [
            self.offline.eq(self._offline.storage),
            self._busy.status.eq(self.busy),
            self._active.status.eq(self.active),

            self.gen.master.eq(self._master.storage),
            self.gen.cpol.eq(self._clk_polarity.storage),
            self.gen.cpha.eq(self._clk_phase.storage),
            self.gen.div.eq(self._clk_div.storage),

            self.reg.half_duplex.eq(self._half_duplex.storage),
            self.reg.lsb.eq(self._lsb_first.storage),

            self.par.tx.eq(self._data_write.storage),
            self.par.bits.eq(self._bits.storage),
            self.par.oe.eq(self._oe.storage),
            self.par.eop.eq(self._eop.storage),
        ]

        self.sync += [
            If(self._data_write.re == 1,
                self.par.stb.eq(1)
            ),
            If(self.par.ack,
                self.par.stb.eq(0)
            ),
            If(self.par.done,
                self._data_read.status.eq(self.par.rx)
            )
        ]


class WBEngine(Engine):
    def __init__(self, bus=None):
        Engine.__init__(self, data_width=32, div_width=8)

        if bus is None:
            bus = wishbone.Interface(data_width=32)
        self.bus = bus

        self.submodules.cs = CSBank(self.spi.cs_b, 8)

        config = Cat(
                self.gen.div, self.cs.mask, self.par.bits,
                self.par.oe, self.par.eop,
                self.offline, self.gen.master, self.gen.cpol,
                self.gen.cpha, self.reg.half_duplex, self.reg.lsb
        )

        rx = Signal.like(self.par.rx)
        self.comb += [
            bus.dat_r.eq(Mux(
                bus.adr[0], rx, Cat(config, self.active, self.busy))),
            self.par.tx.eq(bus.dat_w),
        ]

        self.sync += [
            self.par.stb.eq(bus.ack & bus.we & ~bus.adr[0]),
            bus.ack.eq(bus.cyc & bus.stb & (
                ~bus.we | bus.adr[0] | self.par.ack)),
            If(bus.ack & bus.we & bus.adr[0],
                config.eq(bus.dat_w)
            ),
            If(self.par.done,
                rx.eq(self.par.rx)
            )
        ]


def szip(*iters):
    # TODO: this only handles the non-error case
    # unroll the GeneratorExit and throw() semantics from
    # https://www.python.org/dev/peps/pep-0380/#id13
    active = {it: None for it in iters}
    ret = {it: None for it in iters}
    while active:
        for it in list(active):
            while True:
                try:
                    val = it.send(active[it])
                except StopIteration as e:
                    del active[it]
                    ret[it] = e.value
                    break
                if val is None:
                    break
                else:
                    active[it] = (yield val)
        val = (yield None)
        for it in active:
            active[it] = val
    return tuple(ret[it] for it in iters)


class TB(Module):
    def __init__(self):
        self.submodules.m = m = Engine(data_width=8)
        self.submodules.s = s = Engine(data_width=8)
        self.comb += [m.gen.master.eq(1)] + [
                getattr(a, sig).i.eq(Mux(getattr(a, sig).oe,
                    getattr(a, sig).o, Mux(getattr(b, sig).oe,
                        getattr(b, sig).o, pu)))
                for a, b in [(m.spi, s.spi), (s.spi, m.spi)]
                for sig, pu in zip("cs_b clk mosi miso".split(),
                    [1, 0, 0, 0])
        ]

    def test(self):
        run_simulation(self, [self.test_master(), self.test_slave()],
                vcd_name="spi.vcd")

    def test_master(self):
        yield from self.m.cfg(div=5, cpha=0)
        for i in range(10):
            yield
        d = yield from self.m.xfer(0x81, eop=0)
        print("m:", d)
        yield
        d = yield from self.m.xfer(0x00, oe=0)
        print("m:", d)
        yield
        while not (yield self.m.spi.cs_b.o):
            yield
        for i in range(10):
            yield

    def test_slave(self):
        yield from self.s.cfg(div=3, cpha=0, master=0)
        d = yield from self.s.xfer(0xff, eop=0)
        print("s:", d)
        yield
        d = yield from self.s.xfer(0x81, oe=1)
        print("s:", d)


if __name__ == "__main__":
    from migen.fhdl import verilog
    e = Engine()
    print(verilog.convert(e, ios={
        e.offline, e.reg.lsb,
        e.gen.master, e.gen.div, e.gen.cpol, e.gen.cpha,
        e.par.tx, e.par.rx, e.par.bits, e.par.eop, e.par.oe, e.par.en,
        e.par.ack, e.par.stb, e.par.done,
        e.spi.cs_b.o, e.spi.cs_b.oe, e.spi.cs_b.i,
        e.spi.clk.o, e.spi.clk.oe, e.spi.clk.i,
        e.spi.mosi.o, e.spi.mosi.oe, e.spi.mosi.i,
        e.spi.miso.o, e.spi.miso.oe, e.spi.miso.i,
        }))
    # print(verilog.convert(TB()))
    # print(verilog.convert(CSREngine()))

    TB().test()
