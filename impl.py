from migen import *
from migen.build.generic_platform import *
from migen.genlib import io

import arty


class Impl(Module):
    def __init__(self, plat, clk=150e6):
        self.platform = plat
        plat.default_clk_period = 1e9/clk
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

    def dummy_inputs(self, ins, load):
        sr_in = Signal(len(Cat(ins)), reset_less=True)
        but = self.platform.request("user_btn")
        x = Signal(reset_less=True)
        self.sync += [
                x.eq(but),
                sr_in.eq(Cat(x, sr_in)),
                If(load,
                    Cat(ins).eq(sr_in)
                )
        ]

    def dummy_outputs(self, outs, load):
        sr_out = Signal(len(Cat(outs)), reset_less=True)
        led = self.platform.request("user_led")
        self.sync += [
                Cat(led, sr_out).eq(sr_out),
                If(load,
                    sr_out.eq(Cat(outs))
                )
        ]
