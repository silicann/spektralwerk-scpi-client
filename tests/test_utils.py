import pytest

from spektralwerk_scpi_client.devices.models import Spectrum
from spektralwerk_scpi_client.scpi.mnemonics import OutputFormat
from spektralwerk_scpi_client.utils.convert import decoded_spectrum


@pytest.mark.parametrize(
    ("input_raw_spectrum", "expected_spectrum", "output_format"),
    [
        # COBS int16 sample
        (
            b"\x04\x11\xb1\x06\x01\x01\x01\x01\x03V\r",
            Spectrum(timestamp_sec=0.438545, data=[3414.0]),
            OutputFormat.COBS_INT16,
        ),
        # HUMAN; string representation
        (
            "123456789,1,2,3,4",
            Spectrum(timestamp_sec=123456789.0, data=[1, 2, 3, 4]),
            OutputFormat.HUMAN,
        ),
        # HUMAN; byte representation
        (
            b"123456789,1,2,3,4",
            Spectrum(timestamp_sec=123456789.0, data=[1, 2, 3, 4]),
            OutputFormat.HUMAN,
        ),
        # BASE64 int16 sample
        (
            b"0PTnBwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            Spectrum(
                timestamp_sec=132.642,
                data=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            ),
            OutputFormat.BASE64_INT16,
        ),
        # BASE64 float sample
        (
            b"WHJlDAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==",
            Spectrum(
                timestamp_sec=207.975,
                data=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            ),
            OutputFormat.BASE64_FLOAT,
        ),
    ],
)
def test_human_readable_input(input_raw_spectrum, expected_spectrum, output_format):
    assert decoded_spectrum(input_raw_spectrum, output_format) == expected_spectrum
