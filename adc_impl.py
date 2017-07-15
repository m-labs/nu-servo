from migen import *
from migen.build.generic_platform import *
from migen.genlib import io

import adc_ser, arty, impl


class Top(impl.Impl):
    def __init__(self, plat):
        super().__init__(plat, clk=250e6)
        params = adc_ser.ADCParams(width=16, channels=8,
                t_cnvh=4, t_conv=57, t_rtt=4)
        self.submodules.adc = adc = adc_ser.ADC(
                plat.request("adc_ser"), params)

        self.dummy_inputs([adc.start], 1)
        self.dummy_outputs([adc.done, adc.reading] + adc.data, adc.done)


if __name__ == "__main__":
    plat = arty.Platform()
    top = Top(plat)
    plat.build(top)
