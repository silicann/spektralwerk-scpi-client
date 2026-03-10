import struct

import cobs.cobs

from spektralwerk_scpi_client.devices.models import Spectrum
from spektralwerk_scpi_client.scpi.mnemonics import COBS_INT16_FORMAT, OutputFormat


def decoded_spectrum(
    raw_spectrum: str | bytes, output_format: OutputFormat | None = OutputFormat.HUMAN
) -> Spectrum:
    """
    Decode an incoming raw spectrum depending on the encoding

    Args:
        raw_spectrum: un-processed spectrum response from the Spektralwerk
        output_format: the format of the raw spectrum

    Returns:
        decoded Spectrum
    """
    match output_format:
        case OutputFormat.HUMAN | None:
            if type(raw_spectrum) is str:
                [timestamp, *data] = raw_spectrum.split(",")
            elif type(raw_spectrum) is bytes:
                [timestamp, *data] = raw_spectrum.decode("utf-8").split(",")
            return Spectrum(
                timestamp_sec=float(timestamp), data=[float(value) for value in data]
            )
        case OutputFormat.COBS_INT16:
            decoded_spectrum = cobs.cobs.decode(raw_spectrum)
            pixel_count = (
                len(decoded_spectrum)
                - struct.calcsize(COBS_INT16_FORMAT.timestamp_format)
            ) // struct.calcsize(COBS_INT16_FORMAT.pixel_format)
            unpack_format = f"<{COBS_INT16_FORMAT.timestamp_format}{pixel_count}{COBS_INT16_FORMAT.pixel_format}"
            [timestamp_musec, *spectral_data] = struct.unpack(
                unpack_format, decoded_spectrum
            )
            return Spectrum(
                float(timestamp_musec / 1_000_000),
                [float(value) for value in spectral_data],
            )
        case _:
            raise NotImplementedError
