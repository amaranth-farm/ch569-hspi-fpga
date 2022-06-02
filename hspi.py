import operator
from functools import reduce
from amaranth import *
from amaranth.hdl.rec import Layout, DIR_FANIN, DIR_FANOUT
from amaranth.build import Platform

from amlib.stream import StreamInterface

class CRC(Elaboratable):
    def __init__(self, *, polynomial, crc_size, datawidth, init=None, delay=False):
        self.datawidth   = datawidth
        self.crc_size    = crc_size
        self.init        = init
        self.polynomial  = polynomial
        self.delay       = delay

        if init is None:
            self.init = (1 << crc_size) - 1

        self.reset_in  = Signal()
        self.enable_in = Signal()
        self.data_in   = Signal(datawidth)
        self.crc_out   = Signal(crc_size)

    def elaborate(self, platform):
        m = Module()

        crcreg = [Signal(self.crc_size, reset=self.init) for i in range(self.datawidth + 1)]

        for i in range(self.datawidth):
            inv = self.data_in[i] ^ crcreg[i][self.crc_size - 1]
            tmp = []
            tmp.append(inv)
            for j in range(self.crc_size - 1):
                if((self.polynomial >> (j + 1)) & 1):
                    tmp.append(crcreg[i][j] ^ inv)
                else:
                    tmp.append(crcreg[i][j])
            m.d.comb += crcreg[i + 1].eq(Cat(*tmp))

        with m.If(self.reset_in):
            m.d.sync += crcreg[0].eq(self.init)
        with m.Elif(self.enable_in):
            m.d.sync += crcreg[0].eq(crcreg[self.datawidth])

        domain = m.d.sync if self.delay else m.d.comb
        domain += self.crc_out.eq(crcreg[self.datawidth][::-1] ^ self.init)

        return m


class HSPIInterface(Record):
    """ Record that represents a HSPI interface. """

    LAYOUT = [
        ('hd', [('i', 32, DIR_FANIN), ('o', 32, DIR_FANOUT), ('oe', 1, DIR_FANOUT)]),
        ("tx_ack",    1, DIR_FANOUT),
        ("tx_ready",  1, DIR_FANIN),
        ("tx_req",    1, DIR_FANOUT),
        ("rx_act",    1, DIR_FANIN),
        ("tx_valid",  1, DIR_FANOUT),
        ("rx_valid",  1, DIR_FANIN),
    ]

    def __init__(self):
        super().__init__(self.LAYOUT)

class HSPITransmitter(Elaboratable):
    def __init__(self):
        self.hspi_out = HSPIInterface()

        self.state = Signal(3)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        m.submodules.crc = crc = CRC(polynomial=0x04C11DB7, crc_size=32, datawidth=32, delay=True)

        hspi = self.hspi_out

        m.d.comb += [
            hspi.hd.oe.eq(hspi.tx_valid),
        ]

        header       = Signal(32)
        sequence_nr  = Signal(26)
        data         = Signal(32)

        m.d.comb += [
            header.eq(Cat(
                Mux(~sequence_nr[0], Const(0x3ABCDEF, 26), Const(0x3456789, 26)),
                sequence_nr[0:4],
                Const(0b11, 2)))
        ]

        with m.FSM() as fsm:
            m.d.comb += self.state.eq(fsm.state)
            with m.State("START"):
                m.d.sync += hspi.tx_req.eq(1)
                m.next = "WAIT_TX_READY"

            with m.State("WAIT_TX_READY"):
                with m.If(hspi.tx_ready):
                    m.next = "TX_HEADER"

            with m.State("TX_HEADER"):
                m.d.comb += [
                    hspi.hd.o.eq(header),
                    hspi.tx_valid.eq(1),

                    crc.data_in.eq(header),
                    crc.enable_in.eq(1),
                ]
                m.d.sync += sequence_nr.eq(sequence_nr + 1)

                m.next = "TX_DATA"

            with m.State("TX_DATA"):
                m.d.comb += [
                    hspi.hd.o.eq(data),
                    hspi.tx_valid.eq(1),

                    crc.data_in.eq(data),
                    crc.enable_in.eq(1),
                ]
                m.d.sync += data.eq(data + 1)

                with m.If((data[:7]) == 0x7f):
                    m.next = "TX_CRC"

            with m.State("TX_CRC"):
                m.d.comb += [
                    hspi.hd.o.eq(crc.crc_out),
                    hspi.tx_valid.eq(1),
                    crc.reset_in.eq(1),
                ]
                m.d.sync += hspi.tx_req.eq(0)
                m.next = "WAIT_HTRDY"

            with m.State("WAIT_HTRDY"):
                with m.If(~hspi.tx_ready):
                    m.next = "DONE"

            with m.State("DONE"):
                with m.If(data >= 8192):
                    m.d.sync += data.eq(0)
                    m.next = "PAUSE"
                with m.Else():
                    m.next = "START"

            with m.State("PAUSE"):
                m.d.sync += data.eq(data + 1)
                with m.If(data[29]):
                    m.d.sync += data.eq(0)
                    m.next = "START"

        return m


class HSPIReceiver(Elaboratable):
    def __init__(self):
        self.hspi_in = HSPIInterface()
        self.state = Signal(2)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        hspi = self.hspi_in

        m.d.comb += [
            hspi.hd.oe.eq(0),
        ]

        with m.FSM() as fsm:
            m.d.comb += self.state.eq(fsm.state)
            with m.State("START"):
                with m.If(hspi.rx_act):
                    m.d.sync += hspi.tx_ack.eq(1)
                    m.next = "RX"

            with m.State("RX"):
                with m.If(~hspi.rx_act):
                    m.d.sync += hspi.tx_ack.eq(0)
                    m.next = "START"

        return m

from amlib.test import GatewareTestCase, sync_test_case

class HSPITransmitterTest(GatewareTestCase):
    FRAGMENT_UNDER_TEST = HSPITransmitter
    FRAGMENT_ARGUMENTS  = dict()

    @sync_test_case
    def test_hspi_tx(self):
        dut = self.dut
        for i in range(5):
            yield from self.advance_cycles(3)
            yield dut.hspi_out.tx_ready.eq(1)
            yield from self.advance_cycles(135)
            yield dut.hspi_out.tx_ready.eq(0)
