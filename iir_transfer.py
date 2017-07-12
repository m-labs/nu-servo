import logging

import numpy as np
import matplotlib.pyplot as plt
from migen import *

import iir


def drive(dut, x, y, cfg=None):
    if cfg is not None:
        yield from cfg
    for i, xi in enumerate(x):
        yield dut.adc[0].eq(int(xi))
        # yield from dut.check_iter()
        yield from dut.fast_iter()
        dds = yield dut.dds[0]
        asf = dds >> 3*dut.widths.word
        y[i] = asf
        # yi = yield from dut.get_state(0, 0, "y1")
        # y[i] = yi


def drive_uni(dut, samples=1<<10, amplitude=1., seed=None, cfg=None):
    if seed is not None:
        np.random.seed(seed)
    v = (1 << dut.widths.adc - 1) - 1
    w = (1 << dut.widths.asf) - 1
    x = np.round(np.random.uniform(
        -amplitude*v, amplitude*v, samples)).astype(np.int64)
    y = np.empty_like(x)
    run_simulation(dut, [drive(dut, x, y, cfg)],
            vcd_name="iir_transfer.vcd")
    return x/-v, y/w


def analyze(x, y, log=False):
    fig, ax = plt.subplots(3)
    ax[0].plot(x, "c-.", label="input")
    ax[0].plot(y, "r-", label="output")
    ax[0].legend(loc="right")
    ax[0].set_xlabel("time (1/fs)")
    ax[0].set_ylabel("signal")
    x = x - np.mean(x)
    y = y - np.mean(y)
    n = len(x)
    # w = np.hanning(n)
    # x = (x.reshape(-1, n)*w).sum(0)
    # y = (y.reshape(-1, n)*w).sum(0)
    t = (np.fft.rfft(y)/np.fft.rfft(x))
    f = np.fft.rfftfreq(n)
    fmin = f[1]
    ax[1].plot(f,  20*np.log10(np.abs(t)), "r-")
    # ax[1].set_ylim(-70, 3)
    ax[1].set_xlim(fmin, .5)
    if log:
        ax[1].set_xscale("log")
    ax[1].set_xlabel("frequency (fs)")
    ax[1].set_ylabel("magnitude (dB)")
    ax[1].grid(True)
    ax[2].plot(f,  np.rad2deg(np.angle(t)), "r-")
    ax[2].set_xlim(fmin, .5)
    if log:
        ax[2].set_xscale("log")
    ax[2].set_xlabel("frequency (fs)")
    ax[2].set_ylabel("phase (deg)")
    ax[2].grid(True)
    return fig


def f2i(f, width, shift):
    i = int(round(f*(1 << shift)))
    k = 1 << width - 1
    assert -k <= i <= k - 1, (f, width, shift, hex(i), hex(k))
    return i


def pi_iir(widths, f, k, g=np.inf):
    # transfer function: H(s) = k*(s/(2*pi*f) + 1)/(s/(2*pi*f) + 1/g)
    # g=inf, H(s) = k*(s/w + 1)/(s/w) = k*(1 + w/s) = k + k*2*pi*f/s
    # f: integrator corner a.k.a. P zero (in units of fs)
    # k: P gain
    # g: I gain limit

    # H1(s) = k + m/s
    # k [2e-2, 2e1]
    # f [2e-2, 2e-1]
    # m=k*2*pi*f [1e-3, 1e1]
    f *= np.pi
    z = f/g + 1
    a1 = f2i((f/g - 1)/z, widths.coeff, widths.shift)
    b0 = f2i(k*(f + 1)/z, widths.coeff, widths.shift + 1)  # pre-adder
    b1 = f2i(k*(f - 1)/z, widths.coeff, widths.shift + 1)  # pre-adder
    return a1, b0, b1


def main():
    w = iir.IIRWidths(state=25, coeff=18, adc=16,
            asf=14, word=16, accu=48, shift=11,
            channel=1, profile=1)
    dut = iir.IIR(w)

    def cfg(dut):
        w = dut.widths
        ch = 0
        pr = 0
        yield dut.ctrl[ch].en_iir.eq(1)
        yield dut.ctrl[ch].en_out.eq(1)
        yield dut.ctrl[ch].profile.eq(pr)
        yield from dut.set_state(ch, 0, coeff="x1")
        yield from dut.set_state(ch, 0, coeff="x0")
        a1 = -(1 << w.coeff - 3)
        b0 = 1 << w.coeff - 3
        b1 = b0
        offset = 1 << w.coeff - 2
        y1 = offset

        # a1, b0, b1 = pi_iir(w, f=.2, k=.1)
        # a1, b0, b1 = pi_iir(w, f=.3, k=15.9)
        a1, b0, b1 = pi_iir(w, f=.005, k=.01)
        y1 = f2i(.5, w.state, w.state - 1)
        offset = 0
        print([hex(_) for _ in (offset, y1, a1, b0, b1)])
        yield from dut.set_state(ch, y1, profile=pr, coeff="y1")
        yield from dut.set_coeff(ch, pr, "cfg",
                        (ch << 0) | (0 << 8))
        yield from dut.set_coeff(ch, pr, "a1", a1)
        yield from dut.set_coeff(ch, pr, "b0", b0)
        yield from dut.set_coeff(ch, pr, "b1", b1)
        yield
        yield from dut.set_coeff(ch, pr, "offset", offset)
        yield

    x, y = drive_uni(dut, samples=1<<8, amplitude=.8, seed=0x123,
            cfg=cfg(dut))
    analyze(x, y, log=True)
    plt.show()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
