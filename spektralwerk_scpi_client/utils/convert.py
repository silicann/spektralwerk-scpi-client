import base64
import struct

import cobs.cobs

from spektralwerk_scpi_client.devices.models import Spectrum
from spektralwerk_scpi_client.scpi.mnemonics import (
    BASE64_FLOAT_FORMAT,
    BASE64_INT16_FORMAT,
    COBS_INT16_FORMAT,
    Format,
    OutputFormat,
)


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
                # human output format timestamp is already in seconds
                timestamp_sec=float(timestamp),
                data=[float(value) for value in data],
            )
        case OutputFormat.BASE64_FLOAT:
            decoded_spectrum = base64.b64decode(raw_spectrum)
            [timestamp_usec, *spectral_data] = _unpack_spectrum(
                decoded_spectrum, BASE64_FLOAT_FORMAT
            )  # type: float, list[float]
            return Spectrum(
                float(timestamp_usec / 1_000_000),
                [float(value) for value in spectral_data],
            )
        case OutputFormat.BASE64_INT16:
            decoded_spectrum = base64.b64decode(raw_spectrum)
            [timestamp_usec, *spectral_data] = _unpack_spectrum(
                decoded_spectrum, BASE64_INT16_FORMAT
            )
            return Spectrum(
                float(timestamp_usec / 1_000_000),
                [float(value) for value in spectral_data],
            )
        case OutputFormat.COBS_INT16:
            decoded_spectrum = cobs.cobs.decode(raw_spectrum)
            [timestamp_usec, *spectral_data] = _unpack_spectrum(
                decoded_spectrum, COBS_INT16_FORMAT
            )
            return Spectrum(
                float(timestamp_usec / 1_000_000),
                [float(value) for value in spectral_data],
            )


def _unpack_spectrum(byte_spectrum: bytes, fmt: Format) -> tuple[float]:
    pixel_count = (
        len(byte_spectrum) - struct.calcsize(fmt.timestamp_format)
    ) // struct.calcsize(fmt.pixel_format)
    unpack_format = f"<{fmt.timestamp_format}{pixel_count}{fmt.pixel_format}"
    return struct.unpack(unpack_format, byte_spectrum)
