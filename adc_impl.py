from migen import *
from migen.build.generic_platform import *
from migen.genlib import io

from artiq.gateware.suservo import adc_ser

import impl


class Top(impl.Impl):
    def __init__(self, plat):
        super().__init__(plat, clk=250e6)
        params = adc_ser.ADCParams(width=16, channels=8, lanes=4,
                t_cnvh=4, t_conv=57, t_rtt=4)

        adc_pads = plat.request("adc_ser")
        self.submodules.adc = adc = adc_ser.ADC(adc_pads, params)

        plat.add_period_constraint(adc_pads.clkout_p,
                plat.default_clk_period)
        plat.add_false_path_constraints(
                plat.lookup_request(plat.default_clk_name),
                adc_pads.clkout_p)

        self.dummy_inputs([adc.start], 1)
        self.dummy_outputs([adc.done, adc.reading] + adc.data, adc.done)


if __name__ == "__main__":
    plat = impl.Platform()
    top = Top(plat)
    plat.build(top)
