from dataclasses import dataclass
from typing import NamedTuple


@dataclass
class Identity:
    vendor: str
    model: str
    serial_number: str
    firmware_version: str


class Spectrum(NamedTuple):
    """
    Basic spectrum class

    A spectrum consists of a timestamp in [s] and list of floats containing the spectral
    intensities.
    """

    timestamp_sec: float
    data: list[float]
