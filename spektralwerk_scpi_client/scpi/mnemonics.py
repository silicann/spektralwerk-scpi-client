import enum
import typing


class ProcessingStep(enum.StrEnum):
    AVERAGE = "average"
    BINNING = "binning"
    NONE = "none"
    REFERENCE_DARK = "reference_dark"
    REFERENCE_LIGHT = "reference_light"
    ROI = "roi"
    SCALE = "scale"


class OutputFormat(enum.StrEnum):
    HUMAN = "human"
    BASE64_INT16 = "base64_int16"
    BASE64_FLOAT = "base64_float"
    COBS_INT16 = "cobs_int16"


class Trigger(enum.StrEnum):
    NONE = "none"
    TRIGGER_RISING = "input,rising"
    TRIGGER_FALLING = "input,falling"
    TRIGGER_ANY = "input,any"


class Format(typing.NamedTuple):
    timestamp_format: str
    pixel_format: str


COBS_INT16_FORMAT = Format("Q", "H")
