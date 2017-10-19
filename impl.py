from migen import *
from migen.build.generic_platform import *
from migen.genlib import io
from migen.build.platforms.sinara.kasli import Platform


class Impl(Module):
    def __init__(self, plat, clk=150e6):
        self.platform = plat
        plat.default_clk_period = 1e9/clk
        plat.constraint_manager.available.extend([
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
                ),

                ("dds_ser", 0,
                    Subsignal("clk_p", Pins("J19"), IOStandard("LVDS_25")),
                    Subsignal("clk_n", Pins("H19"), IOStandard("LVDS_25")),

                    Subsignal("cs_n_p", Pins("N20"), IOStandard("LVDS_25")),
                    Subsignal("cs_n_n", Pins("M20"), IOStandard("LVDS_25")),

                    Subsignal("io_update_p", Pins("K13"), IOStandard("LVDS_25")),
                    Subsignal("io_update_n", Pins("K14"), IOStandard("LVDS_25")),

                    Subsignal("mosi0_p", Pins("H13"), IOStandard("LVDS_25")),
                    Subsignal("mosi0_n", Pins("G13"), IOStandard("LVDS_25")),
                    Subsignal("mosi1_p", Pins("G15"), IOStandard("LVDS_25")),
                    Subsignal("mosi1_n", Pins("G16"), IOStandard("LVDS_25")),
                    Subsignal("mosi2_p", Pins("J14"), IOStandard("LVDS_25")),
                    Subsignal("mosi2_n", Pins("H14"), IOStandard("LVDS_25")),
                    Subsignal("mosi3_p", Pins("G17"), IOStandard("LVDS_25")),
                    Subsignal("mosi3_n", Pins("G18"), IOStandard("LVDS_25")),
                    Subsignal("mosi4_p", Pins("J15"), IOStandard("LVDS_25")),
                    Subsignal("mosi4_n", Pins("H15"), IOStandard("LVDS_25")),
                    Subsignal("mosi5_p", Pins("H17"), IOStandard("LVDS_25")),
                    Subsignal("mosi5_n", Pins("H18"), IOStandard("LVDS_25")),
                    Subsignal("mosi6_p", Pins("J22"), IOStandard("LVDS_25")),
                    Subsignal("mosi6_n", Pins("H22"), IOStandard("LVDS_25")),
                    Subsignal("mosi7_p", Pins("L19"), IOStandard("LVDS_25")),
                    Subsignal("mosi7_n", Pins("L20"), IOStandard("LVDS_25")),
                )
        ])

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
