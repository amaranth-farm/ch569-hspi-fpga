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

        # Generate our domain clocks/resets.
        m.submodules.car = platform.clock_domain_generator()

        hspi = platform.request("hspi", 0)

        m.d.comb += [
            hspi.tx_ack.eq(1),
            hspi.hd.oe.eq(0),
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
                #hspi.tx_ack,
                #hspi.tx_ready,
                #hspi.tx_req,
                hspi.rx_act,
                #hspi.tx_valid,
                hspi.rx_valid,
                hspi.hd.i,
            ]

            signals_bits = sum([s.width for s in signals])
            depth = 3 * 8 * 1024 #int(33*8*1024/signals_bits)
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
                ila.enable.eq(hspi.rx_act),
            ]

            ILACoreParameters(ila).pickle()

        return m

if __name__ == "__main__":
    os.environ["AMARANTH_verbose"] = "True"
    os.environ["AMARANTH_synth_opts"] = "-abc9"
    os.environ["AMARANTH_nextpnr_opts"] = "--timing-allow-fail"
    os.environ["LUNA_PLATFORM"] = "boardsetup:ColorlightHSPIPlatform"
    top_level_cli(ColorlightHSPI)