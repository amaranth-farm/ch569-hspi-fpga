from amaranth         import *
from amaranth.lib.cdc import ResetSynchronizer

from amaranth.build import *
from amaranth.vendor.lattice_ecp5 import *

from amaranth_boards.resources         import *
from amaranth_boards.colorlight_i5     import ColorLightI5Platform
from amaranth_boards.colorlight_i9     import ColorLightI9Platform
from amaranth_boards.colorlight_qmtech import ColorlightQMTechPlatform

from luna.gateware.platform.core       import LUNAPlatform

class ColorlightDomainGenerator(Elaboratable):
    """ Clock generator for the Colorlight I5/I9 board. """
    def __init__(self, clock_frequencies=None):
        pass

    def elaborate(self, platform):
        m = Module()

        # Create our domains.
        m.domains.sync   = ClockDomain("sync")
        m.domains.usb    = ClockDomain("usb")
        m.domains.hspi   = ClockDomain("hspi")


        # Grab our clock and global reset signals.
        clk25 = platform.request(platform.default_clk)

        main_locked   = Signal()
        hspi_locked   = Signal()
        reset         = Signal()

        # USB PLL
        main_feedback    = Signal()
        m.submodules.main_pll = Instance("EHXPLLL",
                # Status.
                o_LOCK=main_locked,

                # PLL parameters...
                p_PLLRST_ENA="DISABLED",
                p_INTFB_WAKE="DISABLED",
                p_STDBY_ENABLE="DISABLED",
                p_DPHASE_SOURCE="DISABLED",
                p_OUTDIVIDER_MUXA="DIVA",
                p_OUTDIVIDER_MUXB="DIVB",
                p_OUTDIVIDER_MUXC="DIVC",
                p_OUTDIVIDER_MUXD="DIVD",

                # 60 MHz
                p_CLKI_DIV = 5,
                p_CLKOP_ENABLE = "ENABLED",
                p_CLKOP_DIV = 10,
                p_CLKOP_CPHASE = 15,
                p_CLKOP_FPHASE = 0,

                p_FEEDBK_PATH = "CLKOP",
                p_CLKFB_DIV = 12,

                # Clock in.
                i_CLKI=clk25,

                # Internal feedback.
                i_CLKFB=main_feedback,

                # Control signals.
                i_RST=reset,
                i_PHASESEL0=0,
                i_PHASESEL1=0,
                i_PHASEDIR=1,
                i_PHASESTEP=1,
                i_PHASELOADREG=1,
                i_STDBY=0,
                i_PLLWAKESYNC=0,

                # Output Enables.
                i_ENCLKOP=0,

                # Generated clock outputs.
                o_CLKOP=main_feedback,

                # Synthesis attributes.
                a_FREQUENCY_PIN_CLKI="25",
                a_FREQUENCY_PIN_CLKOP="60",

                a_ICP_CURRENT="6",
                a_LPF_RESISTOR="16",
                a_MFG_ENABLE_FILTEROPAMP="1",
                a_MFG_GMCREF_SEL="2"
        )

        # HSPI PLL
        hspi_clocks = platform.request("hspi-clocks", 0)
        hspi_feedback = Signal()
        m.submodules.hspi_pll = Instance("EHXPLLL",
                # Status.
                o_LOCK=hspi_locked,

                # PLL parameters...
                p_PLLRST_ENA="DISABLED",
                p_INTFB_WAKE="DISABLED",
                p_STDBY_ENABLE="DISABLED",
                p_DPHASE_SOURCE="DISABLED",
                p_OUTDIVIDER_MUXA="DIVA",
                p_OUTDIVIDER_MUXB="DIVB",
                p_OUTDIVIDER_MUXC="DIVC",
                p_OUTDIVIDER_MUXD="DIVD",

                p_CLKI_DIV = 1,

                p_CLKOP_ENABLE = "ENABLED",
                p_CLKOP_DIV = 10,
                p_CLKOP_CPHASE = 15,
                p_CLKOP_FPHASE = 0,

                p_FEEDBK_PATH = "CLKOP",
                p_CLKFB_DIV = 1,

                # Clock in.
                i_CLKI=hspi_clocks.rx_clk,

                # Internal feedback.
                i_CLKFB=hspi_feedback,

                # Control signals.
                i_RST=reset,
                i_PHASESEL0=0,
                i_PHASESEL1=0,
                i_PHASEDIR=1,
                i_PHASESTEP=1,
                i_PHASELOADREG=1,
                i_STDBY=0,
                i_PLLWAKESYNC=0,

                # Output Enables.
                i_ENCLKOP=0,

                # Generated clock outputs.
                o_CLKOP=hspi_feedback,

                # Synthesis attributes.
                a_FREQUENCY_PIN_CLKI="60",
                a_FREQUENCY_PIN_CLKOP="60",

                a_ICP_CURRENT="6",
                a_LPF_RESISTOR="16",
                a_MFG_ENABLE_FILTEROPAMP="1",
                a_MFG_GMCREF_SEL="2"
        )


        reset = Signal()
        # Control our resets.
        m.d.comb += [
            ClockSignal("usb")     .eq(main_feedback),
            ClockSignal("sync")    .eq(ClockSignal("usb")),
            ClockSignal("hspi")    .eq(hspi_feedback),

            reset.eq(~(main_locked)),
        ]

        led = platform.request("led", 0)
        m.d.comb += [
            led.eq(~hspi_locked),
        ]

        m.submodules.reset_sync_hspi = ResetSynchronizer(reset, domain="hspi")
        m.submodules.reset_sync_usb  = ResetSynchronizer(reset, domain="usb")
        m.submodules.reset_sync_sync = ResetSynchronizer(reset, domain="sync")

        return m


GND       = None
left_row  = list(range(7, 60, 2))
right_row = list(range(8, 61, 2))

btb_upper = [None,   None,   GND, "HD12",   "HD13",  "HD14",  "HD15",
                             GND, "HD16",   "HD17",  "HD18",  "HD19",
                             GND, "HD20",   "HD21",  "HD22",  "HD23",
                             GND, "HD24",   "HD25",  "HD26",  "HD27",
                             GND, "HD28",   "HD29",  "HD30",  "HD31"]

btb_lower = ["HD10", "HD11", GND, "HRCLK", "HRACT", "HRVLD", "HTRDY",
                             GND, "HD0",     "HD1",   "HD2",   "HD3",
                             GND, "HD4",     "HD5",   "HD6",   "HD7",
                             GND, "HD8",     "HD9", "HTVLD", "HTREQ",
                             GND, "HTACK", "HTCLK"]

left        = list(zip(btb_upper, left_row))
right       = list(zip(btb_lower, right_row))
pinmap      = dict(filter(lambda t: t[0] != None, left + right))
hd_pins     = " ".join([f"J_2:{pinmap[pin]}" for pin in [f"HD{i}" for i in range(0, 32)]])
control_pin = lambda pin: "J_2:" + str(pinmap[pin])

class ColorlightHSPIPlatform(ColorlightQMTechPlatform, LUNAPlatform):
    clock_domain_generator = ColorlightDomainGenerator
    default_usb_connection = "ulpi"
    ignore_phy_vbus = False

    def __init__(self) -> None:
        colorlight = ColorLightI5Platform

        colorlight.resources += [
            *ButtonResources(pins="R1", attrs=Attrs(IO_TYPE="LVCMOS33")),
            # HSPI
            Resource("hspi", 0,
                Subsignal("hd",        Pins(hd_pins, dir="io")),

                Subsignal("tx_ack",    Pins(control_pin('HTRDY'), dir="o")),
                Subsignal("tx_ready",  Pins(control_pin('HTACK'), dir="i")),

                Subsignal("tx_req",    Pins(control_pin('HRACT'), dir="o")),
                Subsignal("rx_act",    Pins(control_pin('HTREQ'), dir="i")),

                Subsignal("tx_valid",  Pins(control_pin('HRVLD'), dir="o")),
                Subsignal("rx_valid",  Pins(control_pin('HTVLD'), dir="i")),
                Attrs(IO_TYPE="LVCMOS33")
            ),
            Resource("hspi-clocks", 0,
                Subsignal("tx_clk",    Pins(control_pin('HRCLK'), dir="o")),
                Subsignal("rx_clk",    Pins(control_pin('HTCLK'), dir="i")),
                Attrs(IO_TYPE="LVCMOS33")
            ),

            # HSPI Slave wiring (Master connected on pinmap)
            Resource("ulpi", 0,
                Subsignal("reset",   Pins("J_3:9", dir="o", invert=True), Attrs(IO_TYPE="LVCMOS33")),
                Subsignal("clk",     Pins("J_3:10", dir="o"), Attrs(IO_TYPE="LVCMOS33", DRIVE="4")),
                Subsignal("stp",     Pins("J_3:11", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
                Subsignal("dir",     Pins("J_3:12", dir="i"), Attrs(IO_TYPE="LVCMOS33")),
                Subsignal("nxt",     Pins("J_3:13", dir="i"), Attrs(IO_TYPE="LVCMOS33")),
                Subsignal("data",    Pins("J_3:17 J_3:19 J_3:21 J_3:23 J_3:18 J_3:20 J_3:22 J_3:24", dir="io"), Attrs(IO_TYPE="LVCMOS33")),
        ),
        ]

        super().__init__(colorlight, False)

    def toolchain_program(self, products, name):
        import os
        import subprocess
        tool = os.environ.get("OPENFPGALOADER", "openFPGALoader")
        with products.extract("{}.bit".format(name)) as bitstream_filename:
            subprocess.check_call([tool, '-c', 'cmsisdap', '-m', bitstream_filename])