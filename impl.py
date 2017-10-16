from migen import *
from migen.build.generic_platform import *
from migen.genlib import io
from migen.build.platforms.sinara.kasli import Platform


class Impl(Module):
    def __init__(self, plat, clk=150e6):
        self.platform = plat
        plat.default_clk_period = 1e9/clk
        plat.constraint_manager.available.append(
                ("adc_ser", 0,
                    Subsignal("sck_p", Pins("V4"), IOStandard("LVDS_25")),
                    Subsignal("sck_n", Pins("W4"), IOStandard("LVDS_25")),

                    # clock-capable!
                    Subsignal("clkout_p", Pins("R4"), IOStandard("LVDS_25")),
                    Subsignal("clkout_n", Pins("T4"), IOStandard("LVDS_25")),

                    Subsignal("cnv_b", Pins("T1"), IOStandard("LVCMOS25")),

                    Subsignal("sdoa_p", Pins("R3"), IOStandard("LVDS_25")),
                    Subsignal("sdoa_n", Pins("R2"), IOStandard("LVDS_25")),
                    Subsignal("sdob_p", Pins("W2"), IOStandard("LVDS_25")),
                    Subsignal("sdob_n", Pins("Y2"), IOStandard("LVDS_25")),
                    Subsignal("sdoc_p", Pins("W1"), IOStandard("LVDS_25")),
                    Subsignal("sdoc_n", Pins("Y1"), IOStandard("LVDS_25")),
                    Subsignal("sdod_p", Pins("U3"), IOStandard("LVDS_25")),
                    Subsignal("sdod_n", Pins("V3"), IOStandard("LVDS_25")),
                )
        )

        clk = plat.request(plat.default_clk_name)
        self.submodules.crg = io.CRG(clk)

    def dummy_inputs(self, ins, load):
        sr_in = Signal(len(Cat(ins)), reset_less=True)
        but = self.platform.request("clk_sel")
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
