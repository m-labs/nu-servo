from migen import *

import iir, arty, impl

class Top(impl.Impl):
    def __init__(self, plat):
        super().__init__(plat, clk=150e6)
        w = iir.IIRWidths(state=25, coeff=18, adc=16,
                asf=14, word=16, accu=48, shift=11,
                channel=3, profile=5)

        top = iir.IIR(w)
        self.submodules += top

        m_coeff = top.m_coeff.get_port(write_capable=True)
        m_state = top.m_state.get_port(write_capable=True)
        self.specials += m_coeff, m_state

        ins = [
                m_state.adr, m_state.we, m_state.dat_w,
                m_coeff.adr, m_coeff.we, m_coeff.dat_w,
                top.start] + top.adc
        for ctrl in top.ctrl:
            ins += ctrl.flatten()
        self.dummy_inputs(ins, top.start)

        outs = [top.shifting, top.loading, top.processing, top.done,
                m_state.dat_r, m_coeff.dat_r] + top.dds
        self.dummy_outputs(outs, top.done)


if __name__ == "__main__":
    plat = arty.Platform()
    top = Top(plat)
    plat.build(top)
