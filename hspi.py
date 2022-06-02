import operator
from functools import reduce
from amaranth import *
from amaranth.hdl.rec import Layout, DIR_FANIN, DIR_FANOUT
from amaranth.build import Platform

from amlib.stream import StreamInterface

class HSPICRC(Elaboratable):
    def __init__(self) -> None:
        self.reset_in  = Signal()
        self.enable_in = Signal()
        self.data_in   = Signal(32)
        self.crc_out   = Signal(32)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        new_crc     = Signal(32)
        current_crc = Signal(32, reset=0xffffffff)

        xor_reduce = lambda signal: reduce(operator.xor, signal)
        bits       = lambda list, indices: [list[i] for i in indices]
        calculate  = lambda indices: xor_reduce(Cat(bits(current_crc, indices), bits(self.data_in, indices)))

        m.d.comb += [
            new_crc[0] .eq(calculate([0, 6, 9, 10, 12, 16, 24, 25, 26, 28, 29, 30, 31])),
            new_crc[1] .eq(calculate([0, 1, 6, 7, 9, 11, 12, 13, 16, 17, 24, 27, 28])),
            new_crc[2] .eq(calculate([0, 1, 2, 6, 7, 8, 9, 13, 14, 16, 17, 18, 24, 26, 30, 31])),
            new_crc[3] .eq(calculate([1, 2, 3, 7, 8, 9, 10, 14, 15, 17, 18, 19, 25, 27, 31])),
            new_crc[4] .eq(calculate([0, 2, 3, 4, 6, 8, 11, 12, 15, 18, 19, 20, 24, 25, 29, 30, 31])),
            new_crc[5] .eq(calculate([0, 1, 3, 4, 5, 6, 7, 10, 13, 19, 20, 21, 24, 28, 29])),
            new_crc[6] .eq(calculate([1, 2, 4, 5, 6, 7, 8, 11, 14, 20, 21, 22, 25, 29, 30])),
            new_crc[7] .eq(calculate([0, 2, 3, 5, 7, 8, 10, 15, 16, 21, 22, 23, 24, 25, 28, 29])),
            new_crc[8] .eq(calculate([0, 1, 3, 4, 8, 10, 11, 12, 17, 22, 23, 28, 31])),
            new_crc[9] .eq(calculate([1, 2, 4, 5, 9, 11, 12, 13, 18, 23, 24, 29])),
            new_crc[10].eq(calculate([0, 2, 3, 5, 9, 13, 14, 16, 19, 26, 28, 29, 31])),
            new_crc[11].eq(calculate([0, 1, 3, 4, 9, 12, 14, 15, 16, 17, 20, 24, 25, 26, 27, 28, 31])),
            new_crc[12].eq(calculate([0, 1, 2, 4, 5, 6, 9, 12, 13, 15, 17, 18, 21, 24, 27, 30, 31])),
            new_crc[13].eq(calculate([1, 2, 3, 5, 6, 7, 10, 13, 14, 16, 18, 19, 22, 25, 28, 31])),
            new_crc[14].eq(calculate([2, 3, 4, 6, 7, 8, 11, 14, 15, 17, 19, 20, 23, 26, 29])),
            new_crc[15].eq(calculate([3, 4, 5, 7, 8, 9, 12, 15, 16, 18, 20, 21, 24, 27, 30])),
            new_crc[16].eq(calculate([0, 4, 5, 8, 12, 13, 17, 19, 21, 22, 24, 26, 29, 30])),
            new_crc[17].eq(calculate([1, 5, 6, 9, 13, 14, 18, 20, 22, 23, 25, 27, 30, 31])),
            new_crc[18].eq(calculate([2, 6, 7, 10, 14, 15, 19, 21, 23, 24, 26, 28, 31])),
            new_crc[19].eq(calculate([3, 7, 8, 11, 15, 16, 20, 22, 24, 25, 27, 29])),
            new_crc[20].eq(calculate([4, 8, 9, 12, 16, 17, 21, 23, 25, 26, 28, 30])),
            new_crc[21].eq(calculate([5, 9, 10, 13, 17, 18, 22, 24, 26, 27, 29, 31])),
            new_crc[22].eq(calculate([0, 9, 11, 12, 14, 16, 18, 19, 23, 24, 26, 27, 29, 31])),
            new_crc[23].eq(calculate([0, 1, 6, 9, 13, 15, 16, 17, 19, 20, 26, 27, 29, 31])),
            new_crc[24].eq(calculate([1, 2, 7, 10, 14, 16, 17, 18, 20, 21, 27, 28, 30])),
            new_crc[25].eq(calculate([2, 3, 8, 11, 15, 17, 18, 19, 21, 22, 28, 29, 31])),
            new_crc[26].eq(calculate([0, 3, 4, 6, 10, 18, 19, 20, 22, 23, 24, 25, 26, 28, 31])),
            new_crc[27].eq(calculate([1, 4, 5, 7, 11, 19, 20, 21, 23, 24, 25, 26, 27, 29])),
            new_crc[28].eq(calculate([2, 5, 6, 8, 12, 20, 21, 22, 24, 25, 26, 27, 28, 30])),
            new_crc[29].eq(calculate([3, 6, 7, 9, 13, 21, 22, 23, 25, 26, 27, 28, 29, 31])),
            new_crc[30].eq(calculate([4, 7, 8, 10, 14, 22, 23, 24, 26, 27, 28, 29, 30])),
            new_crc[31].eq(calculate([5, 8, 9, 11, 15, 23, 24, 25, 27, 28, 29, 30, 31])),

            self.crc_out.eq(current_crc),
        ]

        m.d.sync += current_crc.eq(Mux(self.reset_in, 0xffffffff, Mux(self.enable_in, new_crc, current_crc)))

        return m

class CRC(Elaboratable):
    def __init__(self, *, polynomial, size, datawidth, init=None, delay=False):
        self.datawidth   = datawidth
        self.size        = size
        self.init        = init
        self.polynomial  = polynomial
        self.delay       = delay

        if init is None:
            self.init = (1 << size) - 1

        self.reset_in  = Signal()
        self.enable_in = Signal()
        self.data_in   = Signal(datawidth)
        self.crc_out   = Signal(size)

    def elaborate(self, platform):
        m = Module()

        crcreg = [Signal(self.size, reset=self.init) for i in range(self.datawidth + 1)]

        for i in range(self.datawidth):
            inv = self.data_in[i] ^ crcreg[i][self.size - 1]
            tmp = []
            tmp.append(inv)
            for j in range(self.size - 1):
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
        m.submodules.crc = crc = CRC(polynomial=0x04C11DB7, size=32, datawidth=32, delay=True)

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
