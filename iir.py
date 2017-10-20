from collections import namedtuple
import logging

from migen import *


logger = logging.getLogger(__name__)


# all these are number of bits!
IIRWidths = namedtuple("IIRWidths", [
    "state",    # the signed x and y states of the IIR filter
                # DSP A input, x state is one bit smaller
                # due to AD pre-adder, y has full width
    "coeff",    # signed IIR filter coefficients a1, b0, b1
    "accu",     # IIR accumulator width
    "adc",      # signed ADC data
    "word",     # "word" size to break up DDS profile data
    "asf",      # unsigned amplitude scale factor for DDS
    "shift",    # fixed point scaling coefficient for a1, b0, b1
    "channel",  # channels (log2!)
    "profile",  # profiles per channel (log2!)
])


def signed(v, w):
    if v >= 1 << w - 1:
        v -= 1 << w
    return v


class DSP(Module):
    """Thin abstraction of DSP functionality used here, commonly present,
    and inferrable in FPGAs: multiplier with pre- and post-adder and
    pipeline registers at every stage."""
    def __init__(self, w):
        self.state = Signal((w.state, True))
        self.offset = Signal((w.state, True))
        self.coeff = Signal((w.coeff, True))
        self.output = Signal((w.state, True))
        self.accu_clr = Signal()
        self.offset_load = Signal()
        self.clip = Signal()

        a = Signal((w.state, True), reset_less=True)
        d = Signal((w.state, True), reset_less=True)
        ad = Signal((w.state, True), reset_less=True)
        b = Signal((w.coeff, True), reset_less=True)
        m = Signal((w.accu, True), reset_less=True)
        p = Signal((w.accu, True), reset_less=True)

        self.sync += [
                a.eq(self.state),
                If(self.offset_load,
                    d.eq(self.offset)
                ),
                ad.eq(d - a),
                b.eq(self.coeff),
                m.eq(ad*b),
                p.eq(p + m),
                If(self.accu_clr,
                    # inject symmetric rouding constant
                    # (won't infer P reg)
                    # p.eq(1 << (w.shift - 1))
                    p.eq(0),
                )
        ]
        # w.shift | w.state - 1 | n_sign - 1 | 1 (sign)
        n_sign = w.accu - w.state - w.shift + 1
        assert n_sign > 1

        self.comb += [
                # signed
                # self.clip.eq(p[-n_sign:] != Replicate(p[-1], sign)),
                # unsigned
                self.clip.eq(p[-n_sign:] != 0),
                self.output.eq(Mux(self.clip,
                        # signed
                        # Cat(Replicate(~p[-1], w.state - 1), p[-1]),
                        # unsigned
                        Replicate(~p[-1], w.state - 1),
                        p[w.shift:])
                )
        ]


class IIR(Module):
    def __init__(self, w):
        self.widths = w
        for i, j in enumerate(w):
            assert j > 0, (i, j, w)
        assert w.word <= w.coeff  # same memory
        assert w.state + w.coeff + 3 <= w.accu

        # m_coeff of active profiles should only be accessed during
        # ~processing
        self.specials.m_coeff = Memory(
                width=2*w.coeff,  # Cat(pow/ftw/offset, cfg/a/b)
                depth=4 << w.profile + w.channel)
        # m_state[x] should only be read during ~(shifting |
        # loading)
        # m_state[y] of active profiles should only be read during
        # ~processing
        self.specials.m_state = Memory(
                width=w.state,  # y1,x0,x1
                depth=(1 << w.profile + w.channel) + (2 << w.channel))
        # ctrl should only be updated synchronously
        # TODO: implement dlys clearing when changing profile or
        # clearing en_out
        self.ctrl = [Record([
            ("profile", w.profile),
            ("en_out", 1),
            ("en_iir", 1)])
            for i in range(1 << w.channel)]
        # only update during ~loading
        self.adc = [Signal((w.adc, True), reset_less=True)
                for i in range(1 << w.channel)]
        # Cat(ftw0, ftw1, pow, asf)
        # only read during ~processing
        self.dds = [Signal(4*w.word, reset_less=True)
                for i in range(1 << w.channel)]
        # perform one IIR iteration, start with shifting, then loading,
        # then processing, end with done
        self.start = Signal()
        # shifting input state values around (x0 becomes x1)
        self.shifting = Signal()
        # adc inputs being loaded into RAM (becoming x0)
        self.loading = Signal()
        # processing state data (extracting ftw0/ftw1/pow,
        # computing asf/y0, and storing as y1)
        self.processing = Signal()
        # dds outputs ready and won't be touched again until processing
        self.done = Signal()

        ###

        # pivot arrays for muxing
        profiles = Array([ch.profile for ch in self.ctrl])
        en_outs = Array([ch.en_out for ch in self.ctrl])
        en_iirs = Array([ch.en_iir for ch in self.ctrl])

        # state counter
        state = Signal(w.channel + 2)
        # pipeline group activity flags (SR)
        stage = Signal(3)
        self.submodules.fsm = fsm = FSM("IDLE")
        state_clr = Signal()
        stage_en = Signal()
        fsm.act("IDLE",
                self.done.eq(1),
                state_clr.eq(1),
                If(self.start,
                    NextState("LOAD")
                )
        )
        fsm.act("LOAD",
                self.loading.eq(1),
                If(state == (1 << w.channel) - 1,
                    state_clr.eq(1),
                    stage_en.eq(1),
                    NextState("PROCESS")
                )
        )
        fsm.act("PROCESS",
                self.processing.eq(1),
                # this is technically wasting three cycles
                # (one for setting stage, and phase=2,3 with stage[2])
                If(stage == 0,
                    state_clr.eq(1),
                    NextState("SHIFT")
                )
        )
        fsm.act("SHIFT",
                self.shifting.eq(1),
                If(state == (2 << w.channel) - 1,
                    NextState("IDLE")
                )
        )

        self.sync += [
                state.eq(state + 1),
                If(state_clr,
                    state.eq(0),
                ),
                If(stage_en,
                    stage[0].eq(1)
                )
        ]

        # pipeline group channel pointer (SR)
        channel = [Signal(w.channel, reset_less=True) for i in range(3)]
        # pipeline group profile pointer (SR)
        profile = [Signal(w.profile, reset_less=True) for i in range(2)]
        # pipeline phase (lower two bits of state)
        phase = Signal(2, reset_less=True)

        self.comb += Cat(phase, channel[0]).eq(state)
        self.sync += [
                Case(phase, {
                    0: [
                        profile[0].eq(profiles[channel[0]]),
                        profile[1].eq(profile[0])
                    ],
                    3: [
                        Cat(channel[1:]).eq(Cat(channel[:-1])),
                        stage[1:].eq(stage[:-1]),
                        If(channel[0] == (1 << w.channel) - 1,
                            stage[0].eq(0)
                        )
                    ]
                })
        ]

        m_coeff = self.m_coeff.get_port()
        m_state = self.m_state.get_port(write_capable=True)
        self.specials += m_state, m_coeff

        dsp = DSP(w)
        self.submodules += dsp

        offset_clr = Signal()

        self.comb += [
                m_coeff.adr.eq(Cat(phase, profile[0],
                    Mux(phase==0, channel[1], channel[0]))),
                dsp.offset[-w.coeff - 1:].eq(Mux(offset_clr, 0,
                    Cat(m_coeff.dat_r[:w.coeff], m_coeff.dat_r[w.coeff - 1])
                )),
                dsp.coeff.eq(m_coeff.dat_r[w.coeff:]),
                dsp.state.eq(m_state.dat_r),
                Case(phase, {
                    0: dsp.accu_clr.eq(1),
                    2: [
                        offset_clr.eq(1),
                        dsp.offset_load.eq(1)
                    ],
                    3: dsp.offset_load.eq(1)
                })
        ]

        # selected adc (combinatorial from dat_r)
        sel_profile = Signal(w.channel)
        # profile delay (combinatorial from dat_r)
        dly_profile = Signal(8)

        # latched adc selection
        sel = Signal(w.channel, reset_less=True)
        # iir enable SR
        en = Signal(2, reset_less=True)

        assert w.channel <= 8
        assert w.profile <= len(dly_profile)
        assert w.profile + 8 <= len(m_coeff.dat_r)

        self.comb += [
                sel_profile.eq(m_coeff.dat_r[w.coeff:]),
                dly_profile.eq(m_coeff.dat_r[w.coeff + 8:]),
                If(self.shifting,
                    m_state.adr.eq(state | (1 << w.profile + w.channel)),
                    m_state.dat_w.eq(m_state.dat_r),
                    m_state.we.eq(state[0])
                ),
                If(self.loading,
                    m_state.adr.eq((state << 1) | (1 << w.profile + w.channel)),
                    m_state.dat_w[-w.adc - 1:-1].eq(Array(self.adc)[state]),
                    m_state.dat_w[-1].eq(m_state.dat_w[-2]),
                    m_state.we.eq(1)
                ),
                If(self.processing,
                    m_state.adr.eq(Array([
                        # write back y
                        Cat(profile[1], channel[2]),
                        # old y
                        Cat(profile[0], channel[0]),
                        # x0 (recent)
                        0 | (sel_profile << 1) | (1 << w.profile + w.channel),
                        # x1 (old)
                        1 | (sel << 1) | (1 << w.profile + w.channel),
                    ])[phase]),
                    m_state.dat_w.eq(dsp.output),
                    m_state.we.eq((phase == 0) & stage[2] & en[1]),
                )
        ]

        # internal channel delay counters
        dlys = Array([Signal(len(dly_profile))
            for i in range(1 << w.channel)])
        self._dlys = dlys  # expose for debugging only
        # latched channel delay
        dly = Signal(len(dly_profile), reset_less=True)
        # latched channel en_out
        en_out = Signal(reset_less=True)
        # latched channel en_iir
        en_iir = Signal(reset_less=True)
        # muxing
        ddss = Array(self.dds)

        self.sync += [
                Case(phase, {
                    0: [
                        dly.eq(dlys[channel[0]]),
                        en_out.eq(en_outs[channel[0]]),
                        en_iir.eq(en_iirs[channel[0]]),
                        If(stage[1],
                            ddss[channel[1]][:w.word].eq(
                                m_coeff.dat_r),
                        )
                    ],
                    1: [
                        If(stage[1],
                            ddss[channel[1]][w.word:2*w.word].eq(
                                m_coeff.dat_r),
                        ),
                        If(stage[2],
                            ddss[channel[2]][3*w.word:].eq(
                                m_state.dat_r[w.state - w.asf - 1:w.state - 1])
                        )
                    ],
                    2: [
                        en[0].eq(0),
                        en[1].eq(en[0]),
                        sel.eq(sel_profile),
                        If(stage[0],
                            ddss[channel[0]][2*w.word:3*w.word].eq(
                                m_coeff.dat_r),
                            If(en_out,
                                If(dly != dly_profile,
                                    dlys[channel[0]].eq(dly + 1)
                                ).Elif(en_iir,
                                    en[0].eq(1)
                                )
                            )
                        )
                    ],
                    3: [
                    ],
                }),
        ]

    def _coeff(self, channel, profile, coeff):
        w = self.widths
        addr = "ftw1 b1 pow cfg offset a1 ftw0 b0".split().index(coeff)
        coeff_addr = ((channel << w.profile + 2) | (profile << 2) |
                (addr >> 1))
        mask = (1 << w.coeff) - 1
        return addr & 1, coeff_addr, mask

    def set_coeff(self, channel, profile, coeff, value):
        w = self.widths
        word, addr, mask = self._coeff(channel, profile, coeff)
        val = yield self.m_coeff[addr]
        if word:
            val = (val & mask) | ((value & mask) << w.coeff)
        else:
            val = (value & mask) | (val & (mask << w.coeff))
        yield self.m_coeff[addr].eq(val)

    def get_coeff(self, channel, profile, coeff):
        w = self.widths
        word, addr, mask = self._coeff(channel, profile, coeff)
        val = yield self.m_coeff[addr]
        if word:
            return val >> w.coeff
        else:
            return val & mask
        if val in "offset a1 b0 b1".split():
            val = signed(val, w.coeff)
        return val

    def set_state(self, channel, val, profile=None, coeff="y1"):
        w = self.widths
        if coeff == "y1":
            assert profile is not None
            yield self.m_state[profile | (channel << w.profile)].eq(val)
        elif coeff == "x0":
            assert profile is None
            yield self.m_state[(channel << 1) |
                    (1 << w.profile + w.channel)].eq(val)
        elif coeff == "x1":
            assert profile is None
            yield self.m_state[1 | (channel << 1) |
                    (1 << w.profile + w.channel)].eq(val)
        else:
            raise ValueError("no such state", coeff)

    def get_state(self, channel, profile=None, coeff="y1"):
        w = self.widths
        if coeff == "y1":
            val = yield self.m_state[profile | (channel << w.profile)]
        elif coeff == "x0":
            val = yield self.m_state[(channel << 1) |
                    (1 << w.profile + w.channel)]
        elif coeff == "x1":
            val = yield self.m_state[1 | (channel << 1) |
                    (1 << w.profile + w.channel)]
        else:
            raise ValueError("no such state", coeff)
        return signed(val, w.state)

    def fast_iter(self):
        assert (yield self.done)
        yield self.start.eq(1)
        yield
        yield self.start.eq(0)
        yield
        while not (yield self.done):
            yield

    def check_iter(self):
        w = self.widths

        while not (yield self.done):
            yield

        yield self.start.eq(1)
        yield
        yield self.start.eq(0)
        yield
        assert not (yield self.done)
        assert (yield self.loading)
        while (yield self.loading):
            yield

        x0s = []
        # check adc loading
        for i in range(1 << w.channel):
            v_adc = signed((yield self.adc[i]), w.adc)
            x0 = yield from self.get_state(i, coeff="x0")
            x0s.append(x0)
            assert v_adc << (w.state - w.adc) == x0, (hex(v_adc), hex(x0))
            logger.debug("adc[%d] adc=%x x0=%x", i, v_adc, x0)

        data = []
        # predict output
        for i in range(1 << w.channel):
            j = yield self.ctrl[i].profile
            en_iir = yield self.ctrl[i].en_iir
            en_out = yield self.ctrl[i].en_out
            dly_i = yield self._dlys[i]
            logger.debug("ctrl[%d] profile=%d en_iir=%d en_out=%d dly=%d",
                    i, j, en_iir, en_out, dly_i)

            cfg = yield from self.get_coeff(i, j, "cfg")
            k_j = cfg & ((1 << w.channel) - 1)
            dly_j = (cfg >> 8) & 0xff
            logger.debug("cfg[%d,%d] sel=%d dly=%d", i, j, k_j, dly_j)

            en = en_iir & en_out & (dly_i >= dly_j)
            logger.debug("en[%d,%d] %d", i, j, en)

            offset = yield from self.get_coeff(i, j, "offset")
            offset <<= w.state - w.coeff
            a1 = yield from self.get_coeff(i, j, "a1")
            b0 = yield from self.get_coeff(i, j, "b0")
            b1 = yield from self.get_coeff(i, j, "b1")
            logger.debug("coeff[%d,%d] offset=%#x a1=%#x b0=%#x b1=%#x",
                    i, j, offset, a1, b0, b1)

            ftw0 = yield from self.get_coeff(i, j, "ftw0")
            ftw1 = yield from self.get_coeff(i, j, "ftw1")
            pow = yield from self.get_coeff(i, j, "pow")
            logger.debug("dds[%d,%d] ftw0=%#x ftw1=%#x pow=%#x",
                    i, j, ftw0, ftw1, pow)

            y1 = yield from self.get_state(i, j, "y1")
            x1 = yield from self.get_state(k_j, coeff="x1")
            x0 = yield from self.get_state(k_j, coeff="x0")
            logger.debug("state y1[%d,%d]=%#x x0[%d]=%#x x1[%d]=%#x",
                    i, j, y1, k_j, x0, k_j, x1)

            p = (0*(1 << w.shift - 1) + a1*(0 - y1) +
                    b0*(offset - x0) + b1*(offset - x1))
            out = p >> w.shift
            y0 = min(max(0, out), (1 << w.state - 1) - 1)
            logger.debug("dsp[%d,%d] p=%#x out=%#x y0=%#x",
                    i, j, p, out, y0)

            if not en:
                y0 = y1
            data.append((ftw0, ftw1, pow, y0, x1, x0))

        # wait for output
        assert (yield self.processing)
        while (yield self.processing):
            yield

        assert (yield self.shifting)
        while (yield self.shifting):
            yield

        # check x shifting
        for i, x0 in enumerate(x0s):
            x1 = yield from self.get_state(i, coeff="x1")
            assert x1 == x0, (hex(x1), hex(x0))
            logger.debug("adc[%d] x0=%x x1=%x", i, x0, x1)

        # check new state
        for i in range(1 << w.channel):
            j = yield self.ctrl[i].profile
            logger.debug("ch[%d] profile=%d", i, j)
            y1 = yield from self.get_state(i, j, "y1")
            ftw0, ftw1, pow, y0, x1, x0 = data[i]
            assert y1 == y0, (hex(y1), hex(y0))

        # check dds output
        for i in range(1 << w.channel):
            ftw0, ftw1, pow, y0, x1, x0 = data[i]
            asf = y0 >> (w.state - w.asf - 1)
            dds = (ftw0 | (ftw1 << w.word) |
                    (pow << 2*w.word) | (asf << 3*w.word))
            dds_state = yield self.dds[i]
            logger.debug("ch[%d] dds_state=%#x dds=%#x", i, dds_state, dds)
            assert dds_state == dds, [hex(_) for _ in
                    (dds_state, asf, pow, ftw1, ftw0)]

        assert (yield self.done)
        return data
