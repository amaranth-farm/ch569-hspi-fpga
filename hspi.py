import operator
from functools import reduce

from amaranth          import *
from amaranth.lib.cdc  import FFSynchronizer
from amaranth.lib.fifo import SyncFIFO
from amaranth.hdl.ast  import Past
from amaranth.hdl.rec  import Layout, DIR_FANIN, DIR_FANOUT
from amaranth.build    import Platform

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

    def __init__(self, name=None):
        super().__init__(self.LAYOUT, name=name)

class HSPITransmitter(Elaboratable):
    def __init__(self, name=None, domain=None):
        self.send_ack     = Signal()
        self.ack_done     = Signal()
        self.tll_2b_in    = Signal(2)
        self.user_id0_in  = Signal(26)
        self.user_id1_in  = Signal(26)
        self.stream_in    = StreamInterface(name="tx_data_in", payload_width=32)
        self.hspi_out     = HSPIInterface(name=name)

        self.state        = Signal(3)

        self.domain = domain

    def connect_to_pads(self, hspi_pads):
        hspi_out = self.hspi_out

        return [
            # HSPI inputs
            hspi_out.tx_ready .eq(hspi_pads.tx_ready),
            hspi_out.tx_ack   .eq(hspi_pads.tx_ack),

            # HSPI outputs
            hspi_pads.tx_req   .eq(hspi_out.tx_req),
            hspi_pads.tx_valid .eq(hspi_out.tx_valid),
            hspi_pads.hd.oe    .eq(hspi_out.hd.oe),
            hspi_pads.hd.o     .eq(hspi_out.hd.o),
        ]

    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        domain = "sync" if self.domain is None else self.domain
        sync   = m.d.__getattr__(domain)
        comb   = m.d.comb

        m.submodules.crc = crc = DomainRenamer(domain)(CRC(polynomial=0x04C11DB7, crc_size=32, datawidth=32, delay=True))

        hspi      = self.hspi_out
        stream_in = self.stream_in
        last_seen = Signal()

        header       = Signal(32)
        sequence_nr  = Signal(26)
        # maximum frame size is 4096 in
        word_index   = Signal(range(4096))

        comb += [
            header.eq(Cat(
                Mux(~sequence_nr[0], self.user_id0_in, self.user_id1_in),
                sequence_nr[0:4],
                self.tll_2b_in))
        ]

        ack_in_process = Signal()
        rx_complete    = Signal()

        with m.FSM(domain=domain) as fsm:
            comb += [
                self.state.eq(fsm.state),
                rx_complete.eq(~hspi.tx_ack & ~hspi.tx_ready),
            ]

            with m.State("WAIT_INPUT"):
                with m.If(self.send_ack):
                    sync += ack_in_process.eq(1)
                    m.next = "START"
                with m.Elif(stream_in.valid & stream_in.first & rx_complete):
                    sync += last_seen.eq(0)
                    m.next = "START"

            with m.State("START"):
                # wait until an ongoing RX is complete
                with m.If(rx_complete):
                    sync += hspi.tx_req.eq(1)
                    m.next = "WAIT_TX_READY"

            with m.State("WAIT_TX_READY"):
                with m.If(hspi.tx_ready):
                    with m.If(ack_in_process):
                        m.next = "TX_ACK"
                    with m.Else():
                        m.next = "TX_HEADER"

            with m.State("TX_ACK"):
                comb += [
                    hspi.hd.oe.eq(1),
                    hspi.hd.o.eq(0xf0),
                    hspi.tx_valid.eq(1),
                ]
                m.next = "ACK_DONE"

            with m.State("ACK_DONE"):
                sync += ack_in_process.eq(0)
                sync += hspi.tx_req.eq(0)
                comb += self.ack_done.eq(1)
                m.next = "WAIT_INPUT"

            with m.State("TX_HEADER"):
                comb += [
                    hspi.hd.oe.eq(1),
                    hspi.hd.o.eq(header),
                    hspi.tx_valid.eq(1),

                    crc.data_in.eq(header),
                    crc.enable_in.eq(1),
                ]

                m.next = "TX_DATA"

            with m.State("TX_DATA"):
                comb += [
                    stream_in.ready.eq(1),

                    hspi.hd.oe.eq(1),
                    hspi.hd.o.eq(stream_in.payload),
                    hspi.tx_valid.eq(stream_in.valid),

                    crc.data_in.eq(stream_in.data),
                    crc.enable_in.eq(1),
                ]

                with m.If(stream_in.valid):
                    sync += word_index.eq(word_index + 1)

                with m.If(stream_in.last | (word_index == 4095)):
                    with m.If(stream_in.last):
                        sync += last_seen.eq(1)
                    m.next = "TX_CRC"

            with m.State("TX_CRC"):
                comb += [
                    hspi.hd.oe.eq(1),
                    hspi.hd.o.eq(crc.crc_out),
                    hspi.tx_valid.eq(1),
                    crc.reset_in.eq(1),
                ]
                sync += hspi.tx_req.eq(0)
                m.next = "WAIT_HTRDY"

            with m.State("WAIT_HTRDY"):
                sync += sequence_nr.eq(sequence_nr + 1)
                with m.If(~hspi.tx_ready):
                    with m.If(~last_seen):
                        m.next = "WAIT_LAST"
                    with m.Else():
                        m.next = "WAIT_INPUT"

            with m.State("WAIT_LAST"):
                comb += stream_in.ready.eq(1)
                with m.If(stream_in.last):
                    m.next = "WAIT_INPUT"

        return m

class HSPIReceiver(Elaboratable):
    def __init__(self, domain=None):
        self.hspi_in           = HSPIInterface()
        self.stream_out        = StreamInterface(name="rx_data_out", payload_width=32, extra_fields=[("crc_error", 1)])
        self.packet_done_out   = Signal(1)
        self.tll_2b_out        = Signal(2)
        self.sequence_nr_out   = Signal(4)
        self.user_data_out     = Signal(26)
        self.num_words_out     = Signal(13)

        self.state       = Signal(3)

        self.domain = domain

    def connect_to_pads(self, hspi_pads):
        hspi_in = self.hspi_in

        return [
            # HSPI inputs
            hspi_in.rx_act.eq(hspi_pads.rx_act),
            hspi_in.rx_valid.eq(hspi_pads.rx_valid),
            hspi_in.hd.i.eq(hspi_pads.hd.i),

            # HSPI outputs
            hspi_pads.tx_ack.eq(hspi_in.tx_ack),
        ]

    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        hspi       = self.hspi_in
        stream_out = self.stream_out
        domain     = "sync" if self.domain is None else self.domain
        sync       = m.d.__getattr__(domain)
        comb       = m.d.comb

        m.submodules.crc = crc = DomainRenamer(domain)(CRC(polynomial=0x04C11DB7, crc_size=32, datawidth=32, delay=True))

        word_pos  = Signal(13)
        crc_equal = Signal()
        valid     = Signal()

        with m.FSM(domain=domain) as fsm:
            comb += [
                self.state.eq(fsm.state),
                stream_out.payload .eq(Past(hspi.hd.i, clocks=2, domain=domain)),
                stream_out.valid   .eq(Past(valid,     clocks=2, domain=domain)),
            ]

            with m.State("WAIT"):
                comb += stream_out.valid.eq(0),
                with m.If(hspi.rx_act):
                    sync += [
                        word_pos.eq(0),
                        hspi.tx_ack.eq(1),
                    ]
                    m.next = "RX"

            with m.State("RX"):
                with m.If(hspi.rx_valid):
                    sync += word_pos.eq(word_pos + 1)
                    comb += [
                        crc.enable_in.eq(1),
                        crc.data_in.eq(hspi.hd.i),
                    ]
                    sync += crc_equal.eq(crc.crc_out == hspi.hd.i)

                # extract header
                with m.If(word_pos == 0):
                    sync += Cat(self.user_data_out, self.sequence_nr_out, self.tll_2b_out).eq(hspi.hd.i)

                # don't include header in stream data.
                # valid is delayed by 2, so this comes at the same time as first
                with m.If(word_pos >= 1):
                    comb += valid.eq(hspi.rx_valid)

                with m.If(word_pos == 3):
                    comb += stream_out.first.eq(1)

                with m.If(~hspi.rx_act):
                    comb += [
                        stream_out.last.eq(1),
                        self.packet_done_out.eq(1),
                        stream_out.crc_error.eq(~crc_equal),
                        self.num_words_out.eq(word_pos - 1),
                    ]
                    sync += [
                        hspi.tx_ack.eq(0),
                        crc_equal.eq(0),
                    ]
                    m.next = "WAIT"

        return m

from amlib.test import GatewareTestCase, sync_test_case

class HSPITransmitterTest(GatewareTestCase):
    FRAGMENT_UNDER_TEST = HSPITransmitter
    FRAGMENT_ARGUMENTS  = dict()

    @sync_test_case
    def test_hspi_tx(self):
        dut = self.dut
        data = 0

        for i in range(5):
            yield from self.advance_cycles(3)
            yield dut.hspi_out.tx_ready.eq(1)
            yield dut.tll_2b_in.eq(0b11)
            yield dut.user_id0_in.eq(0x3ABCDEF)
            yield dut.user_id1_in.eq(0x3456789)
            yield dut.stream_in.payload.eq(data)
            yield dut.stream_in.first.eq(1)
            yield dut.stream_in.valid.eq(1)
            yield
            yield
            yield
            yield

            for i in range(0x400):
                yield dut.stream_in.first.eq(1 if i == 0 else 0)
                yield dut.stream_in.payload.eq(data)
                if i == 0x3ff:
                    yield dut.stream_in.last.eq(1)
                else:
                    yield dut.stream_in.last.eq(0)
                yield
                data += 1

            yield dut.stream_in.last.eq(0)
            yield dut.stream_in.valid.eq(0)
            yield

            yield dut.hspi_out.tx_ready.eq(0)

class HSPIReceiverTest(GatewareTestCase):
    FRAGMENT_UNDER_TEST = HSPIReceiver
    FRAGMENT_ARGUMENTS  = dict()

    @sync_test_case
    def test_hspi_rx(self):
        dut = self.dut
        hspi = dut.hspi_in
        data = 0

        yield from self.advance_cycles(3)
        yield hspi.rx_act.eq(1)
        yield
        yield
        yield
        yield hspi.hd.i.eq(0xc3abcdef)
        yield hspi.rx_valid.eq(1)
        yield
        for i in range(0x40):
            yield hspi.hd.i.eq(i)
            yield
        yield hspi.rx_valid.eq(0)
        yield
        yield
        yield
        yield hspi.rx_valid.eq(1)
        for i in range(0x40, 0x80):
            yield hspi.hd.i.eq(i)
            yield
        yield hspi.hd.i.eq(0x1106c501)
        yield
        yield hspi.hd.i.eq(0)
        yield hspi.rx_valid.eq(0)
        yield hspi.rx_act.eq(0)
        yield
        self.assertEqual((yield dut.stream_out.crc_error), 0)
        yield
        yield
        yield
