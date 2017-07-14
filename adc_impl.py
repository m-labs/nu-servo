from migen import *
from migen.build.generic_platform import *
from migen.genlib import io

import adc_ser, arty


class Top(Module):
    def __init__(self, plat):
        # build a makeshift ADC interface out of PMODs
        plat.constraint_manager.available.append(
                ("adc_ser", 0,
                    Subsignal("sck_p", Pins("E15"), IOStandard("LVDS_25")),
                    Subsignal("sck_n", Pins("E16"), IOStandard("LVDS_25")),

                    # clock-capable!
                    Subsignal("clkout_p", Pins("D15"), IOStandard("LVDS_25")),
                    Subsignal("clkout_n", Pins("C15"), IOStandard("LVDS_25")),

                    Subsignal("cnv_b", Pins("T10"), IOStandard("LVCMOS25")),

                    Subsignal("sdoa_p", Pins("U12"), IOStandard("LVDS_25")),
                    Subsignal("sdoa_n", Pins("V12"), IOStandard("LVDS_25")),
                    Subsignal("sdob_p", Pins("V10"), IOStandard("LVDS_25")),
                    Subsignal("sdob_n", Pins("V11"), IOStandard("LVDS_25")),
                    Subsignal("sdoc_p", Pins("U14"), IOStandard("LVDS_25")),
                    Subsignal("sdoc_n", Pins("V14"), IOStandard("LVDS_25")),
                    Subsignal("sdod_p", Pins("T13"), IOStandard("LVDS_25")),
                    Subsignal("sdod_n", Pins("U13"), IOStandard("LVDS_25")),
                )
        )

        clk = plat.request(plat.default_clk_name)
        self.submodules += io.CRG(clk)

        params = adc_ser.ADCParams(width=16, channels=8,
                t_cnvh=4, t_conv=57, t_rtt=4)
        self.submodules.adc = adc = adc_ser.ADC(
                plat.request("adc_ser"), params)

        outs = adc.data
        sr1 = Signal(len(Cat(outs)), reset_less=True)
        led = plat.request("user_led")
        but = plat.request("user_btn")
        x = Signal(reset_less=True)
        self.sync += [
                x.eq(but),

                adc.start.eq(x),

                led.eq(sr1[0]),
                sr1.eq(sr1[1:]),
                If(adc.done,
                    sr1.eq(Cat(outs)),
                ),
        ]


def main():
    plat = arty.Platform()
    plat.default_clk_period = 1000/250
    top = Top(plat)
    plat.build(top)


if __name__ == "__main__":
    main()
