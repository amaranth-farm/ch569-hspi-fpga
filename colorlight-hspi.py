import os
import subprocess

from amaranth          import *
from amaranth.lib.cdc  import ResetSynchronizer
from amaranth.lib.fifo import SyncFIFOBuffered

from amaranth.build import *
from amaranth.vendor.lattice_ecp5 import *

from amlib.stream import connect_fifo_to_stream, connect_stream_to_fifo

from usb_protocol.types                import USBRequestType, USBDirection, USBStandardRequests
from usb_protocol.emitters             import DeviceDescriptorCollection

from luna                                     import top_level_cli
from luna.usb2                                import USBDevice
from luna.gateware.usb.usb2.request           import StallOnlyRequestHandler
from luna.gateware.usb.usb2.endpoints.stream  import USBMultibyteStreamInEndpoint

from amlib.debug.ila     import StreamILA, ILACoreParameters

from hspi import HSPITransmitter, HSPIReceiver

class ColorlightHSPI(Elaboratable):
    ILA_MAX_PACKET_SIZE = 512
    USE_ILA = True
    USE_ACK = False

    def create_descriptors(self):
        """ Creates the descriptors that describe our audio topology. """

        descriptors = DeviceDescriptorCollection()

        with descriptors.DeviceDescriptor() as d:
            d.bcdUSB             = 2.00
            d.bDeviceClass       = 0xEF
            d.bDeviceSubclass    = 0x02
            d.bDeviceProtocol    = 0x01
            d.idVendor           = 0x1209
            d.idProduct          = 0x4711

            d.iManufacturer      = "Hans Baier"
            d.iProduct           = "HSPI-ILA"
            d.iSerialNumber      = "4711"
            d.bcdDevice          = 0.01

            d.bNumConfigurations = 1

        with descriptors.ConfigurationDescriptor() as configDescr:
            with configDescr.InterfaceDescriptor() as i:
                i.bInterfaceNumber = 0

                with i.EndpointDescriptor() as e:
                    e.bEndpointAddress = USBDirection.IN.to_endpoint_address(1) # EP 1 IN
                    e.wMaxPacketSize   = self.ILA_MAX_PACKET_SIZE

        return descriptors


    def elaborate(self, platform):
        m = Module()

        # Generate our domain clocks/resets.
        m.submodules.car = platform.clock_domain_generator()

        hspi_pads = platform.request("hspi", 0)

        m.submodules.hspi_tx      = hspi_tx       = HSPITransmitter(domain="hspi")
        m.submodules.hspi_rx      = hspi_rx       = HSPIReceiver(domain="hspi")
        m.submodules.looback_fifo = loopback_fifo = DomainRenamer("hspi")(SyncFIFOBuffered(width=34, depth=4096))

        m.d.comb += [
            ## connect HSPI receiver
            *hspi_rx.connect_to_pads(hspi_pads),
            *connect_stream_to_fifo(hspi_rx.stream_out, loopback_fifo, firstBit=-2, lastBit=-1),

            ## connect HSPI transmitter
            hspi_tx.user_id0_in.eq(0x3ABCDEF),
            hspi_tx.user_id1_in.eq(0x3456789),
            hspi_tx.tll_2b_in.eq(0b11),
            hspi_tx.sequence_nr_in.eq(hspi_rx.sequence_nr_out),

            *hspi_tx.connect_to_pads(hspi_pads),
            *connect_fifo_to_stream(loopback_fifo, hspi_tx.stream_in, firstBit=-2, lastBit=-1),
        ]

        if self.USE_ACK:
            with m.FSM(domain="hspi"):
                with m.State("WAIT_RX"):
                    with m.If(hspi_rx.stream_out.first & hspi_rx.stream_out.valid):
                        m.next = "WAIT_RX_DONE"

                with m.State("WAIT_RX_DONE"):
                    with m.If(~hspi_pads.tx_ack):
                        m.d.comb += hspi_tx.send_ack.eq(1)
                        m.next = "WAIT_ACK"

                with m.State("WAIT_ACK"):
                    with m.If(hspi_tx.ack_done):
                        m.next = "WAIT_RX"
        else:
            m.d.comb += hspi_tx.send_ack.eq(0)

        if self.USE_ILA:
            trace_transmit = False
            trace_receive  = False
            trace_loopback = False
            use_enable     = False

            ulpi = platform.request(platform.default_usb_connection)
            m.submodules.usb = usb = USBDevice(bus=ulpi)

            # Connect our device as a high speed device
            m.d.comb += [
                usb.connect          .eq(1),
                usb.full_speed_only  .eq(0),
            ]

            # Add our standard control endpoint to the device.
            descriptors = self.create_descriptors()
            control_ep = usb.add_control_endpoint()
            control_ep.add_standard_request_handlers(descriptors, blacklist=[
                lambda setup:   (setup.type    == USBRequestType.STANDARD)
                              & (setup.request == USBStandardRequests.SET_INTERFACE)
            ])

            # Attach class-request handlers that stall any vendor or reserved requests,
            # as we don't have or need any.
            stall_condition = lambda setup : \
                (setup.type == USBRequestType.VENDOR) | \
                (setup.type == USBRequestType.RESERVED)
            control_ep.add_request_handler(StallOnlyRequestHandler(stall_condition))

            debug = platform.request("debug")

            signals = [
                debug.led1,
                debug.led2,

                hspi_pads.tx_req,
                hspi_pads.tx_ready,
                hspi_pads.tx_valid,
            ]

            if self.USE_ACK:
                signals += [
                    hspi_tx.send_ack,
                    hspi_tx.ack_done,
                ]

            signals += [
                hspi_pads.rx_act,
                hspi_pads.tx_ack,
                hspi_pads.rx_valid,
            ]

            if trace_transmit:
                signals = signals + [
                    hspi_pads.hd.oe,
                    hspi_pads.hd.o,
                ]

            if trace_receive:
                signals = signals + [
                hspi_rx.stream_out.crc_error,
                hspi_pads.hd.i,
            ]

            if trace_transmit:
                traced_stream = hspi_tx.stream_in
            else:
                traced_stream = hspi_rx.stream_out

            if trace_loopback:
                signals += [
                    traced_stream.payload,
                    traced_stream.valid,
                    traced_stream.ready,
                    traced_stream.first,
                    traced_stream.last,
                ]

            signals_bits = sum([s.width for s in signals])
            depth = 8 * 6 * 1024 #int(33*8*1024/signals_bits)
            m.submodules.ila = ila = \
                StreamILA(
                    signals=signals,
                    sample_rate=96e6,
                    sample_depth=depth,
                    domain="hspi", o_domain="usb",
                    samples_pretrigger=256,
                    with_enable=use_enable)

            stream_ep = USBMultibyteStreamInEndpoint(
                endpoint_number=1, # EP 1 IN
                max_packet_size=self.ILA_MAX_PACKET_SIZE,
                byte_width=ila.bytes_per_sample
            )
            usb.add_endpoint(stream_ep)

            m.d.comb += stream_ep.stream.stream_eq(ila.stream),

            if use_enable:
                m.d.comb += ila.trigger.eq(1),
                if trace_transmit:
                    m.d.comb += ila.enable.eq(hspi_pads.tx_req)
                if trace_receive:
                    m.d.comb += ila.enable.eq(hspi_pads.rx_act)
                if trace_loopback:
                    m.d.comb += ila.enable.eq(traced_stream.valid)
            else:
                if trace_transmit:
                    m.d.comb += ila.trigger.eq(hspi_pads.tx_req)
                if trace_receive:
                    m.d.comb += ila.trigger.eq(hspi_pads.rx_act)
                if trace_loopback:
                    m.d.comb += ila.trigger.eq(traced_stream.valid)
                if not (trace_loopback or trace_receive or trace_transmit):
                    m.d.comb += ila.trigger.eq(debug.led1)


            ILACoreParameters(ila).pickle()

        return m

if __name__ == "__main__":
    os.environ["AMARANTH_verbose"] = "True"
    os.environ["AMARANTH_synth_opts"] = "-abc9"
    os.environ["AMARANTH_nextpnr_opts"] = "--timing-allow-fail"
    os.environ["LUNA_PLATFORM"] = "boardsetup:ColorlightHSPIPlatform"
    top_level_cli(ColorlightHSPI)