import os
import subprocess

from amaranth         import *
from amaranth.lib.cdc import ResetSynchronizer

from amaranth.build import *
from amaranth.vendor.lattice_ecp5 import *

from usb_protocol.types                import USBRequestType, USBDirection, USBStandardRequests
from usb_protocol.emitters             import DeviceDescriptorCollection

from luna                                     import top_level_cli
from luna.usb2                                import USBDevice
from luna.gateware.usb.usb2.request           import StallOnlyRequestHandler
from luna.gateware.usb.usb2.endpoints.stream  import USBMultibyteStreamInEndpoint

from amlib.debug.ila     import StreamILA, ILACoreParameters

from hspi import HSPITransmitter, HSPIReceiver

class ColorlightHSPI(Elaboratable):
    USE_ILA = True
    ILA_MAX_PACKET_SIZE = 512

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

        transmit = True

        # Generate our domain clocks/resets.
        m.submodules.car = platform.clock_domain_generator()

        hspi_pads = platform.request("hspi", 0)


        if transmit:
            m.submodules.hspi_tx = hspi_tx = DomainRenamer("hspi")(HSPITransmitter())
            m.d.comb += [
                # HSPI inputs
                hspi_tx.hspi_out.tx_ready.eq(hspi_pads.tx_ready),
                hspi_tx.hspi_out.rx_act.eq(hspi_pads.rx_act),
                hspi_tx.hspi_out.rx_valid.eq(hspi_pads.rx_valid),
                hspi_tx.hspi_out.hd.i.eq(hspi_pads.hd.i),

                # HSPI outputs
                hspi_pads.tx_ack.eq(hspi_tx.hspi_out.tx_ack),
                hspi_pads.tx_req.eq(hspi_tx.hspi_out.tx_req),
                hspi_pads.tx_valid.eq(hspi_tx.hspi_out.tx_valid),
                hspi_pads.hd.oe.eq(hspi_tx.hspi_out.hd.oe),
                hspi_pads.hd.o.eq(hspi_tx.hspi_out.hd.o),
            ]
        else:
            m.submodules.hspi_rx = hspi_rx = DomainRenamer("hspi")(HSPIReceiver())
            m.d.comb += [
                # HSPI inputs
                hspi_rx.hspi_in.tx_ready.eq(hspi_pads.tx_ready),
                hspi_rx.hspi_in.rx_act.eq(hspi_pads.rx_act),
                hspi_rx.hspi_in.rx_valid.eq(hspi_pads.rx_valid),
                hspi_rx.hspi_in.hd.i.eq(hspi_pads.hd.i),

                # HSPI outputs
                hspi_pads.tx_ack.eq(hspi_rx.hspi_in.tx_ack),
                hspi_pads.tx_req.eq(hspi_rx.hspi_in.tx_req),
                hspi_pads.tx_valid.eq(hspi_rx.hspi_in.tx_valid),
                hspi_pads.hd.oe.eq(hspi_rx.hspi_in.hd.oe),
                hspi_pads.hd.o.eq(hspi_rx.hspi_in.hd.o),
            ]

        if self.USE_ILA:
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

            signals = [
                hspi_pads.tx_ack,
                hspi_pads.tx_ready,

                hspi_pads.tx_req,
                hspi_pads.rx_act,

                hspi_pads.tx_valid,
                hspi_pads.rx_valid,
            ]
            if transmit:
                signals = [hspi_tx.state] + signals + [
                    hspi_pads.hd.oe,
                    hspi_pads.hd.o,
                ]
            else:
                signals =[hspi_rx.state] + signals + [
                hspi_pads.hd.i,
            ]

            signals_bits = sum([s.width for s in signals])
            depth = 2 * 8 * 1024 #int(33*8*1024/signals_bits)
            m.submodules.ila = ila = \
                StreamILA(
                    signals=signals,
                    sample_depth=depth,
                    domain="hspi", o_domain="usb",
                    samples_pretrigger=256,
                    with_enable=True)

            stream_ep = USBMultibyteStreamInEndpoint(
                endpoint_number=1, # EP 1 IN
                max_packet_size=self.ILA_MAX_PACKET_SIZE,
                byte_width=ila.bytes_per_sample
            )
            usb.add_endpoint(stream_ep)

            m.d.comb += [
                stream_ep.stream.stream_eq(ila.stream),
                ila.trigger.eq(1),
            ]
            if transmit:
                m.d.comb += ila.enable.eq(hspi_pads.tx_req),
            else:
                m.d.comb += ila.enable.eq(hspi_pads.rx_act),


            ILACoreParameters(ila).pickle()

        return m

if __name__ == "__main__":
    os.environ["AMARANTH_verbose"] = "True"
    os.environ["AMARANTH_synth_opts"] = "-abc9"
    os.environ["AMARANTH_nextpnr_opts"] = "--timing-allow-fail"
    os.environ["LUNA_PLATFORM"] = "boardsetup:ColorlightHSPIPlatform"
    top_level_cli(ColorlightHSPI)