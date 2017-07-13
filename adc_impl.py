from migen import *
from migen.build.generic_platform import *
from migen.genlib import io

import adc_ser, arty


class Top(Module):
    def __init__(self, plat):
        plat.constraint_manager.available.append(
                ("adc_ser", 0,
                    Subsignal("sck_p", Pins("G13"), IOStandard("LVDS")),
                    Subsignal("sck_n", Pins("B11"), IOStandard("LVDS")),
                    Subsignal("clkout_p", Pins("A11"), IOStandard("LVDS")),
                    Subsignal("clkout_n", Pins("D12"), IOStandard("LVDS")),
                    Subsignal("cnv_b", Pins("D13"), IOStandard("LVCMOS33")),
                    Subsignal("sdoa_p", Pins("E15"), IOStandard("LVDS")),
                    Subsignal("sdoa_n", Pins("E16"), IOStandard("LVDS")),
                    Subsignal("sdob_p", Pins("D15"), IOStandard("LVDS")),
                    Subsignal("sdob_n", Pins("D15"), IOStandard("LVDS")),
                    Subsignal("sdoc_p", Pins("J17"), IOStandard("LVDS")),
                    Subsignal("sdoc_n", Pins("J18"), IOStandard("LVDS")),
                    Subsignal("sdod_p", Pins("J15"), IOStandard("LVDS")),
                    Subsignal("sdod_n", Pins("J15"), IOStandard("LVDS")),
                )
        )

        clk = plat.request(plat.default_clk_name)
        self.submodules += io.CRG(clk)
        # plat.add_period_constraint(clk, plat.default_clk_period)
        # del plat.default_clk_period

        params = adc_ser.ADCParams(width=16, channels=8,
                t_cnvh=4, t_conv=57, t_rtt=4)
        self.submodules.adc = adc = adc_ser.ADC(
                plat.request("adc_ser"), params)


def main():
    plat = arty.Platform()
    plat.default_clk_period = 1000/150
    top = Top(plat)
    plat.build(top)


if __name__ == "__main__":
    main()
