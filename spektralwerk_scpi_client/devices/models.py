from dataclasses import dataclass
from typing import NamedTuple


@dataclass
class Identity:
    vendor: str
    model: str
    serial_number: str
    firmware_version: str


@dataclass
class SCPIValueContext:
    minimum: int | float
    maximum: int | float
    default: int | float
    unit: str | None


class Spectrum(NamedTuple):
    """
    Basic spectrum class

    A spectrum consists of a timestamp in [s] and list of floats containing the spectral
    intensities.
    """

    timestamp_sec: float
    data: list[float]
