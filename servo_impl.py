from migen import *
from migen.build.generic_platform import *
from migen.genlib import io

import impl, servo


class Top(impl.Impl):
    def __init__(self, plat):
        super().__init__(plat, clk=200e6)
        adc_p = servo.ADCParams(width=16, channels=8, lanes=4,
                t_cnvh=4, t_conv=57, t_rtt=4)
        iir_p = servo.IIRWidths(state=25, coeff=18, adc=16,
                asf=14, word=16, accu=48, shift=11,
                channel=3, profile=5)
        dds_p = servo.DDSParams(width=8 + 32 + 16 + 16,
                channels=adc_p.channels, clk=1)

        adc_pads = plat.request("adc_ser")
        dds_pads = plat.request("dds_ser")

        self.submodules.servo = servo.Servo(adc_pads, dds_pads,
                adc_p, iir_p, dds_p)

        plat.add_period_constraint(adc_pads.clkout_p,
                plat.default_clk_period)
        plat.add_false_path_constraints(
                plat.lookup_request(plat.default_clk_name),
                adc_pads.clkout_p)

        m_coeff = self.servo.iir.m_coeff.get_port(write_capable=True)
        m_state = self.servo.iir.m_state.get_port(write_capable=True)
        self.specials += m_coeff, m_state
        ins = [
                m_state.adr, m_state.we, m_state.dat_w,
                m_coeff.adr, m_coeff.we, m_coeff.dat_w,
                self.servo.start]
        for ctrl in self.servo.iir.ctrl:
            ins += ctrl.flatten()
        self.dummy_inputs(ins, 1)

        outs = [m_state.dat_r, m_coeff.dat_r]
        self.dummy_outputs(outs, self.servo.dds.done)


if __name__ == "__main__":
    plat = impl.Platform()
    top = Top(plat)
    plat.build(top)
