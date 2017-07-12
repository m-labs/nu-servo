from migen import *

import iir, arty


class Servo(Module):
    def __init__(self, plat):
        w = iir.IIRWidths(state=25, coeff=18, adc=16,
                asf=14, word=16, accu=48, shift=11,
                channel=3, profile=5)

        top = iir.IIR(w)
        self.submodules += top

        m_coeff = top.m_coeff.get_port(write_capable=True)
        m_state = top.m_state.get_port()
        self.specials += m_coeff, m_state

        # wire dummy SRs to inputs and outputs to prevent optimization

        ins = [
                m_state.adr, # m_state.we, m_state.dat_w,
                m_coeff.adr, m_coeff.we, m_coeff.dat_w,
                ] + top.adc
        for ctrl in top.ctrl:
            ins += ctrl.flatten()

        outs = [top.shifting, top.loading, top.processing, top.done,
                m_state.dat_r, m_coeff.dat_r] + top.dds

        sr0 = Signal(len(Cat(ins)), reset_less=True)
        sr1 = Signal(len(Cat(outs)), reset_less=True)
        led = plat.request("user_led")
        but = plat.request("user_btn")
        x = Signal(reset_less=True)
        self.sync += [
                x.eq(but),

                top.start.eq(x),

                sr0[0].eq(x),
                sr0[1:].eq(sr0),
                If(top.done,
                    Cat(ins).eq(sr0)
                ),

                led.eq(sr1[0]),
                sr1.eq(sr1[1:]),
                If(top.done,
                    sr1.eq(Cat(outs)),
                ),
        ]


def main():
    plat = arty.Platform()
    plat.default_clk_period = 1000/150
    top = Servo(plat)
    plat.build(top)


if __name__ == "__main__":
    main()
