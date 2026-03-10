from typing import NamedTuple
from pydantic import BaseModel


class Identity(BaseModel):
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
